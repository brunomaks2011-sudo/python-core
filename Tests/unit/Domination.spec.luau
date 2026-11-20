-- Unit tests for the Three Flags Domination rules (runs under Lune).
local T = require("../TestLib")
local DominationMode = require("../../Assets/Scripts/Shared/DominationMode")

local BLUE, RED, NONE = 1, 2, 0
local RATE = 10 -- match ticks per second

local POINTS = {
	{ id = "A", name = "Industrial", x = -1290, z = -186, radius = 114 },
	{ id = "B", name = "Village", x = 0, z = 120, radius = 102 },
	{ id = "C", name = "Base", x = 1365, z = 0, radius = 114 },
}

local function secs(s: number): number
	return math.floor(s * RATE + 0.5)
end

local function run(m, occ: { [string]: { [number]: { string } } }, ticks: number)
	for _ = 1, ticks do
		m:tick(function(p)
			return occ[p.id] or { [BLUE] = {}, [RED] = {} }
		end)
	end
end

local function new()
	return DominationMode.new(POINTS, { TICK_RATE = RATE })
end

T.test("BLUE captures neutral point A in exactly 30 s with one soldier", function()
	local m = new()
	local occ = { A = { [BLUE] = { "b1" }, [RED] = {} } }
	run(m, occ, secs(30) - 1)
	T.eq(m:pointById("A").owner, NONE, "one tick early")
	T.eq(m:pointById("A").capturingTeam, BLUE)
	run(m, occ, 1)
	T.eq(m:pointById("A").owner, BLUE)
	local captured = 0
	for _, e in m:drainEvents() do
		if e.type == "captured" then
			captured += 1
			T.eq(e.point, "A")
			T.eq(e.soldiers[1], "b1")
		end
	end
	T.eq(captured, 1)
end)

T.test("RED captures point B", function()
	local m = new()
	run(m, { B = { [BLUE] = {}, [RED] = { "r1" } } }, secs(30))
	T.eq(m:pointById("B").owner, RED)
	T.eq(m:pointById("B").progress, -m.progressMax)
end)

T.test("both teams inside C: contested, frozen, no time earned", function()
	local m = new()
	run(m, { C = { [BLUE] = {}, [RED] = { "r1" } } }, secs(30))
	T.eq(m:pointById("C").owner, RED)
	local redBefore = m.timers[RED]
	local progBefore = m:pointById("C").progress
	run(m, { C = { [BLUE] = { "b1", "b2" }, [RED] = { "r1" } } }, secs(20))
	local c = m:pointById("C")
	T.eq(c.contested, true)
	T.eq(c.progress, progBefore, "contested point does not move")
	T.eq(m.timers[RED], redBefore, "contested point earns nothing")
	local sawContested = false
	for _, e in m:drainEvents() do
		if e.type == "contested" and e.point == "C" then
			sawContested = true
		end
	end
	T.truthy(sawContested, "contested event")
	run(m, { C = { [BLUE] = { "b1" }, [RED] = {} } }, 1)
	T.eq(c.contested, false)
	T.eq(c.capturingTeam, BLUE)
end)

T.test("enemy point: neutralised after 30 s, captured after 60 s", function()
	local m = new()
	run(m, { A = { [BLUE] = {}, [RED] = { "r" } } }, secs(30))
	T.eq(m:pointById("A").owner, RED)
	run(m, { A = { [BLUE] = { "b" }, [RED] = {} } }, secs(30) - 1)
	T.eq(m:pointById("A").owner, RED, "still red just before neutral")
	run(m, { A = { [BLUE] = { "b" }, [RED] = {} } }, 1)
	T.eq(m:pointById("A").owner, NONE, "neutral at 30 s")
	run(m, { A = { [BLUE] = { "b" }, [RED] = {} } }, secs(30))
	T.eq(m:pointById("A").owner, BLUE, "blue at 60 s")
end)

T.test("timer grows 1 s per second whether 1, 2 or 3 points are held", function()
	for held = 1, 3 do
		local m = new()
		local occ = {}
		for i = 1, held do
			occ[POINTS[i].id] = { [BLUE] = { "b" }, [RED] = {} }
		end
		run(m, occ, secs(30))
		T.eq(m:ownedCount(BLUE), held)
		local start = m.timers[BLUE]
		run(m, {}, secs(100))
		T.eq(m.timers[BLUE] - start, secs(100), "held=" .. held)
	end
end)

T.test("a team with no points stops while the enemy keeps accumulating", function()
	local m = new()
	run(m, { A = { [BLUE] = { "b" }, [RED] = {} }, B = { [BLUE] = {}, [RED] = { "r" } } }, secs(30))
	T.eq(m.timers[BLUE], 1, "earning starts on the capture tick")
	T.eq(m.timers[RED], 1)
	run(m, {}, secs(50))
	run(m, { A = { [BLUE] = {}, [RED] = { "r2" } } }, secs(60))
	T.eq(m:ownedCount(BLUE), 0)
	local stopped = m.timers[BLUE]
	T.eq(stopped, 1 + secs(50) + secs(30) - 1, "blue counted until A went neutral")
	run(m, {}, secs(40))
	T.eq(m.timers[BLUE], stopped, "blue timer stopped")
	T.eq(m.timers[RED], 1 + secs(50) + secs(60) + secs(40))
end)

