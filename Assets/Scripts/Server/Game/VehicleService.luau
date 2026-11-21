--!strict
-- Vehicles: spawning, seats, network ownership, weapons, damage, auras, respawn.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local Rig = require(ReplicatedStorage.Shared.Rig)
local VehiclePhysics = require(ReplicatedStorage.Shared.VehiclePhysics)
local SoldierRegistry = require(script.Parent.SoldierRegistry)
local CombatService = require(script.Parent.CombatService)
local DestructionService = require(script.Parent.DestructionService)
local EffectsBus = require(script.Parent.EffectsBus)
local MovementGuard = require(script.Parent.MovementGuard)
local MatchService = require(script.Parent.MatchService)
local SpawnService = require(script.Parent.SpawnService)

type Soldier = SoldierRegistry.Soldier

local VehicleService = {}

export type Vehicle = {
	id: number,
	kind: string,
	def: { [string]: any },
	team: number,
	model: Model,
	rig: Rig.Rigged,
	root: BasePart,
	phys: VehiclePhysics.State,
	seats: { [number]: number? }, -- seat index -> soldier id
	hp: number,
	alive: boolean,
	slot: { [string]: any }?,
	slotIndex: number,
	idleSince: number,
	anchored: boolean,
	aim: { [number]: { yaw: number, pitch: number, target: Vector3? } },
	aimJoints: { [string]: { seat: number, mode: string } },
	cooldown: { [string]: number },
	mags: { [string]: number },
	lastAttacker: Soldier?,
	name: string,
	destroyedAt: number,
}

local vehicles: { [number]: Vehicle } = {}
local nextId = 0
local folder: Folder
local slotState: { [number]: { vehicle: number?, respawnAt: number } } = {}
local templates: { [string]: Model } = {}
local matchEvent: RemoteEvent

local BULLET_FACTOR = { tracked = 0.0, apc = 0.15, heli = 0.35, light = 0.6 }
local ARMOR_MULT = { mbt = 0.6, ifv = 0.75, artillery = 0.75, recovery = 0.7, apc = 0.9 }

local function template(name: string): Model?
	if not next(templates) then
		for _, d in ReplicatedStorage:WaitForChild("Assets"):WaitForChild("Models"):GetDescendants() do
			if d:IsA("Model") and d:GetAttribute("Category") then
				templates[d.Name] = d
			end
		end
	end
	return templates[name]
end

function VehicleService.get(id: number?): Vehicle?
	if not id then
		return nil
	end
	return vehicles[id]
end

function VehicleService.all(): { [number]: Vehicle }
	return vehicles
end

-- World CFrame of a muzzle attachment, applying the replicated turret aim.
local function jointRotation(v: Vehicle, jointName: string): CFrame
	local j = v.aimJoints[jointName]
	if not j then
		return CFrame.identity
	end
	local a = v.aim[j.seat]
	if not a then
		return CFrame.identity
	end
	if j.mode == "yaw" then
		return CFrame.Angles(0, a.yaw, 0)
	elseif j.mode == "pitch" then
		return CFrame.Angles(a.pitch, 0, 0)
	end
	return CFrame.Angles(0, a.yaw, 0) * CFrame.Angles(a.pitch, 0, 0)
end

