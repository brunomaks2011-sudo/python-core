// Lightweight math helpers that work identically in Node and the browser.

export const DEG = Math.PI / 180;
export const TAU = Math.PI * 2;

export const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
export const lerp = (a, b, t) => a + (b - a) * t;
export const invLerp = (a, b, v) => (b === a ? 0 : (v - a) / (b - a));
export const smoothstep = (a, b, v) => {
  const t = clamp((v - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};
export const sq = (x) => x * x;

export function wrapAngle(a) {
  a = (a + Math.PI) % TAU;
  if (a < 0) a += TAU;
  return a - Math.PI;
}

export function angleDiff(a, b) {
  return wrapAngle(b - a);
}

export function approachAngle(current, target, maxStep) {
  const d = angleDiff(current, target);
  if (Math.abs(d) <= maxStep) return target;
  return wrapAngle(current + Math.sign(d) * maxStep);
}

export function approach(current, target, maxStep) {
  if (current < target) return Math.min(current + maxStep, target);
  return Math.max(current - maxStep, target);
}

export function dist2D(ax, az, bx, bz) {
  const dx = ax - bx, dz = az - bz;
  return Math.sqrt(dx * dx + dz * dz);
}

export function dist2DSq(ax, az, bx, bz) {
  const dx = ax - bx, dz = az - bz;
  return dx * dx + dz * dz;
}

export function dist3(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

// Yaw convention: yaw = 0 faces -Z (north); positive yaw turns toward -X (west),
// matching three.js rotation.y. forward = (-sin(yaw), 0, -cos(yaw)).
export function yawToDir(yaw) {
  return { x: -Math.sin(yaw), z: -Math.cos(yaw) };
}

export function dirToYaw(dx, dz) {
  return Math.atan2(-dx, -dz);
}

export function pointInPolygon(x, z, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], zi = poly[i][1];
    const xj = poly[j][0], zj = poly[j][1];
    if ((zi > z) !== (zj > z) && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}

// Distance from point to a polyline (array of [x,z]); returns {d, t, seg, px, pz}
export function distToPolyline(x, z, pts) {
  let best = { d: Infinity, seg: 0, t: 0, px: 0, pz: 0 };
  for (let i = 0; i < pts.length - 1; i++) {
    const ax = pts[i][0], az = pts[i][1], bx = pts[i + 1][0], bz = pts[i + 1][1];
    const abx = bx - ax, abz = bz - az;
    const len2 = abx * abx + abz * abz || 1e-9;
    let t = ((x - ax) * abx + (z - az) * abz) / len2;
    t = clamp(t, 0, 1);
    const px = ax + abx * t, pz = az + abz * t;
    const d = Math.hypot(x - px, z - pz);
    if (d < best.d) best = { d, seg: i, t, px, pz };
  }
  return best;
}

export function polylineLength(pts) {
  let L = 0;
  for (let i = 0; i < pts.length - 1; i++) L += Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]);
  return L;
}

// Resample polyline at a fixed spacing; returns [[x,z,yaw], ...]
export function resamplePolyline(pts, spacing) {
  const out = [];
  let carry = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const ax = pts[i][0], az = pts[i][1], bx = pts[i + 1][0], bz = pts[i + 1][1];
    const segLen = Math.hypot(bx - ax, bz - az);
    const yaw = dirToYaw(bx - ax, bz - az);
    let s = carry;
    while (s <= segLen) {
      const t = s / segLen;
      out.push([ax + (bx - ax) * t, az + (bz - az) * t, yaw]);
      s += spacing;
    }
    carry = s - segLen;
  }
  return out;
}

// Catmull-Rom smoothing of a control polyline into a dense polyline.
export function smoothPolyline(ctrl, samplesPerSeg = 8) {
  if (ctrl.length < 3) return ctrl.map((p) => [p[0], p[1]]);
  const out = [];
  const P = (i) => ctrl[clamp(i, 0, ctrl.length - 1)];
  for (let i = 0; i < ctrl.length - 1; i++) {
    const p0 = P(i - 1), p1 = P(i), p2 = P(i + 1), p3 = P(i + 2);
    for (let s = 0; s < samplesPerSeg; s++) {
      const t = s / samplesPerSeg, t2 = t * t, t3 = t2 * t;
      const f = (a, b, c, d) => 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
      out.push([f(p0[0], p1[0], p2[0], p3[0]), f(p0[1], p1[1], p2[1], p3[1])]);
    }
  }
  const last = ctrl[ctrl.length - 1];
  out.push([last[0], last[1]]);
  return out;
}