T.test("victory at exactly 1000 s, then the match ends", function()
	local m = new()
	run(m, { B = { [BLUE] = { "b" }, [RED] = {} } }, secs(30))
	run(m, {}, secs(1000) - 2)
	T.eq(m.state, "live")
	T.near(m:secondsOf(BLUE), 1000 - 1 / RATE, 1e-9)
	run(m, {}, 1)
	T.eq(m.state, "ended")
	T.eq(m.winner, BLUE)
	T.eq(m:secondsOf(BLUE), 1000)
	local ticks = m.tickCount
	run(m, {}, 100)
	T.eq(m.tickCount, ticks, "no ticks after the end")
	T.eq(m:secondsOf(BLUE), 1000, "never exceeds 1000")
end)

T.test("both reach 1000 on the same tick: more points wins; tie -> sudden death", function()
	local m = new()
	m.timers[BLUE] = m.victoryTicks - 1
	m.timers[RED] = m.victoryTicks - 1
	m.points[1].owner, m.points[1].progress = BLUE, m.progressMax
	m.points[2].owner, m.points[2].progress = BLUE, m.progressMax
	m.points[3].owner, m.points[3].progress = RED, -m.progressMax
	run(m, {}, 1)
	T.eq(m.state, "ended")
	T.eq(m.winner, BLUE)
	T.eq(m.timers[RED], m.victoryTicks - 1, "loser never reaches 1000")

	local t = new()
	t.timers[BLUE] = t.victoryTicks - 1
	t.timers[RED] = t.victoryTicks - 1
	t.points[1].owner, t.points[1].progress = BLUE, t.progressMax
	t.points[3].owner, t.points[3].progress = RED, -t.progressMax
	run(t, {}, 10)
	T.eq(t.state, "live")
	T.eq(t.suddenDeath, true)
	T.eq(t.timers[BLUE], t.victoryTicks - 1)
	run(t, { B = { [BLUE] = {}, [RED] = { "r" } } }, secs(30))
	T.eq(t.state, "ended")
	T.eq(t.winner, RED)
end)

T.test("a contested point that is a team's only holding earns nothing", function()
	local m = new()
	run(m, { A = { [BLUE] = { "b" }, [RED] = {} } }, secs(30))
	T.eq(m.timers[BLUE], 1)
	run(m, { A = { [BLUE] = { "b" }, [RED] = { "r" } } }, secs(10))
	T.eq(m.timers[BLUE], 1)
end)

T.test("nobody inside: partial progress drifts back to neutral", function()
	local m = new()
	run(m, { B = { [BLUE] = { "b" }, [RED] = {} } }, secs(15))
	T.near(m:pointById("B").progress / m.progressMax, 0.5, 1e-9)
	run(m, {}, secs(60))
	T.eq(m:pointById("B").progress, 0)
end)

T.test("more soldiers capture faster, capped at 1.8x", function()
	local squad = { "a", "b", "c", "d", "e", "f", "g", "h" }
	local m = new()
	run(m, { A = { [BLUE] = squad, [RED] = {} } }, math.ceil(secs(30) / 1.8))
	T.eq(m:pointById("A").owner, BLUE)
	local m2 = new()
	run(m2, { A = { [BLUE] = squad, [RED] = {} } }, math.ceil(secs(30) / 1.8) - 2)
	T.eq(m2:pointById("A").owner, NONE)
end)

T.test("reset restores a fresh match", function()
	local m = new()
	run(m, { A = { [BLUE] = { "b" }, [RED] = {} } }, secs(200))
	m:reset()
	T.eq(m.state, "live")
	T.eq(m.timers[BLUE], 0)
	T.eq(m.timers[RED], 0)
	T.eq(m.tickCount, 0)
	for _, p in m.points do
		T.eq(p.owner, NONE)
		T.eq(p.progress, 0)
	end
end)

T.test("serialize exposes timers, owners, progress and contested state", function()
	local m = new()
	run(m, { A = { [BLUE] = { "b" }, [RED] = {} }, C = { [BLUE] = { "b2" }, [RED] = { "r" } } }, secs(10))
	local s = m:serialize()
	T.eq(#s.points, 3)
	T.eq(s.points[1].capturing, BLUE)
	T.truthy(s.points[1].progress > 0.33 and s.points[1].progress < 0.34)
	T.eq(s.points[3].contested, true)
	T.eq(s.blueTicks, 0)
	T.eq(s.victoryTicks, 1000 * RATE)
end)

T.test("full 1000 s match from neutral, played tick by tick", function()
	local m = new()
	-- Blue takes A and B, Red takes C; then Red pushes Blue off B and A.
	run(m, { A = { [BLUE] = { "b1" }, [RED] = {} }, B = { [BLUE] = { "b2" }, [RED] = {} }, C = { [BLUE] = {}, [RED] = { "r1" } } }, secs(30))
	run(m, {}, secs(300))
	run(m, { B = { [BLUE] = {}, [RED] = { "r2", "r3" } } }, secs(60))
	run(m, { A = { [BLUE] = {}, [RED] = { "r4" } } }, secs(60))
	T.eq(m:ownedCount(RED), 3)
	local guard = 0
	while m.state == "live" and guard < secs(2000) do
		run(m, {}, 1)
		guard += 1
	end
	T.eq(m.state, "ended")
	T.eq(m.winner, RED)
	T.eq(m:secondsOf(RED), 1000)
	T.truthy(m:secondsOf(BLUE) < 1000)
	local sum = m:summary()
	T.eq(sum.finalPointsHeld[RED], 3)
	T.truthy(sum.stats.points.B.captures[RED] == 1)
end)

return nil
