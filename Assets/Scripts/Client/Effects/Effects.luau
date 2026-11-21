--!strict
-- Client-side visual effects. Server effect events arrive batched through the
-- "Effect" remote; local shots call the same functions directly for instant
-- feedback. Built-in Roblox particle textures only (no uploads needed).

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Debris = game:GetService("Debris")

local Net = require(ReplicatedStorage.Shared.Net)
local ClientState = require(script.Parent.Parent.ClientState)

local Effects = {}

local SMOKE = "rbxasset://textures/particles/smoke_main.dds"
local FIRE = "rbxasset://textures/particles/fire_main.dds"
local SPARK = "rbxasset://textures/particles/sparkles_main.dds"

local player = Players.LocalPlayer
local folder: Folder
local anchorPart: Part
local emitters: { [string]: ParticleEmitter } = {}
Effects.onSound = nil :: ((name: string, pos: Vector3, volume: number?) -> ())?

local function quality(): number
	local q = ClientState.settings.quality
	return if q == "low" then 0.4 elseif q == "medium" then 0.7 else 1
end

local function makeEmitter(name: string, texture: string, props: { [string]: any }): ParticleEmitter
	local att = Instance.new("Attachment")
	att.Name = name
	att.Parent = anchorPart
	local e = Instance.new("ParticleEmitter")
	e.Texture = texture
	e.Enabled = false
	e.LightEmission = props.light or 0
	e.LightInfluence = props.influence or 1
	e.Lifetime = props.life or NumberRange.new(1, 2)
	e.Speed = props.speed or NumberRange.new(2, 6)
	e.SpreadAngle = props.spread or Vector2.new(180, 180)
	e.Size = props.size or NumberSequence.new(1)
	e.Transparency = props.transparency or NumberSequence.new(0.3, 1)
	e.Color = props.color or ColorSequence.new(Color3.new(1, 1, 1))
	e.Rotation = NumberRange.new(0, 360)
	e.RotSpeed = NumberRange.new(-40, 40)
	e.Acceleration = props.accel or Vector3.zero
	e.Drag = props.drag or 1
	e.ZOffset = props.zoffset or 0
	e.Parent = att
	emitters[name] = e
	return e
end

local function burst(name: string, pos: Vector3, count: number, color: ColorSequence?, dir: Vector3?)
	local e = emitters[name]
	if not e then
		return
	end
	local att = e.Parent :: Attachment
	att.WorldCFrame = if dir then CFrame.lookAt(pos, pos + dir) else CFrame.new(pos)
	if color then
		e.Color = color
	end
	e:Emit(math.max(1, math.floor(count * quality())))
end

-- ---------------------------------------------------------------------------
-- Shots
-- ---------------------------------------------------------------------------
local tracerPool: { Part } = {}
local function tracerPart(): Part
	local p = table.remove(tracerPool)
	if p then
		return p
	end
	local n = Instance.new("Part")
	n.Anchored = true
	n.CanCollide = false
	n.CanQuery = false
	n.CanTouch = false
	n.CastShadow = false
	n.Material = Enum.Material.Neon
	n.Color = Color3.fromRGB(255, 214, 140)
	n.Parent = folder
	return n
end

function Effects.tracer(a: Vector3, b: Vector3, color: Color3?)
	local d = b - a
	local len = d.Magnitude
	if len < 1 then
		return
	end
	-- a short glowing streak travelling along the path
	local p = tracerPart()
	local streak = math.min(18, len * 0.4)
	p.Size = Vector3.new(0.12, 0.12, streak)
	p.Color = color or Color3.fromRGB(255, 214, 140)
	p.Transparency = 0.1
	local speed = 2500
	local t = 0
	local conn: RBXScriptConnection? = nil
	conn = RunService.RenderStepped:Connect(function(dt)
		t += dt
		local dist = math.min(len, t * speed)
		local head = a + d.Unit * dist
		p.CFrame = CFrame.lookAt(head - d.Unit * streak / 2, head)
		if dist >= len then
			if conn then
				conn:Disconnect()
			end
			p.Transparency = 1
			p.CFrame = CFrame.new(0, -1000, 0)
			table.insert(tracerPool, p)
		end
	end)
end

