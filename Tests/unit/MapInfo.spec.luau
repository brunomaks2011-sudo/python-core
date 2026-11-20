-- Verifies the generated map data decodes correctly in Luau (base64 -> buffer,
-- height sampling, materials, vegetation) and matches the generator's output.
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local T = require("../TestLib")
local Shim = require("../RobloxShim")

local MapInfo = Shim.load("Assets/Scripts/Shared/MapInfo")
local Util = Shim.load("Assets/Scripts/Shared/Util")
local DIR = "Assets/Maps/DolynaValley/"

local function readModuleString(name: string): string
	local src = fs.readFile(DIR .. name .. ".luau")
	local s = string.match(src, 'return "([^"]*)"')
	assert(s, "no string in " .. name)
	return s
end

local infoSrc = fs.readFile(DIR .. "Info.luau")
local json = string.match(infoSrc, "%[==%[(.*)%]==%]")
local info = serde.decode("json", json)

local t0 = os.clock()
MapInfo.fromData(info, function(prefix, count)
	local parts = {}
	for i = 1, count do
		parts[i] = readModuleString(string.format("%s%02d", prefix, i))
	end
	return table.concat(parts)
end, function()
	return readModuleString("Vegetation")
end)
local decodeTime = os.clock() - t0

T.test("base64 decoder round-trips known bytes", function()
	local b = Util.base64ToBuffer("TWFu") -- "Man"
	T.eq(buffer.len(b), 3)
	T.eq(buffer.tostring(b), "Man")
	T.eq(buffer.tostring(Util.base64ToBuffer("TWE=")), "Ma")
	T.eq(buffer.tostring(Util.base64ToBuffer("TQ==")), "M")
	T.eq(buffer.tostring(Util.base64ToBuffer("SGVsbG8sIER1bGluYSEgMTIzNDU2Nzg5MA==")), "Hello, Dulina! 1234567890")
end)

T.test("map decodes quickly enough for server start", function()
	T.truthy(decodeTime < 5, "decode took " .. decodeTime .. " s")
end)

T.test("heights match the generator's metre heightmap (x3 studs)", function()
	-- compare with the raw uint16 heightmap written for tools (metres)
	local raw = fs.readFile("Assets/Maps/dolyna_valley/height.bin")
	local n = info.heightRes
	local metaMin, metaMax = info.heightMin / 3, info.heightMax / 3
	for _, ij in { { 0, 0 }, { 512, 512 }, { 100, 900 }, { 1024, 1024 }, { 700, 300 } } do
		local i, j = ij[1], ij[2]
		local lo, hi = string.byte(raw, (j * n + i) * 2 + 1, (j * n + i) * 2 + 2)
		local metres = metaMin + (lo + hi * 256) / 65535 * (metaMax - metaMin)
		T.near(MapInfo.rawHeight(i, j), metres * 3, 0.05, "cell " .. i .. "," .. j)
	end
end)

T.test("control points sit on terrain and inside the playable area", function()
	for _, p in info.points do
		T.truthy(MapInfo.isPlayable(p.x, p.z), p.id .. " playable")
		T.near(MapInfo.heightAt(p.x, p.z), p.y, 3, p.id .. " height")
		T.truthy(p.y > info.waterLevel + 3, p.id .. " above water")
	end
	T.eq(#info.points, 3)
end)

T.test("river channel is below the water level, banks above", function()
	local below = 0
	for _, pt in info.river.pts do
		if math.abs(pt[2]) < 2000 then
			if MapInfo.heightAt(pt[1], pt[2]) < info.waterLevel then
				below += 1
			end
		end
	end
	T.truthy(below > 50, "river cells under water: " .. below)
end)

T.test("materials decode to valid indices", function()
	local counts = {}
	for k = 1, 2000 do
		local x = (k * 37.7) % 6000 - 3000
		local z = (k * 91.3) % 6000 - 3000
		local m = MapInfo.materialIndexAt(x, z)
		T.truthy(m >= 0 and m < #info.materials, "material " .. m)
		counts[m] = (counts[m] or 0) + 1
	end
	T.truthy((counts[0] or 0) + (counts[1] or 0) > 300, "mostly grass")
end)

T.test("vegetation decodes", function()
	local veg = MapInfo.vegetation()
	T.truthy(#veg.trees > 5000)
	T.truthy(#veg.bushes > 500)
	local t = veg.trees[1]
	T.truthy(t.type >= 0 and t.type < #info.treeTypes)
	T.truthy(t.scale > 0.5 and t.scale < 2)
	T.truthy(math.abs(t.x) <= 3072 and math.abs(t.z) <= 3072)
end)

T.test("HQs and vehicle slots are consistent", function()
	T.eq(#info.hqs, 2)
	local perTeam = { [1] = 0, [2] = 0 }
	for _, v in info.vehicleSlots do
		if v.team > 0 then
			perTeam[v.team] += 1
		end
	end
	T.eq(perTeam[1], perTeam[2], "symmetric vehicle rosters")
	T.truthy(#info.hqSpawns["1"] >= 8 and #info.hqSpawns["2"] >= 8)
end)

return nil
