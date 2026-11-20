#!/usr/bin/env node
// Generates the Dolyna Valley battlefield: heightmap, splat maps and the full
// map description (roads, rail, river, bridges, buildings, props, vegetation,
// control points, HQs, spawns, vehicle slots).
//
//   node Tools/gen_map.mjs
//
// Output: Assets/Maps/dolyna_valley/{map.json,height.bin,splatA.png,splatB.png,preview.png}
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Noise2D } from './lib/Noise.js';
import { RNG } from './lib/Random.js';
import { smoothPolyline, pointInPolygon, clamp, lerp, smoothstep } from './lib/MathUtil.js';
import * as L from './mapgen/layout.mjs';
import { encodePNG } from './mapgen/png.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'Assets/Maps', L.MAP_ID);
fs.mkdirSync(OUT, { recursive: true });

const SPECS = JSON.parse(fs.readFileSync(path.join(ROOT, 'Assets/Models/Buildings/building_specs.json'), 'utf8'));
const MOD = SPECS.module;

const { N, CELL, HALF } = L;
const rng = new RNG('dolyna-valley-v1');
const noiseA = new Noise2D(1337);
const noiseB = new Noise2D(4242);
const noiseC = new Noise2D(9001);

const idx = (i, j) => j * N + i;
const wx = (i) => -HALF + i * CELL;
const ci = (x) => Math.round((x + HALF) / CELL);
const inGrid = (i, j) => i >= 0 && j >= 0 && i < N && j < N;
const r2 = (v) => Math.round(v * 100) / 100;
const r1 = (v) => Math.round(v * 10) / 10;

console.time('total');

// ---------------------------------------------------------------------------
// Utility: rasterise a polyline into a distance + arc-length field
// ---------------------------------------------------------------------------
function polylineField(pts, radius) {
  const d = new Float32Array(N * N).fill(Infinity);
  const s = new Float32Array(N * N).fill(-1);
  let acc = 0;
  for (let k = 0; k < pts.length - 1; k++) {
    const ax = pts[k][0], az = pts[k][1], bx = pts[k + 1][0], bz = pts[k + 1][1];
    const abx = bx - ax, abz = bz - az;
    const len2 = abx * abx + abz * abz;
    const segLen = Math.sqrt(len2);
    if (segLen < 1e-6) continue;
    const i0 = Math.max(0, ci(Math.min(ax, bx) - radius)), i1 = Math.min(N - 1, ci(Math.max(ax, bx) + radius));
    const j0 = Math.max(0, ci(Math.min(az, bz) - radius)), j1 = Math.min(N - 1, ci(Math.max(az, bz) + radius));
    for (let j = j0; j <= j1; j++) {
      const z = wx(j);
      for (let i = i0; i <= i1; i++) {
        const x = wx(i);
        let t = ((x - ax) * abx + (z - az) * abz) / len2;
        t = t < 0 ? 0 : t > 1 ? 1 : t;
        const px = ax + abx * t, pz = az + abz * t;
        const dd = Math.hypot(x - px, z - pz);
        const c = idx(i, j);
        if (dd < radius && dd < d[c]) {
          d[c] = dd;
          s[c] = acc + t * segLen;
        }
      }
    }
    acc += segLen;
  }
  return { d, s, length: acc };
}

function densify(ctrl, spacing = 2) {
  // smooth with Catmull-Rom then resample at fixed arc-length spacing
  const smooth = smoothPolyline(ctrl, 12);
  const out = [[smooth[0][0], smooth[0][1], 0]];
  let carry = 0, acc = 0;
  for (let k = 0; k < smooth.length - 1; k++) {
    const ax = smooth[k][0], az = smooth[k][1], bx = smooth[k + 1][0], bz = smooth[k + 1][1];
    const len = Math.hypot(bx - ax, bz - az);
    let s = spacing - carry;
    while (s <= len) {
      const t = s / len;
      out.push([ax + (bx - ax) * t, az + (bz - az) * t, acc + s]);
      s += spacing;
    }
    carry = len - (s - spacing);
    acc += len;
  }
  const last = smooth[smooth.length - 1];
  out.push([last[0], last[1], acc]);
  return out;
}

// bilinear height sample on the working heightmap
function sampleH(H, x, z) {
  const fx = (x + HALF) / CELL, fz = (z + HALF) / CELL;
  const i = clamp(Math.floor(fx), 0, N - 2), j = clamp(Math.floor(fz), 0, N - 2);
  const tx = clamp(fx - i, 0, 1), tz = clamp(fz - j, 0, 1);
  const a = H[idx(i, j)], b = H[idx(i + 1, j)], c = H[idx(i, j + 1)], d = H[idx(i + 1, j + 1)];
  return lerp(lerp(a, b, tx), lerp(c, d, tx), tz);
}

// ---------------------------------------------------------------------------
// 1. Base terrain
// ---------------------------------------------------------------------------
console.time('terrain');
const H = new Float32Array(N * N);
for (let j = 0; j < N; j++) {
  const z = wx(j);
  for (let i = 0; i < N; i++) {
    const x = wx(i);
    let h = L.BASE_HEIGHT
      + 5.0 * noiseA.fbm(x / 520, z / 520, 4)
      + 2.2 * noiseB.fbm(x / 140, z / 140, 4)
      + 0.45 * noiseC.fbm(x / 28, z / 28, 3);
    for (const hl of L.HILLS) {
      const dx = x - hl.x, dz = z - hl.z;
      const sig = hl.r * 0.5;
      h += hl.h * Math.exp(-(dx * dx + dz * dz) / (2 * sig * sig)) * (0.85 + 0.3 * noiseB.noise(x / 90, z / 90));
    }
    const e = Math.pow(Math.pow(Math.abs(x), 4) + Math.pow(Math.abs(z), 4), 0.25) + 70 * noiseB.fbm(x / 260 + 7, z / 260, 3);
    if (e > 730) h += smoothstep(730, 1060, e) * (30 + 22 * (0.5 + 0.5 * noiseA.fbm(x / 230, z / 230, 4)));
    H[idx(i, j)] = h;
  }
}
console.timeEnd('terrain');

// ---------------------------------------------------------------------------
// 2. River valley + channel (+ ford)
// ---------------------------------------------------------------------------
console.time('river');
const riverPts = [];
for (let z = -1110; z <= 1110; z += 6) riverPts.push([L.riverX(z), z]);
const riverField = polylineField(riverPts, 180);
const RHW = L.RIVER_WIDTH / 2;
const BANK = 14;

// Ford position: where the ford road crosses the river
const fordRoad = L.ROADS.find((r) => r.ford);
const fordDense = densify(fordRoad.ctrl, 2);
let fordPt = null;
for (let k = 0; k < fordDense.length - 1; k++) {
  const a = fordDense[k], b = fordDense[k + 1];
  const sa = a[0] - L.riverX(a[1]), sb = b[0] - L.riverX(b[1]);
  if (sa === 0 || Math.sign(sa) !== Math.sign(sb)) { fordPt = [a[0], a[1]]; break; }
}

for (let c = 0; c < N * N; c++) {
  const d = riverField.d[c];
  if (d === Infinity) continue;
  let h = H[c];
  const vf = 1 - smoothstep(35, 180, d);
  h = lerp(h, 17.7 + d * 0.01, vf * 0.88);
  if (d < RHW + BANK) {
    if (d < RHW) {
      const bed = L.WATER_LEVEL - 0.8 - 3.1 * (1 - (d / RHW) * (d / RHW));
      h = Math.min(h, bed);
    } else {
      const t = smoothstep(0, 1, (d - RHW) / BANK);
      h = lerp(L.WATER_LEVEL - 0.8, h, t);
    }
  }
  H[c] = h;
}
if (fordPt) {
  const [fx, fz] = fordPt;
  for (let j = ci(fz - 40); j <= ci(fz + 40); j++) for (let i = ci(fx - 40); i <= ci(fx + 40); i++) {
    if (!inGrid(i, j)) continue;
    const c = idx(i, j);
    const dd = Math.hypot(wx(i) - fx, wx(j) - fz);
    if (dd < 34) {
      const shallow = L.WATER_LEVEL - 0.55;
      const k = 1 - smoothstep(18, 34, dd);
      if (H[c] < shallow) H[c] = lerp(H[c], shallow, k);
    }
  }
}
console.timeEnd('river');

// ---------------------------------------------------------------------------
// 3. Zones: flatten compounds
// ---------------------------------------------------------------------------
function flattenRect(rect, margin, strength) {
  const [x0, z0, x1, z1] = rect;
  let sum = 0, n = 0;
  for (let z = z0; z <= z1; z += 4) for (let x = x0; x <= x1; x += 4) { sum += sampleH(H, x, z); n++; }
  const avg = sum / n;
  for (let j = ci(z0 - margin); j <= ci(z1 + margin); j++) for (let i = ci(x0 - margin); i <= ci(x1 + margin); i++) {
    if (!inGrid(i, j)) continue;
    const x = wx(i), z = wx(j);
    const dx = Math.max(x0 - x, 0, x - x1), dz = Math.max(z0 - z, 0, z - z1);
    const dd = Math.hypot(dx, dz);
    const k = (1 - smoothstep(0, margin, dd)) * strength;
    H[idx(i, j)] = lerp(H[idx(i, j)], avg, k);
  }
  return avg;
}
function flattenCircle(cx, cz, r, margin, strength) {
  let sum = 0, n = 0;
  for (let a = 0; a < 24; a++) for (let rr = 0; rr <= r; rr += r / 4) {
    sum += sampleH(H, cx + Math.cos(a) * rr, cz + Math.sin(a) * rr); n++;
  }
  const avg = sum / n;
  for (let j = ci(cz - r - margin); j <= ci(cz + r + margin); j++) for (let i = ci(cx - r - margin); i <= ci(cx + r + margin); i++) {
    if (!inGrid(i, j)) continue;
    const dd = Math.max(0, Math.hypot(wx(i) - cx, wx(j) - cz) - r);
    const k = (1 - smoothstep(0, margin, dd)) * strength;
    H[idx(i, j)] = lerp(H[idx(i, j)], avg, k);
  }
  return avg;
}
for (const z of L.ZONES) {
  if (z.rect) flattenRect(z.rect, 30, 0.95);
  else if (z.id === 'village') flattenCircle(z.circle[0], z.circle[1], z.circle[2] * 0.6, 60, 0.55);
  else flattenCircle(z.circle[0], z.circle[1], z.circle[2], 35, 0.93);
}

