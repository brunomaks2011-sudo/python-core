--!strict
-- Builds the Dolyna Valley voxel terrain from the generated heightmap:
-- terrain materials per cell, asphalt roads painted from the road polylines,
-- river water up to the water level. Runs once at server start in 128x128
-- stud chunks with yields so the server stays responsive.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local MapInfo = require(ReplicatedStorage.Shared.MapInfo)

local TerrainBuilder = {}

local VOXEL = 4
local CHUNK = 32 -- voxels per chunk side (128 studs)

local MATERIAL_COLORS: { [Enum.Material]: Color3 } = {
	[Enum.Material.Grass] = Color3.fromRGB(92, 118, 62),
	[Enum.Material.LeafyGrass] = Color3.fromRGB(70, 96, 48),
	[Enum.Material.Ground] = Color3.fromRGB(112, 92, 68),
	[Enum.Material.Mud] = Color3.fromRGB(78, 64, 50),
	[Enum.Material.Rock] = Color3.fromRGB(118, 116, 110),
	[Enum.Material.Sand] = Color3.fromRGB(178, 164, 128),
	[Enum.Material.Salt] = Color3.fromRGB(196, 170, 98), -- ripe wheat fields
	[Enum.Material.Pavement] = Color3.fromRGB(128, 126, 120),
	[Enum.Material.Concrete] = Color3.fromRGB(140, 140, 136),
	[Enum.Material.Basalt] = Color3.fromRGB(72, 70, 68), -- rail ballast
	[Enum.Material.Asphalt] = Color3.fromRGB(58, 58, 60),
	[Enum.Material.Cobblestone] = Color3.fromRGB(110, 106, 98),
	[Enum.Material.Limestone] = Color3.fromRGB(150, 144, 130),
}

local function materialEnums(names: { string }): { Enum.Material }
	local out = {}
	for i, n in names do
		out[i] = (Enum.Material :: any)[n]
	end
	return out
end

type Seg = { ax: number, az: number, bx: number, bz: number, hw: number }

local function segDist(px: number, pz: number, s: Seg): number
	local abx, abz = s.bx - s.ax, s.bz - s.az
	local len2 = abx * abx + abz * abz
	local t = 0
	if len2 > 1e-6 then
		t = math.clamp(((px - s.ax) * abx + (pz - s.az) * abz) / len2, 0, 1)
	end
	local qx, qz = s.ax + abx * t, s.az + abz * t
	return math.sqrt((px - qx) ^ 2 + (pz - qz) ^ 2)
end

-- Road segments bucketed per chunk so painting is cheap.
local function bucketRoads(info: any, half: number): { [number]: { Seg } }
	local buckets: { [number]: { Seg } } = {}
	local chunkStuds = CHUNK * VOXEL
	local dim = math.ceil(half * 2 / chunkStuds)
	for _, road in info.roads do
		if road.kind == "dirt" then
			continue -- dirt tracks are already in the material map
		end
		local hw = road.width / 2
		local pts = road.pts
		for k = 1, #pts - 1 do
			local a, b = pts[k], pts[k + 1]
			local s: Seg = { ax = a[1], az = a[3], bx = b[1], bz = b[3], hw = hw }
			local x0 = math.floor((math.min(s.ax, s.bx) - hw - 4 + half) / chunkStuds)
			local x1 = math.floor((math.max(s.ax, s.bx) + hw + 4 + half) / chunkStuds)
			local z0 = math.floor((math.min(s.az, s.bz) - hw - 4 + half) / chunkStuds)
			local z1 = math.floor((math.max(s.az, s.bz) + hw + 4 + half) / chunkStuds)
			for cx = math.max(0, x0), math.min(dim - 1, x1) do
				for cz = math.max(0, z0), math.min(dim - 1, z1) do
					local key = cz * dim + cx
					local list = buckets[key]
					if not list then
						list = {}
						buckets[key] = list
					end
					table.insert(list, s)
				end
			end
		end
	end
	return buckets
end

-- Bridge spans: do not pave the river under bridges.
local function bridgeBoxes(info: any): { { x: number, z: number, r: number } }
	local out = {}
	for _, b in info.bridges do
		table.insert(out, { x = b.x, z = b.z, r = b.length * 0.5 })
	end
	return out
end

