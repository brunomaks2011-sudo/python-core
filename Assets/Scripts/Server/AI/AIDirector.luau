--!strict
-- Fills both armies with AI soldiers, organises them into squads, runs the
-- team commanders, respawns bots and puts crews into vehicles.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Util = require(ReplicatedStorage.Shared.Util)
local SoldierRegistry = require(script.Parent.Parent.Game.SoldierRegistry)
local SpawnService = require(script.Parent.Parent.Game.SpawnService)
local MatchService = require(script.Parent.Parent.Game.MatchService)
local VehicleService = require(script.Parent.Parent.Game.VehicleService)
local BotBrain = require(script.Parent.BotBrain)
local Commander = require(script.Parent.Commander)
local VehicleDriver = require(script.Parent.VehicleDriver)

type Soldier = SoldierRegistry.Soldier

local AIDirector = {}

AIDirector.botsPerTeam = Constants.BOTS_PER_TEAM_DEFAULT
AIDirector.enabled = true

type Squad = { id: number, team: number, members: { number }, order: any, vehicleId: number?, armor: boolean }

local squads: { [number]: { Squad } } = { [1] = {}, [2] = {} }
local commanders = { [1] = Commander.new(1), [2] = Commander.new(2) }
local drivers: { [number]: any } = {}
local nextSquad = 0
local rng = Random.new(20261120)

local ROLE_WEIGHTS = { { role = "rifleman", w = 34 }, { role = "medic", w = 14 }, { role = "engineer", w = 18 }, { role = "support", w = 14 }, { role = "recon", w = 10 }, { role = "crew", w = 10 } }

local function pickRole(): string
	local total = 0
	for _, r in ROLE_WEIGHTS do
		total += r.w
	end
	local x = rng:NextNumber() * total
	for _, r in ROLE_WEIGHTS do
		x -= r.w
		if x <= 0 then
			return r.role
		end
	end
	return "rifleman"
end

local function hqOf(team: number): { [string]: any }
	for _, h in MapInfo.get().hqs do
		if h.team == team then
			return h
		end
	end
	return MapInfo.get().hqs[1]
end

local function humansOn(team: number): number
	local n = 0
	for _, p in Players:GetPlayers() do
		local s = SoldierRegistry.forPlayer(p)
		if s and s.team == team then
			n += 1
		end
	end
	return n
end

local function squadFor(team: number, s: Soldier): Squad
	for _, sq in squads[team] do
		if #sq.members < 5 and not sq.armor then
			table.insert(sq.members, s.id)
			return sq
		end
	end
	nextSquad += 1
	local sq: Squad = { id = nextSquad, team = team, members = { s.id }, order = nil, vehicleId = nil, armor = false }
	table.insert(squads[team], sq)
	return sq
end

-- Keep each team at the requested size (bots replace missing humans).
function AIDirector.balance()
	if not AIDirector.enabled then
		return
	end
	for _, team in Constants.TEAMS do
		local want = math.max(0, AIDirector.botsPerTeam - humansOn(team))
		local bots = {}
		for _, s in SoldierRegistry.all() do
			if s.isBot and s.team == team then
				table.insert(bots, s)
			end
		end
		while #bots < want do
			local role = pickRole()
			local s = SoldierRegistry.create(Util.soldierName(rng), team, role, nil)
			s.respawnAt = os.clock() + rng:NextNumber() * 4
			BotBrain.new(s)
			s.squad = squadFor(team, s)
			table.insert(bots, s)
		end
		while #bots > want do
			local s = table.remove(bots) :: Soldier
			if s.vehicleId then
				VehicleService.ejectSoldier(s, true)
			end
			if s.model then
				s.model:Destroy()
			end
			if s.squad then
				local idx = table.find(s.squad.members, s.id)
				if idx then
					table.remove(s.squad.members, idx)
				end
			end
			SoldierRegistry.remove(s)
		end
	end
end

