--!strict
-- Driving and gunnery for the local player. The driver's client owns the
-- vehicle's physics and runs VehiclePhysics; gunners aim turrets with the
-- mouse (sent to the server, animated locally without lag).
-- Keys: WASD drive | Space brake / climb | Ctrl descend | Q/E yaw (heli)
--       Mouse aim | LMB fire | 1/2 weapon | C camera | F switch seat | E exit | L lights

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local Rig = require(ReplicatedStorage.Shared.Rig)
local Util = require(ReplicatedStorage.Shared.Util)
local VehiclePhysics = require(ReplicatedStorage.Shared.VehiclePhysics)
local ClientState = require(script.Parent.Parent.ClientState)
local CameraController = require(script.Parent.Parent.Player.CameraController)

local VehicleController = {}

local player = Players.LocalPlayer
local model: Model? = nil
local def: { [string]: any }? = nil
local seat = 0
local phys: VehiclePhysics.State? = nil
local hull: BasePart? = nil
local aimYaw, aimPitch = 0, 0
local camModeIndex = 1
local mouseDown = false
local cooldowns: { [number]: number } = {}
local aimSendAcc = 0
local remotes: { [string]: RemoteEvent } = {}
local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude

-- raycasts from the vehicle ignore the vehicle itself and the local character
local function ignoreList(model: Instance): { Instance }
	local list: { Instance } = { model }
	local char = player.Character
	if char then
		table.insert(list, char)
	end
	return list
end

local function seatDef(): { [string]: any }?
	return def and def.seats[seat]
end

local function seatWeapons(): { any }
	local sd = seatDef()
	return if sd and sd.weapons then sd.weapons else {}
end

local function weaponAt(i: number): { [string]: any }?
	local e = seatWeapons()[i]
	if e == nil or not def then
		return nil
	end
	return if type(e) == "number" then def.weapons[e] else e
end

local function controlsTurret(): boolean
	local aimMap = model and model:GetAttribute("AimMap")
	if type(aimMap) ~= "string" then
		return false
	end
	for entry in string.gmatch(aimMap, "[^,]+") do
		local _, s = string.match(entry, "(%w+):(%d+):")
		if tonumber(s) == seat then
			return true
		end
	end
	return false
end

local function cameraModes(): { string }
	local sd = seatDef()
	local main = if sd then sd.camera or "chase" else "chase"
	if main == "chase" then
		return { "chase", "driver" }
	end
	return { main, "chase" }
end

local function findModel(id: number): Model?
	local folder = workspace:FindFirstChild("Vehicles")
	if not folder then
		return nil
	end
	for _, m in folder:GetChildren() do
		if m:GetAttribute("VehicleId") == id then
			return m :: Model
		end
	end
	return nil
end

-- ---------------------------------------------------------------------------
-- Camera
-- ---------------------------------------------------------------------------
local function vehicleCamera(dt: number, cam: Camera, yaw: number, pitch: number): CFrame?
	if not model or not hull or not hull.Parent then
		return nil
	end
	local mode = cameraModes()[camModeIndex] or "chase"
	ClientState.cameraMode = mode
	local hcf = hull.CFrame
	local look = CFrame.Angles(0, yaw, 0) * CFrame.Angles(pitch, 0, 0)
	if mode == "gunner" or mode == "mg" or mode == "door" then
		local att = Rig.findAttachment(model, "CamGunner") or Rig.findAttachment(model, "CamDriver")
		local pos = if att then att.WorldPosition else hcf.Position + Vector3.new(0, 6, 0)
		if mode ~= "gunner" then
			pos = hcf.Position + hcf.UpVector * (def and def.size.Y or 6) + Vector3.new(0, 3, 0)
		end
		return CFrame.new(pos) * look
	elseif mode == "driver" then
		local att = Rig.findAttachment(model, "CamDriver")
		local pos = if att then att.WorldPosition else hcf.Position + hcf.UpVector * 5
		return CFrame.new(pos) * look
	elseif mode == "artillery" then
		local size = if def then def.size.Magnitude else 30
		local pos = hcf.Position + Vector3.new(0, size * 1.6, 0) - (look.LookVector * Vector3.new(1, 0, 1)).Unit * size * 1.4
		return CFrame.lookAt(pos, pos + look.LookVector)
	end
	-- chase
	local size = if def then def.size.Magnitude else 30
	local offset = look * Vector3.new(0, size * 0.25, size * 1.15)
	local focus = hcf.Position + Vector3.new(0, size * 0.22, 0)
	rayParams.FilterDescendantsInstances = ignoreList(model)
	local hit = workspace:Raycast(focus, offset, rayParams)
	local dist = if hit then math.max(4, (hit.Position - focus).Magnitude - 1) else offset.Magnitude
	return CFrame.new(focus + offset.Unit * dist) * look
