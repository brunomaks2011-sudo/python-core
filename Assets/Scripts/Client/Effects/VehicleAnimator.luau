--!strict
-- Animates every vehicle near the camera on the client (purely visual):
-- turrets/guns from the replicated per-seat aim (local gunner = no lag),
-- wheels and track sprockets rolling, steering, rotors/propellers, doors,
-- headlights, exhaust and damage smoke/fire.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Util = require(ReplicatedStorage.Shared.Util)
local Net = require(ReplicatedStorage.Shared.Net)
local ClientState = require(script.Parent.Parent.ClientState)

local VehicleAnimator = {}

local SMOKE = "rbxasset://textures/particles/smoke_main.dds"
local FIRE = "rbxasset://textures/particles/fire_main.dds"

type Joint = { m6: Motor6D, kind: string, seat: number?, mode: string?, radius: number, angle: number, side: number }
type Rec = {
	model: Model,
	root: BasePart,
	joints: { Joint },
	aim: { [string]: { seat: number, mode: string } },
	smooth: { [number]: { yaw: number, pitch: number } },
	lights: { Light },
	lamps: { BasePart },
	smoke: ParticleEmitter?,
	fire: ParticleEmitter?,
	exhaust: ParticleEmitter?,
	doorOpenUntil: number,
	rotorDisc: { BasePart },
	lastLights: boolean?,
}

local recs: { [Model]: Rec } = {}
local player = Players.LocalPlayer

local function parseAimMap(s: any): { [string]: { seat: number, mode: string } }
	local out = {}
	if type(s) ~= "string" then
		return out
	end
	for entry in string.gmatch(s, "[^,]+") do
		local name, seat, mode = string.match(entry, "(%w+):(%d+):(%a+)")
		if name and seat and mode then
			out[name] = { seat = tonumber(seat) :: number, mode = mode }
		end
	end
	return out
end

local function emitter(att: Attachment, texture: string, rate: number, color: Color3, size: number, light: number): ParticleEmitter
	local e = Instance.new("ParticleEmitter")
	e.Texture = texture
	e.Rate = rate
	e.Lifetime = NumberRange.new(1.5, 3)
	e.Speed = NumberRange.new(2, 5)
	e.SpreadAngle = Vector2.new(15, 15)
	e.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, size * 0.5), NumberSequenceKeypoint.new(1, size * 2.5) })
	e.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.4), NumberSequenceKeypoint.new(1, 1) })
	e.Color = ColorSequence.new(color)
	e.LightEmission = light
	e.Acceleration = Vector3.new(0, 3, 0)
	e.Enabled = false
	e.Parent = att
	return e
end

local function register(model: Model)
	local root = model:FindFirstChild("Hitbox") :: BasePart?
	if not root then
		return
	end
	local rec: Rec = {
		model = model, root = root, joints = {}, aim = parseAimMap(model:GetAttribute("AimMap")), smooth = {},
		lights = {}, lamps = {}, smoke = nil, fire = nil, exhaust = nil, doorOpenUntil = 0, rotorDisc = {}, lastLights = nil,
	}
	for _, d in model:GetDescendants() do
		if d:IsA("Motor6D") then
			local n = d.Name
			local kind = "other"
			local radius = 1
			local side = 1
			if string.sub(n, 1, 5) == "Wheel" or string.sub(n, 1, 8) == "Sprocket" or string.sub(n, 1, 5) == "Idler" then
				kind = "wheel"
				local g = d.Part1 and d.Part1.Parent
				local best = 0
				if g then
					for _, p in g:GetChildren() do
						if p:IsA("BasePart") and p.Name ~= "Pivot" then
							best = math.max(best, p.Size.Y / 2)
						end
					end
				end
				radius = if best > 0.1 then best else 1.2
				side = if string.find(n, "L") then -1 else 1
			elseif string.sub(n, 1, 5) == "Steer" then
				kind = "steer"
			elseif n == "Rotor" then
				kind = "rotor"
			elseif n == "TailRotor" then
				kind = "tailrotor"
			elseif n == "Prop" then
				kind = "prop"
			elseif string.sub(n, 1, 4) == "Door" then
				kind = "door"
				side = if string.find(n, "R") then 1 else -1
			elseif rec.aim[n] then
				kind = "aim"
			end
			table.insert(rec.joints, { m6 = d, kind = kind, seat = nil, mode = nil, radius = radius, angle = 0, side = side })
		elseif d:IsA("SpotLight") or d:IsA("PointLight") then
			table.insert(rec.lights, d)
		elseif d:IsA("BasePart") then
			if string.sub(d.Name, 1, 8) == "Headlamp" then
				table.insert(rec.lamps, d)
			elseif d:GetAttribute("rotorDisc") then
				table.insert(rec.rotorDisc, d)
			end
		elseif d:IsA("Attachment") then
			if d.Name == "EngineSmoke" then
				rec.smoke = emitter(d, SMOKE, 12, Color3.fromRGB(40, 40, 40), 3, 0)
				rec.fire = emitter(d, FIRE, 25, Color3.fromRGB(255, 140, 50), 2, 1)
			elseif d.Name == "Exhaust" then
				rec.exhaust = emitter(d, SMOKE, 6, Color3.fromRGB(110, 108, 104), 0.8, 0)
			end
		end
	end
	recs[model] = rec