-- Spawn location for a bot: an owned point near its squad objective, else HQ.
local function botSpawnCFrame(s: Soldier): CFrame
	local info = MapInfo.get()
	local mode = MatchService.mode()
	local sq = s.squad
	local target = sq and sq.order and sq.order.pos
	local best: { [string]: any }? = nil
	local bestD = math.huge
	if target and mode then
		for _, p in info.points do
			local pt = mode:pointById(p.id)
			if pt and pt.owner == s.team and not pt.contested then
				local d = (Vector3.new(p.x, 0, p.z) - Vector3.new(target.X, 0, target.Z)).Magnitude
				if d < bestD then
					bestD = d
					best = p
				end
			end
		end
	end
	if best and bestD < 1400 and rng:NextNumber() < 0.75 then
		local list = info.pointSpawns[best.id]
		local sp = list[rng:NextInteger(1, #list)]
		return CFrame.new(sp.x, MapInfo.heightAt(sp.x, sp.z) + 3.5, sp.z) * CFrame.Angles(0, sp.yaw, 0)
	end
	local list = info.hqSpawns[tostring(s.team)]
	local sp = list[rng:NextInteger(1, #list)]
	return CFrame.new(sp.x + rng:NextNumber() * 8 - 4, MapInfo.heightAt(sp.x, sp.z) + 3.5, sp.z + rng:NextNumber() * 8 - 4) * CFrame.Angles(0, sp.yaw, 0)
end

local function respawnBots()
	local now = os.clock()
	local mode = MatchService.mode()
	if mode and mode.state ~= "live" then
		return
	end
	for _, s in SoldierRegistry.all() do
		if s.isBot and not s.alive and now >= s.respawnAt then
			-- crew bots try to deploy straight into an armoured vehicle
			local spawned = false
			if s.role == "crew" then
				for _, kind in { "mbt", "ifv", "apc", "artillery", "recovery" } do
					local v = VehicleService.claimForDeploy(s.team, kind)
					if v then
						if SpawnService.spawnSoldier(s, VehicleService.seatCFrame(v, 1) + Vector3.new(0, 3, 0)) then
							if s.brain then
								s.brain:setupBody()
							end
							VehicleService.enter(s, v, 1)
							drivers[v.id] = drivers[v.id] or VehicleDriver.new(v)
							spawned = true
						end
						break
					end
				end
			end
			if not spawned then
				if SpawnService.spawnSoldier(s, botSpawnCFrame(s)) and s.brain then
					s.brain:setupBody()
				end
			end
			s.respawnAt = now + 2
			return -- at most one spawn per call keeps frames smooth
		end
	end
end

local function memberOrder(sq: Squad, idx: number, order: any): Vector3
	local p = order.pos
	local r = order.radius or 100
	local a = (idx / math.max(1, #sq.members)) * math.pi * 2 + sq.id
	local dist = if order.kind == "defend" then r * (0.55 + 0.25 * ((idx % 3) / 2)) else r * 0.35 * ((idx % 3) + 1) / 3
	local x, z = p.X + math.cos(a) * dist, p.Z + math.sin(a) * dist
	return Vector3.new(x, MapInfo.heightAt(x, z), z)
end

local function plan()
	local mode = MatchService.mode()
	if not mode then
		return
	end
	for _, team in Constants.TEAMS do
		local hq = hqOf(team)
		local orders = commanders[team]:plan(squads[team], mode, hq)
		for _, sq in squads[team] do
			local order = orders[sq.id]
			sq.order = order
			if order then
				for i, id in sq.members do
					local s = SoldierRegistry.get(id)
					if s and s.brain then
						s.brain:setOrder(order.kind, memberOrder(sq, i, order), order.point)
					end
				end
			end
		end
		-- armoured vehicles driven by bots follow the most important objective
		for vid, d in drivers do
			local v = d.v
			if v.alive and v.team == team then
				local best = nil
				for _, o in orders do
					if not best or o.kind == "capture" then
						best = o
					end
				end
				if best then
					-- tanks keep a stand-off distance and support with fire
					local standOff = if v.def.drive == "tracked" then 140 else 60
					d:setGoal(best.pos, standOff)
				end
			elseif not v.alive then
				drivers[vid] = nil
			end
		end
	end
end

local thinkAcc: { [number]: number } = {}

function AIDirector.init()
	local planAcc = 0
	local balanceAcc = 0
	local spawnAcc = 0
	RunService.Heartbeat:Connect(function(dt)
		if not AIDirector.enabled then
			return
		end
		local mode = MatchService.mode()
		if mode and mode.state ~= "live" then
			return
		end
		balanceAcc += dt
		if balanceAcc > 3 then
			balanceAcc = 0
			AIDirector.balance()
		end
		spawnAcc += dt
		if spawnAcc > 0.25 then
			spawnAcc = 0
			respawnBots()
		end
		planAcc += dt
		if planAcc > 4 then
			planAcc = 0
			plan()
		end
		for _, s in SoldierRegistry.all() do
			if s.isBot and s.alive and s.brain then
				local brain = s.brain
				local acc = (thinkAcc[s.id] or brain.thinkOffset) + dt
				if acc >= 0.2 then
					acc = 0
					local ok, err = pcall(function()
						brain:think()
					end)
					if not ok then
						warn("[AI] think error: " .. tostring(err))
					end
				end
				thinkAcc[s.id] = acc
				brain:combatStep(dt)
			end
		end
		for _, d in drivers do
			local v = d.v
			if v.alive then
				local driver = SoldierRegistry.get(v.seats[1])
				if driver and driver.isBot then
					d:drive(dt)
				end
				d:gunnery(dt)
			end
		end
	end)
end

function AIDirector.reset()
	for _, s in SoldierRegistry.all() do
		if s.isBot then
			s.respawnAt = os.clock() + rng:NextNumber() * 5
		end
	end
	table.clear(drivers)
	table.clear(thinkAcc)
end

function AIDirector.setDifficulty(level: number)
	BotBrain.difficulty = math.clamp(math.floor(level), 0, 2)
end

-- vehicles that bots end up in (e.g. passenger seats) still need gunnery
function AIDirector.trackVehicle(v: any)
	drivers[v.id] = drivers[v.id] or VehicleDriver.new(v)
end

return AIDirector
