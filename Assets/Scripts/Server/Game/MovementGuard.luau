--!strict
-- Server-side movement validation.
--
-- Player characters and player-driven vehicles are simulated by the owning
-- client (Roblox network ownership), so a modified client could teleport or
-- speed-hack - for example straight into a capture zone. Four times a second
-- the server compares the movement of every player soldier on foot, and of
-- every player-driven vehicle, with the fastest legal speed and pulls
-- offenders back by the illegal displacement. Falling is always allowed.
--
-- Legitimate server moves never trip it: a respawn is a new model (the track
-- restarts), vehicle crews are tracked through their vehicle, and ladder
-- climbing happens here on the server (MovementGuard.climb).

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local AntiCheat = require(ReplicatedStorage.Shared.AntiCheat)
local Constants = require(ReplicatedStorage.Shared.Constants)
local SoldierRegistry = require(script.Parent.SoldierRegistry)

type Soldier = SoldierRegistry.Soldier

local MovementGuard = {}

local CHECK_INTERVAL = 0.25
local SLACK = 10 -- studs of tolerance per check (network bursts, physics shoves)
local FOOT_SPEED = Constants.SOLDIER.SPRINT_SPEED * 1.35 -- studs/s
local FOOT_RISE = 45 -- studs/s upward: jumps, stairs, ramps
local LADDER_REACH = 7 -- studs from a ladder end to use it

-- VehicleService, injected by Main (a require would be circular).
MovementGuard.vehicles = nil :: any
-- Number of pull-backs since the server started (diagnostics / tests).
MovementGuard.pullBacks = 0

type Track = { model: Instance, pos: Vector3, t: number, strikes: number }
local soldierTracks: { [number]: Track } = {}
local vehicleTracks: { [number]: Track } = {}

-- Forget a soldier's last legal position (after a server-side move).
function MovementGuard.reset(s: Soldier)
	soldierTracks[s.id] = nil
end

local function check(tracks: { [number]: Track }, key: number, model: Model, root: BasePart, now: number, horizontal: number, rise: number, label: string)
	local pos = root.Position
	local tr = tracks[key]
	if not tr or tr.model ~= model then
		if pos == pos then
			tracks[key] = { model = model, pos = pos, t = now, strikes = 0 }
		end
		return
	end
	if AntiCheat.movementLegal(tr.pos, pos, now - tr.t, horizontal, rise, SLACK) then
		tr.pos = pos
		tr.t = now
		return
	end
	-- pull everything back by the illegal displacement
	local back = if pos == pos then tr.pos - pos else nil
	if back then
		model:PivotTo(model:GetPivot() + back)
	else
		model:PivotTo(CFrame.new(tr.pos))
	end
	root.AssemblyLinearVelocity = Vector3.zero
	root.AssemblyAngularVelocity = Vector3.zero
	tr.t = now
	tr.strikes += 1
	MovementGuard.pullBacks += 1
	if tr.strikes == 1 or tr.strikes % 25 == 0 then
		warn(string.format("[MovementGuard] pulled %s back (%d time(s))", label, tr.strikes))
	end
end

local function step(now: number)
	-- soldiers on foot
	local seen: { [number]: boolean } = {}
	for _, s in SoldierRegistry.alive() do
		if s.player and s.model and s.root then
			seen[s.id] = true
			if s.vehicleId then
				soldierTracks[s.id] = nil -- the vehicle is tracked instead
			else
				check(soldierTracks, s.id, s.model, s.root, now, FOOT_SPEED, FOOT_RISE, s.player.Name)
			end
		end
	end
	for id in soldierTracks do
		if not seen[id] then
			soldierTracks[id] = nil
		end
	end
	-- vehicles driven by players
	local vs = MovementGuard.vehicles
	if not vs then
		return
	end
	local live: { [number]: boolean } = {}
	for id, v in vs.all() do
		local driverId = v.alive and v.seats[1]
		local driver = if driverId then SoldierRegistry.get(driverId) else nil
		if driver and driver.player then
			live[id] = true
			local maxSpeed = (v.def.maxSpeed or 60) * 1.5
			local rise = if v.def.drive == "heli" then maxSpeed else 60
			check(vehicleTracks, id, v.model, v.root, now, maxSpeed, rise, driver.player.Name .. "'s " .. v.kind)
		end
	end
	for id in vehicleTracks do
		if not live[id] then
			vehicleTracks[id] = nil
		end
	end
end

-- Climb the nearest watchtower / water tower ladder (up or down).
function MovementGuard.climb(s: Soldier): boolean
	local root = s.root
	local model = s.model
	if not root or not model or s.vehicleId or not s.alive then
		return false
	end
	local map = workspace:FindFirstChild("Map")
	local props = map and map:FindFirstChild("Props")
	if not props then
		return false
	end
	local pos = root.Position
	local best: Vector3? = nil
	local bestDist = LADDER_REACH
	for _, m in props:GetChildren() do
		local kind = m:GetAttribute("PropKind")
		if kind == "watchtower" or kind == "water_tower" then
			local bottom = m:FindFirstChild("LadderBottom", true)
			local top = m:FindFirstChild("LadderTop", true)
			if bottom and top and bottom:IsA("Attachment") and top:IsA("Attachment") then
				local db = (bottom.WorldPosition - pos).Magnitude
				local dt = (top.WorldPosition - pos).Magnitude
				if db < bestDist then
					best, bestDist = top.WorldPosition, db
				end
				if dt < bestDist then
					best, bestDist = bottom.WorldPosition, dt
				end
			end
		end
	end
	if not best then
		return false
	end
	local dest = best + Vector3.new(0, 3, 0)
	model:PivotTo(model:GetPivot() + (dest - pos))
	root.AssemblyLinearVelocity = Vector3.zero
	MovementGuard.reset(s)
	return true
end

function MovementGuard.init()
	local acc = 0
	RunService.Heartbeat:Connect(function(dt)
		acc += dt
		if acc >= CHECK_INTERVAL then
			acc = 0
			step(os.clock())
		end
	end)
end

return MovementGuard
