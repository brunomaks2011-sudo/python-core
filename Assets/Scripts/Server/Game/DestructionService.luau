--!strict
-- Destructible environment.
--
-- * Buildings are made of kit pieces with a structural support graph
--   (World/BuildingLayout). Damaged pieces crack (stage 2), destroyed pieces
--   become physical debris, unsupported pieces collapse progressively.
-- * Building damage stages: 1 intact, 2 cracks/broken windows, 3 holes and
--   falling debris, 4 partial collapse, 5 destroyed (ruin + rubble).
-- * Props: fall (poles, trees, chimneys), explode (cars, barrels, fuel), or
--   break into debris (fences, sandbags, crates, tents).
-- * Destruction is persistent for the whole match; MapBuilder rebuilds the
--   structures on match restart.
-- * Performance: limited live debris, debris settles and is re-anchored,
--   tiny fragments are culled, oldest rubble is trimmed past a budget.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local PhysicsService = game:GetService("PhysicsService")

local Defs = require(ReplicatedStorage.Shared.Defs)
local BuildingLayout = require(script.Parent.Parent.World.BuildingLayout)
local EffectsBus = require(script.Parent.EffectsBus)

local DestructionService = {}

export type PieceRec = {
	id: number,
	inst: Instance,
	parts: { BasePart },
	mat: string,
	kind: string,
	hp: number,
	maxHp: number,
	alive: boolean,
	behavior: string, -- "building" | "glass" | "fall" | "explode" | "debris"
	building: BuildingRec?,
	index: number?, -- index in the building layout
	center: Vector3,
	size: Vector3,
	cracked: boolean,
	propKind: string?,
}

export type BuildingRec = {
	id: number,
	model: Model,
	layout: { BuildingLayout.Piece },
	ids: { [number]: number }, -- layout index -> piece id
	alive: { boolean },
	stage: number,
	structuralTotal: number,
	destroyedStructural: number,
	collapsed: boolean,
	damagedAny: boolean,
	name: string,
	center: Vector3,
	size: Vector3,
}

local pieces: { [number]: PieceRec } = {}
local buildings: { [number]: BuildingRec } = {}
local nextPiece = 0
local nextBuilding = 0
local structuresFolder: Folder? = nil
local debrisFolder: Folder? = nil

type Debris = { part: BasePart, t: number, settled: boolean }
local liveDebris: { Debris } = {}
local settledDebris: { BasePart } = {}
local collapseQueue: { { id: number, at: number } } = {}

local MAX_LIVE_DEBRIS = 700
local MAX_SETTLED_DEBRIS = 6000
local SETTLE_TIME = 7

DestructionService.onExplode = nil :: ((pos: Vector3, radius: number, damage: number, source: string) -> ())?
DestructionService.onBuildingStage = nil :: ((BuildingRec, number) -> ())?

local MATERIAL_COLORS_DEBRIS = {
	concrete = Color3.fromRGB(150, 148, 142),
	brick = Color3.fromRGB(140, 74, 56),
}

-- ---------------------------------------------------------------------------
-- Setup
-- ---------------------------------------------------------------------------
local function ensureGroup(name: string)
	local ok = pcall(function()
		PhysicsService:RegisterCollisionGroup(name)
	end)
	return ok
end

function DestructionService.init(structures: Folder, debris: Folder)
	structuresFolder = structures
	debrisFolder = debris
	ensureGroup("Debris")
	ensureGroup("Soldiers")
	ensureGroup("Vehicles")
	PhysicsService:CollisionGroupSetCollidable("Debris", "Soldiers", false)
	PhysicsService:CollisionGroupSetCollidable("Debris", "Debris", true)
	RunService.Heartbeat:Connect(DestructionService.step)
end

local function collectParts(inst: Instance): { BasePart }
	local out = {}
	if inst:IsA("BasePart") then
		table.insert(out, inst)
	end
	for _, d in inst:GetDescendants() do
		if d:IsA("BasePart") and d.Name ~= "Pivot" then
			table.insert(out, d)
		end
	end
	return out
end

