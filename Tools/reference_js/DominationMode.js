// THREE FLAGS - DOMINATION
//
// Authoritative rules (runs only on the server / listen server):
//  * Three control points A, B, C. A point changes toward a team while only
//    that team has soldiers inside its zone. Both teams inside = CONTESTED
//    (frozen, and it earns nobody time).
//  * Taking a NEUTRAL point takes CAPTURE_SECONDS (30 s) with one soldier.
//    An enemy point is first neutralized (30 s), then captured (30 s).
//    More soldiers speed this up slightly (capped).
//  * Each team has a control timer. Every second a team holds at least one
//    uncontested point, its timer grows by exactly one second, no matter if it
//    holds one, two or three points.
//  * The first team to reach exactly VICTORY_SECONDS wins. If both teams would
//    reach it on the same tick, the team holding more points wins; on a full
//    tie neither advances (sudden death) until the tie is broken.
//
// Everything is integer-tick based so results are exact and deterministic.
import { TEAM, TICK_RATE, DOMINATION, MATCH_STATE, enemyOf } from '../Core/Constants.js';

export class ControlPoint {
  constructor(def, progressMax) {
    this.id = def.id;
    this.name = def.name;
    this.x = def.x;
    this.y = def.y ?? 0;
    this.z = def.z;
    this.radius = def.radius;
    this.progressMax = progressMax;
    this.reset();
  }

  reset() {
    this.owner = TEAM.NONE;
    this.progress = 0; // integer, +progressMax = BLUE, -progressMax = RED
    this.contested = false;
    this.capturingTeam = TEAM.NONE;
    this.counts = { 1: 0, 2: 0 };
    this.occupants = { 1: [], 2: [] };
    this.lastChangeTick = 0;
  }

  get progressFloat() {
    return this.progress / this.progressMax;
  }

  contains(x, y, z, zoneHeight = DOMINATION.ZONE_HEIGHT) {
    const dx = x - this.x, dz = z - this.z;
    if (dx * dx + dz * dz > this.radius * this.radius) return false;
    return y > this.y - 6 && y < this.y + zoneHeight;
  }
}

export class DominationMode {
  constructor(pointDefs, options = {}) {
    this.cfg = { ...DOMINATION, ...options };
    this.tickRate = options.tickRate ?? TICK_RATE;
    this.victoryTicks = Math.round(this.cfg.VICTORY_SECONDS * this.tickRate);
    // progress units: one soldier advances 100 units per tick
    this.progressMax = Math.round(this.cfg.CAPTURE_SECONDS * this.tickRate * 100);
    this.regenPerTick = Math.max(1, Math.round(this.progressMax / (this.cfg.REGEN_SECONDS * this.tickRate)));
    this.points = pointDefs.map((p) => new ControlPoint(p, this.progressMax));
    this.events = [];
    this.reset();
  }

  reset() {
    for (const p of this.points) p.reset();
    this.timers = { [TEAM.BLUE]: 0, [TEAM.RED]: 0 };
    this.state = MATCH_STATE.LIVE;
    this.winner = TEAM.NONE;
    this.suddenDeath = false;
    this.tickCount = 0;
    this.endTick = 0;
    this.events.length = 0;
    this.stats = {
      points: Object.fromEntries(this.points.map((p) => [p.id, {
        heldTicks: { [TEAM.BLUE]: 0, [TEAM.RED]: 0 },
        contestedTicks: 0,
        captures: { [TEAM.BLUE]: 0, [TEAM.RED]: 0 },
        neutralizations: { [TEAM.BLUE]: 0, [TEAM.RED]: 0 },
      }])),
      maxHeld: { [TEAM.BLUE]: 0, [TEAM.RED]: 0 },
      allThreeTicks: { [TEAM.BLUE]: 0, [TEAM.RED]: 0 },
      noPointTicks: { [TEAM.BLUE]: 0, [TEAM.RED]: 0 },
      leadChanges: 0,
    };
    this._leader = TEAM.NONE;
  }