// ---------------------------------------------------------------------------
// 4. Roads + rail: profiles, bridges, carving
// ---------------------------------------------------------------------------
console.time('roads');
const DECK_Y = L.WATER_LEVEL + 5.2;
const BRIDGE_LEN = L.RIVER_WIDTH + 2 * BANK + 10;
const bridges = [];

function buildLinear(id, kind, width, ctrl, opts = {}) {
  const pts = densify(ctrl, 2);
  const hw = width / 2;
  // detect river crossings
  const spans = [];
  if (!opts.ford) {
    for (let k = 0; k < pts.length - 1; k++) {
      const a = pts[k], b = pts[k + 1];
      const sa = a[0] - L.riverX(a[1]), sb = b[0] - L.riverX(b[1]);
      if (Math.sign(sa) !== Math.sign(sb)) {
        const sCross = a[2];
        spans.push([sCross - BRIDGE_LEN / 2, sCross + BRIDGE_LEN / 2]);
        const yaw = Math.atan2(b[0] - a[0], b[1] - a[1]); // local +Z along travel
        bridges.push({
          id: `bridge_${id}`, kind: kind === 'rail' ? 'rail' : 'road', x: r2(a[0]), z: r2(a[1]), yaw: r2(yaw),
          length: BRIDGE_LEN, width: kind === 'rail' ? 6 : Math.max(width + 2, 9), deckY: r2(DECK_Y), road: id,
        });
      }
    }
  }
  const inSpan = (s, pad = 0) => spans.some(([s0, s1]) => s >= s0 - pad && s <= s1 + pad);
  // raw profile
  let prof = pts.map((p) => sampleH(H, p[0], p[1]));
  for (let k = 0; k < pts.length; k++) if (inSpan(pts[k][2])) prof[k] = DECK_Y;
  // smooth (keeping decks fixed); long window gives drivable grades
  for (let pass = 0; pass < 6; pass++) {
    const win = kind === 'highway' ? 14 : kind === 'rail' ? 18 : 9;
    const next = prof.slice();
    for (let k = 0; k < pts.length; k++) {
      if (inSpan(pts[k][2])) { next[k] = DECK_Y; continue; }
      let sum = 0, n = 0;
      for (let q = -win; q <= win; q++) {
        const kk = clamp(k + q, 0, pts.length - 1);
        sum += prof[kk]; n++;
      }
      next[k] = sum / n;
    }
    prof = next;
  }
  // ford: never let the road go above terrain in the water (drive through)
  const shoulder = kind === 'highway' ? 10 : kind === 'rail' ? 8 : kind === 'dirt' ? 5 : 6;
  const field = polylineField(pts.map((p) => [p[0], p[1]]), hw + shoulder);
  const total = field.length;
  for (let c = 0; c < N * N; c++) {
    const d = field.d[c];
    if (d === Infinity) continue;
    const s = field.s[c];
    if (inSpan(s, 1.5)) continue; // bridge: leave river channel untouched
    const fk = clamp((s / total) * (pts.length - 1), 0, pts.length - 1);
    const k0 = Math.floor(fk), k1 = Math.min(k0 + 1, pts.length - 1);
    const ph = lerp(prof[k0], prof[k1], fk - k0) + (kind === 'rail' ? 0.6 : 0);
    if (d <= hw + 0.6) H[c] = ph - 0.03;
    else {
      const t = smoothstep(hw + 0.6, hw + shoulder, d);
      H[c] = lerp(ph - 0.03, H[c], t);
    }
  }
  const out = pts.map((p, k) => [r2(p[0]), r2(prof[k]), r2(p[1])]);
  return { id, kind, width, pts: out, spans, field, hw };
}

// order: minor first so that major roads win at junctions
const roadOrder = ['dirt', 'street', 'road', 'highway'];
const roadDefs = [...L.ROADS].sort((a, b) => roadOrder.indexOf(a.kind) - roadOrder.indexOf(b.kind));
const roads = [];
const rail = buildLinear('rail', 'rail', 4.6, L.RAIL.ctrl);
for (const r of roadDefs) roads.push(buildLinear(r.id, r.kind, r.width, r.ctrl, { ford: !!r.ford }));
console.timeEnd('roads');

// Combined clearance field: distance to nearest road edge (negative = on road)
const roadClear = new Float32Array(N * N).fill(1e9);
for (const r of [...roads, rail]) {
  for (let c = 0; c < N * N; c++) {
    const d = r.field.d[c];
    if (d !== Infinity) roadClear[c] = Math.min(roadClear[c], d - r.hw);
  }
}
const clearAt = (x, z) => {
  const i = ci(x), j = ci(z);
  if (!inGrid(i, j)) return -1;
  return roadClear[idx(i, j)];
};
const riverDistAt = (x, z) => {
  const i = ci(x), j = ci(z);
  if (!inGrid(i, j)) return 0;
  const d = riverField.d[idx(i, j)];
  return d === Infinity ? 1e9 : d;
};

// ---------------------------------------------------------------------------
// 5. Buildings
// ---------------------------------------------------------------------------
const buildings = [];
const props = [];
const fences = [];
const paved = [];
const footprintOf = (arch) => {
  const a = SPECS.archetypes[arch];
  if (!a) throw new Error(`unknown archetype ${arch}`);
  return { W: a.w * MOD, D: a.d * MOD, spec: a };
};

function rectCorners(cx, cz, yaw, W, D) {
  const c = Math.cos(yaw), s = Math.sin(yaw);
  // local (lx, lz) -> world: x = cx + lx*c + lz*s ; z = cz - lx*s + lz*c (rotation.y = yaw)
  return [[-W / 2, -D / 2], [W / 2, -D / 2], [W / 2, D / 2], [-W / 2, D / 2]].map(([lx, lz]) => [cx + lx * c + lz * s, cz - lx * s + lz * c]);
}
function localToWorld(cx, cz, yaw, lx, lz) {
  const c = Math.cos(yaw), s = Math.sin(yaw);
  return [cx + lx * c + lz * s, cz - lx * s + lz * c];
}
function obbOverlap(a, b) {
  const axes = [];
  for (const r of [a, b]) {
    const c = Math.cos(r.yaw), s = Math.sin(r.yaw);
    axes.push([c, -s], [s, c]);
  }
  const ca = rectCorners(a.x, a.z, a.yaw, a.W, a.D), cb = rectCorners(b.x, b.z, b.yaw, b.W, b.D);
  for (const [ax, az] of axes) {
    let amin = Infinity, amax = -Infinity, bmin = Infinity, bmax = -Infinity;
    for (const p of ca) { const v = p[0] * ax + p[1] * az; amin = Math.min(amin, v); amax = Math.max(amax, v); }
    for (const p of cb) { const v = p[0] * ax + p[1] * az; bmin = Math.min(bmin, v); bmax = Math.max(bmax, v); }
    if (amax < bmin || bmax < amin) return false;
  }
  return true;
}
const occupied = []; // {x,z,yaw,W,D}
function areaFree(x, z, yaw, W, D, opt = {}) {
  const margin = opt.margin ?? 2;
  const roadMargin = opt.roadMargin ?? 2.5;
  // bounds
  for (const [px, pz] of rectCorners(x, z, yaw, W + margin * 2, D + margin * 2)) {
    if (Math.abs(px) > 1000 || Math.abs(pz) > 1000) return false;
  }
  // road/river sampling
  for (let lz = -D / 2 - margin; lz <= D / 2 + margin; lz += 2) {
    for (let lx = -W / 2 - margin; lx <= W / 2 + margin; lx += 2) {
      const [px, pz] = localToWorld(x, z, yaw, lx, lz);
      if (clearAt(px, pz) < roadMargin - margin) return false;
      if (riverDistAt(px, pz) < RHW + BANK + 4) return false;
    }
  }
  const me = { x, z, yaw, W: W + margin * 2, D: D + margin * 2 };
  for (const o of occupied) if (obbOverlap(me, o)) return false;
  if (!opt.allowPoint) {
    for (const p of L.POINTS) if (Math.hypot(x - p.x, z - p.z) < p.radius * 0.55 + Math.max(W, D) / 2) return false;
  }
  return true;
}
let bid = 0;
function addBuilding(arch, x, z, yaw, extra = {}) {
  const { W, D, spec } = footprintOf(arch);
  const b = {
    id: `b${bid++}`, arch, x: r2(x), z: r2(z), yaw: r2(yaw), W, D, rows: spec.rows,
    style: extra.style || spec.style, zone: extra.zone || 'rural', preDamage: extra.preDamage || 0,
    seed: rng.int(1, 1e6),
  };
  buildings.push(b);
  occupied.push({ x, z, yaw, W: W + 2, D: D + 2 });
  return b;
}
function tryBuilding(arch, x, z, yaw, extra = {}) {
  const { W, D } = footprintOf(arch);
  if (!areaFree(x, z, yaw, W, D, extra)) {
    if (extra.force) {
      console.warn(`  forced placement of ${arch} at ${x.toFixed(0)},${z.toFixed(0)}`);
      return addBuilding(arch, x, z, yaw, extra);
    }
    return null;
  }
  return addBuilding(arch, x, z, yaw, extra);
}
let pid = 0;
function addProp(type, x, z, yaw = 0, extra = {}) {
  const p = { id: `p${pid++}`, type, x: r2(x), z: r2(z), yaw: r2(yaw), ...extra };
  props.push(p);
  return p;
}
function occupy(x, z, yaw, W, D) { occupied.push({ x, z, yaw, W, D }); }