local function boundsOf(parts: { BasePart }): (Vector3, Vector3)
	local mn = Vector3.new(math.huge, math.huge, math.huge)
	local mx = -mn
	for _, p in parts do
		local half = p.Size * 0.5
		local cf = p.CFrame
		-- conservative AABB of the oriented box
		local ext = Vector3.new(
			math.abs(cf.RightVector.X) * half.X + math.abs(cf.UpVector.X) * half.Y + math.abs(cf.LookVector.X) * half.Z,
			math.abs(cf.RightVector.Y) * half.X + math.abs(cf.UpVector.Y) * half.Y + math.abs(cf.LookVector.Y) * half.Z,
			math.abs(cf.RightVector.Z) * half.X + math.abs(cf.UpVector.Z) * half.Y + math.abs(cf.LookVector.Z) * half.Z
		)
		mn = mn:Min(cf.Position - ext)
		mx = mx:Max(cf.Position + ext)
	end
	if mn.X == math.huge then
		return Vector3.zero, Vector3.one
	end
	return (mn + mx) / 2, mx - mn
end

local function newPiece(inst: Instance, mat: string, kind: string, hp: number, behavior: string): PieceRec
	nextPiece += 1
	local parts = collectParts(inst)
	local center, size = boundsOf(parts)
	local rec: PieceRec = {
		id = nextPiece, inst = inst, parts = parts, mat = mat, kind = kind, hp = hp, maxHp = hp, alive = true,
		behavior = behavior, building = nil, index = nil, center = center, size = size, cracked = false, propKind = nil,
	}
	inst:SetAttribute("PieceId", nextPiece)
	pieces[nextPiece] = rec
	return rec
end

