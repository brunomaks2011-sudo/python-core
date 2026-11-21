--!strict
-- Team commander: reads the three-flag situation and the team timers and
-- assigns squads to capture or defend objectives. Re-plans every few seconds.
--
-- Priorities:
--   * never be left holding zero points (the team timer stops) - the nearest
--     neutral/enemy point becomes a top priority;
--   * defend owned points that are under threat (enemies nearby / contested),
--     especially if it is the only point held;
--   * push contested and neutral points; when losing on time, attack harder,
--     when winning, hold what we have.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Constants = require(ReplicatedStorage.Shared.Constants)
local SoldierRegistry = require(script.Parent.Parent.Game.SoldierRegistry)

local Commander = {}
Commander.__index = Commander

export type Order = { kind: string, point: string, pos: Vector3, radius: number }

function Commander.new(team: number)
	return setmetatable({ team = team, lastPlan = 0, plan = {} :: { [number]: Order } }, Commander)
end

local function threatNear(team: number, p: any): number
	local enemy = Constants.enemyOf(team)
	local n = 0
	for _, e in SoldierRegistry.alive(enemy) do
		local r = e.root
		if r then
			local dx, dz = r.Position.X - p.x, r.Position.Z - p.z
			if dx * dx + dz * dz < (p.radius * 2.6) ^ 2 then
				n += 1
			end
		end
	end
	return n
end

local function squadCentre(sq: any): Vector3?
	local sum, n = Vector3.zero, 0
	for _, id in sq.members do
		local s = SoldierRegistry.get(id)
		if s and s.alive and s.root then
			sum += s.root.Position
			n += 1
		end
	end
	return if n > 0 then sum / n else nil
end

-- squads: { {id, members, leader...} }, mode: DominationMode, hq: {x,z}
function Commander.plan(self: any, squads: { any }, mode: any, hq: { x: number, z: number })
	local team = self.team
	local enemy = Constants.enemyOf(team)
	local myTime, theirTime = mode.timers[team], mode.timers[enemy]
	local losing = myTime < theirTime - 200
	local winning = myTime > theirTime + 400
	local owned = mode:ownedCount(team)
	local objectives = {}
	for _, p in mode.points do
		local threat = threatNear(team, p)
		local score
		local kind
		if p.owner == team then
			kind = "defend"
			score = 0.6 + threat * 0.9 + (if p.contested then 2.5 else 0) + (if owned == 1 then 1.5 else 0) + (if winning then 0.8 else 0)
		else
			kind = "capture"
			score = 1.4 + (if p.owner == 0 then 0.6 else 0) + (if owned == 0 then 3.5 else 0) + (if losing then 1.0 else 0)
			-- contested points we are fighting for
			if p.contested or p.capturingTeam == team then
				score += 1.2
			end
		end
		table.insert(objectives, { point = p, kind = kind, score = score, assigned = 0, threat = threat })
	end
	-- greedy assignment: each squad takes the best objective accounting for
	-- distance and how many squads already go there
	local plan: { [number]: Order } = {}
	for _, sq in squads do
		local centre = squadCentre(sq) or Vector3.new(hq.x, 0, hq.z)
		local best, bestVal = nil, -math.huge
		for _, o in objectives do
			local d = (Vector3.new(o.point.x, 0, o.point.z) - Vector3.new(centre.X, 0, centre.Z)).Magnitude
			local need = if o.kind == "defend" then math.max(1, math.ceil(o.threat / 3)) else 2
			local crowd = math.max(0, o.assigned - need + 1) * 1.1
			local val = o.score - d / 1400 - crowd
			if val > bestVal then
				best, bestVal = o, val
			end
		end
		if best then
			best.assigned += 1
			plan[sq.id] = { kind = best.kind, point = best.point.id, pos = Vector3.new(best.point.x, best.point.y, best.point.z), radius = best.point.radius }
		end
	end
	self.plan = plan
	return plan
end

return Commander