const facing = (fromX, fromZ, toX, toZ) => Math.atan2(toX - fromX, toZ - fromZ); // yaw so local +Z points at target

// ---- 5a. Industrial complex (Point A) -------------------------------------
{
  const A = L.POINTS[0];
  const z = 'industrial';
  tryBuilding('factory_hall', -505, -128, 0, { zone: z, force: true });
  tryBuilding('factory_hall', -352, -128, 0, { zone: z, force: true });
  tryBuilding('power_station', -472, -174, 0, { zone: z, force: true });
  tryBuilding('warehouse', -522, -20, Math.PI / 2, { zone: z, force: true });
  tryBuilding('warehouse', -337, -22, -Math.PI / 2, { zone: z, force: true });
  tryBuilding('warehouse', -500, 28, Math.PI, { zone: z, force: true, preDamage: 4 });
  tryBuilding('admin_building', -372, 26, Math.PI, { zone: z, force: true });
  addProp('water_tower', -548, -78, 0);
  occupy(-548, -78, 0, 10, 10);
  addProp('chimney', -508, -168, 0);
  occupy(-508, -168, 0, 8, 8);
  for (let k = 0; k < 4; k++) addProp('transformer', -408 + k * 7, -152, 0);
  for (let k = 0; k < 3; k++) addProp('chem_tank', -300 - 8, -70 + k * 11, 0);
  addProp('container_stack', -470, -18, 0.15);
  addProp('container_stack', -395, -24, -0.1);
  addProp('container', -478, -102, Math.PI / 2);
  addProp('container', -386, -98, Math.PI / 2 + 0.2);
  addProp('crate_stack', -455, -30, 0.4);
  addProp('crate_stack', -404, -94, 1.2);
  addProp('pipe_rack', -430, -146, 0);
  addProp('fuel_barrels', -470, -96, 0.3);
  addProp('fuel_barrels', -392, -30, 2.1);
  // rail cars on the siding
  addProp('rail_car', -520, -192, Math.PI / 2 + 0.02);
  addProp('rail_car', -497, -191, Math.PI / 2 + 0.02);
  addProp('locomotive', -360, -180, Math.PI / 2 - 0.15);
  // perimeter fence (concrete) with gates (S, N, E)
  const [x0, z0, x1, z1] = [-562, -205, -298, 46];
  const gateS = -440, gateN = -430, gateE = -90;
  fences.push({ kind: 'concrete', pts: [[x0, z1], [gateS - 9, z1]] }, { kind: 'concrete', pts: [[gateS + 9, z1], [x1, z1]] });
  fences.push({ kind: 'concrete', pts: [[x0, z0], [gateN - 9, z0]] }, { kind: 'concrete', pts: [[gateN + 9, z0], [x1, z0]] });
  fences.push({ kind: 'concrete', pts: [[x0, z0], [x0, z1]] });
  fences.push({ kind: 'concrete', pts: [[x1, z0], [x1, gateE - 8]] }, { kind: 'concrete', pts: [[x1, gateE + 8], [x1, z1]] });
  addProp('guardhouse', gateS + 14, z1 - 5, Math.PI);
  paved.push({ kind: 'concrete', poly: [[-475, -100], [-385, -100], [-385, -22], [-475, -22]] });
}

// ---- 5b. Military base (Point C) -------------------------------------------
{
  const z = 'base';
  const C = L.POINTS[2];
  tryBuilding('command_building', 455, -70, 0, { zone: z, force: true, allowPoint: true });
  tryBuilding('barracks', 378, -100, Math.PI / 2, { zone: z, force: true });
  tryBuilding('barracks', 378, -62, Math.PI / 2, { zone: z, force: true });
  tryBuilding('barracks', 378, -24, Math.PI / 2, { zone: z, force: true });
  tryBuilding('hangar', 540, -70, -Math.PI / 2, { zone: z, force: true });
  tryBuilding('hangar', 540, -22, -Math.PI / 2, { zone: z, force: true });
  addProp('radar', 382, 96, 0);
  addProp('comms_tower', 404, 122, 0);
  addProp('fuel_tank', 546, 104, 0);
  addProp('fuel_tank', 558, 116, 0);
  addProp('supply_depot', 378, 24, Math.PI / 2);
  addProp('helipad', 425, 85, 0);
  addProp('launch_platform', 500, 100, Math.PI);
  for (const [tx, tz] of [[356, -130], [564, -130], [356, 130], [564, 130]]) addProp('watchtower', tx, tz, facing(tx, tz, C.x, C.z));
  for (let k = 0; k < 4; k++) addProp('tent', 408 + k * 12, -118, 0);
  addProp('tent_large', 420, 30, Math.PI / 2);
  addProp('flagpole_hq', 455, 132, 0);
  for (let k = 0; k < 6; k++) addProp('concrete_barrier', 438 + k * 7, 150, 0);
  for (let k = 0; k < 4; k++) addProp('sandbag_wall', 430 + k * 16, 48, 0);
  addProp('sandbag_ring', 485, -30, 0);
  addProp('sandbag_ring', 425, -30, 0);
  addProp('bunker', 455, 150, 0);
  for (const o of [[356, -130], [564, -130], [356, 130], [564, 130], [382, 96], [404, 122], [546, 104], [558, 116], [378, 24], [425, 85], [500, 100]])
    occupy(o[0], o[1], 0, 14, 14);
  const [x0, z0, x1, z1] = [350, -136, 570, 136];
  const gS = 455, gN = 520;
  fences.push({ kind: 'military', pts: [[x0, z1], [gS - 8, z1]] }, { kind: 'military', pts: [[gS + 8, z1], [x1, z1]] });
  fences.push({ kind: 'military', pts: [[x0, z0], [gN - 7, z0]] }, { kind: 'military', pts: [[gN + 7, z0], [x1, z0]] });
  fences.push({ kind: 'military', pts: [[x0, z0], [x0, z1]] }, { kind: 'military', pts: [[x1, z0], [x1, z1]] });
  addProp('gate_barrier', gS, z1, 0);
  addProp('gate_barrier', gN, z0, 0);
  addProp('guardhouse', gS + 13, z1 - 6, Math.PI);
  paved.push({ kind: 'concrete', poly: [[418, -40], [492, -40], [492, 40], [418, 40]] });
  paved.push({ kind: 'concrete', poly: [[500, 50], [560, 50], [560, 95], [500, 95]] });
}