end

-- ---------------------------------------------------------------------------
-- Enter / exit
-- ---------------------------------------------------------------------------
function VehicleController.enter(id: number, seatIndex: number, kind: string)
	local m = findModel(id)
	for _ = 1, 20 do
		if m then
			break
		end
		task.wait(0.1)
		m = findModel(id)
	end
	if not m then
		return
	end
	model = m
	def = Defs.Vehicles[kind]
	seat = seatIndex
	hull = m:FindFirstChild("Hitbox") :: BasePart?
	ClientState.vehicleId = id
	ClientState.seat = seatIndex
	ClientState.vehicleKind = kind
	ClientState.vehicleModel = m
	ClientState.vehicleWeapon = 1
	camModeIndex = 1
	local w = weaponAt(1)
	ClientState.weaponName = if w then string.upper(w.name) else string.upper(Defs.vehicleName(kind, ClientState.team))
	if seatIndex == 1 and hull and def then
		local p = VehiclePhysics.bind(hull, def)
		p.engineOn = true
		phys = p
	else
		phys = nil
	end
	-- start aiming where the camera points
	local y, p = CameraController.angles()
	if hull then
		local hy = math.atan2(-hull.CFrame.LookVector.X, -hull.CFrame.LookVector.Z)
		aimYaw = Util.wrapAngle(y - hy)
		aimPitch = p
	end
	CameraController.override = vehicleCamera
end

function VehicleController.exit()
	model = nil
	def = nil
	phys = nil
	hull = nil
	seat = 0
	ClientState.vehicleId = nil
	ClientState.seat = nil
	ClientState.vehicleKind = nil
	ClientState.vehicleModel = nil
	ClientState.localAim = {}
	CameraController.override = nil
end

-- ---------------------------------------------------------------------------
-- Input
-- ---------------------------------------------------------------------------
local function keyDown(k: Enum.KeyCode): boolean
	return UserInputService:IsKeyDown(k)
end

local function readInput(): VehiclePhysics.Input
	local throttle = (if keyDown(Enum.KeyCode.W) then 1 else 0) - (if keyDown(Enum.KeyCode.S) then 1 else 0)
	local steer = (if keyDown(Enum.KeyCode.D) then 1 else 0) - (if keyDown(Enum.KeyCode.A) then 1 else 0)
	local lift = (if keyDown(Enum.KeyCode.Space) then 1 else 0) - (if keyDown(Enum.KeyCode.LeftControl) then 1 else 0)
	local yaw = (if keyDown(Enum.KeyCode.E) and def and def.drive == "heli" then 1 else 0) - (if keyDown(Enum.KeyCode.Q) then 1 else 0)
	return { throttle = throttle, steer = steer, brake = keyDown(Enum.KeyCode.Space) and def ~= nil and def.drive ~= "heli", lift = lift, yaw = yaw }
end

local function fire()
	if not model or not def or not hull then
		return
	end
	local idx = ClientState.vehicleWeapon
	local w = weaponAt(idx)
	if not w then
		return
	end
	local now = os.clock()
	local interval = if w.rpm then 60 / w.rpm else (w.reload or 1)
	if now < (cooldowns[idx] or 0) then
		return
	end
	cooldowns[idx] = now + interval
	local cam = workspace.CurrentCamera
	rayParams.FilterDescendantsInstances = ignoreList(model)
	local res = workspace:Raycast(cam.CFrame.Position, cam.CFrame.LookVector * 3000, rayParams)
	local target = if res then res.Position else cam.CFrame.Position + cam.CFrame.LookVector * 3000
	-- fire along the barrel: hull orientation + local turret aim
	local dir = (hull.CFrame * CFrame.Angles(0, aimYaw, 0) * CFrame.Angles(aimPitch, 0, 0)).LookVector
	if not controlsTurret() then
		dir = (target - hull.Position).Unit
	end
	remotes.VehicleFire:FireServer(idx, dir, target)
	if w.kind ~= "hitscan" then
		ClientState.cameraShake:Fire(0.35)
	end
