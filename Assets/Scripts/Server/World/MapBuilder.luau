--!strict
-- Builds the battlefield's structures from the map description and the
-- Blender-made kit/models: buildings (destructible, structural graph), props,
-- fences, bridges, railway, road markings, power lines, vegetation, HQ camps
-- and the three control-point flags. Can be rebuilt on match restart.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Rig = require(ReplicatedStorage.Shared.Rig)
local Constants = require(ReplicatedStorage.Shared.Constants)
local BuildingLayout = require(script.Parent.BuildingLayout)
local DestructionService = require(script.Parent.Parent.Game.DestructionService)

local MapBuilder = {}

local modelIndex: { [string]: Model } = {}
local root: Folder? = nil
local folders: { [string]: Folder } = {}
MapBuilder.flags = {} :: { [string]: Model }
MapBuilder.hqFlags = {} :: { [number]: Model }
MapBuilder.propsByKind = {} :: { [string]: { Model } }
MapBuilder.launchPlatform = nil :: Model?
MapBuilder.treeDensity = 1

local PLASTER_TINTS = {
	Color3.fromRGB(222, 210, 168), Color3.fromRGB(204, 214, 196), Color3.fromRGB(214, 196, 186), Color3.fromRGB(196, 206, 216),
	Color3.fromRGB(228, 222, 206), Color3.fromRGB(218, 196, 150), Color3.fromRGB(190, 200, 170), Color3.fromRGB(230, 214, 196),
}

local PROP_MODELS: { [string]: string } = {
	streetlight = "Streetlight", power_pole = "PowerPole", road_sign = "RoadSign", bus_stop = "BusStop", bench = "Bench",
	car_wreck = "CarWreck", tank_wreck = "TankWreck", haystack = "Haystack", concrete_barrier = "ConcreteBarrier",
	tank_trap = "TankTrap", sandbag_wall = "SandbagWall", sandbag_ring = "SandbagRing", bunker = "Bunker",
	crate_stack = "CrateStack", fuel_barrels = "FuelBarrels", container_stack = "ContainerStack", transformer = "Transformer",
	chem_tank = "ChemTank", pipe_rack = "PipeRack", gas_pump = "GasPump", fuel_canopy = "FuelCanopy", watchtower = "Watchtower",
	water_tower = "WaterTower", chimney = "Chimney", radar = "Radar", radar_mobile = "RadarMobile", comms_tower = "CommsTower",
	fuel_tank = "FuelTank", supply_depot = "SupplyDepot", helipad = "Helipad", launch_platform = "LaunchPlatform", tent = "Tent",
	tent_large = "TentLarge", command_tent = "CommandTent", flagpole_hq = "HQFlag", gate_barrier = "GateBarrier",
	guardhouse = "Guardhouse", rail_car = "RailCar", locomotive = "Locomotive", rail_platform = "RailPlatform",
	monument = "Monument", shed = "Shed", well = "Well", woodpile = "Woodpile", rock = "Rock", rock_large = "RockLarge",
}
-- destruction behaviour, durability class and hit points per prop kind
local PROP_DESTRUCT: { [string]: { b: string, m: string, hp: number } } = {
	streetlight = { b = "fall", m = "metal", hp = 160 }, power_pole = { b = "fall", m = "wood", hp = 220 }, road_sign = { b = "fall", m = "metal", hp = 60 },
	bus_stop = { b = "debris", m = "metal", hp = 260 }, bench = { b = "debris", m = "wood", hp = 80 }, car_wreck = { b = "debris", m = "metal", hp = 600 },
	car_civilian = { b = "explode", m = "metal", hp = 300 }, tank_wreck = { b = "debris", m = "steel", hp = 5000 }, haystack = { b = "debris", m = "hay", hp = 150 },
	concrete_barrier = { b = "debris", m = "concrete", hp = 700 }, tank_trap = { b = "debris", m = "steel", hp = 900 }, sandbag_wall = { b = "debris", m = "sand", hp = 900 },
	sandbag_ring = { b = "debris", m = "sand", hp = 900 }, bunker = { b = "debris", m = "concrete", hp = 3500 }, crate_stack = { b = "debris", m = "wood", hp = 220 },
	fuel_barrels = { b = "explode", m = "metal", hp = 60 }, container = { b = "debris", m = "metal", hp = 1500 }, container_stack = { b = "debris", m = "metal", hp = 2500 },
	transformer = { b = "explode", m = "metal", hp = 400 }, chem_tank = { b = "debris", m = "metal", hp = 1200 }, pipe_rack = { b = "debris", m = "steel", hp = 900 },
	gas_pump = { b = "explode", m = "metal", hp = 120 }, fuel_canopy = { b = "debris", m = "metal", hp = 900 }, watchtower = { b = "fall", m = "wood", hp = 900 },
	water_tower = { b = "fall", m = "concrete", hp = 6000 }, chimney = { b = "fall", m = "brick", hp = 4500 }, radar = { b = "debris", m = "metal", hp = 1300 },
	radar_mobile = { b = "debris", m = "metal", hp = 900 }, comms_tower = { b = "fall", m = "steel", hp = 1400 }, fuel_tank = { b = "explode", m = "metal", hp = 1600 },
	supply_depot = { b = "debris", m = "wood", hp = 700 }, tent = { b = "debris", m = "canvas", hp = 120 }, tent_large = { b = "debris", m = "canvas", hp = 200 },
	command_tent = { b = "debris", m = "canvas", hp = 220 }, gate_barrier = { b = "debris", m = "metal", hp = 40 }, guardhouse = { b = "debris", m = "concrete", hp = 900 },
	rail_car = { b = "debris", m = "steel", hp = 3000 }, locomotive = { b = "debris", m = "steel", hp = 4000 }, monument = { b = "debris", m = "concrete", hp = 1500 },
	shed = { b = "debris", m = "wood", hp = 300 }, well = { b = "debris", m = "concrete", hp = 600 }, woodpile = { b = "debris", m = "wood", hp = 200 },
	launch_platform = { b = "debris", m = "steel", hp = 2200 },
}