// ---- 5c. Village (Point B) ---------------------------------------------------
{
  const z = 'village';
  const B = L.POINTS[1];
  // landmarks around the square
  tryBuilding('apartment_block', -56, -4, 0, { zone: z, force: true });
  tryBuilding('apartment_block', 62, 2, 0, { zone: z, force: true });
  tryBuilding('apartment_tall', -64, 80, Math.PI, { zone: z, force: true });
  tryBuilding('shop', 40, 64, Math.PI, { zone: z, force: true });
  tryBuilding('school', -134, -2, 0, { zone: z, force: true });
  tryBuilding('railway_station', -52, -106, 0, { zone: z, force: true });
  addProp('rail_platform', -52, -118, Math.PI / 2 - 0.1);
  tryBuilding('gas_station_shop', -206, 136, Math.PI, { zone: z, force: true });
  addProp('fuel_canopy', -206, 118, Math.PI);
  addProp('gas_pump', -212, 118, Math.PI);
  addProp('gas_pump', -200, 118, Math.PI);
  occupy(-206, 118, 0, 16, 10);
  addProp('bus_stop', 18, 122, Math.PI);
  addProp('monument', B.x + 14, B.z + 14, Math.PI * 0.25);
  paved.push({ kind: 'asphalt', poly: [[-22, 18], [22, 18], [24, 62], [-22, 62]] });
  // houses along streets
  const streets = ['main_street', 'street_ew', 'street_north', 'lane_sw', 'lane_e'];
  const archs = [['house_small', 0.4], ['house_medium', 0.35], ['house_long', 0.25]];
  const ruined = L.RUINED_AREA;
  for (const sid of streets) {
    const road = roads.find((r) => r.id === sid);
    const pts = road.pts;
    for (let k = 4; k < pts.length - 4; k += rng.int(7, 10)) {
      const [px, , pz] = pts[k];
      if (Math.hypot(px - 0, pz - 30) > 200) continue;
      const [nx0, , nz0] = pts[Math.min(k + 1, pts.length - 1)];
      let dx = nx0 - px, dz = nz0 - pz;
      const len = Math.hypot(dx, dz) || 1;
      dx /= len; dz /= len;
      for (const side of [-1, 1]) {
        if (rng.chance(0.18)) continue;
        const arch = rng.weighted(archs, (a) => a[1])[0];
        const { W, D } = footprintOf(arch);
        const setback = road.hw + rng.range(4.5, 7.5);
        const nx = -dz * side, nz = dx * side;
        const cx = px + nx * (setback + D / 2), cz = pz + nz * (setback + D / 2);
        const yaw = Math.atan2(-nx, -nz); // front (+Z local) faces the road
        const inRuin = Math.hypot(cx - ruined.x, cz - ruined.z) < ruined.r;
        const pre = inRuin ? rng.pick([3, 4, 5, 4]) : rng.chance(0.06) ? 2 : 0;
        const b = tryBuilding(arch, cx, cz, yaw, { zone: z, preDamage: pre, margin: 2.5 });
        if (b) {
          // yard fence: behind and on the sides of the house
          const yardD = D / 2 + rng.range(6, 10);
          const yardW = W / 2 + rng.range(1.5, 3);
          const kind = rng.pick(['wood', 'wood', 'metal', 'picket']);
          const c1 = localToWorld(cx, cz, yaw, -yardW, -yardD), c2 = localToWorld(cx, cz, yaw, yardW, -yardD);
          const c3 = localToWorld(cx, cz, yaw, yardW, D / 2 + 2), c4 = localToWorld(cx, cz, yaw, -yardW, D / 2 + 2);
          const okFence = [c1, c2, c3, c4].every((p) => clearAt(p[0], p[1]) > 1.0 && riverDistAt(p[0], p[1]) > RHW + BANK);
          if (okFence && rng.chance(0.8)) {
            fences.push({ kind, pts: [c4, c1, c2, c3] });
            occupy(...localToWorld(cx, cz, yaw, 0, -(yardD - D / 2) / 2), yaw, yardW * 2, yardD + 2);
          }
          // garden extras
          if (rng.chance(0.35)) {
            const g = localToWorld(cx, cz, yaw, rng.range(-yardW + 2, yardW - 2), -D / 2 - 4);
            addProp(rng.pick(['shed', 'well', 'woodpile']), g[0], g[1], yaw + rng.range(-0.3, 0.3));
          }
          if (rng.chance(0.25) && !inRuin) {
            const g = localToWorld(cx, cz, yaw, W / 2 + 3, D / 2 + 3.5);
            if (clearAt(g[0], g[1]) > 0.5) addProp('car_civilian', g[0], g[1], yaw + Math.PI / 2 + rng.range(-0.2, 0.2), { variant: rng.int(0, 3) });
          }
        }
      }
    }
  }
  // street furniture
  for (const sid of ['main_street', 'street_ew', 'highway']) {
    const road = roads.find((r) => r.id === sid);
    for (let k = 0; k < road.pts.length; k += 15) {
      const [px, , pz] = road.pts[k];
      if (Math.hypot(px, pz - 30) > 210) continue;
      const nxt = road.pts[Math.min(k + 1, road.pts.length - 1)];
      let dx = nxt[0] - px, dz = nxt[2] - pz;
      const len = Math.hypot(dx, dz) || 1;
      dx /= len; dz /= len;
      const side = (k / 15) % 2 ? 1 : -1;
      const off = road.hw + 1.4;
      const lx = px - dz * side * off, lz = pz + dx * side * off;
      if (riverDistAt(lx, lz) < RHW + BANK + 2) continue;
      addProp('streetlight', lx, lz, Math.atan2(dz * side, -dx * side));
    }
  }
  // ruins: rubble piles + wrecks
  for (let k = 0; k < 7; k++) {
    const a = rng.range(0, Math.PI * 2), d = rng.range(5, ruined.r * 0.9);
    const x = ruined.x + Math.cos(a) * d, zz = ruined.z + Math.sin(a) * d;
    if (clearAt(x, zz) > 2) addProp('rubble_pile', x, zz, rng.range(0, 6.28));
  }
  addProp('car_wreck', 118, 40, 0.6);
  addProp('car_wreck', 150, 25, 2.2);
  addProp('car_wreck', -170, 96, 1.4);
  // defensive positions around the square
  addProp('sandbag_wall', -26, 70, 0);
  addProp('sandbag_wall', 26, 12, Math.PI);
  addProp('sandbag_ring', -30, 12, 0);
  addProp('sandbag_ring', 30, 72, 0);
  addProp('tank_trap', 96, 112, 0.3); addProp('tank_trap', 104, 114, 1.0);
  addProp('concrete_barrier', -6, 118, 0); addProp('concrete_barrier', 6, 118, 0);
}

// ---- 5d. Farms and rural houses --------------------------------------------
{
  const farms = [[-150, 236, 0.2], [146, -350, Math.PI + 0.3], [-300, -380, 1.2], [420, 380, -0.4], [-480, 330, 0.6], [470, -380, 2.6]];
  for (const [fx, fz, fyaw] of farms) {
    tryBuilding('house_long', fx, fz, fyaw, { zone: 'farm' }) || tryBuilding('house_small', fx, fz, fyaw, { zone: 'farm' });
    const [bx, bz] = localToWorld(fx, fz, fyaw, 4, -24);
    tryBuilding('barn', bx, bz, fyaw, { zone: 'farm' });
    for (let k = 0; k < 4; k++) {
      const [hx, hz] = localToWorld(fx, fz, fyaw, -18 + k * 5, -14 + rng.range(-2, 2));
      addProp('haystack', hx, hz, rng.range(0, 6));
    }
    const fc = [localToWorld(fx, fz, fyaw, -26, 12), localToWorld(fx, fz, fyaw, -26, -40), localToWorld(fx, fz, fyaw, 22, -40), localToWorld(fx, fz, fyaw, 22, 12)];
    if (fc.every((p) => clearAt(p[0], p[1]) > 1 && riverDistAt(p[0], p[1]) > RHW + BANK)) fences.push({ kind: 'wood', pts: [fc[0], fc[1], fc[2], fc[3]] });
  }
}

// ---- 5e. HQs -----------------------------------------------------------------
const vehicleSlots = [];
const hqSpawns = { 1: [], 2: [] };
const VEHICLE_ROSTER = [
  ['mbt', 2], ['ifv', 2], ['apc', 2], ['jeep', 3], ['truck', 1], ['supply_truck', 1], ['ambulance', 1],
  ['mlrs', 1], ['artillery', 1], ['recovery', 1], ['comms', 1], ['attack_heli', 1], ['transport_heli', 1],
];
for (const hq of L.HQS) {
  const toCenter = Math.atan2(0 - hq.x, 0 - hq.z); // local +Z toward map centre
  const yaw = toCenter;
  const lw = (lx, lz) => localToWorld(hq.x, hq.z, yaw, lx, lz);
  // camp structures
  const [cpx, cpz] = lw(0, -18);
  addProp('command_tent', cpx, cpz, yaw, { team: hq.team });
  for (let k = 0; k < 5; k++) {
    const [tx, tz] = lw(-40 + k * 10, -36);
    addProp('tent', tx, tz, yaw, { team: hq.team });
  }
  const [fpx, fpz] = lw(0, -4);
  addProp('flagpole_hq', fpx, fpz, yaw, { team: hq.team });
  const [rx, rz] = lw(34, -30);
  addProp('radar_mobile', rx, rz, yaw, { team: hq.team });
  const [sx, sz] = lw(-32, -14);
  addProp('supply_depot', sx, sz, yaw, { team: hq.team });
  for (const [lx, lz] of [[-56, 30], [56, 30], [-62, -10], [62, -10]]) {
    const [bx, bz] = lw(lx, lz);
    addProp('sandbag_wall', bx, bz, yaw + (lx < 0 ? 0.6 : -0.6), { team: hq.team });
  }
  for (let k = -3; k <= 3; k++) {
    const [bx, bz] = lw(k * 6, 52);
    addProp('concrete_barrier', bx, bz, yaw, { team: hq.team });
  }
  // infantry spawn points (ring)
  for (let k = 0; k < 12; k++) {
    const a = (k / 12) * Math.PI * 2;
    const [px, pz] = lw(Math.cos(a) * 9, 8 + Math.sin(a) * 6);
    hqSpawns[hq.team].push({ x: r2(px), z: r2(pz), yaw: r2(yaw + Math.PI) });
  }
  // vehicle slots: two rows behind the camp facing the battlefield
  let slot = 0;
  for (const [type, count] of VEHICLE_ROSTER) {
    for (let c = 0; c < count; c++) {
      let lx, lz;
      if (type.endsWith('heli')) {
        lx = type === 'attack_heli' ? -62 : 62;
        lz = -44;
        const [hx, hz] = lw(lx, lz);
        addProp('helipad', hx, hz, yaw, { team: hq.team });
      } else {
        const col = slot % 9, row = Math.floor(slot / 9);
        lx = -44 + col * 11;
        lz = 22 + row * 14;
        slot++;
      }
      const [vx, vz] = lw(lx, lz);
      vehicleSlots.push({ team: hq.team, type, x: r2(vx), z: r2(vz), yaw: r2(yaw + Math.PI), home: 'hq' });
    }
  }
  paved.push({ kind: 'gravel', poly: [lw(-56, 12), lw(56, 12), lw(56, 46), lw(-56, 46)] });
  occupy(hq.x, hq.z, yaw, 150, 130);
}
// Base C motor pool: available to whoever holds C
vehicleSlots.push({ team: 0, type: 'mbt', x: 512, z: 64, yaw: Math.PI, home: 'C' });
vehicleSlots.push({ team: 0, type: 'ifv', x: 528, z: 64, yaw: Math.PI, home: 'C' });
vehicleSlots.push({ team: 0, type: 'jeep', x: 544, z: 64, yaw: Math.PI, home: 'C' });
// Industrial A yard: a truck for whoever holds A
vehicleSlots.push({ team: 0, type: 'truck', x: -470, z: -48, yaw: 0, home: 'A' });
vehicleSlots.push({ team: 0, type: 'jeep', x: 18, z: 80, yaw: Math.PI / 2, home: 'B' });

// Bridge approach defences + bunkers
for (const br of bridges) {
  for (const side of [-1, 1]) {
    const ox = Math.sin(br.yaw) * side * (br.length / 2 + 14), oz = Math.cos(br.yaw) * side * (br.length / 2 + 14);
    const px = br.x + ox + Math.cos(br.yaw) * 9, pz = br.z + oz - Math.sin(br.yaw) * 9;
    if (clearAt(px, pz) > 1) addProp('sandbag_ring', px, pz, br.yaw);
  }
}
addProp('bunker', 222, 56, 0.4);
addProp('bunker', 318, -105, -2.2);