function DestructionService.registerBuilding(model: Model, layout: { BuildingLayout.Piece }, instances: { [number]: Instance }, name: string): BuildingRec
	nextBuilding += 1
	local b: BuildingRec = {
		id = nextBuilding, model = model, layout = layout, ids = {}, alive = table.create(#layout, true), stage = 1,
		structuralTotal = 0, destroyedStructural = 0, collapsed = false, damagedAny = false, name = name,
		center = Vector3.zero, size = Vector3.zero,
	}
	for idx, p in layout do
		local inst = instances[idx]
		if inst then
			local rec = newPiece(inst, p.mat, p.kind, p.hp, if p.kind == "glass" then "glass" else "building")
			rec.building = b
			rec.index = idx
			b.ids[idx] = rec.id
			if p.structural then
				b.structuralTotal += 1
			end
		else
			b.alive[idx] = false
		end
	end
	local pv = model:GetPivot()
	local _, size = model:GetBoundingBox()
	b.center = pv.Position + Vector3.new(0, size.Y / 2, 0)
	b.size = size
	model:SetAttribute("BuildingId", b.id)
	model:SetAttribute("Stage", 1)
	buildings[b.id] = b
	return b
end

function DestructionService.registerProp(inst: Instance, propKind: string, mat: string, hp: number, behavior: string): PieceRec
	local rec = newPiece(inst, mat, "prop", hp, behavior)
	rec.propKind = propKind
	return rec
end

function DestructionService.get(id: number): PieceRec?
	return pieces[id]
end

function DestructionService.buildings(): { [number]: BuildingRec }
	return buildings
end

-- ---------------------------------------------------------------------------
-- Debris
-- ---------------------------------------------------------------------------
local function addDebris(part: BasePart, impulse: Vector3)
	part.Anchored = false
	part.CanCollide = true
	part.CanTouch = false
	part.CanQuery = part.Size.Magnitude > 3
	part.CollisionGroup = "Debris"
	part.Massless = false
	part:SetAttribute("PieceId", nil)
	part.Parent = debrisFolder
	part.AssemblyLinearVelocity = impulse + Vector3.new(math.random() * 6 - 3, math.random() * 6, math.random() * 6 - 3)
	part.AssemblyAngularVelocity = Vector3.new(math.random() * 6 - 3, math.random() * 6 - 3, math.random() * 6 - 3)
	table.insert(liveDebris, { part = part, t = os.clock(), settled = false })
end

-- Split a large slab-like part into a grid of chunks so walls crumble instead
-- of falling as one plank.
local function fragment(part: BasePart, impulse: Vector3, budget: number): number
	local s = part.Size
	local nx = math.clamp(math.floor(s.X / 3.5), 1, 3)
	local ny = math.clamp(math.floor(s.Y / 3.5), 1, 3)
	local nz = math.clamp(math.floor(s.Z / 3.5), 1, 3)
	if part:IsA("WedgePart") or nx * ny * nz <= 1 or budget <= 1 then
		addDebris(part, impulse)
		return 1
	end
	local count = 0
	local cs = Vector3.new(s.X / nx, s.Y / ny, s.Z / nz)
	for i = 0, nx - 1 do
		for j = 0, ny - 1 do
			for k = 0, nz - 1 do
				if count >= budget then
					break
				end
				local off = Vector3.new((i + 0.5) * cs.X - s.X / 2, (j + 0.5) * cs.Y - s.Y / 2, (k + 0.5) * cs.Z - s.Z / 2)
				local c = Instance.new("Part")
				c.Size = cs * (0.86 + math.random() * 0.1)
				c.CFrame = part.CFrame * CFrame.new(off) * CFrame.Angles(math.random() * 0.3, math.random() * 0.3, math.random() * 0.3)
				c.Material = part.Material
				c.Color = part.Color
				c.TopSurface = Enum.SurfaceType.Smooth
				c.BottomSurface = Enum.SurfaceType.Smooth
				addDebris(c, impulse)
				count += 1
			end
		end
	end
	part:Destroy()
	return count
end

local function settleDebris(d: Debris)
	local p = d.part
	if not p.Parent then
		return
	end
	p.Anchored = true
	p.CanQuery = p.Size.Magnitude > 4
	p.CanCollide = p.Size.Magnitude > 2.5
	table.insert(settledDebris, p)
	if #settledDebris > MAX_SETTLED_DEBRIS then
		local old = table.remove(settledDebris, 1)
		if old then
			old:Destroy()
		end
	end
end

-- ---------------------------------------------------------------------------
-- Building stages
-- ---------------------------------------------------------------------------
local function setStage(b: BuildingRec, stage: number)
	if stage <= b.stage then
		return
	end
	b.stage = stage
	b.model:SetAttribute("Stage", stage)
	EffectsBus.push({ k = "stage", b = b.id, s = stage, p = b.center, sz = b.size })
	if DestructionService.onBuildingStage then
		DestructionService.onBuildingStage(b, stage)
	end
end

local function evaluateBuilding(b: BuildingRec)
	local frac = if b.structuralTotal > 0 then b.destroyedStructural / b.structuralTotal else 0
	local stage = 1
	if b.damagedAny then
		stage = 2
	end
	if frac >= 0.03 then
		stage = 3
	end
	if frac >= 0.25 or b.collapsed then
		stage = math.max(stage, 4)
	end
	if frac >= 0.55 then
		stage = 5
	end
	setStage(b, stage)
	if stage == 5 and not b.model:GetAttribute("Ruined") then
		b.model:SetAttribute("Ruined", true)
		-- complete destruction: everything above the ground floor comes down,
		-- some ground-floor stubs remain as an unstable ruin
		local now = os.clock()
		for idx, p in b.layout do
			local id = b.ids[idx]
			if id and b.alive[idx] and (p.row >= 1 or math.random() < 0.55) then
				table.insert(collapseQueue, { id = id, at = now + 0.2 + math.random() * 1.6 + p.row * 0.25 })
			end
		end
	end
end

local function structuralCheck(b: BuildingRec)
	local stable = BuildingLayout.stable(b.layout, b.alive)
	local now = os.clock()
	local any = false
	for idx, _ in b.layout do
		if b.alive[idx] and not stable[idx] then
			local id = b.ids[idx]
			if id and pieces[id] and pieces[id].alive and not pieces[id].cracked then
				-- falls after a short creak; higher pieces later (progressive collapse)
				pieces[id].cracked = true
				table.insert(collapseQueue, { id = id, at = now + 0.15 + math.random() * 0.5 + b.layout[idx].row * 0.18 })
				any = true
			end
		end
	end
	if any then
		b.collapsed = true
	end
end

-- ---------------------------------------------------------------------------
-- Damage & destruction
-- ---------------------------------------------------------------------------
local function crackVisual(rec: PieceRec)
	-- darken / scorch the piece and draw a few crack lines on the largest part
	local largest: BasePart? = nil
	for _, p in rec.parts do
		if p.Parent and (not largest or p.Size.Magnitude > largest.Size.Magnitude) then
			largest = p
		end
		if p.Parent and p.Material ~= Enum.Material.Glass then
			p.Color = p.Color:Lerp(Color3.fromRGB(40, 38, 36), 0.18)
		end
	end
	if largest and largest.Size.X > 2 and largest.Size.Y > 2 then
		for _ = 1, 3 do
			local c = Instance.new("Part")
			c.Anchored = true
			c.CanCollide = false
			c.CanQuery = false
			c.CanTouch = false
			c.Material = Enum.Material.SmoothPlastic
			c.Color = Color3.fromRGB(32, 30, 28)
			c.Size = Vector3.new(0.12, math.random() * 3 + 1.5, 0.05)
			local face = if math.random() < 0.5 then -1 else 1
			c.CFrame = largest.CFrame
				* CFrame.new((math.random() - 0.5) * largest.Size.X * 0.7, (math.random() - 0.5) * largest.Size.Y * 0.6, face * (largest.Size.Z / 2 + 0.03))
				* CFrame.Angles(0, 0, (math.random() - 0.5) * 2.2)
			c.Name = "Crack"
			c.Parent = rec.inst
			table.insert(rec.parts, c)
		end
	end
end

local function breakGlass(rec: PieceRec)
	rec.alive = false
	EffectsBus.push({ k = "glass", p = rec.center, sz = rec.size })
	for _, p in rec.parts do
		p:Destroy()
	end
	local b = rec.building
	if b and rec.index then
		b.alive[rec.index] = false
		b.damagedAny = true
		evaluateBuilding(b)
	end
end

local function topple(rec: PieceRec, from: Vector3?)
	-- weld the prop together and let it fall over around its base
	local parts = rec.parts
	if #parts == 0 then
		return
	end
	local base = parts[1]
	for _, p in parts do
		if p.Parent and p.Size.Y > base.Size.Y then
			base = p
		end
	end
	for _, p in parts do
		if p ~= base and p.Parent then
			local w = Instance.new("WeldConstraint")
			w.Part0 = base
			w.Part1 = p
			w.Parent = base
		end
	end
	for _, p in parts do
		if p.Parent then
			p.Anchored = false
			p.CanCollide = true
			p.CollisionGroup = "Debris"
			p.Massless = false
		end
	end
	local dir = if from then (rec.center - from) * Vector3.new(1, 0, 1) else Vector3.new(math.random() - 0.5, 0, math.random() - 0.5)
	if dir.Magnitude < 0.1 then
		dir = Vector3.xAxis
	end
	dir = dir.Unit
	local axis = Vector3.yAxis:Cross(dir)
	base.AssemblyAngularVelocity = axis * 1.6
	base.AssemblyLinearVelocity = dir * 6
	table.insert(liveDebris, { part = base, t = os.clock() - 2, settled = false })
	EffectsBus.push({ k = "fall", p = rec.center, sz = rec.size, m = rec.mat })
end

local function scorch(rec: PieceRec)
	for _, p in rec.parts do
		if p.Parent then
			p.Color = Color3.fromRGB(38, 34, 32):Lerp(p.Color, 0.15)
			if p.Material ~= Enum.Material.Glass then
				p.Material = Enum.Material.CorrodedMetal
			else
				p.Transparency = 1
			end
		end
	end
	local fire = Instance.new("Fire")
	fire.Size = math.clamp(rec.size.Magnitude * 0.6, 4, 16)
	fire.Heat = 12
	fire.Parent = rec.parts[1]
	task.delay(25 + math.random() * 20, function()
		if fire.Parent then
			fire.Enabled = false
			local smoke = Instance.new("Smoke")
			smoke.Size = 8
			smoke.RiseVelocity = 6
			smoke.Opacity = 0.18
			smoke.Color = Color3.fromRGB(50, 50, 50)
			smoke.Parent = fire.Parent
			task.delay(90, function()
				smoke.Enabled = false
			end)
		end
	end)
end

local function destroyPiece(rec: PieceRec, from: Vector3?, cause: string)
	if not rec.alive then
		return
	end
	if rec.behavior == "glass" then
		breakGlass(rec)
		return
	end
	rec.alive = false
	local b = rec.building
	if rec.behavior == "fall" then
		topple(rec, from)
		return
	end
	if rec.behavior == "explode" then
		scorch(rec)
		if DestructionService.onExplode then
			DestructionService.onExplode(rec.center, math.clamp(rec.size.Magnitude * 1.4, 10, 36), 120, "prop")
		end
		EffectsBus.push({ k = "explosion", p = rec.center, r = math.clamp(rec.size.Magnitude, 8, 30), big = rec.size.Magnitude > 12 })
		return
	end
	-- break into physical debris
	local impulseDir = if from then (rec.center - from) else Vector3.new(0, 1, 0)
	if impulseDir.Magnitude < 0.1 then
		impulseDir = Vector3.yAxis
	end
	local strength = if cause == "blast" then 26 elseif cause == "crush" then 10 else 4
	local impulse = impulseDir.Unit * strength
	local budget = math.max(1, MAX_LIVE_DEBRIS - #liveDebris)
	for _, p in rec.parts do
		if p.Parent then
			if p.Name == "Crack" or p.Size.Magnitude < 0.6 or budget <= 0 then
				p:Destroy()
			else
				budget -= fragment(p, impulse, math.min(budget, 8))
			end
		end
	end
	if rec.inst.Parent and rec.inst:IsA("Model") then
		local pv = rec.inst:FindFirstChild("Pivot")
		if pv then
			pv:Destroy()
		end
	end
	EffectsBus.push({ k = "debris", p = rec.center, sz = rec.size, m = rec.mat, blast = cause == "blast" })
	if b and rec.index then
		b.alive[rec.index] = false
		local lp = b.layout[rec.index]
		if lp.structural then
			b.destroyedStructural += 1
		end
		b.damagedAny = true
		-- glass in a destroyed opening goes with it
		for idx, p2 in b.layout do
			if p2.kind == "glass" and b.alive[idx] and table.find(p2.supports, rec.index) then
				local gid = b.ids[idx]
				if gid and pieces[gid] then
					breakGlass(pieces[gid])
				end
			end
		end
		structuralCheck(b)
		evaluateBuilding(b)
	end
end

function DestructionService.damagePiece(id: number, amount: number, kind: string, from: Vector3?): boolean
	local rec = pieces[id]
	if not rec or not rec.alive then
		return false
	end
	local resist = Defs.MaterialResist[rec.mat]
	local mult = 1
	if resist then
		mult = if kind == "bullet" then resist.bullet else resist.blast
	end
	if kind == "crush" then
		mult = if rec.mat == "steel" or rec.mat == "rock" then 0.05 else 1
	end
	local dmg = amount * mult
	if dmg <= 0 then
		return false
	end
	rec.hp -= dmg
	local b = rec.building
	if b and not b.damagedAny then
		b.damagedAny = true
		evaluateBuilding(b)
	end
	if rec.hp <= 0 then
		destroyPiece(rec, from, kind)
		return true
	elseif not rec.cracked and rec.hp < rec.maxHp * 0.55 and rec.behavior == "building" then
		rec.cracked = true
		crackVisual(rec)
	end
	return false
end

-- Area damage from an explosion. Returns number of pieces destroyed.
local overlap = OverlapParams.new()
overlap.FilterType = Enum.RaycastFilterType.Include
function DestructionService.blast(pos: Vector3, radius: number, damage: number): number
	if not structuresFolder then
		return 0
	end
	overlap.FilterDescendantsInstances = { structuresFolder :: Instance }
	local parts = workspace:GetPartBoundsInRadius(pos, radius, overlap)
	local seen: { [number]: number } = {}
	for _, part in parts do
		local cur: Instance? = part
		local id: number? = nil
		for _ = 1, 3 do
			if not cur then
				break
			end
			local v = cur:GetAttribute("PieceId")
			if v then
				id = v :: number
				break
			end
			cur = cur.Parent
		end
		if id then
			-- distance from the blast to the closest point of this part
			local lp = part.CFrame:PointToObjectSpace(pos)
			local h = part.Size / 2
			local clamped = Vector3.new(math.clamp(lp.X, -h.X, h.X), math.clamp(lp.Y, -h.Y, h.Y), math.clamp(lp.Z, -h.Z, h.Z))
			local d = (lp - clamped).Magnitude
			if seen[id] == nil or d < seen[id] then
				seen[id] = d
			end
		end
	end
	local destroyed = 0
	for id, d in seen do
		local falloff = math.clamp(1 - (d / radius) ^ 1.4, 0, 1)
		if falloff > 0 and DestructionService.damagePiece(id, damage * falloff, "blast", pos) then
			destroyed += 1
		end
	end
	return destroyed
end

-- Instantly wreck part of a building at spawn (pre-damaged ruins), without debris physics.
function DestructionService.preDamage(b: BuildingRec, stage: number, spawnRubble: (CFrame) -> ())
	local rng = Random.new(b.id * 7919)
	local targetFrac = ({ [2] = 0.0, [3] = 0.08, [4] = 0.32, [5] = 0.62 })[stage] or 0
	-- break most windows
	for idx, p in b.layout do
		local id = b.ids[idx]
		if id and p.kind == "glass" and rng:NextNumber() < 0.75 then
			local rec = pieces[id]
			rec.alive = false
			b.alive[idx] = false
			for _, part in rec.parts do
				part:Destroy()
			end
		end
	end
	b.damagedAny = true
	-- remove structural pieces, preferring upper storeys and one side
	local candidates = {}
	for idx, p in b.layout do
		if p.structural and b.ids[idx] then
			table.insert(candidates, idx)
		end
	end
	table.sort(candidates, function(a, c)
		return b.layout[a].row > b.layout[c].row
	end)
	local want = math.floor(#candidates * targetFrac)
	local removed = 0
	for _, idx in candidates do
		if removed >= want then
			break
		end
		if rng:NextNumber() < 0.7 then
			local rec = pieces[b.ids[idx]]
			rec.alive = false
			b.alive[idx] = false
			b.destroyedStructural += 1
			removed += 1
			for _, part in rec.parts do
				part:Destroy()
			end
		end
	end
	-- anything left unsupported goes too
	local stable = BuildingLayout.stable(b.layout, b.alive)
	for idx in b.layout do
		if b.alive[idx] and not stable[idx] then
			local rec = pieces[b.ids[idx]]
			if rec then
				rec.alive = false
				for _, part in rec.parts do
					part:Destroy()
				end
			end
			b.alive[idx] = false
			if b.layout[idx].structural then
				b.destroyedStructural += 1
			end
		end
	end
	local n = math.clamp(math.floor(b.size.X * b.size.Z / 300 * targetFrac) + 1, 1, 8)
	local pv = b.model:GetPivot()
	for _ = 1, n do
		spawnRubble(pv * CFrame.new((rng:NextNumber() - 0.5) * b.size.X * 0.8, 0, (rng:NextNumber() - 0.5) * b.size.Z * 0.8) * CFrame.Angles(0, rng:NextNumber() * 6.28, 0))
	end
	b.stage = 1
	evaluateBuilding(b)
end

-- ---------------------------------------------------------------------------
-- Per-frame update
-- ---------------------------------------------------------------------------
function DestructionService.step()
	local now = os.clock()
	-- progressive collapses
	if #collapseQueue > 0 then
		local remaining = {}
		local budget = 25
		for _, c in collapseQueue do
			if c.at <= now and budget > 0 then
				budget -= 1
				local rec = pieces[c.id]
				if rec and rec.alive then
					destroyPiece(rec, rec.center + Vector3.new(0, 6, 0), "collapse")
				end
			else
				table.insert(remaining, c)
			end
		end
		collapseQueue = remaining
	end
	-- settle debris
	if #liveDebris > 0 then
		local keep = {}
		for _, d in liveDebris do
			local p = d.part
			if not p.Parent then
				continue
			end
			local age = now - d.t
			if age > SETTLE_TIME or (age > 2 and p.AssemblyLinearVelocity.Magnitude < 0.4) then
				if p.Size.Magnitude < 1.4 then
					p:Destroy()
				else
					settleDebris(d)
				end
			elseif p.Position.Y < -50 then
				p:Destroy()
			else
				table.insert(keep, d)
			end
		end
		liveDebris = keep
	end
end

-- Forget everything (MapBuilder destroys and rebuilds the instances).
function DestructionService.reset()
	for _, d in liveDebris do
		if d.part.Parent then
			d.part:Destroy()
		end
	end
	for _, p in settledDebris do
		if p.Parent then
			p:Destroy()
		end
	end
	if debrisFolder then
		debrisFolder:ClearAllChildren()
	end
	table.clear(liveDebris)
	table.clear(settledDebris)
	table.clear(collapseQueue)
	table.clear(pieces)
	table.clear(buildings)
	nextPiece = 0
	nextBuilding = 0
end

function DestructionService.stats()
	local destroyed, total = 0, 0
	local stages = { 0, 0, 0, 0, 0 }
	for _, b in buildings do
		total += 1
		stages[b.stage] += 1
		if b.stage >= 4 then
			destroyed += 1
		end
	end
	return { buildings = total, destroyed = destroyed, stages = stages, liveDebris = #liveDebris, settledDebris = #settledDebris }
end

local _ = MATERIAL_COLORS_DEBRIS
return DestructionService