local function indexModels()
	if next(modelIndex) then
		return
	end
	local assets = ReplicatedStorage:WaitForChild("Assets"):WaitForChild("Models")
	for _, d in assets:GetDescendants() do
		if d:IsA("Model") and d:FindFirstChild("Pivot") and d:GetAttribute("Category") then
			modelIndex[d.Name] = d
		end
	end
end

function MapBuilder.model(name: string): Model?
	indexModels()
	return modelIndex[name]
end

local function folder(name: string): Folder
	local f = folders[name]
	if f and f.Parent then
		return f
	end
	local nf = Instance.new("Folder")
	nf.Name = name
	nf.Parent = root
	folders[name] = nf
	return nf
end

local function ground(x: number, z: number): number
	return MapInfo.heightAt(x, z)
end

local function place(name: string, cf: CFrame, parent: Instance, collide: boolean?): Model?
	local template = MapBuilder.model(name)
	if not template then
		warn("[MapBuilder] missing model " .. name)
		return nil
	end
	local m = template:Clone()
	Rig.anchorAll(m, collide)
	m:PivotTo(cf)
	m.Parent = parent
	return m
end

local function teamTint(m: Model, team: number?)
	if team and team > 0 then
		Rig.tint(m, "Team", Constants.TEAM_COLOR[team])
	end
end