end

function VehicleController.init()
	for _, n in { "Interact", "VehicleAim", "VehicleFire", "VehicleToggle" } do
		remotes[n] = Net.event(n)
	end
	Net.event("MatchEvent").OnClientEvent:Connect(function(e)
		if type(e) ~= "table" then
			return
		end
		if e.kind == "vehicleEnter" then
			task.spawn(VehicleController.enter, e.id, e.seat, e.vehicle)
		elseif e.kind == "vehicleExit" then
			VehicleController.exit()
		end
	end)
	UserInputService.InputBegan:Connect(function(input, processed)
		if processed or not ClientState.vehicleId then
			return
		end
		local k = input.KeyCode
		if input.UserInputType == Enum.UserInputType.MouseButton1 then
			mouseDown = true
			fire()
		elseif k == Enum.KeyCode.E and not (def and def.drive == "heli" and seat == 1) then
			remotes.Interact:FireServer({ action = "exit" })
		elseif k == Enum.KeyCode.G and def and def.drive == "heli" and seat == 1 then
			remotes.Interact:FireServer({ action = "exit" })
		elseif k == Enum.KeyCode.F then
			if def then
				local nextSeat = (seat % #def.seats) + 1
				remotes.Interact:FireServer({ action = "seat", index = nextSeat })
			end
		elseif k == Enum.KeyCode.C then
			camModeIndex = (camModeIndex % #cameraModes()) + 1
		elseif k == Enum.KeyCode.L then
			remotes.VehicleToggle:FireServer("lights")
		elseif k == Enum.KeyCode.One then
			ClientState.vehicleWeapon = 1
		elseif k == Enum.KeyCode.Two and weaponAt(2) then
			ClientState.vehicleWeapon = 2
		end
		local w = weaponAt(ClientState.vehicleWeapon)
		if w then
			ClientState.weaponName = string.upper(w.name)
		end
	end)
	UserInputService.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 then
			mouseDown = false
		end
	end)
	RunService.Heartbeat:Connect(function(dt)
		if not ClientState.vehicleId or not model then
			return
		end
		if not model.Parent or model:GetAttribute("Destroyed") then
			VehicleController.exit()
			return
		end
		-- driving (we own the physics as the driver)
		if phys and seat == 1 then
			VehiclePhysics.step(phys, readInput(), dt)
		end
		-- turret aim follows the camera, limited by traverse speed
		if hull and controlsTurret() and def then
			local y, p = CameraController.angles()
			local hy = math.atan2(-hull.CFrame.LookVector.X, -hull.CFrame.LookVector.Z)
			local wantYaw = Util.wrapAngle(y - hy)
			local t = def.turret
			local yawSpeed = if t and seat == 1 then t.yawSpeed else 3
			aimYaw = Util.approachAngle(aimYaw, wantYaw, yawSpeed * dt)
			aimPitch = Util.approach(aimPitch, math.clamp(p, if t then t.pitchMin else -0.3, if t then t.pitchMax else 0.8), 1.2 * dt)
			ClientState.localAim[seat] = { yaw = aimYaw, pitch = aimPitch }
			aimSendAcc += dt
			if aimSendAcc > 0.066 then
				aimSendAcc = 0
				remotes.VehicleAim:FireServer(aimYaw, aimPitch)
			end
		end
		-- automatic weapons keep firing while held
		local w = weaponAt(ClientState.vehicleWeapon)
		if mouseDown and w and w.kind == "hitscan" then
			fire()
		end
		if w then
			local interval = if w.rpm then 60 / w.rpm else (w.reload or 1)
			ClientState.vehicleReload = 1 - math.clamp(((cooldowns[ClientState.vehicleWeapon] or 0) - os.clock()) / interval, 0, 1)
		end
	end)
end

return VehicleController