function Effects.muzzle(pos: Vector3, dir: Vector3, big: boolean?)
	burst("muzzle", pos, if big then 14 else 4, nil, dir)
	local light = Instance.new("PointLight")
	light.Brightness = if big then 8 else 3
	light.Range = if big then 30 else 12
	light.Color = Color3.fromRGB(255, 196, 120)
	local att = Instance.new("Attachment")
	att.WorldPosition = pos
	att.Parent = workspace.Terrain
	light.Parent = att
	Debris:AddItem(att, 0.06)
	if big then
		burst("smoke", pos + dir * 4, 8, ColorSequence.new(Color3.fromRGB(150, 146, 140)))
		ClientState.cameraShake:Fire(math.clamp(30 / math.max(5, (workspace.CurrentCamera.CFrame.Position - pos).Magnitude), 0, 0.8))
	end
end

local MAT_COLORS: { [string]: Color3 } = {
	Concrete = Color3.fromRGB(170, 168, 160), Brick = Color3.fromRGB(150, 90, 70), Plaster = Color3.fromRGB(220, 214, 196),
	Wood = Color3.fromRGB(130, 100, 70), WoodPlanks = Color3.fromRGB(130, 100, 70), Grass = Color3.fromRGB(96, 110, 60),
	LeafyGrass = Color3.fromRGB(80, 100, 50), Ground = Color3.fromRGB(120, 100, 76), Mud = Color3.fromRGB(80, 66, 52),
	Sand = Color3.fromRGB(190, 176, 140), Rock = Color3.fromRGB(130, 128, 122), Asphalt = Color3.fromRGB(80, 80, 82),
	Water = Color3.fromRGB(200, 220, 230),
}

function Effects.impact(pos: Vector3, normal: Vector3, mat: string?, soldier: boolean?)
	if soldier then
		burst("hit", pos, 6, ColorSequence.new(Color3.fromRGB(70, 40, 36)), normal)
		return
	end
	local metal = mat == "Metal" or mat == "DiamondPlate" or mat == "CorrodedMetal"
	if metal then
		burst("sparks", pos, 8, nil, normal)
	end
	local c = MAT_COLORS[mat or ""] or Color3.fromRGB(150, 140, 125)
	burst("dust", pos, if metal then 2 else 6, ColorSequence.new(c), normal)
end

-- ---------------------------------------------------------------------------
-- Explosions, debris, glass, burning buildings
-- ---------------------------------------------------------------------------
function Effects.explosion(pos: Vector3, radius: number, big: boolean?)
	local q = quality()
	burst("fireball", pos, (if big then 30 else 16) * 1, nil)
	burst("smoke", pos, (if big then 26 else 14), ColorSequence.new(Color3.fromRGB(60, 56, 52), Color3.fromRGB(120, 116, 110)))
	burst("sparks", pos, if big then 40 else 18, nil, Vector3.yAxis)
	burst("dust", pos, if big then 30 else 14, ColorSequence.new(Color3.fromRGB(130, 116, 96)), Vector3.yAxis)
	local att = Instance.new("Attachment")
	att.WorldPosition = pos + Vector3.new(0, 2, 0)
	att.Parent = workspace.Terrain
	local light = Instance.new("PointLight")
	light.Brightness = if big then 14 else 8
	light.Range = math.clamp(radius * 2.5, 20, 60)
	light.Color = Color3.fromRGB(255, 170, 90)
	light.Parent = att
	task.spawn(function()
		for i = 1, 8 do
			light.Brightness *= 0.6
			task.wait(0.03)
			local _ = i
		end
		att:Destroy()
	end)
	-- lingering smoke column
	if q > 0.5 then
		local col = Instance.new("Attachment")
		col.WorldPosition = pos
		col.Parent = workspace.Terrain
		local e = Instance.new("ParticleEmitter")
		e.Texture = SMOKE
		e.Rate = if big then 14 else 7
		e.Lifetime = NumberRange.new(5, 9)
		e.Speed = NumberRange.new(3, 7)
		e.SpreadAngle = Vector2.new(20, 20)
		e.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 4), NumberSequenceKeypoint.new(1, if big then 26 else 16) })
		e.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.55), NumberSequenceKeypoint.new(1, 1) })
		e.Color = ColorSequence.new(Color3.fromRGB(56, 54, 52))
		e.Acceleration = Vector3.new(1.5, 2, 1)
		e.Parent = col
		task.delay(if big then 6 else 3, function()
			e.Enabled = false
		end)
		Debris:AddItem(col, 16)
	end
	local cam = workspace.CurrentCamera
	local d = (cam.CFrame.Position - pos).Magnitude
	ClientState.cameraShake:Fire(math.clamp(radius * 6 / math.max(10, d), 0, 1.4))
	if Effects.onSound then
		Effects.onSound(if big then "explosion_big" else "explosion", pos, 1)
	end