end

local function update(dt: number)
	local camPos = workspace.CurrentCamera.CFrame.Position
	local now = os.clock()
	for model, rec in recs do
		if not model.Parent then
			recs[model] = nil
			continue
		end
		local root = rec.root
		if not root.Parent then
			continue
		end
		if (root.Position - camPos).Magnitude > 900 then
			continue
		end
		local vel = root.AssemblyLinearVelocity
		local cf = root.CFrame
		local fwd = vel:Dot(cf.LookVector)
		local turn = root.AssemblyAngularVelocity.Y
		local engine = model:GetAttribute("Engine") == true
		local destroyed = model:GetAttribute("Destroyed") == true
		local isMine = ClientState.vehicleModel == model
		for _, j in rec.joints do
			local k = j.kind
			if k == "wheel" then
				local v = fwd - turn * j.side * 4
				j.angle -= v / math.max(0.3, j.radius) * dt
				j.m6.Transform = CFrame.Angles(j.angle, 0, 0)
			elseif k == "steer" then
				local steer = if math.abs(fwd) > 1 then math.clamp(turn * 6 / fwd, -0.55, 0.55) else 0
				j.angle += (steer - j.angle) * math.min(1, dt * 8)
				local front = string.find(j.m6.Name, "1") ~= nil
				j.m6.Transform = CFrame.Angles(0, if front then j.angle else -j.angle * 0.5, 0)
			elseif k == "rotor" then
				local spin = if engine and not destroyed then 28 else 0
				j.radius += (spin - j.radius) * math.min(1, dt * 0.4)
				j.angle += j.radius * dt
				j.m6.Transform = CFrame.Angles(0, j.angle, 0)
				for _, disc in rec.rotorDisc do
					disc.Transparency = if j.radius > 12 then 0.88 else 1
				end
			elseif k == "tailrotor" then
				j.angle += (if engine and not destroyed then 60 else 0) * dt
				j.m6.Transform = CFrame.Angles(j.angle, 0, 0)
			elseif k == "prop" then
				j.angle += 60 * dt
				j.m6.Transform = CFrame.Angles(0, 0, j.angle)
			elseif k == "door" then
				local open = rec.doorOpenUntil > now
				local target = if open then -1.2 * j.side else 0
				j.angle += (target - j.angle) * math.min(1, dt * 6)
				j.m6.Transform = CFrame.Angles(0, j.angle, 0)
			elseif k == "aim" then
				local a = rec.aim[j.m6.Name]
				if a then
					local local_ = if isMine and ClientState.seat == a.seat then ClientState.localAim[a.seat] else nil
					local s = rec.smooth[a.seat]
					if not s then
						s = { yaw = 0, pitch = 0 }
						rec.smooth[a.seat] = s
					end
					if local_ then
						s.yaw, s.pitch = local_.yaw, local_.pitch
					else
						local ty = (model:GetAttribute("AimYaw" .. a.seat) :: number?) or 0
						local tp = (model:GetAttribute("AimPitch" .. a.seat) :: number?) or 0
						s.yaw = Util.approachAngle(s.yaw, ty, 3 * dt)
						s.pitch = Util.approach(s.pitch, tp, 2 * dt)
					end
					if a.mode == "yaw" then
						j.m6.Transform = CFrame.Angles(0, s.yaw, 0)
					elseif a.mode == "pitch" then
						j.m6.Transform = CFrame.Angles(s.pitch, 0, 0)
					else
						j.m6.Transform = CFrame.Angles(0, s.yaw, 0) * CFrame.Angles(s.pitch, 0, 0)
					end
				end
			end
		end
		-- lights (also on automatically at night for crewed vehicles)
		local lights = model:GetAttribute("Lights") == true
		if lights ~= rec.lastLights then
			rec.lastLights = lights
			for _, l in rec.lights do
				l.Enabled = lights
			end
			for _, p in rec.lamps do
				p.Material = if lights then Enum.Material.Neon else Enum.Material.Glass
			end
		end
		local dmg = model:GetAttribute("Damage") or 0
		if rec.smoke then
			rec.smoke.Enabled = dmg >= 1 and not destroyed
		end
		if rec.fire then
			rec.fire.Enabled = dmg >= 2 and not destroyed
		end
		if rec.exhaust then
			rec.exhaust.Enabled = engine and not destroyed
			rec.exhaust.Rate = 4 + math.abs(fwd) * 0.3
		end
	end
end

function VehicleAnimator.init()
	local function watch(folder: Instance)
		for _, m in folder:GetChildren() do
			if m:IsA("Model") then
				task.defer(register, m)
			end
		end
		folder.ChildAdded:Connect(function(m)
			if m:IsA("Model") then
				task.wait(0.2)
				register(m)
			end
		end)
	end
	task.spawn(function()
		watch(workspace:WaitForChild("Vehicles"))
	end)
	Net.event("Effect").OnClientEvent:Connect(function(batch)
		if type(batch) ~= "table" then
			return
		end
		for _, e in batch do
			if type(e) == "table" and e.k == "door" then
				for m, rec in recs do
					if m:GetAttribute("VehicleId") == e.v then
						rec.doorOpenUntil = os.clock() + 1.6
					end
				end
			end
		end
	end)
	RunService.RenderStepped:Connect(update)
	local _ = player
end

return VehicleAnimator
