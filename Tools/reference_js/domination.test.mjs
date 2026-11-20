import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DominationMode } from '../../Assets/Scripts/Domination/DominationMode.js';
import { TEAM, TICK_RATE, MATCH_STATE } from '../../Assets/Scripts/Core/Constants.js';

const POINTS = [
  { id: 'A', name: 'Industrial', x: -430, z: -60, radius: 38 },
  { id: 'B', name: 'Village', x: 0, z: 40, radius: 34 },
  { id: 'C', name: 'Base', x: 455, z: 0, radius: 38 },
];

// occupancy table: { A: {1:[ids],2:[ids]}, ... }
function runTicks(mode, occ, ticks) {
  for (let i = 0; i < ticks; i++) mode.tick((p) => occ[p.id] || { 1: [], 2: [] });
}
const secs = (s) => Math.round(s * TICK_RATE);

test('BLUE captures neutral point A in exactly 30 seconds with one soldier', () => {
  const m = new DominationMode(POINTS);
  const occ = { A: { 1: ['b1'], 2: [] } };
  runTicks(m, occ, secs(30) - 1);
  assert.equal(m.pointById('A').owner, TEAM.NONE, 'not yet captured one tick early');
  assert.equal(m.pointById('A').capturingTeam, TEAM.BLUE);
  runTicks(m, occ, 1);
  assert.equal(m.pointById('A').owner, TEAM.BLUE);
  const ev = m.drainEvents().filter((e) => e.type === 'captured');
  assert.equal(ev.length, 1);
  assert.equal(ev[0].point, 'A');
  assert.deepEqual(ev[0].soldiers, ['b1']);
});

test('RED captures point B', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { B: { 1: [], 2: ['r1'] } }, secs(30));
  assert.equal(m.pointById('B').owner, TEAM.RED);
  assert.equal(m.pointById('B').progressFloat, -1);
});

test('both teams inside C -> contested, no progress, no time earned', () => {
  const m = new DominationMode(POINTS);
  // RED owns C first
  runTicks(m, { C: { 1: [], 2: ['r1'] } }, secs(30));
  assert.equal(m.pointById('C').owner, TEAM.RED);
  const redBefore = m.timers[TEAM.RED];
  const progBefore = m.pointById('C').progress;
  runTicks(m, { C: { 1: ['b1', 'b2'], 2: ['r1'] } }, secs(20));
  const c = m.pointById('C');
  assert.equal(c.contested, true);
  assert.equal(c.progress, progBefore, 'contested point does not move');
  assert.equal(m.timers[TEAM.RED], redBefore, 'contested point gives no time');
  assert.ok(m.drainEvents().some((e) => e.type === 'contested' && e.point === 'C'));
  // RED leaves: BLUE starts neutralising
  runTicks(m, { C: { 1: ['b1'], 2: [] } }, 1);
  assert.equal(c.contested, false);
  assert.equal(c.capturingTeam, TEAM.BLUE);
});

test('enemy point: neutralised after 30 s, captured after 60 s', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { A: { 1: [], 2: ['r1'] } }, secs(30));
  assert.equal(m.pointById('A').owner, TEAM.RED);
  runTicks(m, { A: { 1: ['b1'], 2: [] } }, secs(30) - 1);
  assert.equal(m.pointById('A').owner, TEAM.RED, 'still red one tick before neutral');
  runTicks(m, { A: { 1: ['b1'], 2: [] } }, 1);
  assert.equal(m.pointById('A').owner, TEAM.NONE, 'neutral at 30 s');
  runTicks(m, { A: { 1: ['b1'], 2: [] } }, secs(30));
  assert.equal(m.pointById('A').owner, TEAM.BLUE, 'blue at 60 s');
});

test('timer grows 1 s per second regardless of how many points are held', () => {
  for (const held of [1, 2, 3]) {
    const m = new DominationMode(POINTS);
    const ids = ['A', 'B', 'C'].slice(0, held);
    const occ = Object.fromEntries(ids.map((id) => [id, { 1: ['b'], 2: [] }]));
    runTicks(m, occ, secs(30)); // capture all simultaneously
    assert.equal(m.ownedCount(TEAM.BLUE), held);
    const start = m.timers[TEAM.BLUE];
    runTicks(m, {}, secs(100));
    assert.equal(m.timers[TEAM.BLUE] - start, secs(100), `held=${held}`);
  }
});

test('a team with no points stops; the enemy keeps accumulating', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { A: { 1: ['b'], 2: [] }, B: { 1: [], 2: ['r'] } }, secs(30));
  // a point starts earning on the tick it is captured
  assert.equal(m.timers[TEAM.BLUE], 1);
  assert.equal(m.timers[TEAM.RED], 1);
  runTicks(m, {}, secs(50));
  assert.equal(m.timers[TEAM.BLUE], 1 + secs(50));
  assert.equal(m.timers[TEAM.RED], 1 + secs(50));
  // RED takes A (neutralise 30 s + capture 30 s). BLUE keeps counting until A goes neutral.
  runTicks(m, { A: { 1: [], 2: ['r2'] } }, secs(60));
  assert.equal(m.ownedCount(TEAM.BLUE), 0);
  const blueStopped = m.timers[TEAM.BLUE];
  assert.equal(blueStopped, 1 + secs(50) + secs(30) - 1, 'blue counted while A was still blue');
  runTicks(m, {}, secs(40));
  assert.equal(m.timers[TEAM.BLUE], blueStopped, 'blue timer is stopped');
  assert.equal(m.timers[TEAM.RED], 1 + secs(50) + secs(60) + secs(40));
});