end

function Effects.debris(pos: Vector3, size: Vector3, mat: string?, blast: boolean?)
	local c = if mat == "brick" then Color3.fromRGB(150, 100, 80) elseif mat == "wood" then Color3.fromRGB(120, 96, 70) else Color3.fromRGB(176, 170, 160)
	local n = math.clamp(size.Magnitude, 6, 30)
	burst("dust", pos, n, ColorSequence.new(c), Vector3.yAxis)
	burst("bigdust", pos, n * 0.6, ColorSequence.new(c))
	if Effects.onSound then
		Effects.onSound("debris", pos, if blast then 1 else 0.7)
	end
end

function Effects.glass(pos: Vector3, size: Vector3)
	burst("glass", pos, 14, nil, Vector3.new(0, -1, 0))
	if Effects.onSound then
		Effects.onSound("glass", pos, 0.8)
	end
	local _ = size
end

local burning: { [number]: Model } = {}
function Effects.buildingStage(id: number, stage: number, pos: Vector3, size: Vector3)
	if stage < 3 then
		return
	end
	local m = burning[id]
	if not m then
		local nm = Instance.new("Model")
		nm.Name = "Burning" .. id
		nm.Parent = folder
		burning[id] = nm
		m = nm
	end
	m:ClearAllChildren()
	local part = Instance.new("Part")
	part.Anchored = true
	part.CanCollide = false
	part.CanQuery = false
	part.Transparency = 1
	part.Size = Vector3.new(size.X * 0.7, 1, size.Z * 0.7)
	part.CFrame = CFrame.new(pos + Vector3.new(0, size.Y * 0.2, 0))
	part.Parent = m
	local smoke = Instance.new("ParticleEmitter")
	smoke.Texture = SMOKE
	smoke.Rate = (if stage == 3 then 3 elseif stage == 4 then 7 else 10) * quality()
	smoke.Lifetime = NumberRange.new(8, 14)
	smoke.Speed = NumberRange.new(4, 9)
	smoke.SpreadAngle = Vector2.new(12, 12)
	smoke.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 6), NumberSequenceKeypoint.new(1, 32) })
	smoke.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.5), NumberSequenceKeypoint.new(1, 1) })
	smoke.Color = ColorSequence.new(Color3.fromRGB(46, 44, 42), Color3.fromRGB(90, 88, 84))
	smoke.Acceleration = Vector3.new(2, 1.5, 1.2)
	smoke.Parent = part
	if stage >= 4 then
		local fire = Instance.new("ParticleEmitter")
		fire.Texture = FIRE
		fire.LightEmission = 1
		fire.Rate = (if stage == 4 then 10 else 18) * quality()
		fire.Lifetime = NumberRange.new(0.8, 1.6)
		fire.Speed = NumberRange.new(3, 6)
		fire.SpreadAngle = Vector2.new(25, 25)
		fire.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 4), NumberSequenceKeypoint.new(1, 1) })
		fire.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.2), NumberSequenceKeypoint.new(1, 1) })
		fire.Color = ColorSequence.new(Color3.fromRGB(255, 180, 80), Color3.fromRGB(255, 80, 30))
		fire.Parent = part
		local light = Instance.new("PointLight")
		light.Color = Color3.fromRGB(255, 140, 60)
		light.Brightness = 3
		light.Range = 30
		light.Parent = part
		task.delay(120 + math.random() * 60, function()
			fire.Enabled = false
			light.Enabled = false
		end)
	end
end

-- ---------------------------------------------------------------------------
-- Projectiles (simulated locally from the launch event)
-- ---------------------------------------------------------------------------
type Proj = { part: BasePart, vel: Vector3, g: number, t: number, stuck: boolean, trail: ParticleEmitter? }
local projectiles: { [number]: Proj } = {}