function TerrainBuilder.build(progress: ((number) -> ())?)
	local info = MapInfo.get()
	local terrain = workspace.Terrain
	terrain:Clear()
	for mat, color in MATERIAL_COLORS do
		terrain:SetMaterialColor(mat, color)
	end
	local mats = materialEnums(info.materials)
	local half = info.half
	local water = info.waterLevel
	local dim = math.ceil(half * 2 / (CHUNK * VOXEL))
	local roads = bucketRoads(info, half)
	local bridges = bridgeBoxes(info)
	local ASPHALT = Enum.Material.Asphalt
	local GROUND = Enum.Material.Ground
	local ROCK = Enum.Material.Rock
	local WATER = Enum.Material.Water
	local AIR = Enum.Material.Air
	local total = dim * dim
	local done = 0
	local startClock = os.clock()

	-- build chunks from the centre outward so the battlefield appears first
	local order = {}
	for cz = 0, dim - 1 do
		for cx = 0, dim - 1 do
			local mx, mz = (cx + 0.5) - dim / 2, (cz + 0.5) - dim / 2
			table.insert(order, { cx = cx, cz = cz, d = mx * mx + mz * mz })
		end
	end
	table.sort(order, function(a, b)
		return a.d < b.d
	end)

	local heights = table.create(CHUNK * CHUNK, 0)
	local columnMat = table.create(CHUNK * CHUNK, GROUND)
	local lastYield = os.clock()
	for _, ch in order do
		local x0 = -half + ch.cx * CHUNK * VOXEL
		local z0 = -half + ch.cz * CHUNK * VOXEL
		local segs = roads[ch.cz * dim + ch.cx]
		local minH, maxH = math.huge, -math.huge
		for i = 0, CHUNK - 1 do
			local x = x0 + i * VOXEL + VOXEL / 2
			for k = 0, CHUNK - 1 do
				local z = z0 + k * VOXEL + VOXEL / 2
				local h = MapInfo.heightAt(x, z)
				local idx = i * CHUNK + k + 1
				heights[idx] = h
				local m = mats[MapInfo.materialIndexAt(x, z) + 1] or GROUND
				if segs then
					for _, s in segs do
						if segDist(x, z, s) <= s.hw then
							local onBridge = false
							for _, b in bridges do
								if (x - b.x) ^ 2 + (z - b.z) ^ 2 < b.r * b.r and h < water + 1 then
									onBridge = true
									break
								end
							end
							if not onBridge then
								m = ASPHALT
							end
							break
						end
					end
				end
				if h < water - 0.5 and m ~= ASPHALT then
					m = if h < water - 4 then ROCK else (if m == Enum.Material.Sand then m else Enum.Material.Mud)
				end
				columnMat[idx] = m
				if h < minH then
					minH = h
				end
				if h > maxH then
					maxH = h
				end
			end
		end
		local yBottom = math.floor((minH - 8) / VOXEL) * VOXEL
		local yTop = math.ceil((math.max(maxH, if minH < water then water else maxH) + VOXEL) / VOXEL) * VOXEL
		-- solid base under the written band
		if yBottom > -40 then
			terrain:FillBlock(
				CFrame.new(x0 + CHUNK * VOXEL / 2, (yBottom - 40) / 2, z0 + CHUNK * VOXEL / 2),
				Vector3.new(CHUNK * VOXEL, yBottom + 40, CHUNK * VOXEL),
				ROCK
			)
		end
		local ny = math.max(1, (yTop - yBottom) // VOXEL)
		local materials = table.create(CHUNK)
		local occupancy = table.create(CHUNK)
		for i = 1, CHUNK do
			local mi = table.create(ny)
			local oi = table.create(ny)
			for j = 1, ny do
				local mj = table.create(CHUNK, AIR)
				local oj = table.create(CHUNK, 0)
				mi[j] = mj
				oi[j] = oj
			end
			materials[i] = mi
			occupancy[i] = oi
			for k = 1, CHUNK do
				local idx = (i - 1) * CHUNK + k
				local h = heights[idx]
				local topMat = columnMat[idx]
				for j = 1, ny do
					local vy = yBottom + (j - 1) * VOXEL
					local fill = (h - vy) / VOXEL
					if fill >= 1 then
						materials[i][j][k] = if h - vy > 10 then (if topMat == ROCK then ROCK else GROUND) else topMat
						occupancy[i][j][k] = 1
					elseif fill > 0 then
						materials[i][j][k] = topMat
						occupancy[i][j][k] = math.max(0.05, fill)
					elseif vy < water then
						materials[i][j][k] = WATER
						occupancy[i][j][k] = math.clamp((water - vy) / VOXEL, 0, 1)
					end
				end
			end
		end
		local region = Region3.new(Vector3.new(x0, yBottom, z0), Vector3.new(x0 + CHUNK * VOXEL, yBottom + ny * VOXEL, z0 + CHUNK * VOXEL))
		terrain:WriteVoxels(region:ExpandToGrid(VOXEL), VOXEL, materials, occupancy)
		done += 1
		if os.clock() - lastYield > 0.05 then
			if progress then
				progress(done / total)
			end
			task.wait()
			lastYield = os.clock()
		end
	end
	if progress then
		progress(1)
	end
	print(string.format("[Terrain] %d chunks in %.1f s", total, os.clock() - startClock))
end

return TerrainBuilder