test('victory at exactly 1000 seconds, then the match ends', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { B: { 1: ['b'], 2: [] } }, secs(30));
  assert.equal(m.timers[TEAM.BLUE], 1, 'earning starts on the capture tick');
  runTicks(m, {}, secs(1000) - 2);
  assert.equal(m.state, MATCH_STATE.LIVE);
  assert.equal(m.secondsOf(TEAM.BLUE), 1000 - 1 / TICK_RATE);
  runTicks(m, {}, 1);
  assert.equal(m.state, MATCH_STATE.ENDED);
  assert.equal(m.winner, TEAM.BLUE);
  assert.equal(m.secondsOf(TEAM.BLUE), 1000);
  const ticksAtEnd = m.tickCount;
  runTicks(m, {}, 100);
  assert.equal(m.tickCount, ticksAtEnd, 'no ticks after the end');
  assert.equal(m.secondsOf(TEAM.BLUE), 1000, 'never exceeds 1000');
  const v = m.drainEvents().filter((e) => e.type === 'victory');
  assert.equal(v.length, 1);
});

test('both reaching 1000 on the same tick: more points wins; full tie -> sudden death', () => {
  const m = new DominationMode(POINTS);
  m.timers[TEAM.BLUE] = m.victoryTicks - 1;
  m.timers[TEAM.RED] = m.victoryTicks - 1;
  m.points[0].owner = TEAM.BLUE; m.points[0].progress = m.progressMax;
  m.points[1].owner = TEAM.BLUE; m.points[1].progress = m.progressMax;
  m.points[2].owner = TEAM.RED; m.points[2].progress = -m.progressMax;
  runTicks(m, {}, 1);
  assert.equal(m.state, MATCH_STATE.ENDED);
  assert.equal(m.winner, TEAM.BLUE);
  assert.equal(m.timers[TEAM.RED], m.victoryTicks - 1, 'loser never reaches 1000');

  const t = new DominationMode(POINTS);
  t.timers[TEAM.BLUE] = t.victoryTicks - 1;
  t.timers[TEAM.RED] = t.victoryTicks - 1;
  t.points[0].owner = TEAM.BLUE; t.points[0].progress = t.progressMax;
  t.points[2].owner = TEAM.RED; t.points[2].progress = -t.progressMax;
  runTicks(t, {}, 10);
  assert.equal(t.state, MATCH_STATE.LIVE);
  assert.equal(t.suddenDeath, true);
  assert.equal(t.timers[TEAM.BLUE], t.victoryTicks - 1);
  assert.equal(t.timers[TEAM.RED], t.victoryTicks - 1);
  // RED captures neutral B -> 2 vs 1 -> RED wins
  runTicks(t, { B: { 1: [], 2: ['r'] } }, secs(30));
  assert.equal(t.state, MATCH_STATE.ENDED);
  assert.equal(t.winner, TEAM.RED);
  assert.equal(t.timers[TEAM.BLUE], t.victoryTicks - 1);
});

test('a contested point that is the only holding earns nothing', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { A: { 1: ['b'], 2: [] } }, secs(30));
  assert.equal(m.timers[TEAM.BLUE], 1);
  runTicks(m, { A: { 1: ['b'], 2: ['r'] } }, secs(10));
  assert.equal(m.timers[TEAM.BLUE], 1, 'no time while contested');
});

test('nobody inside: partial progress drifts back', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { B: { 1: ['b'], 2: [] } }, secs(15));
  assert.ok(Math.abs(m.pointById('B').progressFloat - 0.5) < 1e-6);
  runTicks(m, {}, secs(60));
  assert.equal(m.pointById('B').progress, 0);
});

test('more soldiers capture faster, capped', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { A: { 1: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'], 2: [] } }, secs(30 / 1.8) + 1);
  assert.equal(m.pointById('A').owner, TEAM.BLUE);
  const m2 = new DominationMode(POINTS);
  runTicks(m2, { A: { 1: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'], 2: [] } }, secs(30 / 1.8) - 2);
  assert.equal(m2.pointById('A').owner, TEAM.NONE, 'cap is 1.8x');
});

test('reset restores a fresh match', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { A: { 1: ['b'], 2: [] } }, secs(200));
  m.reset();
  assert.equal(m.state, MATCH_STATE.LIVE);
  assert.equal(m.timers[TEAM.BLUE], 0);
  assert.equal(m.timers[TEAM.RED], 0);
  for (const p of m.points) {
    assert.equal(p.owner, TEAM.NONE);
    assert.equal(p.progress, 0);
  }
  assert.equal(m.tickCount, 0);
});

test('serialize exposes timers, owners, capture progress and contested state', () => {
  const m = new DominationMode(POINTS);
  runTicks(m, { A: { 1: ['b'], 2: [] }, C: { 1: ['b2'], 2: ['r'] } }, secs(10));
  const s = m.serialize();
  assert.equal(s.points.length, 3);
  assert.equal(s.points[0].capturing, TEAM.BLUE);
  assert.ok(s.points[0].progress > 0.33 && s.points[0].progress < 0.34);
  assert.equal(s.points[2].contested, true);
  assert.equal(s.timers[1], 0);
  assert.equal(s.victoryTicks, 1000 * TICK_RATE);
});