local function projectileVisual(kind: string): (BasePart, ParticleEmitter?)
	local p = Instance.new("Part")
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	local trail: ParticleEmitter? = nil
	if kind == "throw" or kind == "grenade" then
		p.Shape = Enum.PartType.Ball
		p.Size = Vector3.new(0.5, 0.5, 0.5)
		p.Color = Color3.fromRGB(70, 80, 60)
		p.Material = Enum.Material.Metal
	elseif kind == "shell" then
		p.Size = Vector3.new(0.35, 0.35, 3)
		p.Material = Enum.Material.Neon
		p.Color = Color3.fromRGB(255, 200, 120)
	else
		p.Size = Vector3.new(0.5, 0.5, 2.5)
		p.Material = Enum.Material.Metal
		p.Color = Color3.fromRGB(80, 86, 80)
		local att = Instance.new("Attachment")
		att.Position = Vector3.new(0, 0, 1.4)
		att.Parent = p
		local e = Instance.new("ParticleEmitter")
		e.Texture = SMOKE
		e.Rate = 60 * quality()
		e.Lifetime = NumberRange.new(1.5, 3)
		e.Speed = NumberRange.new(0.5, 1.5)
		e.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 1), NumberSequenceKeypoint.new(1, 4) })
		e.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.4), NumberSequenceKeypoint.new(1, 1) })
		e.Color = ColorSequence.new(Color3.fromRGB(200, 196, 190))
		e.Parent = att
		local f = Instance.new("ParticleEmitter")
		f.Texture = FIRE
		f.LightEmission = 1
		f.Rate = 80
		f.Lifetime = NumberRange.new(0.05, 0.12)
		f.Speed = NumberRange.new(0, 1)
		f.Size = NumberSequence.new(0.9, 0.2)
		f.Color = ColorSequence.new(Color3.fromRGB(255, 200, 120))
		f.Parent = att
		trail = e
	end
	p.Parent = folder
	return p, trail
end

local function spawnProjectile(e: { [string]: any })
	local kind = tostring(e.t or "shell")
	local part, trail = projectileVisual(kind)
	part.CFrame = CFrame.new(e.o)
	projectiles[e.id] = { part = part, vel = e.v, g = e.g or workspace.Gravity, t = 0, stuck = false, trail = trail }
	if kind ~= "throw" and kind ~= "grenade" and Effects.onSound then
		Effects.onSound(if kind == "shell" then "tank_gun" else "rocket", e.o, 0.9)
	end
end

local function endProjectile(id: number)
	local p = projectiles[id]
	if not p then
		return
	end
	projectiles[id] = nil
	if p.trail then
		p.trail.Enabled = false
		p.part.Transparency = 1
		Debris:AddItem(p.part, 3)
	else
		p.part:Destroy()
	end
end

-- ---------------------------------------------------------------------------
function Effects.handle(e: { [string]: any })
	local k = e.k
	if k == "tracer" then
		if e.sid ~= player:GetAttribute("SoldierId") then
			Effects.tracer(e.a, e.b)
			Effects.muzzle(e.a, (e.b - e.a).Unit, false)
			if Effects.onSound then
				Effects.onSound(e.w or "rifle", e.a, 1)
			end
		end
	elseif k == "impact" then
		Effects.impact(e.p, e.n or Vector3.yAxis, e.m, e.s)
	elseif k == "explosion" then
		Effects.explosion(e.p, e.r or 10, e.big)
	elseif k == "debris" then
		Effects.debris(e.p, e.sz or Vector3.one, e.m, e.blast)
	elseif k == "glass" then
		Effects.glass(e.p, e.sz or Vector3.one)
	elseif k == "fall" then
		Effects.debris(e.p, e.sz or Vector3.one, e.m, false)
	elseif k == "stage" then
		Effects.buildingStage(e.b, e.s, e.p, e.sz)
	elseif k == "muzzle" then
		Effects.muzzle(e.p, e.d or Vector3.zAxis, e.big)
		if Effects.onSound and e.w then
			Effects.onSound(e.w, e.p, 1)
		end
	elseif k == "proj" then
		spawnProjectile(e)
	elseif k == "projStick" then
		local p = projectiles[e.id]
		if p then
			p.stuck = true
			p.part.CFrame = CFrame.new(e.p)
		end
	elseif k == "projEnd" then
		endProjectile(e.id)
	end