-- Which seat aims which joint: main turret/gun follow the first seat that owns
-- the vehicle's main weapons; seats with an aimNode drive that node.
local function buildAimJoints(def: { [string]: any }, rig: Rig.Rigged): ({ [string]: { seat: number, mode: string } }, string)
	local main = 1
	local s1 = def.seats[1]
	if not (s1.weapons and #s1.weapons > 0 and type(s1.weapons[1]) == "number") then
		main = if def.seats[2] then 2 else 1
	end
	local js: { [string]: { seat: number, mode: string } } = {}
	if rig.joints.Turret then
		js.Turret = { seat = main, mode = "yaw" }
	end
	if rig.joints.Gun then
		js.Gun = { seat = main, mode = "pitch" }
	end
	for i, sd in def.seats do
		if sd.aimNode then
			if sd.aimNode == "ChinTurret" then
				js.ChinTurret = { seat = i, mode = "yaw" }
				if not rig.joints.Turret then
					js.Gun = { seat = i, mode = "pitch" }
				end
			else
				js[sd.aimNode] = { seat = i, mode = "both" }
			end
		end
	end
	local parts = {}
	for name, j in js do
		table.insert(parts, name .. ":" .. j.seat .. ":" .. j.mode)
	end
	return js, table.concat(parts, ",")
end

-- ---------------------------------------------------------------------------
-- Spawning
-- ---------------------------------------------------------------------------
local function groundCFrame(x: number, z: number, yaw: number, lift: number): CFrame
	return CFrame.new(x, MapInfo.heightAt(x, z) + lift, z) * CFrame.Angles(0, yaw, 0)
end

function VehicleService.spawn(kind: string, team: number, cf: CFrame, slotIndex: number?): Vehicle?
	local def = Defs.Vehicles[kind]
	if not def then
		return nil
	end
	local t = template(def.model[team] or def.model[1])
	if not t then
		warn("[Vehicles] missing model for " .. kind)
		return nil
	end
	local model = t:Clone()
	local rig = Rig.assemble(model)
	nextId += 1
	local id = nextId
	model.Name = kind .. "_" .. id
	model:SetAttribute("VehicleId", id)
	model:SetAttribute("Kind", kind)
	model:SetAttribute("Team", team)
	model:SetAttribute("HP", def.hp)
	model:SetAttribute("MaxHP", def.hp)
	model:SetAttribute("Damage", 0)
	local root = rig.root
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") then
			d.CollisionGroup = "Vehicles"
			if d ~= root and not d:GetAttribute("hitbox") then
				d.CanCollide = false
				d.Massless = true
			end
		end
	end
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") and d:GetAttribute("hitbox") then
			d.CanCollide = true
			d.CanTouch = d == root
			d.Massless = d ~= root
		end
	end
	-- heavy, low centre of mass hull
	root.CustomPhysicalProperties = PhysicalProperties.new(if def.drive == "heli" then 1.2 else 2.6, 0.6, 0.1)
	local lift = if def.drive == "heli" then 0.5 else 1.5
	model:PivotTo(cf + Vector3.new(0, lift, 0))
	-- stream to clients as one unit so the animator always sees a complete rig
	model.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
	model.Parent = folder
	local phys = VehiclePhysics.setup(root, def)
	local seats: { [number]: number? } = {}
	local aim = {}
	for i = 1, #def.seats do
		seats[i] = nil
		aim[i] = { yaw = 0, pitch = 0, target = nil }
	end
	local mags = {}
	for i, w in def.weapons do
		if w.mag then
			mags[tostring(i)] = w.mag
		end
	end
	local aimJoints, aimMap = buildAimJoints(def, rig)
	model:SetAttribute("AimMap", aimMap)
	local v: Vehicle = {
		id = id, kind = kind, def = def, team = team, model = model, rig = rig, root = root, phys = phys, seats = seats,
		hp = def.hp, alive = true, slot = nil, slotIndex = slotIndex or 0, idleSince = os.clock(), anchored = false,
		aim = aim, aimJoints = aimJoints, cooldown = {}, mags = mags, lastAttacker = nil,
		name = Defs.vehicleName(kind, team), destroyedAt = 0,
	}
	vehicles[id] = v
	-- crushing: heavy vehicles flatten fences, walls, cars, trees and soldiers
	root.Touched:Connect(function(other)
		VehicleService.onTouch(v, other)
	end)
	return v
end

local function spawnSlot(i: number)
	local info = MapInfo.get()
	local slot = info.vehicleSlots[i]
	local team = slot.team
	if team == 0 then
		-- capturable motor pools belong to the owner of the nearby point
		local mode = MatchService.mode()
		local pt = mode and mode:pointById(slot.home)
		if not pt or pt.owner == 0 then
			return
		end
		team = pt.owner
	end
	local v = VehicleService.spawn(slot.type, team, groundCFrame(slot.x, slot.z, slot.yaw, 0), i)
	if v then
		v.slot = slot
		slotState[i] = { vehicle = v.id, respawnAt = 0 }
	end
end

function VehicleService.spawnAll()
	local info = MapInfo.get()
	for i in info.vehicleSlots do
		slotState[i] = { vehicle = nil, respawnAt = 0 }
		spawnSlot(i)
	end
end

function VehicleService.despawn(v: Vehicle)
	for i, sid in v.seats do
		local s = SoldierRegistry.get(sid)
		if s then
			VehicleService.exit(s, true)
		end
		v.seats[i] = nil
	end
	v.alive = false
	vehicles[v.id] = nil
	if v.model.Parent then
		v.model:Destroy()
	end
end

function VehicleService.resetAll()
	for _, v in vehicles do
		VehicleService.despawn(v)
	end
	table.clear(vehicles)
	table.clear(slotState)
	VehicleService.spawnAll()
end

-- ---------------------------------------------------------------------------
-- Seats
-- ---------------------------------------------------------------------------
function VehicleService.seatPart(v: Vehicle, index: number): Seat?
	return v.rig.seats[index]
end

function VehicleService.seatCFrame(v: Vehicle, index: number): CFrame
	local seat = VehicleService.seatPart(v, index)
	return if seat then seat.CFrame else v.root.CFrame
end

function VehicleService.freeSeat(v: Vehicle, from: number?): number?
	for i = from or 1, #v.def.seats do
		if v.seats[i] == nil then
			return i
		end
	end
	return nil
end

local function setHidden(s: Soldier, hidden: boolean)
	local m = s.model
	if not m then
		return
	end
	m:SetAttribute("HiddenInVehicle", hidden)
	for _, d in m:GetDescendants() do
		if d:IsA("BasePart") then
			d.CanQuery = not hidden
		end
	end
end

local function updateOwnership(v: Vehicle)
	local driver = SoldierRegistry.get(v.seats[1])
	if v.anchored then
		return
	end
	local ok = pcall(function()
		if driver and driver.player then
			v.root:SetNetworkOwner(driver.player)
		else
			v.root:SetNetworkOwner(nil)
		end
	end)
	local _ = ok
	v.model:SetAttribute("Driver", if driver then driver.id else 0)
end

local function wake(v: Vehicle)
	if v.anchored then
		v.anchored = false
		v.root.Anchored = false
	end
	v.idleSince = os.clock()
end

function VehicleService.enter(s: Soldier, v: Vehicle, index: number?): boolean
	if not v.alive or not s.alive or not s.humanoid or not s.root then
		return false
	end
	if v.team ~= s.team then
		local occupied = false
		for _, sid in v.seats do
			if sid then
				occupied = true
			end
		end
		if occupied then
			return false
		end
		return false -- enemy vehicles cannot be stolen
	end
	local idx = index or VehicleService.freeSeat(v)
	if not idx or v.seats[idx] ~= nil then
		return false
	end
	local seat = VehicleService.seatPart(v, idx)
	if not seat then
		return false
	end
	if s.vehicleId then
		VehicleService.exit(s, false)
	end
	wake(v)
	v.seats[idx] = s.id
	s.vehicleId = v.id
	s.seatIndex = idx
	seat.Disabled = false
	local hum = s.humanoid :: Humanoid
	s.root.CFrame = seat.CFrame + seat.CFrame.UpVector * 1.5
	seat:Sit(hum)
	task.defer(function()
		seat.Disabled = true
	end)
	local seatDef = v.def.seats[idx]
	setHidden(s, seatDef.hidden == true)
	if s.model then
		s.model:SetAttribute("VehicleId", v.id)
		s.model:SetAttribute("Seat", idx)
	end
	if idx == 1 then
		v.phys.engineOn = true
	end
	updateOwnership(v)
	if s.player then
		matchEvent:FireClient(s.player, { kind = "vehicleEnter", id = v.id, seat = idx, vehicle = v.kind })
	end
	EffectsBus.push({ k = "door", v = v.id, seat = idx })
	return true
end

function VehicleService.exit(s: Soldier, silent: boolean?)
	local v = vehicles[s.vehicleId or -1]
	local idx = s.seatIndex
	s.vehicleId = nil
	s.seatIndex = nil
	if s.model then
		s.model:SetAttribute("VehicleId", nil)
		s.model:SetAttribute("Seat", nil)
	end
	if not v or not idx then
		return
	end
	v.seats[idx] = nil
	setHidden(s, false)
	local hum = s.humanoid
	if hum then
		hum.Sit = false
	end
	local seat = VehicleService.seatPart(v, idx)
	if seat then
		local weld = seat:FindFirstChild("SeatWeld")
		if weld then
			weld:Destroy()
		end
	end
	-- exit point: attachment "ExitN" if present, else beside the hull
	if s.alive and s.root then
		local exitAtt = v.rig.attachments["Exit" .. idx]
		local pos = if exitAtt then exitAtt.WorldPosition else (v.root.CFrame * CFrame.new(-v.def.size.X / 2 - 3, 0, 0)).Position
		local y = MapInfo.heightAt(pos.X, pos.Z)
		s.root.CFrame = CFrame.new(pos.X, math.max(pos.Y, y) + 3.5, pos.Z) * v.root.CFrame.Rotation
		s.root.AssemblyLinearVelocity = v.root.AssemblyLinearVelocity * 0.5
		MovementGuard.reset(s)
	end
	if idx == 1 then
		v.phys.engineOn = false
	end
	updateOwnership(v)
	v.idleSince = os.clock()
	if s.player and not silent then
		matchEvent:FireClient(s.player, { kind = "vehicleExit", id = v.id })
	elseif s.player then
		matchEvent:FireClient(s.player, { kind = "vehicleExit", id = v.id })
	end
	EffectsBus.push({ k = "door", v = v.id, seat = idx })
end

function VehicleService.ejectSoldier(s: Soldier, dead: boolean)
	VehicleService.exit(s, dead)
end

function VehicleService.switchSeat(s: Soldier, index: number)
	local v = vehicles[s.vehicleId or -1]
	if not v or not v.def.seats[index] or v.seats[index] ~= nil then
		return
	end
	VehicleService.exit(s, true)
	VehicleService.enter(s, v, index)
end

-- ---------------------------------------------------------------------------
-- Weapons
-- ---------------------------------------------------------------------------
function VehicleService.muzzleCFrame(v: Vehicle, attachmentName: string): CFrame
	local att = v.rig.attachments[attachmentName]
	if not att then
		return v.root.CFrame * CFrame.new(0, v.def.size.Y, -v.def.size.Z / 2)
	end
	-- walk up the joint chain: pivot <- joint <- parent pivot ...
	local chain = {}
	local part = att.Parent :: BasePart
	while part do
		local joint: Motor6D? = nil
		for _, j in v.rig.joints do
			if j.Part1 == part then
				joint = j
				break
			end
		end
		if not joint then
			break
		end
		table.insert(chain, 1, joint)
		part = joint.Part0 :: BasePart
	end
	local cf = v.rig.pivot.CFrame
	for _, j in chain do
		cf = cf * j.C0 * jointRotation(v, j.Name)
	end
	return cf * att.CFrame
end

local function ballisticDirection(origin: Vector3, target: Vector3, speed: number, g: number): Vector3
	local d = target - origin
	local dxz = Vector3.new(d.X, 0, d.Z)
	local x = dxz.Magnitude
	local y = d.Y
	local v2 = speed * speed
	local disc = v2 * v2 - g * (g * x * x + 2 * y * v2)
	local angle
	if disc < 0 then
		angle = math.rad(45)
	else
		angle = math.atan((v2 + math.sqrt(disc)) / (g * x)) -- high arc (indirect fire)
	end
	local h = if x > 0.01 then dxz.Unit else Vector3.zAxis
	return (h * math.cos(angle) + Vector3.new(0, math.sin(angle), 0)).Unit
end

function VehicleService.fire(s: Soldier, v: Vehicle, weaponIndex: number, aimDir: Vector3, target: Vector3?): boolean
	local seatIdx = s.seatIndex
	if not seatIdx or v.seats[seatIdx] ~= s.id or not v.alive then
		return false
	end
	local seatDef = v.def.seats[seatIdx]
	local list = seatDef.weapons
	if not list or not list[weaponIndex] then
		return false
	end
	local entry = list[weaponIndex]
	local w = if type(entry) == "number" then v.def.weapons[entry] else entry
	if not w then
		return false
	end
	local key = seatIdx .. ":" .. weaponIndex
	local now = os.clock()
	local interval = if w.rpm then 60 / w.rpm else (w.reload or 1)
	if now < (v.cooldown[key] or 0) then
		return false
	end
	v.cooldown[key] = now + interval
	if w.mag then
		local left = v.mags[key] or w.mag
		if left <= 0 then
			return false
		end
		left -= 1
		v.mags[key] = left
		if left <= 0 then
			v.cooldown[key] = now + (w.magReload or 5)
			task.delay(w.magReload or 5, function()
				v.mags[key] = w.mag
			end)
		end
	end
	wake(v)
	local muzzle = VehicleService.muzzleCFrame(v, w.muzzle or "Muzzle")
	local origin = muzzle.Position
	local dir = if aimDir.Magnitude > 0.5 then aimDir.Unit else muzzle.LookVector
	-- the shot must leave roughly where the barrel points (no firing backwards)
	if dir:Dot(muzzle.LookVector) < 0.5 and w.kind ~= "rocket_salvo" then
		dir = muzzle.LookVector
	end
	local ignore = { v.model :: Instance }
	if w.kind == "hitscan" then
		local d = CombatService.spreadDir(dir, w.spread or 0.004)
		local endPos = CombatService.bullet(s, w, origin, d, ignore)
		EffectsBus.push({ k = "tracer", a = origin, b = endPos, w = w.sound, sid = s.id, v = v.id })
	elseif w.kind == "rocket_salvo" then
		local reach = w.range or 2600
		local tgt = target or (origin + dir * 1500)
		if (tgt - origin).Magnitude > reach then
			tgt = origin + (tgt - origin).Unit * reach
		end
		v.cooldown[key] = now + (w.reload or 30)
		task.spawn(function()
			for k = 1, (w.count or 12) do
				if not v.alive then
					break
				end
				local tube = VehicleService.muzzleCFrame(v, "Tube" .. (((k - 1) % 12) + 1))
				local spreadT = tgt + Vector3.new((math.random() - 0.5) * (w.dispersion or 60), 0, (math.random() - 0.5) * (w.dispersion or 60))
				local g = workspace.Gravity * (w.gravityScale or 1)
				local bd = ballisticDirection(tube.Position, spreadT, w.speed, g)
				CombatService.launch(tube.Position, bd * w.speed, w, s, ignore, v.id)
				EffectsBus.push({ k = "muzzle", p = tube.Position, d = bd, big = true, w = w.sound })
				task.wait(w.interval or 0.3)
			end
		end)
		return true
	else
		local vel = dir * w.speed
		if v.def.turret and v.def.turret.indirect and target then
			local g = workspace.Gravity * (w.gravityScale or 1)
			vel = ballisticDirection(origin, target, w.speed, g) * w.speed
		end
		CombatService.launch(origin, vel, w, s, ignore, v.id)
		EffectsBus.push({ k = "muzzle", p = origin, d = dir, big = (w.damage or 0) > 150, w = w.sound, v = v.id })
		if w.recoil then
			v.root:ApplyImpulseAtPosition(-dir * v.root.AssemblyMass * 4, origin)
		end
	end
	SpawnService.dropProtection(s)
	return true
end

-- ---------------------------------------------------------------------------
-- Damage
-- ---------------------------------------------------------------------------
local function classOf(v: Vehicle): string
	if v.def.drive == "tracked" then
		return "tracked"
	elseif v.def.drive == "heli" then
		return "heli"
	elseif v.kind == "apc" then
		return "apc"
	end
	return "light"
end

local function destroyVehicle(v: Vehicle, attacker: Soldier?, weaponName: string)
	if not v.alive then
		return
	end
	v.alive = false
	v.destroyedAt = os.clock()
	v.model:SetAttribute("Destroyed", true)
	v.model:SetAttribute("HP", 0)
	-- occupants
	for i, sid in v.seats do
		local s = SoldierRegistry.get(sid)
		if s then
			VehicleService.exit(s, true)
			if s.alive then
				CombatService.damageSoldier(s, 250, attacker, weaponName, nil, v.root.Position)
			end
		end
		v.seats[i] = nil
	end
	if attacker and attacker.team ~= v.team then
		SoldierRegistry.addScore(attacker, "vehicleKills", 1, 200)
	end
	matchEvent:FireAllClients({ kind = "vehicleKill", vehicle = v.name, team = v.team, killer = attacker and attacker.name, killerTeam = attacker and attacker.team, weapon = weaponName })
	CombatService.explode(v.root.Position + Vector3.new(0, 2, 0), 26, 160, attacker, weaponName, { vehicleDamage = 200, structDmg = 600, structRadius = 14 })
	-- wreck: scorched, no movers, settles under gravity
	for _, d in v.model:GetDescendants() do
		if d:IsA("BasePart") and d.Transparency < 0.95 then
			d.Color = Color3.fromRGB(34, 32, 30):Lerp(d.Color, 0.12)
			if d.Material ~= Enum.Material.Glass then
				d.Material = Enum.Material.CorrodedMetal
			else
				d.Transparency = 1
			end
		elseif d:IsA("VectorForce") or d:IsA("AlignOrientation") or d:IsA("LinearVelocity") then
			d.Enabled = false
		end
	end
	local fire = Instance.new("Fire")
	fire.Size = 14
	fire.Heat = 18
	fire.Parent = v.root
	local smoke = Instance.new("Smoke")
	smoke.Size = 14
	smoke.Opacity = 0.35
	smoke.RiseVelocity = 9
	smoke.Color = Color3.fromRGB(30, 30, 30)
	smoke.Parent = v.root
	v.root.Anchored = false
	pcall(function()
		v.root:SetNetworkOwner(nil)
	end)
	-- launch the turret
	local turret = v.rig.joints.Turret
	if turret and v.def.drive == "tracked" and math.random() < 0.5 then
		turret:Destroy()
		local tp = turret.Part1 :: BasePart
		tp.CanCollide = true
		tp.Massless = false
		tp.AssemblyLinearVelocity = Vector3.new(math.random() * 10 - 5, 45, math.random() * 10 - 5)
		tp.AssemblyAngularVelocity = Vector3.new(math.random() * 4 - 2, math.random() * 4 - 2, math.random() * 4 - 2)
	end
	-- respawn the slot after the vehicle's respawn time; remove the wreck later
	local slotIndex = v.slotIndex
	if slotIndex > 0 then
		slotState[slotIndex] = { vehicle = nil, respawnAt = os.clock() + (v.def.respawn or 60) }
	end
	task.delay(90, function()
		fire.Enabled = false
		task.wait(30)
		vehicles[v.id] = nil
		if v.model.Parent then
			v.model:Destroy()
		end
	end)
end

function VehicleService.damage(id: number, amount: number, attacker: Soldier?, kind: string, weaponName: string)
	local v = vehicles[id]
	if not v or not v.alive then
		return
	end
	if attacker and attacker.team == v.team and attacker.vehicleId ~= id then
		return -- no friendly fire on vehicles
	end
	local mult = ARMOR_MULT[v.kind] or 1
	if kind == "bullet" then
		mult *= BULLET_FACTOR[classOf(v)] or 0.5
	end
	local dmg = amount * mult
	if dmg <= 0 then
		return
	end
	wake(v)
	v.hp -= dmg
	v.lastAttacker = attacker
	v.model:SetAttribute("HP", math.max(0, math.floor(v.hp)))
	v.model:SetAttribute("Damage", if v.hp < v.def.hp * 0.25 then 2 elseif v.hp < v.def.hp * 0.5 then 1 else 0)
	if attacker and attacker.player then
		Net.event("Hitmarker"):FireClient(attacker.player, { vehicle = true, kill = v.hp <= 0 })
	end
	for _, sid in v.seats do
		local s = SoldierRegistry.get(sid)
		if s and s.player then
			Net.event("DamageTaken"):FireClient(s.player, { amount = dmg, vehicle = true })
		end
	end
	if v.hp <= 0 then
		destroyVehicle(v, attacker, weaponName)
	end
end

function VehicleService.repair(v: Vehicle, amount: number): boolean
	if not v.alive or v.hp >= v.def.hp then
		return false
	end
	v.hp = math.min(v.def.hp, v.hp + amount)
	v.model:SetAttribute("HP", math.floor(v.hp))
	v.model:SetAttribute("Damage", if v.hp < v.def.hp * 0.25 then 2 elseif v.hp < v.def.hp * 0.5 then 1 else 0)
	return true
end

function VehicleService.near(pos: Vector3, radius: number): { Vehicle }
	local out = {}
	for _, v in vehicles do
		if v.alive and (v.root.Position - pos).Magnitude <= radius then
			table.insert(out, v)
		end
	end
	return out
end

function VehicleService.fromPart(part: BasePart): Vehicle?
	local cur: Instance? = part
	for _ = 1, 8 do
		if not cur then
			break
		end
		local id = cur:GetAttribute("VehicleId")
		if id then
			return vehicles[id :: number]
		end
		cur = cur.Parent
	end
	return nil
end

-- crushing structures / soldiers
local crushCooldown: { [Instance]: number } = {}
function VehicleService.onTouch(v: Vehicle, other: BasePart)
	if not v.alive then
		return
	end
	local speed = v.root.AssemblyLinearVelocity.Magnitude
	if speed < 6 then
		return
	end
	local now = os.clock()
	if (crushCooldown[other] or 0) > now then
		return
	end
	crushCooldown[other] = now + 0.5
	local cur: Instance? = other
	local pieceId: number? = nil
	local soldierId: number? = nil
	for _ = 1, 4 do
		if not cur then
			break
		end
		pieceId = pieceId or (cur:GetAttribute("PieceId") :: number?)
		soldierId = soldierId or (cur:GetAttribute("SoldierId") :: number?)
		cur = cur.Parent
	end
	if pieceId then
		local heavy = v.def.crush == true
		local force = v.def.mass / 1000 * speed * (if heavy then 8 else 1.5)
		DestructionService.damagePiece(pieceId, force, "crush", v.root.Position)
	elseif soldierId and speed > 18 then
		local s = SoldierRegistry.get(soldierId)
		local driver = SoldierRegistry.get(v.seats[1])
		if s and s.alive and s.team ~= v.team and not s.vehicleId then
			CombatService.damageSoldier(s, math.min(200, speed * 3), driver, v.name, nil, v.root.Position)
		end
	end
end

-- ---------------------------------------------------------------------------
-- Deploy helpers
-- ---------------------------------------------------------------------------
local function isIdleAtHome(v: Vehicle): boolean
	if not v.alive then
		return false
	end
	for _, sid in v.seats do
		if sid then
			return false
		end
	end
	if v.slot then
		return (Vector3.new(v.slot.x, 0, v.slot.z) - v.root.Position * Vector3.new(1, 0, 1)).Magnitude < 40
	end
	return false
end

function VehicleService.deployVehicles(team: number): { { [string]: any } }
	local counts: { [string]: { available: number, total: number, respawn: number } } = {}
	local info = MapInfo.get()
	for i, slot in info.vehicleSlots do
		local st = slotState[i]
		local v = st and vehicles[st.vehicle or -1]
		local slotTeam = slot.team
		if slotTeam == 0 then
			local mode = MatchService.mode()
			local pt = mode and mode:pointById(slot.home)
			slotTeam = if pt then pt.owner else 0
		end
		if slotTeam ~= team then
			continue
		end
		local c = counts[slot.type]
		if not c then
			c = { available = 0, total = 0, respawn = 0 }
			counts[slot.type] = c
		end
		c.total += 1
		if v and v.team == team and isIdleAtHome(v) then
			c.available += 1
		elseif st and st.respawnAt > 0 then
			local r = math.max(0, st.respawnAt - os.clock())
			if c.respawn == 0 or r < c.respawn then
				c.respawn = r
			end
		end
	end
	local out = {}
	for _, kind in Defs.VehicleOrder do
		local c = counts[kind]
		if c then
			table.insert(out, { kind = kind, name = Defs.vehicleName(kind, team), category = Defs.Vehicles[kind].category, available = c.available, total = c.total, respawn = math.ceil(c.respawn) })
		end
	end
	return out
end

function VehicleService.claimForDeploy(team: number, kind: string): Vehicle?
	for _, v in vehicles do
		if v.kind == kind and v.team == team and isIdleAtHome(v) then
			return v
		end
	end
	return nil
end

function VehicleService.mobileSpawns(team: number): { { [string]: any } }
	local out = {}
	for _, v in vehicles do
		if v.alive and v.team == team and v.def.mobileSpawn then
			local free = VehicleService.freeSeat(v, 2)
			local enemyNear = false
			for _, e in SoldierRegistry.alive(Constants.enemyOf(team)) do
				if e.root and (e.root.Position - v.root.Position).Magnitude < 60 then
					enemyNear = true
					break
				end
			end
			local p = v.root.Position
			table.insert(out, { id = v.id, name = v.name, x = p.X, z = p.Z, available = free ~= nil and not enemyNear, reason = if not free then "Full" elseif enemyNear then "Under fire" else nil })
		end
	end
	return out
end

-- ---------------------------------------------------------------------------
-- Update loop: idle anchoring, auras, slot respawns, speed sanity
-- ---------------------------------------------------------------------------
local auraAcc = 0
local function step(dt: number)
	local now = os.clock()
	for _, v in vehicles do
		if not v.alive or not v.root.Parent then
			continue
		end
		local driver = SoldierRegistry.get(v.seats[1])
		if not driver then
			if not v.anchored then
				if v.def.drive == "heli" then
					v.phys.engineOn = false
					VehiclePhysics.step(v.phys, nil, dt)
				else
					VehiclePhysics.park(v.phys)
				end
				-- park idle vehicles: anchoring saves physics time
				if now - v.idleSince > 6 and v.root.AssemblyLinearVelocity.Magnitude < 0.5 and v.phys.grounded then
					v.anchored = true
					v.root.Anchored = true
				end
			end
		else
			v.idleSince = now
			-- player-driven: the client simulates; sanity check its speed
			local spd = v.root.AssemblyLinearVelocity.Magnitude
			if spd > (v.def.maxSpeed or 60) * 1.8 + 20 then
				v.root.AssemblyLinearVelocity = v.root.AssemblyLinearVelocity.Unit * (v.def.maxSpeed or 60)
			end
		end
		-- replicate the aim of every seat that controls a turret joint
		for _, j in v.aimJoints do
			local a = v.aim[j.seat]
			if a then
				v.model:SetAttribute("AimYaw" .. j.seat, math.floor(a.yaw * 1000) / 1000)
				v.model:SetAttribute("AimPitch" .. j.seat, math.floor(a.pitch * 1000) / 1000)
			end
		end
		v.model:SetAttribute("Engine", v.phys.engineOn)
	end
	-- auras + slot respawns at 2 Hz
	auraAcc += dt
	if auraAcc < 0.5 then
		return
	end
	local adt = auraAcc
	auraAcc = 0
	for _, v in vehicles do
		local aura = v.def.aura
		if v.alive and aura then
			local pos = v.root.Position
			if aura.kind == "heal" then
				for _, s in SoldierRegistry.alive(v.team) do
					if s.root and s.humanoid and (s.root.Position - pos).Magnitude < aura.radius and s.humanoid.Health < s.humanoid.MaxHealth then
						s.humanoid.Health = math.min(s.humanoid.MaxHealth, s.humanoid.Health + 8 * adt)
					end
				end
			elseif aura.kind == "resupply" then
				for _, s in SoldierRegistry.alive(v.team) do
					if s.root and (s.root.Position - pos).Magnitude < aura.radius then
						SpawnService.refill(s, 0.25 * adt)
					end
				end
			elseif aura.kind == "repair" then
				for _, o in VehicleService.near(pos, aura.radius) do
					if o ~= v and o.team == v.team then
						VehicleService.repair(o, (aura.rate or 40) * adt)
					end
				end
			elseif aura.kind == "radar" then
				for _, e in SoldierRegistry.alive(Constants.enemyOf(v.team)) do
					if e.root and (e.root.Position - pos).Magnitude < aura.radius then
						e.spottedUntil = math.max(e.spottedUntil, now + 1.5)
					end
				end
			end
		end
	end
	local info = MapInfo.get()
	for i, st in slotState do
		if st.vehicle == nil and st.respawnAt > 0 and now >= st.respawnAt then
			st.respawnAt = 0
			spawnSlot(i)
		end
	end
	-- capturable motor pools follow point ownership
	for i, slot in info.vehicleSlots do
		if slot.team == 0 then
			local st = slotState[i]
			local mode = MatchService.mode()
			local pt = mode and mode:pointById(slot.home)
			local owner = if pt then pt.owner else 0
			local v = st and vehicles[st.vehicle or -1]
			if owner ~= 0 and not v then
				if st == nil or st.respawnAt == 0 then
					spawnSlot(i)
				end
			elseif v and v.team ~= owner and isIdleAtHome(v) then
				VehicleService.despawn(v)
				slotState[i] = { vehicle = nil, respawnAt = 0 }
				if owner ~= 0 then
					spawnSlot(i)
				end
			end
		end
	end
end

-- ---------------------------------------------------------------------------
-- Init: remotes
-- ---------------------------------------------------------------------------
function VehicleService.init()
	folder = Instance.new("Folder")
	folder.Name = "Vehicles"
	folder.Parent = workspace
	matchEvent = Net.event("MatchEvent")
	MatchService.vehicleLookup = function(id)
		return vehicles[id]
	end
	CombatService.vehicleDamage = VehicleService.damage
	CombatService.vehiclesNear = VehicleService.near
	CombatService.vehicleRepair = function(s, part, dt)
		local root = s.root
		if not root then
			return false
		end
		local target = if part then VehicleService.fromPart(part) else nil
		if not target then
			local best, bd = nil, 14
			for _, v in VehicleService.near(root.Position, 20) do
				local d = (v.root.Position - root.Position).Magnitude - v.def.size.Magnitude * 0.3
				if v.team == s.team and d < bd then
					best, bd = v, d
				end
			end
			target = best
		end
		if target and target.team == s.team and (target.root.Position - root.Position).Magnitude < target.def.size.Magnitude * 0.6 + 12 then
			local ok = VehicleService.repair(target, (Defs.Weapons.repair.repairPerSec or 50) * dt)
			if ok then
				SoldierRegistry.addScore(s, "score", 0, 2)
			end
			return ok
		end
		return false
	end

	local interactLimiter = Net.rateLimiter(6)
	Net.event("Interact").OnServerEvent:Connect(function(player, payload)
		if not interactLimiter(player) or type(payload) ~= "table" then
			return
		end
		local req = payload :: any
		local s = SoldierRegistry.forPlayer(player)
		if not s or not s.alive or not s.root then
			return
		end
		if req.action == "exit" then
			VehicleService.exit(s, false)
		elseif req.action == "seat" and Util.finiteNumber(req.index) then
			VehicleService.switchSeat(s, math.floor(req.index))
		elseif req.action == "ladder" then
			MovementGuard.climb(s)
		elseif req.action == "enter" and Util.finiteNumber(req.id) then
			local v = vehicles[req.id]
			if v and (v.root.Position - s.root.Position).Magnitude < v.def.size.Magnitude * 0.5 + 14 then
				VehicleService.enter(s, v, nil)
			end
		end
	end)
	local aimLimiter = Net.rateLimiter(30)
	Net.event("VehicleAim").OnServerEvent:Connect(function(player, yawArg, pitchArg, target)
		local yaw, pitch = Util.finiteNumber(yawArg), Util.finiteNumber(pitchArg)
		if not aimLimiter(player) or not yaw or not pitch then
			return
		end
		local s = SoldierRegistry.forPlayer(player)
		local v = s and vehicles[s.vehicleId or -1]
		if not s or not v or not s.seatIndex then
			return
		end
		local tdef = v.def.turret
		local a = v.aim[s.seatIndex]
		if not a then
			return
		end
		a.yaw = yaw % (math.pi * 2)
		if a.yaw > math.pi then
			a.yaw -= math.pi * 2
		end
		a.pitch = math.clamp(pitch, if tdef then tdef.pitchMin else -0.3, if tdef then tdef.pitchMax else 0.8)
		a.target = Util.finiteVector(target)
	end)
	local fireLimiter = Net.rateLimiter(30)
	Net.event("VehicleFire").OnServerEvent:Connect(function(player, weaponArg, dirArg, target)
		local weaponIndex, dir = Util.finiteNumber(weaponArg), Util.finiteVector(dirArg)
		if not fireLimiter(player) or not weaponIndex or not dir then
			return
		end
		local s = SoldierRegistry.forPlayer(player)
		local v = s and vehicles[s.vehicleId or -1]
		if s and v then
			VehicleService.fire(s, v, math.floor(weaponIndex), dir, Util.finiteVector(target))
		end
	end)
	local toggleLimiter = Net.rateLimiter(4)
	Net.event("VehicleToggle").OnServerEvent:Connect(function(player, what)
		if not toggleLimiter(player) then
			return
		end
		local s = SoldierRegistry.forPlayer(player)
		local v = s and vehicles[s.vehicleId or -1]
		if not s or not v or s.seatIndex ~= 1 then
			return
		end
		if what == "lights" then
			v.model:SetAttribute("Lights", not v.model:GetAttribute("Lights"))
		elseif what == "engine" then
			v.phys.engineOn = not v.phys.engineOn
		end
	end)
	RunService.Heartbeat:Connect(step)
	local _ = Players
end

return VehicleService