  get victoryTicksPerTeam() {
    return this.victoryTicks;
  }

  secondsOf(team) {
    return this.timers[team] / this.tickRate;
  }

  pointById(id) {
    return this.points.find((p) => p.id === id);
  }

  ownedCount(team, uncontestedOnly = false) {
    let n = 0;
    for (const p of this.points) if (p.owner === team && (!uncontestedOnly || !p.contested)) n++;
    return n;
  }

  _emit(type, data) {
    this.events.push({ type, tick: this.tickCount, ...data });
  }

  _captureRate(n) {
    const mult = Math.min(1 + this.cfg.CAPTURE_BONUS_PER_SOLDIER * (n - 1), this.cfg.CAPTURE_MAX_MULTIPLIER);
    return Math.round(100 * mult);
  }

  // occupancy(point) must return { 1: [soldierIds...], 2: [soldierIds...] }
  tick(occupancy) {
    if (this.state !== MATCH_STATE.LIVE) return;
    this.tickCount++;

    for (const p of this.points) this._updatePoint(p, occupancy(p));

    // --- team timers ---------------------------------------------------------
    const held = { [TEAM.BLUE]: this.ownedCount(TEAM.BLUE, true), [TEAM.RED]: this.ownedCount(TEAM.RED, true) };
    for (const team of [TEAM.BLUE, TEAM.RED]) {
      const owned = this.ownedCount(team);
      if (owned > this.stats.maxHeld[team]) this.stats.maxHeld[team] = owned;
      if (owned === 3) this.stats.allThreeTicks[team]++;
      if (owned === 0) this.stats.noPointTicks[team]++;
    }
    for (const p of this.points) {
      const st = this.stats.points[p.id];
      if (p.contested) st.contestedTicks++;
      else if (p.owner !== TEAM.NONE) st.heldTicks[p.owner]++;
    }

    const wants = { [TEAM.BLUE]: held[TEAM.BLUE] > 0, [TEAM.RED]: held[TEAM.RED] > 0 };
    const reach = (t) => wants[t] && this.timers[t] + 1 >= this.victoryTicks;
    if (reach(TEAM.BLUE) && reach(TEAM.RED)) {
      // Both would hit 1000 s on this very tick: never let both win.
      if (held[TEAM.BLUE] !== held[TEAM.RED]) {
        const w = held[TEAM.BLUE] > held[TEAM.RED] ? TEAM.BLUE : TEAM.RED;
        this.timers[w] = this.victoryTicks;
        this.suddenDeath = false;
        this._finish(w, 'more points held at the deciding moment');
      } else if (!this.suddenDeath) {
        this.suddenDeath = true;
        this._emit('suddenDeath', {});
      }
      return;
    }
    if (this.suddenDeath && !wants[TEAM.BLUE] && !wants[TEAM.RED]) return;
    for (const t of [TEAM.BLUE, TEAM.RED]) {
      if (!wants[t]) continue;
      this.timers[t] = Math.min(this.victoryTicks, this.timers[t] + 1);
    }
    // lead tracking
    const lead = this.timers[TEAM.BLUE] === this.timers[TEAM.RED] ? TEAM.NONE : this.timers[TEAM.BLUE] > this.timers[TEAM.RED] ? TEAM.BLUE : TEAM.RED;
    if (lead !== TEAM.NONE && lead !== this._leader) {
      if (this._leader !== TEAM.NONE) this.stats.leadChanges++;
      this._leader = lead;
    }
    for (const t of [TEAM.BLUE, TEAM.RED]) {
      if (this.timers[t] >= this.victoryTicks) {
        this._finish(t, this.suddenDeath ? 'sudden death' : 'reached 1000 seconds');
        return;
      }
    }
  }

  _finish(team, reason) {
    this.state = MATCH_STATE.ENDED;
    this.winner = team;
    this.endTick = this.tickCount;
    this._emit('victory', { team, reason, timers: { ...this.timers } });
  }