// Power lines along the main street and the highway
for (const sid of ['highway', 'main_street']) {
  const road = roads.find((r) => r.id === sid);
  const poles = [];
  for (let k = 0; k < road.pts.length; k += 22) {
    const [px, , pz] = road.pts[k];
    if (Math.abs(px) > 980 || Math.abs(pz) > 980) continue;
    const nxt = road.pts[Math.min(k + 1, road.pts.length - 1)];
    let dx = nxt[0] - px, dz = nxt[2] - pz;
    const len = Math.hypot(dx, dz) || 1;
    dx /= len; dz /= len;
    const off = road.hw + 6.5;
    const lx = px + dz * off, lz = pz - dx * off;
    if (riverDistAt(lx, lz) < RHW + BANK + 3) { poles.push(null); continue; }
    const tooClose = occupied.some((o) => Math.hypot(o.x - lx, o.z - lz) < Math.max(o.W, o.D) / 2 + 1);
    if (tooClose) { poles.push(null); continue; }
    poles.push(addProp('power_pole', lx, lz, Math.atan2(dx, dz)).id);
  }
  props.push({ id: `p${pid++}`, type: 'power_line', poles: poles.filter(Boolean), x: 0, z: 0, yaw: 0 });
}

// Road signs at junctions / entries
const SIGNS = [
  [-12, 150, 'DOLYNA'], [12, -150, 'DOLYNA'], [-420, 120, 'KIROV WORKS'], [-415, -240, 'KIROV WORKS'],
  [450, 210, 'GARRISON 41'], [520, -180, 'GARRISON 41'], [-260, 100, 'DOLYNA 3 KM'], [330, 115, 'BRIDGE 12T'],
];
for (const [sx, sz, text] of SIGNS) addProp('road_sign', sx, sz, 0, { text });

// Extra cover in the open: rocks, wrecks, haystacks, foxholes along routes
for (let k = 0; k < 90; k++) {
  const x = rng.range(-680, 680), z = rng.range(-680, 680);
  if (clearAt(x, z) < 4 || riverDistAt(x, z) < RHW + BANK + 3) continue;
  if (occupied.some((o) => Math.hypot(o.x - x, o.z - z) < Math.max(o.W, o.D) / 2 + 6)) continue;
  if (L.HQS.some((h) => Math.hypot(h.x - x, h.z - z) < h.radius + 20)) continue;
  const t = rng.weighted([['rock', 4], ['rock_large', 2], ['car_wreck', 1], ['tank_wreck', 0.6], ['sandbag_ring', 1.2], ['sandbag_wall', 1.2]], (a) => a[1])[0];
  addProp(t, x, z, rng.range(0, Math.PI * 2));
}

// ---------------------------------------------------------------------------
// 6. Building pads
// ---------------------------------------------------------------------------
for (const b of buildings) {
  let sum = 0, n = 0;
  for (let lz = -b.D / 2; lz <= b.D / 2; lz += 2) for (let lx = -b.W / 2; lx <= b.W / 2; lx += 2) {
    const [px, pz] = localToWorld(b.x, b.z, b.yaw, lx, lz);
    sum += sampleH(H, px, pz); n++;
  }
  const pad = sum / n;
  b.y = r2(pad);
  const ext = Math.hypot(b.W, b.D) / 2 + 10;
  const c = Math.cos(b.yaw), s = Math.sin(b.yaw);
  for (let j = ci(b.z - ext); j <= ci(b.z + ext); j++) for (let i = ci(b.x - ext); i <= ci(b.x + ext); i++) {
    if (!inGrid(i, j)) continue;
    const dx = wx(i) - b.x, dz = wx(j) - b.z;
    const lx = dx * c - dz * s, lz = dx * s + dz * c; // inverse rotation
    const ex = Math.max(Math.abs(lx) - (b.W / 2 + 1), 0), ez = Math.max(Math.abs(lz) - (b.D / 2 + 1), 0);
    const dd = Math.hypot(ex, ez);
    if (dd > 8) continue;
    const k = 1 - smoothstep(0, 8, dd);
    H[idx(i, j)] = lerp(H[idx(i, j)], pad - 0.05, k);
  }
}

// ---------------------------------------------------------------------------
// 7. Fields (strips) and forest density
// ---------------------------------------------------------------------------
const fieldStrips = [];
for (const f of L.FIELDS) {
  // split the quad into strips along its longer axis
  const [p0, p1, p2, p3] = f.poly;
  const n = f.crops.length;
  for (let k = 0; k < n; k++) {
    const t0 = k / n, t1 = (k + 1) / n;
    const a = [lerp(p0[0], p1[0], t0), lerp(p0[1], p1[1], t0)];
    const b = [lerp(p0[0], p1[0], t1), lerp(p0[1], p1[1], t1)];
    const c = [lerp(p3[0], p2[0], t1), lerp(p3[1], p2[1], t1)];
    const d = [lerp(p3[0], p2[0], t0), lerp(p3[1], p2[1], t0)];
    const rowYaw = Math.atan2(c[0] - b[0], c[1] - b[1]);
    fieldStrips.push({ crop: f.crops[k], poly: [a, b, c, d].map((p) => [r1(p[0]), r1(p[1])]), rowYaw: r2(rowYaw) });
  }
}
const fieldMask = new Uint8Array(N * N); // 0 none, 1 plowed, 2 wheat, 3 green, 4 sunflower
const CROP_ID = { plowed: 1, wheat: 2, green: 3, sunflower: 4 };
for (const fs_ of fieldStrips) {
  const xs = fs_.poly.map((p) => p[0]), zs = fs_.poly.map((p) => p[1]);
  for (let j = ci(Math.min(...zs)); j <= ci(Math.max(...zs)); j++) for (let i = ci(Math.min(...xs)); i <= ci(Math.max(...xs)); i++) {
    if (!inGrid(i, j)) continue;
    if (pointInPolygon(wx(i), wx(j), fs_.poly) && roadClear[idx(i, j)] > 1.5) fieldMask[idx(i, j)] = CROP_ID[fs_.crop];
  }
}
const forest = new Float32Array(N * N);
for (let j = 0; j < N; j++) {
  const z = wx(j);
  for (let i = 0; i < N; i++) {
    const x = wx(i);
    let f = 0;
    for (const fo of L.FORESTS) {
      const d = Math.hypot(x - fo.x, z - fo.z);
      const edge = fo.r * (0.85 + 0.25 * noiseC.fbm(x / 70, z / 70, 3));
      f = Math.max(f, 1 - smoothstep(edge * 0.82, edge, d));
    }
    const e = Math.pow(Math.pow(Math.abs(x), 4) + Math.pow(Math.abs(z), 4), 0.25);
    f = Math.max(f, smoothstep(745, 805, e + 55 * noiseB.fbm(x / 160, z / 160, 3)) * (0.75 + 0.25 * noiseA.noise(x / 50, z / 50)));
    forest[idx(i, j)] = clamp(f, 0, 1);
  }
}

// ---------------------------------------------------------------------------
// 8. Vegetation placement
// ---------------------------------------------------------------------------
const TREE_TYPES = ['pine', 'spruce', 'birch', 'oak', 'poplar', 'willow', 'fruit'];
const T = Object.fromEntries(TREE_TYPES.map((t, k) => [t, k]));
const trees = [];
const bushes = [];
function blockedForVeg(x, z, clearance) {
  const i = ci(x), j = ci(z);
  if (!inGrid(i, j)) return true;
  const c = idx(i, j);
  if (roadClear[c] < clearance) return true;
  if (riverField.d[c] < RHW + 2) return true;
  if (fieldMask[c]) return true;
  for (const p of L.POINTS) if (Math.hypot(x - p.x, z - p.z) < p.radius + 6) return true;
  for (const h of L.HQS) if (Math.hypot(x - h.x, z - h.z) < h.radius + 10) return true;
  return false;
}
function insideOccupied(x, z, pad) {
  for (const o of occupied) {
    const c = Math.cos(o.yaw), s = Math.sin(o.yaw);
    const dx = x - o.x, dz = z - o.z;
    const lx = dx * c - dz * s, lz = dx * s + dz * c;
    if (Math.abs(lx) < o.W / 2 + pad && Math.abs(lz) < o.D / 2 + pad) return true;
  }
  return false;
}
// spatial grid for occupied to speed up checks
const occGrid = new Map();
const OG = 32;
for (const o of occupied) {
  const r = Math.hypot(o.W, o.D) / 2 + 6;
  for (let gx = Math.floor((o.x - r) / OG); gx <= Math.floor((o.x + r) / OG); gx++)
    for (let gz = Math.floor((o.z - r) / OG); gz <= Math.floor((o.z + r) / OG); gz++) {
      const key = gx + ',' + gz;
      if (!occGrid.has(key)) occGrid.set(key, []);
      occGrid.get(key).push(o);
    }
}
function occupiedFast(x, z, pad) {
  const list = occGrid.get(Math.floor(x / OG) + ',' + Math.floor(z / OG));
  if (!list) return false;
  for (const o of list) {
    const c = Math.cos(o.yaw), s = Math.sin(o.yaw);
    const dx = x - o.x, dz = z - o.z;
    const lx = dx * c - dz * s, lz = dx * s + dz * c;
    if (Math.abs(lx) < o.W / 2 + pad && Math.abs(lz) < o.D / 2 + pad) return true;
  }
  return false;
}

