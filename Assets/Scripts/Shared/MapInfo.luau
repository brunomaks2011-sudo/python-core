--!strict
-- Decodes the generated Dolyna Valley map data (ReplicatedStorage.MapData) and
-- answers spatial queries: terrain height, terrain material, vegetation.
-- All values are in studs.

local Util = require(script.Parent.Util)

local MapInfo = {}

export type Info = { [string]: any }

local info: Info? = nil
local heights: buffer? = nil
local materials: buffer? = nil
local vegetation: { trees: { any }, bushes: { any } }? = nil

local N = 0
local HALF = 0
local CELL = 0
local HMIN = 0
local HRANGE = 1

local function concatChunks(folder: Instance, prefix: string, count: number): string
	local parts = table.create(count)
	for i = 1, count do
		local name = string.format("%s%02d", prefix, i)
		local mod = folder:FindFirstChild(name)
		assert(mod and mod:IsA("ModuleScript"), "missing map chunk " .. name)
		parts[i] = (require :: any)(mod) :: string
	end
	return table.concat(parts)
end

-- Load from the Rojo-built MapData folder (Roblox runtime).
function MapInfo.load(): Info
	if info then
		return info
	end
	local ReplicatedStorage = game:GetService("ReplicatedStorage")
	local HttpService = game:GetService("HttpService")
	local folder = ReplicatedStorage:WaitForChild("MapData")
	local raw = (require :: any)(folder:WaitForChild("Info")) :: string
	local decoded = HttpService:JSONDecode(raw)
	MapInfo.fromData(decoded, function(prefix, count)
		return concatChunks(folder, prefix, count)
	end, function()
		return (require :: any)(folder:WaitForChild("Vegetation")) :: string
	end)
	return info :: Info
end

-- Generic loader (also used by Lune tests).
function MapInfo.fromData(decoded: Info, chunkReader: (string, number) -> string, vegReader: () -> string)
	info = decoded
	local d = decoded
	N = d.heightRes
	HALF = d.half
	CELL = d.cell
	HMIN = d.heightMin
	HRANGE = (d.heightMax - d.heightMin) / 65535
	heights = Util.base64ToBuffer(chunkReader("Height", d.heightChunks))
	materials = Util.base64ToBuffer(chunkReader("Material", d.materialChunks))
	local vb = Util.base64ToBuffer(vegReader())
	local nT = buffer.readu32(vb, 0)
	local nB = buffer.readu32(vb, 4)
	local trees, bushes = table.create(nT), table.create(nB)
	local off = 8
	local function rec()
		local x = buffer.readi16(vb, off)
		local z = buffer.readi16(vb, off + 2)
		local t = buffer.readu8(vb, off + 4)
		local s = buffer.readu8(vb, off + 5) / 100
		local yaw = buffer.readu8(vb, off + 6) / 255 * math.pi * 2
		off += 7
		return { x = x, z = z, type = t, scale = s, yaw = yaw }
	end
	for i = 1, nT do
		trees[i] = rec()
	end
	for i = 1, nB do
		bushes[i] = rec()
	end
	vegetation = { trees = trees, bushes = bushes }
end

function MapInfo.get(): Info
	return info or MapInfo.load()
end

local function rawHeight(i: number, j: number): number
	if i < 0 then
		i = 0
	elseif i > N - 1 then
		i = N - 1
	end
	if j < 0 then
		j = 0
	elseif j > N - 1 then
		j = N - 1
	end
	return HMIN + buffer.readu16(heights :: buffer, (j * N + i) * 2) * HRANGE
end
MapInfo.rawHeight = rawHeight

function MapInfo.gridSize(): number
	return N
end

function MapInfo.cellSize(): number
	return CELL
end

function MapInfo.half(): number
	return HALF
end

-- Terrain surface height (studs) at world x,z (bilinear on the generated grid).
function MapInfo.heightAt(x: number, z: number): number
	local fx = (x + HALF) / CELL
	local fz = (z + HALF) / CELL
	local i = math.floor(fx)
	local j = math.floor(fz)
	local tx = fx - i
	local tz = fz - j
	local a = rawHeight(i, j)
	local b = rawHeight(i + 1, j)
	local c = rawHeight(i, j + 1)
	local d = rawHeight(i + 1, j + 1)
	return (a + (b - a) * tx) + ((c + (d - c) * tx) - (a + (b - a) * tx)) * tz
end

function MapInfo.normalAt(x: number, z: number): Vector3
	local e = CELL
	local hl, hr = MapInfo.heightAt(x - e, z), MapInfo.heightAt(x + e, z)
	local hd, hu = MapInfo.heightAt(x, z - e), MapInfo.heightAt(x, z + e)
	return Vector3.new(hl - hr, 2 * e, hd - hu).Unit
end

-- Terrain material index (see info.materials) of the grid cell containing x,z.
function MapInfo.materialIndexAt(x: number, z: number): number
	local i = math.clamp(math.floor((x + HALF) / CELL + 0.5), 0, N - 1)
	local j = math.clamp(math.floor((z + HALF) / CELL + 0.5), 0, N - 1)
	local c = j * N + i
	local byte = buffer.readu8(materials :: buffer, c // 2)
	return if c % 2 == 1 then bit32.rshift(byte, 4) else bit32.band(byte, 15)
end

function MapInfo.vegetation()
	return vegetation
end

function MapInfo.isPlayable(x: number, z: number): boolean
	local p = MapInfo.get().playable
	return x >= p.minX and x <= p.maxX and z >= p.minZ and z <= p.maxZ
end

function MapInfo.pointDefs(): { { [string]: any } }
	return MapInfo.get().points
end

return MapInfo