  _updatePoint(p, occ) {
    const blue = occ[TEAM.BLUE] || [], red = occ[TEAM.RED] || [];
    p.occupants = { [TEAM.BLUE]: blue, [TEAM.RED]: red };
    p.counts = { [TEAM.BLUE]: blue.length, [TEAM.RED]: red.length };
    const nb = blue.length, nr = red.length;
    const wasContested = p.contested;
    p.contested = nb > 0 && nr > 0;
    if (p.contested) {
      p.capturingTeam = TEAM.NONE;
      if (!wasContested) this._emit('contested', { point: p.id, owner: p.owner });
      return;
    }
    if (wasContested) this._emit('uncontested', { point: p.id, owner: p.owner });

    if (nb === 0 && nr === 0) {
      p.capturingTeam = TEAM.NONE;
      // drift back toward the owner (or neutral)
      const target = p.owner === TEAM.BLUE ? this.progressMax : p.owner === TEAM.RED ? -this.progressMax : 0;
      if (p.progress < target) p.progress = Math.min(target, p.progress + this.regenPerTick);
      else if (p.progress > target) p.progress = Math.max(target, p.progress - this.regenPerTick);
      return;
    }

    const team = nb > 0 ? TEAM.BLUE : TEAM.RED;
    const occupants = team === TEAM.BLUE ? blue : red;
    const dir = team === TEAM.BLUE ? 1 : -1;
    const full = dir * this.progressMax;
    if (p.progress === full) {
      p.capturingTeam = TEAM.NONE; // fully held: defending
      return;
    }
    p.capturingTeam = team;
    const before = p.progress;
    p.progress += dir * this._captureRate(occupants.length);
    if (dir > 0 && p.progress > this.progressMax) p.progress = this.progressMax;
    if (dir < 0 && p.progress < -this.progressMax) p.progress = -this.progressMax;

    const enemy = enemyOf(team);
    // crossing the neutral line removes the enemy's ownership
    const crossed = Math.sign(p.progress) !== Math.sign(before) || p.progress === 0;
    if (p.owner === enemy && crossed) {
      p.owner = TEAM.NONE;
      p.lastChangeTick = this.tickCount;
      this.stats.points[p.id].neutralizations[team]++;
      this._emit('neutralized', { point: p.id, by: team, from: enemy, soldiers: [...occupants] });
    }
    if (p.owner === TEAM.NONE && p.progress === full) {
      p.owner = team;
      p.lastChangeTick = this.tickCount;
      this.stats.points[p.id].captures[team]++;
      this._emit('captured', { point: p.id, team, soldiers: [...occupants] });
    }
  }

  drainEvents() {
    const e = this.events.slice();
    this.events.length = 0;
    return e;
  }

  // Compact state for HUD / network snapshots (read-only view for clients).
  serialize() {
    return {
      state: this.state,
      winner: this.winner,
      suddenDeath: this.suddenDeath,
      tick: this.tickCount,
      tickRate: this.tickRate,
      victoryTicks: this.victoryTicks,
      timers: { 1: this.timers[TEAM.BLUE], 2: this.timers[TEAM.RED] },
      points: this.points.map((p) => ({
        id: p.id,
        owner: p.owner,
        progress: p.progress / this.progressMax,
        contested: p.contested,
        capturing: p.capturingTeam,
        counts: { 1: p.counts[TEAM.BLUE], 2: p.counts[TEAM.RED] },
      })),
    };
  }

  summary() {
    return {
      winner: this.winner,
      durationSeconds: this.tickCount / this.tickRate,
      timersSeconds: { 1: this.timers[TEAM.BLUE] / this.tickRate, 2: this.timers[TEAM.RED] / this.tickRate },
      finalPointsHeld: { 1: this.ownedCount(TEAM.BLUE), 2: this.ownedCount(TEAM.RED) },
      finalOwners: Object.fromEntries(this.points.map((p) => [p.id, p.owner])),
      stats: JSON.parse(JSON.stringify(this.stats)),
    };
  }
}