const FOREST_MIX = Object.fromEntries(L.FORESTS.map((f) => [f.x + ',' + f.z, f.mix]));
function mixAt(x, z) {
  let best = null, bd = Infinity;
  for (const f of L.FORESTS) {
    const d = Math.hypot(x - f.x, z - f.z) / f.r;
    if (d < bd) { bd = d; best = f.mix; }
  }
  if (bd > 1.3) return 'conifer';
  return best;
}
const MIXES = {
  conifer: [['pine', 5], ['spruce', 4], ['birch', 1]],
  mixed: [['pine', 3], ['spruce', 2], ['oak', 2], ['birch', 2]],
  deciduous: [['oak', 5], ['birch', 2], ['pine', 1]],
  birch: [['birch', 6], ['oak', 1], ['pine', 1]],
};
// Roblox budget: every tree is a few parts, so forests are sparser with bigger trees.
const STEP = 8.0;
for (let z = -1020; z <= 1020; z += STEP) {
  for (let x = -1020; x <= 1020; x += STEP) {
    const jx = x + rng.range(-3.2, 3.2), jz = z + rng.range(-3.2, 3.2);
    const i = ci(jx), j = ci(jz);
    if (!inGrid(i, j)) continue;
    const f = forest[idx(i, j)];
    if (f <= 0.02) continue;
    const far = Math.max(Math.abs(jx), Math.abs(jz)) > 760;
    const p = far ? f * 0.32 : f * 0.7;
    if (!rng.chance(p)) continue;
    if (blockedForVeg(jx, jz, 3)) continue;
    if (occupiedFast(jx, jz, 3)) continue;
    const mix = MIXES[mixAt(jx, jz)];
    const type = rng.weighted(mix, (m) => m[1])[0];
    const s = rng.range(0.9, 1.35) * (type === 'oak' ? 1.05 : 1);
    trees.push(jx, jz, T[type], s, rng.range(0, 6.283));
    if (!far && rng.chance(0.12)) {
      const bx = jx + rng.range(-2.5, 2.5), bz = jz + rng.range(-2.5, 2.5);
      if (!blockedForVeg(bx, bz, 2)) bushes.push(bx, bz, rng.int(0, 2), rng.range(0.7, 1.4), rng.range(0, 6.283));
    }
  }
}
// riverside willows
for (let k = 0; k < riverPts.length; k++) {
  if (!rng.chance(0.3)) continue;
  const [rx, rz] = riverPts[k];
  if (Math.abs(rz) > 1000) continue;
  for (const side of [-1, 1]) {
    if (!rng.chance(0.6)) continue;
    const x = rx + side * (RHW + rng.range(4, 18)), z = rz + rng.range(-3, 3);
    if (blockedForVeg(x, z, 4) || occupiedFast(x, z, 3)) continue;
    trees.push(x, z, T[rng.chance(0.7) ? 'willow' : 'birch'], rng.range(0.8, 1.2), rng.range(0, 6.283));
  }
}
// poplar lines along the highway and the main roads outside the village
for (const sid of ['highway', 'road_blue_A', 'road_red_C', 'road_blue_C']) {
  const road = roads.find((r) => r.id === sid);
  for (let k = 0; k < road.pts.length; k += 6) {
    const [px, , pz] = road.pts[k];
    if (Math.hypot(px, pz - 30) < 230) continue;
    if (!rng.chance(0.55)) continue;
    const nxt = road.pts[Math.min(k + 1, road.pts.length - 1)];
    let dx = nxt[0] - px, dz = nxt[2] - pz;
    const len = Math.hypot(dx, dz) || 1;
    dx /= len; dz /= len;
    const side = rng.sign();
    const off = road.hw + rng.range(8, 11);
    const x = px + dz * side * off, z = pz - dx * side * off;
    if (blockedForVeg(x, z, 6) || occupiedFast(x, z, 3)) continue;
    trees.push(x, z, T[rng.chance(0.75) ? 'poplar' : 'birch'], rng.range(0.85, 1.15), rng.range(0, 6.283));
  }
}
// village gardens: fruit trees
for (const b of buildings) {
  if (b.zone !== 'village' && b.zone !== 'farm') continue;
  const n = rng.int(1, 3);
  for (let k = 0; k < n; k++) {
    const [x, z] = localToWorld(b.x, b.z, b.yaw, rng.range(-b.W / 2, b.W / 2), -b.D / 2 - rng.range(4, 8));
    if (blockedForVeg(x, z, 2.5) || occupiedFast(x, z, 1)) continue;
    trees.push(x, z, T.fruit, rng.range(0.8, 1.1), rng.range(0, 6.283));
  }
}
// scattered bushes in grassland
for (let k = 0; k < 1600; k++) {
  const x = rng.range(-980, 980), z = rng.range(-980, 980);
  if (blockedForVeg(x, z, 2.5) || occupiedFast(x, z, 2)) continue;
  bushes.push(x, z, rng.int(0, 2), rng.range(0.6, 1.5), rng.range(0, 6.283));
}
// sunflowers & wheat are rendered from the field strips by the client.

// ---------------------------------------------------------------------------
// 9. Splat maps (1024 x 1024, 2 m texels)
// ---------------------------------------------------------------------------
console.time('splat');
const S = 1024;
const splatA = new Uint8Array(S * S * 4); // R dirt, G rock, B sand, A mud
const splatB = new Uint8Array(S * S * 4); // R plowed, G wheat, B forest floor, A gravel
const dirtRoads = roads.filter((r) => r.kind === 'dirt');
const pavedRoads = roads.filter((r) => r.kind !== 'dirt');
const pavedMask = new Uint8Array(N * N);
for (const pv of paved) {
  const xs = pv.poly.map((p) => p[0]), zs = pv.poly.map((p) => p[1]);
  for (let j = ci(Math.min(...zs)) - 3; j <= ci(Math.max(...zs)) + 3; j++) for (let i = ci(Math.min(...xs)) - 3; i <= ci(Math.max(...xs)) + 3; i++) {
    if (inGrid(i, j) && pointInPolygon(wx(i), wx(j), pv.poly)) pavedMask[idx(i, j)] = 1;
  }
}
const zoneGravel = (x, z) => {
  for (const zz of L.ZONES) {
    if (zz.rect) {
      const [x0, z0, x1, z1] = zz.rect;
      if (x > x0 && x < x1 && z > z0 && z < z1) return 0.55 + 0.35 * noiseA.noise(x / 18, z / 18);
    } else if (zz.id.startsWith('hq')) {
      const d = Math.hypot(x - zz.circle[0], z - zz.circle[1]);
      if (d < zz.circle[2]) return (1 - smoothstep(zz.circle[2] * 0.6, zz.circle[2], d)) * (0.6 + 0.3 * noiseB.noise(x / 15, z / 15));
    }
  }
  return 0;
};
for (let v = 0; v < S; v++) {
  for (let u = 0; u < S; u++) {
    const x = -HALF + (u + 0.5) * 2, z = -HALF + (v + 0.5) * 2;
    const i = ci(x), j = ci(z);
    const c = idx(clamp(i, 0, N - 1), clamp(j, 0, N - 1));
    // slope
    const hL = sampleH(H, x - 2, z), hR = sampleH(H, x + 2, z), hD = sampleH(H, x, z - 2), hU = sampleH(H, x, z + 2);
    const slope = Math.hypot(hR - hL, hU - hD) / 4;
    const h = sampleH(H, x, z);
    let dirt = 0, rock = 0, sand = 0, mud = 0, plowed = 0, wheat = 0, ffloor = 0, gravel = 0;
    rock = smoothstep(0.42, 0.75, slope);
    const rd = riverField.d[c];
    if (rd < RHW + 10) {
      sand = 1 - smoothstep(RHW + 3, RHW + 10, rd);
      mud = (1 - smoothstep(RHW - 2, RHW + 6, rd)) * 0.7 + (h < L.WATER_LEVEL - 0.3 ? 0.3 : 0);
      if (h < L.WATER_LEVEL - 1.2) { rock = Math.max(rock, 0.35); sand = 0.65; }
    }
    // dirt roads
    for (const r of dirtRoads) {
      const d = r.field.d[c];
      if (d < r.hw + 2.5) {
        const k = 1 - smoothstep(r.hw - 0.8, r.hw + 2.5, d);
        dirt = Math.max(dirt, k * (0.85 + 0.15 * noiseA.noise(x / 3, z / 3)));
        mud = Math.max(mud, k * 0.35 * (0.5 + 0.5 * noiseB.noise(x / 9, z / 9)));
      }
    }
    // paved-road shoulders: gravel
    for (const r of [...pavedRoads, rail]) {
      const d = r.field.d[c];
      if (d < r.hw + 3.2) {
        const k = 1 - smoothstep(r.hw + 0.5, r.hw + 3.2, d);
        gravel = Math.max(gravel, k);
      }
    }
    gravel = Math.max(gravel, zoneGravel(x, z), pavedMask[c] ? 0.9 : 0);
    // fields
    const crop = fieldMask[c];
    if (crop === 1 || crop === 4) plowed = 1;
    if (crop === 2) wheat = 1;
    if (crop === 3) { plowed = 0.25; }
    // forest floor
    ffloor = smoothstep(0.15, 0.6, forest[c]);
    // natural dirt patches + wet hollows
    const n1 = noiseC.fbm(x / 45, z / 45, 3);
    if (n1 > 0.35) dirt = Math.max(dirt, smoothstep(0.35, 0.6, n1) * 0.55 * (1 - ffloor));
    const n2 = noiseA.fbm(x / 80 + 20, z / 80, 3);
    if (n2 > 0.4 && h < 19) mud = Math.max(mud, smoothstep(0.4, 0.65, n2) * 0.5);
    // normalise: grass is implicit remainder
    let sum = dirt + rock + sand + mud + plowed + wheat + ffloor + gravel;
    if (sum > 1) { const k = 1 / sum; dirt *= k; rock *= k; sand *= k; mud *= k; plowed *= k; wheat *= k; ffloor *= k; gravel *= k; }
    const o = (v * S + u) * 4;
    splatA[o] = dirt * 255; splatA[o + 1] = rock * 255; splatA[o + 2] = sand * 255; splatA[o + 3] = mud * 255;
    splatB[o] = plowed * 255; splatB[o + 1] = wheat * 255; splatB[o + 2] = ffloor * 255; splatB[o + 3] = gravel * 255;
  }
}
console.timeEnd('splat');

