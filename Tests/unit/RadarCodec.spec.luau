-- The minimap radar must stay under the ~1000-byte limit of unreliable
-- remotes in the biggest battle, and round-trip positions exactly.
local T = require("../TestLib")
local Shim = require("../RobloxShim")

local RadarCodec = Shim.load("Assets/Scripts/Shared/RadarCodec")

local function packet(soldiers: number, vehicles: number, enemies: number, enemyVehicles: number)
	local p = { s = {}, v = {}, e = {}, ev = {} }
	for i = 1, soldiers do
		table.insert(p.s, { -3000 + i * 97, 2900 - i * 61, 1000 + i, i % 2 })
	end
	for i = 1, vehicles do
		table.insert(p.v, { i * 40, -i * 40 })
	end
	for i = 1, enemies do
		table.insert(p.e, { -i * 33, i * 17 })
	end
	for i = 1, enemyVehicles do
		table.insert(p.ev, { i * 11, i * 13 })
	end
	return p
end

T.test("round-trips positions, ids and vehicle flags exactly", function()
	local p = packet(20, 8, 6, 3)
	local d = RadarCodec.decode(RadarCodec.encode(p))
	T.truthy(d, "decodes")
	T.eq(#d.s, 20)
	T.eq(#d.v, 8)
	T.eq(#d.e, 6)
	T.eq(#d.ev, 3)
	for i, e in p.s do
		T.eq(d.s[i][1], e[1], "x")
		T.eq(d.s[i][2], e[2], "z")
		T.eq(d.s[i][3], e[3], "id")
		T.eq(d.s[i][4], e[4], "in vehicle")
	end
	T.eq(d.ev[3][1], 33)
	T.eq(d.ev[3][2], 39)
end)

T.test("rounds to whole studs and clamps to int16", function()
	local d = RadarCodec.decode(RadarCodec.encode({ s = { { 10.6, -10.4, 7, 0 } }, v = { { 99999, -99999 } }, e = {}, ev = {} }))
	T.eq(d.s[1][1], 11)
	T.eq(d.s[1][2], -10)
	T.eq(d.v[1][1], 32767)
	T.eq(d.v[1][2], -32768)
end)

T.test("a full battle fits the unreliable payload limit", function()
	-- 52 players a side, every vehicle on the map, everyone spotted
	local b = RadarCodec.encode(packet(52, 30, 52, 30))
	T.truthy(buffer.len(b) <= RadarCodec.MAX_BYTES, "encoded " .. buffer.len(b) .. " bytes")
	local d = RadarCodec.decode(b)
	T.truthy(d, "decodes")
	T.eq(#d.s, 52, "every friendly soldier kept")
	T.eq(#d.v, 30, "every friendly vehicle kept")
end)

T.test("over budget it drops the least important markers, never overflows", function()
	local b = RadarCodec.encode(packet(200, 200, 200, 200))
	T.truthy(buffer.len(b) <= RadarCodec.MAX_BYTES, "encoded " .. buffer.len(b) .. " bytes")
	T.truthy(RadarCodec.decode(b), "still decodes")
end)

T.test("rejects anything that is not a well-formed radar buffer", function()
	T.eq(RadarCodec.decode(nil), nil)
	T.eq(RadarCodec.decode({ s = {} }), nil, "old table format")
	T.eq(RadarCodec.decode(buffer.create(1)), nil, "truncated header")
	local b = buffer.create(2)
	buffer.writeu16(b, 0, 500) -- claims 500 soldiers, holds none
	T.eq(RadarCodec.decode(b), nil, "count larger than the data")
end)