-- ---------------------------------------------------------------------------
-- Buildings
-- ---------------------------------------------------------------------------
local function buildBuilding(b: { [string]: any }, archetypes: { [string]: any })
	local arch = archetypes[b.arch]
	if not arch then
		return
	end
	local style = b.style or arch.style
	local pieces, size = BuildingLayout.generate(arch, style, b.seed or 1)
	local model = Instance.new("Model")
	model.Name = b.arch .. "_" .. b.id
	local origin = CFrame.new(b.x, b.y, b.z) * CFrame.Angles(0, b.yaw, 0)
	local tint = PLASTER_TINTS[((b.seed or 1) % #PLASTER_TINTS) + 1]
	-- foundation (indestructible): hides the terrain seam
	local foundation = Instance.new("Part")
	foundation.Name = "Foundation"
	foundation.Anchored = true
	foundation.Size = Vector3.new(size.X + 0.6, 4, size.Z + 0.6)
	foundation.CFrame = origin * CFrame.new(0, BuildingLayout.SLAB - 2, 0)
	foundation.Material = Enum.Material.Concrete
	foundation.Color = Color3.fromRGB(120, 118, 112)
	foundation.TopSurface = Enum.SurfaceType.Smooth
	foundation.Parent = model
	local instances: { [number]: Instance } = {}
	for idx, p in pieces do
		local cf = origin * p.cf
		if p.kit then
			local template = MapBuilder.model(p.kit)
			if template then
				local m = template:Clone()
				Rig.anchorAll(m, true)
				m:PivotTo(cf)
				if style == "plaster" then
					for _, d in m:GetDescendants() do
						if d:IsA("BasePart") and string.sub(d.Name, 1, 4) == "Wall" then
							d.Color = tint
						end
					end
				end
				m.Parent = model
				instances[idx] = m
			end
		elseif p.size then
			local part: BasePart
			if p.shape == "wedge" then
				part = Instance.new("WedgePart")
			else
				part = Instance.new("Part")
			end
			part.Anchored = true
			part.Size = p.size
			part.CFrame = cf
			part.Material = p.material or Enum.Material.Concrete
			part.Color = p.color or (if style == "plaster" then tint else Color3.fromRGB(160, 160, 154))
			part.TopSurface = Enum.SurfaceType.Smooth
			part.BottomSurface = Enum.SurfaceType.Smooth
			part.Name = p.kind
			part.Parent = model
			instances[idx] = part
		end
	end
	model:SetAttribute("Arch", b.arch)
	model:SetAttribute("Zone", b.zone)
	model.PrimaryPart = foundation
	model.Parent = folder("Structures")
	local rec = DestructionService.registerBuilding(model, pieces, instances, b.arch)
	if b.preDamage and b.preDamage >= 2 then
		DestructionService.preDamage(rec, b.preDamage, function(cf: CFrame)
			local v = math.random(0, 2)
			local r = place("Rubble" .. v, CFrame.new(cf.Position.X, ground(cf.Position.X, cf.Position.Z), cf.Position.Z) * cf.Rotation, folder("Structures"), true)
			if r then
				r.Name = "Rubble"
			end
		end)
	end
end

-- ---------------------------------------------------------------------------
-- Bridges: deck spans on pillars, destructible (cuts the crossing)
-- ---------------------------------------------------------------------------
local function buildBridge(br: { [string]: any })
	local model = Instance.new("Model")
	model.Name = br.id
	local origin = CFrame.new(br.x, br.deckY, br.z) * CFrame.Angles(0, br.yaw, 0)
	local spans = math.max(3, math.floor(br.length / 24 + 0.5))
	local spanLen = br.length / spans
	local layout: { BuildingLayout.Piece } = {}
	local instances: { [number]: Instance } = {}
	local pillarIdx: { [number]: number } = {}
	local function part(kind: string, size: Vector3, cf: CFrame, mat: Enum.Material, color: Color3, shape: string?): Part
		local p = Instance.new("Part")
		if shape == "cyl" then
			p.Shape = Enum.PartType.Cylinder
		end
		p.Anchored = true
		p.Size = size
		p.CFrame = cf
		p.Material = mat
		p.Color = color
		p.TopSurface = Enum.SurfaceType.Smooth
		p.BottomSurface = Enum.SurfaceType.Smooth
		p.Name = kind
		p.Parent = model
		return p
	end
	-- pillars between spans (grounded in the river bed)
	for k = 1, spans - 1 do
		local localZ = -br.length / 2 + k * spanLen
		local cf = origin * CFrame.new(0, 0, localZ)
		local bottom = ground(cf.Position.X, cf.Position.Z) - 4
		local h = br.deckY - bottom
		local p = part("pillar", Vector3.new(br.width * 0.7, h, 4), origin * CFrame.new(0, -h / 2 - 0.8, localZ), Enum.Material.Concrete, Color3.fromRGB(140, 140, 134))
		table.insert(layout, { kind = "column", cf = CFrame.identity, mat = "concrete", hp = 2600, supports = {}, lateral = {}, grounded = true, row = 0, structural = true } :: any)
		instances[#layout] = p
		pillarIdx[k] = #layout
	end
	-- deck spans
	for k = 0, spans - 1 do
		local localZ = -br.length / 2 + (k + 0.5) * spanLen
		local deck = part("deck", Vector3.new(br.width, 1.6, spanLen - 0.3), origin * CFrame.new(0, -0.8, localZ), if br.kind == "rail" then Enum.Material.Concrete else Enum.Material.Asphalt, if br.kind == "rail" then Color3.fromRGB(130, 128, 122) else Color3.fromRGB(64, 64, 66))
		local beam = part("deckBeam", Vector3.new(br.width - 2, 1.6, spanLen - 0.3), origin * CFrame.new(0, -2.4, localZ), Enum.Material.Concrete, Color3.fromRGB(136, 134, 128))
		local railL = part("railing", Vector3.new(0.4, 2.4, spanLen - 0.3), origin * CFrame.new(-br.width / 2 + 0.2, 1.2, localZ), Enum.Material.Metal, Color3.fromRGB(110, 114, 112))
		local railR = part("railing", Vector3.new(0.4, 2.4, spanLen - 0.3), origin * CFrame.new(br.width / 2 - 0.2, 1.2, localZ), Enum.Material.Metal, Color3.fromRGB(110, 114, 112))
		local g = Instance.new("Model")
		g.Name = "Span" .. k
		for _, p in { deck, beam, railL, railR } do
			p.Parent = g
		end
		g.Parent = model
		local sup: { number } = {}
		if pillarIdx[k] then
			table.insert(sup, pillarIdx[k])
		end
		if pillarIdx[k + 1] then
			table.insert(sup, pillarIdx[k + 1])
		end
		local grounded = k == 0 or k == spans - 1
		table.insert(layout, { kind = "slab", cf = CFrame.identity, mat = "concrete", hp = 2200, supports = sup, lateral = {}, grounded = grounded, row = 1, structural = true } :: any)
		instances[#layout] = g
	end
	model.PrimaryPart = nil
	model.Parent = folder("Structures")
	DestructionService.registerBuilding(model, layout, instances, "bridge")
end

-- ---------------------------------------------------------------------------
-- Railway, road markings, power lines
-- ---------------------------------------------------------------------------
local function buildRail(info: { [string]: any })
	local f = Instance.new("Model")
	f.Name = "Railway"
	local pts = info.rail.pts
	local gauge = info.rail.gauge or 4.5
	local acc = 0
	local nextSleeper = 0
	for k = 1, #pts - 1 do
		local a = Vector3.new(pts[k][1], pts[k][2] + 1.3, pts[k][3])
		local b = Vector3.new(pts[k + 1][1], pts[k + 1][2] + 1.3, pts[k + 1][3])
		if math.abs(a.X) > 3000 or math.abs(a.Z) > 3000 then
			continue
		end
		local seg = b - a
		local len = seg.Magnitude
		if len < 0.01 then
			continue
		end
		local cf = CFrame.lookAt(a + seg / 2, b)
		for _, s in { -1, 1 } do
			local r = Instance.new("Part")
			r.Anchored = true
			r.Size = Vector3.new(0.45, 0.55, len + 0.05)
			r.CFrame = cf * CFrame.new(s * gauge / 2, 0.55, 0)
			r.Material = Enum.Material.Metal
			r.Color = Color3.fromRGB(96, 88, 80)
			r.Name = "Rail"
			r.Parent = f
		end
		while nextSleeper <= acc + len do
			local t = (nextSleeper - acc) / len
			local pos = a + seg * t
			local sl = Instance.new("Part")
			sl.Anchored = true
			sl.Size = Vector3.new(gauge + 3, 0.5, 1.0)
			sl.CFrame = CFrame.lookAt(pos, pos + seg)
			sl.Material = Enum.Material.Wood
			sl.Color = Color3.fromRGB(70, 56, 44)
			sl.CanCollide = false
			sl.Name = "Sleeper"
			sl.Parent = f
			nextSleeper += 7.5
		end
		acc += len
	end
	f.Parent = folder("Roads")
end

local function buildRoadMarkings(info: { [string]: any })
	local f = Instance.new("Model")
	f.Name = "RoadMarkings"
	for _, road in info.roads do
		if road.kind ~= "highway" and road.kind ~= "road" then
			continue
		end
		local pts = road.pts
		local acc = 0
		local nextDash = 0
		for k = 1, #pts - 1 do
			local a = Vector3.new(pts[k][1], pts[k][2], pts[k][3])
			local b = Vector3.new(pts[k + 1][1], pts[k + 1][2], pts[k + 1][3])
			local seg = b - a
			local len = seg.Magnitude
			if len < 0.01 or math.abs(a.X) > 2600 or math.abs(a.Z) > 2600 then
				acc += len
				continue
			end
			while nextDash <= acc + len do
				local t = (nextDash - acc) / len
				local pos = a + seg * t
				local y = MapInfo.heightAt(pos.X, pos.Z)
				local onBridge = false
				for _, br in info.bridges do
					if (pos.X - br.x) ^ 2 + (pos.Z - br.z) ^ 2 < (br.length * 0.55) ^ 2 then
						onBridge = true
						y = br.deckY
					end
				end
				local d = Instance.new("Part")
				d.Anchored = true
				d.CanCollide = false
				d.CanQuery = false
				d.CastShadow = false
				d.Size = Vector3.new(0.45, 0.06, 9)
				d.CFrame = CFrame.lookAt(Vector3.new(pos.X, y + (if onBridge then 0.05 else 0.25), pos.Z), Vector3.new(pos.X, y, pos.Z) + Vector3.new(seg.X, 0, seg.Z))
				d.Material = Enum.Material.SmoothPlastic
				d.Color = Color3.fromRGB(214, 214, 206)
				d.Name = "Dash"
				d.Parent = f
				nextDash += 30
			end
			acc += len
		end
	end
	f.Parent = folder("Roads")
end

local function buildPowerLines(info: { [string]: any }, poles: { [string]: Model })
	for _, p in info.props do
		if p.type ~= "power_line" then
			continue
		end
		local list = p.poles
		for k = 1, #list - 1 do
			local a, b = poles[list[k]], poles[list[k + 1]]
			if a and b then
				for w = 0, 2 do
					local wa = Rig.findAttachment(a, "Wire" .. w)
					local wb = Rig.findAttachment(b, "Wire" .. w)
					if wa and wb then
						local beam = Instance.new("Beam")
						beam.Attachment0 = wa
						beam.Attachment1 = wb
						beam.Width0 = 0.12
						beam.Width1 = 0.12
						beam.Color = ColorSequence.new(Color3.fromRGB(40, 40, 40))
						beam.Transparency = NumberSequence.new(0)
						beam.CurveSize0 = -6
						beam.CurveSize1 = 6
						beam.Segments = 12
						beam.FaceCamera = true
						beam.LightInfluence = 1
						beam.Parent = a
					end
				end
			end
		end
	end
end

-- ---------------------------------------------------------------------------
-- Fences: clone a 3 m kit segment along each polyline
-- ---------------------------------------------------------------------------
local FENCE_MODEL = { wood = "Fence_wood", picket = "Fence_picket", metal = "Fence_metal", concrete = "Fence_concrete", military = "Fence_military" }
local FENCE_MAT = { wood = { m = "wood", hp = 90 }, picket = { m = "wood", hp = 70 }, metal = { m = "metal", hp = 160 }, concrete = { m = "concrete", hp = 600 }, military = { m = "metal", hp = 220 } }

local function buildFences(info: { [string]: any })
	local f = folder("Props")
	for _, fence in info.fences do
		local name = FENCE_MODEL[fence.kind] or "Fence_wood"
		local fm = FENCE_MAT[fence.kind] or FENCE_MAT.wood
		local pts = fence.pts
		for k = 1, #pts - 1 do
			local ax, az, bx, bz = pts[k][1], pts[k][2], pts[k + 1][1], pts[k + 1][2]
			local len = math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2)
			local n = math.max(1, math.floor(len / 9 + 0.5))
			for s = 0, n - 1 do
				local t = (s + 0.5) / n
				local x, z = ax + (bx - ax) * t, az + (bz - az) * t
				local y = ground(x, z)
				-- fence kit spans local X; LookVector perpendicular to the segment
				local cf = CFrame.lookAt(Vector3.new(x, y, z), Vector3.new(x, y, z) + Vector3.new(-(bz - az), 0, bx - ax))
				local m = place(name, cf, f, true)
				if m then
					if n > 1 or len / 9 > 1.1 then
						m:ScaleTo(math.max(0.5, (len / n) / 9))
					end
					DestructionService.registerProp(m, "fence", fm.m, fm.hp, "debris")
				end
			end
		end
	end
end

-- ---------------------------------------------------------------------------
-- Vegetation
-- ---------------------------------------------------------------------------
local TREE_MODELS = { [0] = "Tree_pine", [1] = "Tree_spruce", [2] = "Tree_birch", [3] = "Tree_oak", [4] = "Tree_poplar", [5] = "Tree_willow", [6] = "Tree_fruit" }

local function buildVegetation(density: number)
	local veg = MapInfo.vegetation()
	if not veg then
		return
	end
	local f = folder("Vegetation")
	local info = MapInfo.get()
	local pl = info.playable
	local count = 0
	for i, t in veg.trees do
		local inside = t.x > pl.minX - 150 and t.x < pl.maxX + 150 and t.z > pl.minZ - 150 and t.z < pl.maxZ + 150
		-- thin the scenery forest outside the battlefield
		if not inside and (i % 2 == 0) then
			continue
		end
		if density < 1 and (i % 100) >= density * 100 then
			continue
		end
		local name = TREE_MODELS[t.type] or "Tree_oak"
		local y = ground(t.x, t.z) - 0.5
		local m = place(name, CFrame.new(t.x, y, t.z) * CFrame.Angles(0, t.yaw, 0), f, true)
		if m then
			if math.abs(t.scale - 1) > 0.05 then
				m:ScaleTo(t.scale)
			end
			if inside then
				DestructionService.registerProp(m, "tree", "wood", 260 * t.scale, "fall")
			end
			count += 1
		end
		if count % 400 == 0 then
			task.wait()
		end
	end
	for i, bsh in veg.bushes do
		if density < 1 and (i % 100) >= density * 100 then
			continue
		end
		local m = place("Bush_" .. (bsh.type % 3), CFrame.new(bsh.x, ground(bsh.x, bsh.z) - 0.3, bsh.z) * CFrame.Angles(0, bsh.yaw, 0), f, false)
		if m and math.abs(bsh.scale - 1) > 0.05 then
			m:ScaleTo(bsh.scale)
		end
		if i % 500 == 0 then
			task.wait()
		end
	end
	print("[MapBuilder] trees placed: " .. count)
end

-- ---------------------------------------------------------------------------
-- Props, flags
-- ---------------------------------------------------------------------------
local function buildProps(info: { [string]: any }): { [string]: Model }
	local f = folder("Props")
	local poles: { [string]: Model } = {}
	MapBuilder.propsByKind = {}
	for i, p in info.props do
		local name = PROP_MODELS[p.type]
		if p.type == "car_civilian" then
			name = "Car" .. ((p.variant or 0) % 4)
		elseif p.type == "container" then
			name = "Container" .. (i % 3)
		elseif p.type == "rubble_pile" then
			name = "Rubble" .. (i % 3)
		end
		if not name then
			continue
		end
		local y = ground(p.x, p.z)
		local cf = CFrame.new(p.x, y, p.z) * CFrame.Angles(0, (p.yaw or 0) + math.pi, 0)
		local m = place(name, cf, f, true)
		if not m then
			continue
		end
		m:SetAttribute("PropKind", p.type)
		if p.team then
			m:SetAttribute("Team", p.team)
			teamTint(m, p.team)
		end
		if p.type == "power_pole" then
			poles[p.id] = m
		elseif p.type == "road_sign" and p.text then
			local board = m:FindFirstChild("Board", true)
			if board and board:IsA("BasePart") then
				local gui = Instance.new("SurfaceGui")
				gui.Face = Enum.NormalId.Front
				gui.PixelsPerStud = 40
				gui.LightInfluence = 1
				local label = Instance.new("TextLabel")
				label.Size = UDim2.fromScale(1, 1)
				label.BackgroundTransparency = 1
				label.Text = p.text
				label.TextScaled = true
				label.Font = Enum.Font.GothamBold
				label.TextColor3 = Color3.new(1, 1, 1)
				label.Parent = gui
				gui.Parent = board
				local back = gui:Clone()
				back.Face = Enum.NormalId.Back
				back.Parent = board
			end
		elseif p.type == "flagpole_hq" and p.team then
			MapBuilder.hqFlags[p.team] = m
			m.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
		elseif p.type == "launch_platform" then
			MapBuilder.launchPlatform = m
		end
		local list = MapBuilder.propsByKind[p.type]
		if not list then
			list = {}
			MapBuilder.propsByKind[p.type] = list
		end
		table.insert(list, m)
		local d = PROP_DESTRUCT[p.type]
		if d then
			DestructionService.registerProp(m, p.type, d.m, d.hp, d.b)
		end
		if i % 80 == 0 then
			task.wait()
		end
	end
	return poles
end

local function buildFlags(info: { [string]: any })
	local f = folder("Flags")
	for _, pt in info.points do
		local y = ground(pt.x, pt.z)
		local m = place("ControlPointFlag", CFrame.new(pt.x, y - 0.3, pt.z), f, true)
		if m then
			m.Name = "Flag_" .. pt.id
			m:SetAttribute("PointId", pt.id)
			-- always present on every client (StreamingEnabled), whatever the distance
			m.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
			MapBuilder.flags[pt.id] = m
			-- zone boundary markers (recoloured by the client by owner)
			local markers = Instance.new("Model")
			markers.Name = "ZoneMarkers"
			for k = 0, 23 do
				local a = k / 24 * math.pi * 2
				local x, z = pt.x + math.cos(a) * pt.radius, pt.z + math.sin(a) * pt.radius
				local gy = ground(x, z)
				local post = Instance.new("Part")
				post.Anchored = true
				post.CanCollide = false
				post.CanQuery = false
				post.Size = Vector3.new(0.5, 3, 0.5)
				post.CFrame = CFrame.new(x, gy + 1.4, z)
				post.Material = Enum.Material.Metal
				post.Color = Color3.fromRGB(70, 70, 70)
				post.Name = "Post"
				post.Parent = markers
				local cap = Instance.new("Part")
				cap.Anchored = true
				cap.CanCollide = false
				cap.CanQuery = false
				cap.Size = Vector3.new(0.7, 0.5, 0.7)
				cap.CFrame = CFrame.new(x, gy + 3.1, z)
				cap.Material = Enum.Material.Neon
				cap.Color = Constants.TEAM_COLOR[0]
				cap.Name = "Cap"
				cap.Parent = markers
			end
			markers.Parent = m
			-- billboard letter above the flag
			local bb = Instance.new("BillboardGui")
			bb.Name = "PointLabel"
			bb.Size = UDim2.fromOffset(60, 60)
			bb.StudsOffsetWorldSpace = Vector3.new(0, 52, 0)
			bb.AlwaysOnTop = true
			bb.MaxDistance = 3000
			bb.LightInfluence = 0
			local frame = Instance.new("TextLabel")
			frame.Name = "Letter"
			frame.Size = UDim2.fromScale(1, 1)
			frame.BackgroundColor3 = Constants.TEAM_COLOR[0]
			frame.BackgroundTransparency = 0.25
			frame.Text = pt.id
			frame.TextScaled = true
			frame.Font = Enum.Font.GothamBlack
			frame.TextColor3 = Color3.new(1, 1, 1)
			local corner = Instance.new("UICorner")
			corner.CornerRadius = UDim.new(0.5, 0)
			corner.Parent = frame
			frame.Parent = bb
			bb.Parent = m.PrimaryPart
		end
	end
end

-- ---------------------------------------------------------------------------
-- Entry points
-- ---------------------------------------------------------------------------
function MapBuilder.buildStatic(progress: ((string, number) -> ())?)
	indexModels()
	root = workspace:FindFirstChild("Map") :: Folder?
	if not root then
		local r = Instance.new("Folder")
		r.Name = "Map"
		r.Parent = workspace
		root = r
	end
	local info = MapInfo.get()
	if progress then
		progress("Laying railway and roads", 0)
	end
	buildRail(info)
	buildRoadMarkings(info)
	if progress then
		progress("Raising flags", 0.9)
	end
	buildFlags(info)
end

-- Destructible structures (rebuilt on match restart).
function MapBuilder.buildStructures(progress: ((string, number) -> ())?)
	indexModels()
	local info = MapInfo.get()
	local structures = folder("Structures")
	structures:ClearAllChildren()
	folder("Props"):ClearAllChildren()
	folder("Debris"):ClearAllChildren()
	folder("Vegetation"):ClearAllChildren()
	DestructionService.reset()
	local archetypes = info.archetypes
	for i, b in info.buildings do
		buildBuilding(b, archetypes)
		if progress then
			progress("Building " .. (b.zone or "") .. " structures", i / #info.buildings * 0.7)
		end
		task.wait()
	end
	for _, br in info.bridges do
		buildBridge(br)
	end
	if progress then
		progress("Placing equipment and props", 0.75)
	end
	local poles = buildProps(info)
	buildPowerLines(info, poles)
	buildFences(info)
	if progress then
		progress("Planting forests", 0.85)
	end
	buildVegetation(MapBuilder.treeDensity)
	if progress then
		progress("Ready", 1)
	end
end

function MapBuilder.debrisFolder(): Folder
	return folder("Debris")
end

function MapBuilder.structuresFolder(): Folder
	return folder("Structures")
end

function MapBuilder.root(): Folder
	return root :: Folder
end

return MapBuilder