// ---------------------------------------------------------------------------
// 10. Output
// ---------------------------------------------------------------------------
let hMin = Infinity, hMax = -Infinity;
for (let c = 0; c < N * N; c++) { hMin = Math.min(hMin, H[c]); hMax = Math.max(hMax, H[c]); }
hMin = Math.floor(hMin - 1); hMax = Math.ceil(hMax + 1);
const h16 = new Uint16Array(N * N);
for (let c = 0; c < N * N; c++) h16[c] = Math.round(((H[c] - hMin) / (hMax - hMin)) * 65535);
fs.writeFileSync(path.join(OUT, 'height.bin'), Buffer.from(h16.buffer));
fs.writeFileSync(path.join(OUT, 'splatA.png'), encodePNG(S, S, splatA, 4));
fs.writeFileSync(path.join(OUT, 'splatB.png'), encodePNG(S, S, splatB, 4));

// Spawn spots around each control point (used by the point's owner)
const pointSpawns = {};
for (const p of L.POINTS) {
  const list = [];
  for (let k = 0; k < 40 && list.length < 10; k++) {
    const a = rng.range(0, Math.PI * 2), d = rng.range(p.radius * 1.3, p.radius * 2.3);
    const x = p.x + Math.cos(a) * d, z = p.z + Math.sin(a) * d;
    if (occupiedFast(x, z, 1.5) || riverDistAt(x, z) < RHW + 4) continue;
    list.push({ x: r2(x), z: r2(z), yaw: r2(Math.atan2(p.x - x, p.z - z) + Math.PI) });
  }
  pointSpawns[p.id] = list;
}
for (const p of L.POINTS) p.y = r2(sampleH(H, p.x, p.z));

const map = {
  id: L.MAP_ID,
  name: L.MAP_NAME,
  version: 1,
  half: HALF,
  cell: CELL,
  heightRes: N,
  heightMin: hMin,
  heightMax: hMax,
  waterLevel: L.WATER_LEVEL,
  playable: L.PLAYABLE,
  points: L.POINTS,
  hqs: L.HQS.map((h) => ({ ...h, y: r2(sampleH(H, h.x, h.z)) })),
  hqSpawns,
  pointSpawns,
  vehicleSlots,
  roads: roads.map((r) => ({ id: r.id, kind: r.kind, width: r.width, pts: r.pts, bridgeSpans: r.spans.map((s) => s.map(r2)) })),
  rail: { pts: rail.pts, bridgeSpans: rail.spans.map((s) => s.map(r2)), gauge: L.RAIL.gauge },
  river: { pts: riverPts.map((p) => [r2(p[0]), r2(p[1])]), width: L.RIVER_WIDTH, bank: BANK, ford: fordPt && fordPt.map(r2) },
  bridges,
  buildings,
  props,
  fences: fences.map((f) => ({ kind: f.kind, pts: f.pts.map((p) => [r2(p[0]), r2(p[1])]) })),
  paved: paved.map((p) => ({ kind: p.kind, poly: p.poly.map((q) => [r2(q[0]), r2(q[1])]) })),
  fields: fieldStrips,
  zones: L.ZONES,
  trees: { types: TREE_TYPES, stride: 5, data: trees.map((v, k) => (k % 5 === 2 ? v : r2(v))) },
  bushes: { stride: 5, data: bushes.map((v, k) => (k % 5 === 2 ? v : r2(v))) },
};
fs.writeFileSync(path.join(OUT, 'map.json'), JSON.stringify(map));

// ---------------------------------------------------------------------------
// 10b. Roblox export: Luau data modules (studs) consumed via Rojo
//   Info.luau        JSON (long string) with everything except bulk grids
//   HeightNN.luau    base64 uint16 heightmap chunks
//   MaterialNN.luau  base64 4-bit terrain material per cell
//   Vegetation.luau  base64 packed trees and bushes
// ---------------------------------------------------------------------------
{
  const SC = 3; // studs per metre
  const sc = (v) => Math.round(v * SC * 100) / 100;
  const scp = (p) => [sc(p[0]), sc(p[1])];
  const RBX = path.join(ROOT, 'Assets/Maps/DolynaValley');
  fs.mkdirSync(RBX, { recursive: true });
  for (const f of fs.readdirSync(RBX)) if (/^(Height|Material|Vegetation|Info)\w*\.luau$/.test(f)) fs.unlinkSync(path.join(RBX, f));

  const MATS = ['Grass', 'LeafyGrass', 'Ground', 'Mud', 'Rock', 'Sand', 'Salt', 'Pavement', 'Concrete', 'Basalt', 'Asphalt', 'Cobblestone', 'Limestone'];
  const M = Object.fromEntries(MATS.map((m, k) => [m, k]));
  const pavedKind = new Uint8Array(N * N); // 1 asphalt, 2 concrete, 3 gravel
  for (const pv of paved) {
    const kind = pv.kind === 'asphalt' ? 1 : pv.kind === 'concrete' ? 2 : 3;
    const xs = pv.poly.map((p) => p[0]), zs = pv.poly.map((p) => p[1]);
    for (let j = ci(Math.min(...zs)) - 1; j <= ci(Math.max(...zs)) + 1; j++) for (let i = ci(Math.min(...xs)) - 1; i <= ci(Math.max(...xs)) + 1; i++) {
      if (inGrid(i, j) && pointInPolygon(wx(i), wx(j), pv.poly)) pavedKind[idx(i, j)] = kind;
    }
  }
  const mat = new Uint8Array(N * N);
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const c = idx(i, j);
    const x = wx(i), z = wx(j);
    const u = clamp(i, 0, 1023), v = clamp(j, 0, 1023);
    const o = (v * 1024 + u) * 4;
    const dirt = splatA[o] / 255, rock = splatA[o + 1] / 255, sand = splatA[o + 2] / 255, mud = splatA[o + 3] / 255;
    const plowed = splatB[o] / 255, wheat = splatB[o + 1] / 255, ffl = splatB[o + 2] / 255, gravel = splatB[o + 3] / 255;
    const grass = Math.max(0, 1 - (dirt + rock + sand + mud + plowed + wheat + ffl + gravel));
    let m = M.Grass;
    if (pavedKind[c] === 1) m = M.Asphalt;
    else if (pavedKind[c] === 2) m = M.Concrete;
    else if (pavedKind[c] === 3) m = M.Pavement;
    else if (rail.field.d[c] < rail.hw + 1.2) m = M.Basalt;
    else {
      const cand = [
        [M.Grass, grass * 0.95], [M.LeafyGrass, ffl * 0.9], [M.Ground, Math.max(dirt, plowed)], [M.Mud, mud],
        [M.Rock, rock * 1.1], [M.Sand, sand], [M.Salt, wheat], [M.Pavement, gravel * (zoneGravel(x, z) > 0.2 ? 1.1 : 0)], [M.Ground, gravel * 0.7],
      ];
      let best = -1;
      for (const [id, w] of cand) if (w > best) { best = w; m = id; }
      if (fieldMask[c] === 3) m = M.LeafyGrass;
      if (m === M.Grass && noiseC.fbm(x / 60 + 3, z / 60, 3) > 0.32) m = M.LeafyGrass;
      if (m === M.Rock && noiseB.noise(x / 25, z / 25) > 0.35) m = M.Limestone;
    }
    mat[c] = m;
  }
  // pack two cells per byte
  const packed = new Uint8Array(Math.ceil((N * N) / 2));
  for (let c = 0; c < N * N; c++) packed[c >> 1] |= (c & 1) ? (mat[c] << 4) : mat[c];

  const writeChunks = (prefix, b64, size) => {
    const n = Math.ceil(b64.length / size);
    for (let k = 0; k < n; k++) {
      const name = `${prefix}${String(k + 1).padStart(2, '0')}.luau`;
      fs.writeFileSync(path.join(RBX, name), `-- generated by Tools/gen_map.mjs - do not edit\nreturn "${b64.slice(k * size, (k + 1) * size)}"\n`);
    }
    return n;
  };
  const heightChunks = writeChunks('Height', Buffer.from(h16.buffer).toString('base64'), 160000);
  const materialChunks = writeChunks('Material', Buffer.from(packed).toString('base64'), 160000);

  // vegetation: [u32 trees][u32 bushes] then 7-byte records: i16 x, i16 z, u8 type, u8 scale*100, u8 yaw
  const nT = trees.length / 5, nB = bushes.length / 5;
  const vb = Buffer.alloc(8 + (nT + nB) * 7);
  vb.writeUInt32LE(nT, 0); vb.writeUInt32LE(nB, 4);
  let off = 8;
  const putRec = (arr, k) => {
    vb.writeInt16LE(Math.round(arr[k] * SC), off); vb.writeInt16LE(Math.round(arr[k + 1] * SC), off + 2);
    vb.writeUInt8(arr[k + 2], off + 4); vb.writeUInt8(Math.max(1, Math.min(255, Math.round(arr[k + 3] * 100))), off + 5);
    vb.writeUInt8(Math.round(((arr[k + 4] % (Math.PI * 2)) / (Math.PI * 2)) * 255) & 255, off + 6);
    off += 7;
  };
  for (let k = 0; k < trees.length; k += 5) putRec(trees, k);
  for (let k = 0; k < bushes.length; k += 5) putRec(bushes, k);
  fs.writeFileSync(path.join(RBX, 'Vegetation.luau'), `-- generated by Tools/gen_map.mjs - do not edit\nreturn "${vb.toString('base64')}"\n`);

  const archetypes = {};
  for (const [k, a] of Object.entries(SPECS.archetypes)) archetypes[k] = { ...a };
  const info = {
    id: L.MAP_ID, name: L.MAP_NAME, version: 2, studsPerMeter: SC,
    half: HALF * SC, cell: CELL * SC, heightRes: N, heightMin: hMin * SC, heightMax: hMax * SC,
    heightChunks, materialChunks, materials: MATS,
    waterLevel: sc(L.WATER_LEVEL),
    playable: { minX: sc(L.PLAYABLE.minX), maxX: sc(L.PLAYABLE.maxX), minZ: sc(L.PLAYABLE.minZ), maxZ: sc(L.PLAYABLE.maxZ) },
    points: L.POINTS.map((p) => ({ id: p.id, name: p.name, zone: p.zone, x: sc(p.x), z: sc(p.z), y: sc(p.y), radius: sc(p.radius) })),
    hqs: L.HQS.map((h) => ({ team: h.team, name: h.name, x: sc(h.x), z: sc(h.z), y: sc(sampleH(H, h.x, h.z)), radius: sc(h.radius) })),
    hqSpawns: Object.fromEntries(Object.entries(hqSpawns).map(([t, l]) => [t, l.map((s) => ({ x: sc(s.x), z: sc(s.z), yaw: s.yaw }))])),
    pointSpawns: Object.fromEntries(Object.entries(pointSpawns).map(([t, l]) => [t, l.map((s) => ({ x: sc(s.x), z: sc(s.z), yaw: s.yaw }))])),
    vehicleSlots: vehicleSlots.map((v) => ({ ...v, x: sc(v.x), z: sc(v.z) })),
    roads: roads.map((r) => ({ id: r.id, kind: r.kind, width: sc(r.width), pts: r.pts.filter((_, k) => k % 2 === 0 || k === r.pts.length - 1).map((p) => [sc(p[0]), sc(p[1]), sc(p[2])]), bridgeSpans: r.spans.map((s) => s.map(sc)) })),
    rail: { pts: rail.pts.filter((_, k) => k % 2 === 0).map((p) => [sc(p[0]), sc(p[1]), sc(p[2])]), bridgeSpans: rail.spans.map((s) => s.map(sc)), gauge: sc(L.RAIL.gauge) },
    river: { pts: riverPts.map(scp), width: sc(L.RIVER_WIDTH), bank: sc(BANK), ford: fordPt && scp(fordPt) },
    bridges: bridges.map((b) => ({ ...b, x: sc(b.x), z: sc(b.z), length: sc(b.length), width: sc(b.width), deckY: sc(b.deckY) })),
    buildings: buildings.map((b) => ({ ...b, x: sc(b.x), z: sc(b.z), y: sc(b.y), W: sc(b.W), D: sc(b.D) })),
    props: props.map((p) => ({ ...p, x: sc(p.x), z: sc(p.z) })),
    fences: fences.map((f) => ({ kind: f.kind, pts: f.pts.map(scp) })),
    paved: paved.map((p) => ({ kind: p.kind, poly: p.poly.map(scp) })),
    fields: fieldStrips.map((f) => ({ crop: f.crop, poly: f.poly.map(scp), rowYaw: f.rowYaw })),
    zones: L.ZONES.map((z) => ({ ...z, rect: z.rect && z.rect.map(sc), circle: z.circle && z.circle.map(sc) })),
    treeTypes: TREE_TYPES,
    archetypes,
    module: SPECS.module * SC,
    rowHeight: SPECS.rowHeight * SC,
    wallThickness: SPECS.wallThickness * SC,
  };
  const json = JSON.stringify(info);
  if (json.includes(']==]')) throw new Error('JSON contains long-string terminator');
  fs.writeFileSync(path.join(RBX, 'Info.luau'), `-- generated by Tools/gen_map.mjs - do not edit\n-- Map description (studs). Decode with HttpService:JSONDecode.\nreturn [==[${json}]==]\n`);
  console.log(`roblox export: ${heightChunks} height chunks, ${materialChunks} material chunks, info ${(json.length / 1024).toFixed(0)} KB, vegetation ${(vb.length / 1024).toFixed(0)} KB (${nT} trees, ${nB} bushes)`);
}