end

function Effects.init()
	folder = Instance.new("Folder")
	folder.Name = "LocalEffects"
	folder.Parent = workspace
	anchorPart = Instance.new("Part")
	anchorPart.Name = "EffectAnchor"
	anchorPart.Anchored = true
	anchorPart.CanCollide = false
	anchorPart.CanQuery = false
	anchorPart.Transparency = 1
	anchorPart.Size = Vector3.one
	anchorPart.Parent = folder
	makeEmitter("muzzle", FIRE, { light = 1, life = NumberRange.new(0.04, 0.08), speed = NumberRange.new(5, 12), spread = Vector2.new(12, 12), size = NumberSequence.new(1.2, 0.4), color = ColorSequence.new(Color3.fromRGB(255, 210, 140)) })
	makeEmitter("hit", SMOKE, { life = NumberRange.new(0.2, 0.5), speed = NumberRange.new(2, 6), spread = Vector2.new(30, 30), size = NumberSequence.new(0.6, 1.4) })
	makeEmitter("dust", SMOKE, { life = NumberRange.new(0.5, 1.4), speed = NumberRange.new(3, 9), spread = Vector2.new(40, 40), size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.8), NumberSequenceKeypoint.new(1, 3) }), accel = Vector3.new(0, -6, 0), drag = 2 })
	makeEmitter("bigdust", SMOKE, { life = NumberRange.new(3, 6), speed = NumberRange.new(2, 6), size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 4), NumberSequenceKeypoint.new(1, 14) }), transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.4), NumberSequenceKeypoint.new(1, 1) }), accel = Vector3.new(0, 1, 0), drag = 1.5 })
	makeEmitter("sparks", SPARK, { light = 1, life = NumberRange.new(0.2, 0.6), speed = NumberRange.new(14, 30), spread = Vector2.new(50, 50), size = NumberSequence.new(0.3, 0.05), color = ColorSequence.new(Color3.fromRGB(255, 200, 100)), accel = Vector3.new(0, -40, 0) })
	makeEmitter("fireball", FIRE, { light = 1, life = NumberRange.new(0.3, 0.7), speed = NumberRange.new(6, 18), size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 4), NumberSequenceKeypoint.new(1, 9) }), color = ColorSequence.new(Color3.fromRGB(255, 220, 140), Color3.fromRGB(255, 90, 30)), transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0), NumberSequenceKeypoint.new(1, 1) }) })
	makeEmitter("smoke", SMOKE, { life = NumberRange.new(2, 4), speed = NumberRange.new(4, 10), size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 3), NumberSequenceKeypoint.new(1, 12) }), transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.3), NumberSequenceKeypoint.new(1, 1) }), accel = Vector3.new(0, 3, 0), drag = 1.2 })
	makeEmitter("glass", SPARK, { life = NumberRange.new(0.6, 1.2), speed = NumberRange.new(4, 10), size = NumberSequence.new(0.25, 0.1), color = ColorSequence.new(Color3.fromRGB(200, 230, 240)), accel = Vector3.new(0, -50, 0) })
	Net.event("Effect").OnClientEvent:Connect(function(batch)
		if type(batch) ~= "table" then
			return
		end
		for _, e in batch do
			if type(e) == "table" then
				local ok, err = pcall(Effects.handle :: any, e)
				if not ok then
					warn("[Effects] " .. tostring(err))
				end
			end
		end
	end)
	RunService.RenderStepped:Connect(function(dt)
		for id, p in projectiles do
			if p.stuck then
				continue
			end
			p.t += dt
			local nv = p.vel - Vector3.new(0, p.g * dt, 0)
			local pos = p.part.Position + (p.vel + nv) * 0.5 * dt
			p.vel = nv
			if nv.Magnitude > 0.1 then
				p.part.CFrame = CFrame.lookAt(pos, pos + nv)
			end
			if p.t > 20 then
				endProjectile(id)
			end
		end
	end)
end

return Effects
