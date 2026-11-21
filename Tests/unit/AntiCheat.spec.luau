-- Server-authority rules: remote input validation, movement limits, rate of
-- fire, lag-compensated hit claims and team balance. Each "rejects" case is an
-- exploit a modified client could otherwise use.
local roblox = require("@lune/roblox")
local T = require("../TestLib")
local Shim = require("../RobloxShim")

local AntiCheat = Shim.load("Assets/Scripts/Shared/AntiCheat")
local Util = Shim.load("Assets/Scripts/Shared/Util")

local NAN = 0 / 0
local INF = math.huge
local Vector3 = roblox.Vector3
local V = Vector3.new

T.test("finiteNumber accepts ordinary numbers only", function()
	T.eq(Util.finiteNumber(3.5), 3.5)
	T.eq(Util.finiteNumber(-2), -2)
	T.eq(Util.finiteNumber(NAN), nil, "NaN")
	T.eq(Util.finiteNumber(INF), nil, "inf")
	T.eq(Util.finiteNumber(-INF), nil, "-inf")
	T.eq(Util.finiteNumber(1e9), nil, "absurdly large")
	T.eq(Util.finiteNumber("5"), nil, "string")
	T.eq(Util.finiteNumber(nil), nil, "nil")
end)

T.test("finiteVector rejects NaN / inf / huge vectors and non-vectors", function()
	T.truthy(Util.finiteVector(V(1, 2, 3)), "ordinary vector")
	T.eq(Util.finiteVector(V(NAN, 0, 0)), nil, "NaN x")
	T.eq(Util.finiteVector(V(0, NAN, 0)), nil, "NaN y")
	T.eq(Util.finiteVector(V(0, 0, INF)), nil, "inf z")
	T.eq(Util.finiteVector(V(2e6, 0, 0)), nil, "far outside any map")
	T.eq(Util.finiteVector(V(30, 40, 0), 10), nil, "longer than the allowed magnitude")
	T.truthy(Util.finiteVector(V(3, 4, 0), 10), "within the allowed magnitude")
	T.eq(Util.finiteVector({ X = 1, Y = 2, Z = 3 }), nil, "table posing as a vector")
	T.eq(Util.finiteVector(nil), nil, "nil")
end)

T.test("movement: sprinting, falling and jumping are legal", function()
	local from = V(0, 50, 0)
	-- 0.25 s at sprint speed (23 studs/s) with the guard's 31 studs/s limit
	T.truthy(AntiCheat.movementLegal(from, from + V(5.75, 0, 0), 0.25, 31, 45, 10), "sprint")
	T.truthy(AntiCheat.movementLegal(from, from + V(0, -40, 0), 0.25, 31, 45, 10), "falling off a roof")
	T.truthy(AntiCheat.movementLegal(from, from + V(3, 6, 3), 0.25, 31, 45, 10), "jump")
end)

T.test("movement: rejects teleports, speed hacks, flying and NaN", function()
	local from = V(0, 50, 0)
	T.eq(AntiCheat.movementLegal(from, from + V(400, 0, 0), 0.25, 31, 45, 10), false, "teleport into a capture zone")
	T.eq(AntiCheat.movementLegal(from, from + V(20, 0, 0), 0.25, 31, 45, 10), false, "3x sprint speed")
	T.eq(AntiCheat.movementLegal(from, from + V(0, 60, 0), 0.25, 31, 45, 10), false, "flying up")
	T.eq(AntiCheat.movementLegal(from, V(NAN, 0, 0), 0.25, 31, 45, 10), false, "NaN position")
	-- a longer gap between checks allows proportionally more distance
	T.truthy(AntiCheat.movementLegal(from, from + V(40, 0, 0), 1.5, 31, 45, 10), "server hitch: 1.5 s gap")
end)

T.test("rate of fire: a burst after idling is capped", function()
	-- rifle at 720 rpm: one shot per 1/12 s; bucket holds 3
	local interval = 60 / 720
	local tokens = AntiCheat.refillTokens(nil, 0, 100, interval, 3)
	T.eq(tokens, 3, "after a long pause only 3 shots are banked, not a whole magazine")
	tokens = AntiCheat.refillTokens(0, 100, 100 + interval * 0.5, interval, 3)
	T.near(tokens, 0.5, 1e-9, "half an interval refills half a shot")
end)

T.test("rate of fire: a sustained stream cannot beat the weapon's rpm", function()
	local interval = 60 / 720 -- 12 shots/s
	local tokens, last, fired = 3, 0, 0
	-- a cheater sends 3 shots every frame at 60 Hz for 2 seconds
	for frame = 1, 120 do
		local now = frame / 60
		tokens = AntiCheat.refillTokens(tokens, last, now, interval, 3)
		last = now
		for _ = 1, 3 do
			if tokens >= 1 then
				tokens -= 1
				fired += 1
			end
		end
	end
	-- 2 s at 12 shots/s = 24, plus the 3 banked at the start
	T.truthy(fired <= 27, "fired " .. fired .. " shots in 2 s")
	T.truthy(fired >= 24, "a legitimate full-auto stream is not throttled (" .. fired .. ")")
end)

T.test("hit claims: an honest lag-compensated hit is accepted", function()
	local origin = V(0, 5, 0)
	local dir = V(0, 0, -1)
	-- target 100 studs ahead, moved 3 studs sideways on the server since the shot
	T.truthy(AntiCheat.claimConsistent(origin, dir, V(0, 5, -100), V(3, 5, -100), 2.5, 16, 450, math.huge))
end)

T.test("hit claims: rejects silent aim and through-wall claims", function()
	local origin = V(0, 5, 0)
	local dir = V(0, 0, -1)
	-- shot fired forward, claims an enemy far off to the side (not on the ray)
	T.eq(AntiCheat.claimConsistent(origin, dir, V(300, 5, -50), V(300, 5, -50), 2.5, 0, 450, math.huge), false, "point off the fired ray")
	-- the point is on the ray, but the claimed part is somewhere else entirely
	T.eq(AntiCheat.claimConsistent(origin, dir, V(0, 5, -100), V(250, 5, -400), 2.5, 0, 450, math.huge), false, "part not at the claimed point")
	-- server ray hit a wall 30 studs away; the claim is 100 studs away behind it
	T.eq(AntiCheat.claimConsistent(origin, dir, V(0, 5, -100), V(0, 5, -100), 2.5, 0, 450, 30), false, "behind the wall the server ray hit")
	-- behind the shooter
	T.eq(AntiCheat.claimConsistent(origin, dir, V(0, 5, 20), V(0, 5, 20), 2.5, 0, 450, math.huge), false, "behind the muzzle")
	-- beyond the weapon's range
	T.eq(AntiCheat.claimConsistent(origin, dir, V(0, 5, -900), V(0, 5, -900), 2.5, 0, 450, math.huge), false, "out of range")
	-- degenerate direction
	T.eq(AntiCheat.claimConsistent(origin, V(0, 0, 0), V(0, 5, -10), V(0, 5, -10), 2.5, 0, 450, math.huge), false, "zero direction")
end)

T.test("team balance: friends may group up, stacking is refused", function()
	T.truthy(AntiCheat.teamOpen(0, 0), "first player")
	T.truthy(AntiCheat.teamOpen(1, 0), "second player joins the same team")
	T.eq(AntiCheat.teamOpen(2, 0), false, "third player on the bigger side")
	T.truthy(AntiCheat.teamOpen(5, 4), "nearly even")
	T.eq(AntiCheat.teamOpen(6, 4), false, "two ahead")
end)