// ---------------------------------------------------------------------------
// 11. Preview image (for humans): shaded relief + features
// ---------------------------------------------------------------------------
{
  const P = 1024;
  const img = new Uint8Array(P * P * 3);
  for (let v = 0; v < P; v++) for (let u = 0; u < P; u++) {
    const x = -HALF + (u + 0.5) * 2, z = -HALF + (v + 0.5) * 2;
    const h = sampleH(H, x, z);
    const hx = sampleH(H, x + 2, z) - sampleH(H, x - 2, z), hz = sampleH(H, x, z + 2) - sampleH(H, x, z - 2);
    const shade = clamp(0.75 - (hx * 0.6 + hz * 0.4) * 0.35, 0.3, 1.2);
    const o = (v * P + u) * 4;
    let r = 92, g = 128, b = 64;
    const sa = [splatA[o], splatA[o + 1], splatA[o + 2], splatA[o + 3]].map((q) => q / 255);
    const sb = [splatB[o], splatB[o + 1], splatB[o + 2], splatB[o + 3]].map((q) => q / 255);
    const mixc = (c, w) => { r = lerp(r, c[0], w); g = lerp(g, c[1], w); b = lerp(b, c[2], w); };
    mixc([130, 105, 75], sa[0]); mixc([120, 120, 118], sa[1]); mixc([190, 175, 130], sa[2]); mixc([80, 65, 50], sa[3]);
    mixc([105, 80, 60], sb[0]); mixc([200, 175, 90], sb[1]); mixc([50, 70, 40], sb[2]); mixc([150, 145, 135], sb[3]);
    if (h < L.WATER_LEVEL) { r = 50; g = 90; b = 120; }
    const q = (v * P + u) * 3;
    img[q] = clamp(r * shade, 0, 255); img[q + 1] = clamp(g * shade, 0, 255); img[q + 2] = clamp(b * shade, 0, 255);
  }
  const plot = (x, z, col, rad = 1) => {
    const u = Math.round((x + HALF) / 2), v = Math.round((z + HALF) / 2);
    for (let dv = -rad; dv <= rad; dv++) for (let du = -rad; du <= rad; du++) {
      const uu = u + du, vv = v + dv;
      if (uu < 0 || vv < 0 || uu >= P || vv >= P) continue;
      const q = (vv * P + uu) * 3;
      img[q] = col[0]; img[q + 1] = col[1]; img[q + 2] = col[2];
    }
  };
  for (const r of roads) for (const p of r.pts) plot(p[0], p[2], r.kind === 'dirt' ? [150, 120, 80] : [60, 60, 62], r.kind === 'highway' ? 2 : 1);
  for (const p of rail.pts) plot(p[0], p[2], [110, 80, 60], 1);
  for (let k = 0; k < trees.length; k += 5) plot(trees[k], trees[k + 1], [28, 52, 28], 0);
  for (const b of buildings) {
    for (let lz = -b.D / 2; lz <= b.D / 2; lz += 1.5) for (let lx = -b.W / 2; lx <= b.W / 2; lx += 1.5) {
      const [px, pz] = localToWorld(b.x, b.z, b.yaw, lx, lz);
      plot(px, pz, b.preDamage >= 3 ? [90, 70, 60] : [200, 190, 180], 0);
    }
  }
  for (const f of fences) for (let k = 0; k < f.pts.length - 1; k++) {
    const [ax, az] = f.pts[k], [bx, bz] = f.pts[k + 1];
    const n = Math.ceil(Math.hypot(bx - ax, bz - az) / 1.5);
    for (let s = 0; s <= n; s++) plot(lerp(ax, bx, s / n), lerp(az, bz, s / n), [230, 230, 230], 0);
  }
  for (const p of props) if (p.type !== 'power_line') plot(p.x, p.z, [255, 200, 0], 0);
  for (const br of bridges) plot(br.x, br.z, [255, 255, 255], 3);
  for (const vs of vehicleSlots) plot(vs.x, vs.z, vs.team === 1 ? [40, 110, 255] : vs.team === 2 ? [255, 50, 40] : [255, 255, 255], 1);
  for (const p of L.POINTS) {
    for (let a = 0; a < 360; a += 2) plot(p.x + Math.cos(a * Math.PI / 180) * p.radius, p.z + Math.sin(a * Math.PI / 180) * p.radius, [255, 255, 255], 0);
  }
  for (const h of L.HQS) for (let a = 0; a < 360; a += 2) plot(h.x + Math.cos(a * Math.PI / 180) * h.radius, h.z + Math.sin(a * Math.PI / 180) * h.radius, h.team === 1 ? [40, 110, 255] : [255, 50, 40], 1);
  // playable boundary
  for (let t = -720; t <= 720; t += 2) { plot(t, -720, [255, 0, 0], 0); plot(t, 720, [255, 0, 0], 0); plot(-720, t, [255, 0, 0], 0); plot(720, t, [255, 0, 0], 0); }
  fs.writeFileSync(path.join(OUT, 'preview.png'), encodePNG(P, P, img, 3));
}

console.log(`buildings: ${buildings.length}, props: ${props.length}, fences: ${fences.length}, trees: ${trees.length / 5}, bushes: ${bushes.length / 5}, bridges: ${bridges.length}, vehicle slots: ${vehicleSlots.length}`);
console.log(`height range ${hMin}..${hMax}, ford at ${fordPt}`);
console.timeEnd('total');
