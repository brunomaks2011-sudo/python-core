--[[
	ForestMapGenerator.lua
	Огромная лесная карта в стиле low-poly военной песочницы (Roblox Studio).

	Что строит:
	  • рельеф 2048x2048 studs (Smooth Terrain) с холмами, краевыми грядами, полянами;
	  • асфальтовые трассы, грунтовые дороги и узкие тропы;
	  • озёра и реки (с мостами там, где их пересекают дороги);
	  • тысячи низкополигональных елей, сосен, сухих деревьев, кусты, камни, валуны,
	    поваленные деревья и пни;
	  • заброшенные военные лагеря (палатки, вышки, мешки с песком, ДОТ, грузовики,
	    ящики, бочки, колючая проволока), разрушенную деревню, руины, лесопилку,
	    охотничьи избушки, блокпост на трассе, пирсы, охотничьи вышки;
	  • освещение: атмосферная дымка, тени, приглушённые цвета.

	КАК ЗАПУСТИТЬ
	  A) Через MCP-сервер Roblox_Studio: в Claude Code на ПК попросить
	     «выполни файл ForestMapGenerator.lua в Studio через run_code».
	  B) Вручную: Studio → View → Command Bar → вставить весь файл → Enter.

	ВНИМАНИЕ: при CLEAR_EXISTING = true скрипт очищает ВЕСЬ Terrain,
	удаляет старую модель ForestMap и Baseplate. Запускать в пустом месте (Baseplate).
	Генерация занимает от ~30 секунд до пары минут.
]]

local CONFIG = {
	SEED = 20261117,      -- поменяй число, чтобы получить другую карту
	MAP_SIZE = 2048,      -- размер карты в studs (кратно 128)
	TREE_COUNT = 4500,    -- деревьев (каждое ~4 детали). Слабый ПК: 2000-2500
	BUSH_COUNT = 700,
	ROCK_CLUSTERS = 260,
	BOULDERS = 30,
	FALLEN_TREES = 100,
	STUMPS = 140,
	HUNTING_STANDS = 6,
	CLEAR_EXISTING = true,
	SET_LIGHTING = true,
	YIELD = true,         -- давать Studio «дышать» во время генерации
}

---------------------------------------------------------------------------
-- Сервисы и константы
---------------------------------------------------------------------------
local Workspace = game:GetService("Workspace")
local Lighting = game:GetService("Lighting")
local StarterPlayer = game:GetService("StarterPlayer")
local Terrain = Workspace.Terrain

local RES = 4
local HALF = CONFIG.MAP_SIZE / 2
local N = CONFIG.MAP_SIZE / RES
local CHUNK = 32
local WATER_Y = 12 -- уровень воды (кратно 4)

local floor, sqrt, abs, min, max = math.floor, math.sqrt, math.abs, math.min, math.max
local cos, sin, pi = math.cos, math.sin, math.pi
local noise = math.noise
local atan2 = math.atan2 or function(y, x) return math.atan(y, x) end
local V = Vector3.new

local function clamp(v, a, b)
	if v < a then return a elseif v > b then return b end
	return v
end
local function smoothstep(a, b, x)
	local t = clamp((x - a) / (b - a), 0, 1)
	return t * t * (3 - 2 * t)
end

-- Детерминированный ГСЧ (одинаковая карта при одинаковом SEED)
local function newRng(seed)
	local state = floor(seed) % 4294967296
	local r = {}
	function r.next()
		state = (state * 1664525 + 1013904223) % 4294967296
		return state / 4294967296
	end
	function r.num(a, b) return a + (b - a) * r.next() end
	function r.int(a, b) return a + floor(r.next() * (b - a + 1)) end
	function r.chance(p) return r.next() < p end
	function r.pick(t) return t[r.int(1, #t)] end
	for _ = 1, 8 do r.next() end
	return r
end
local rng = newRng(CONFIG.SEED)

local SZ = (CONFIG.SEED % 9973) * 0.6180339 + 0.5
local function nz(x, z, k)
	return noise(x, z, SZ + k * 7.31)
end

local opCount = 0
local function yieldTick(n)
	opCount = opCount + (n or 1)
	if opCount >= 1500 then
		opCount = 0
		if CONFIG.YIELD then task.wait() end
	end
end

local function log(msg)
	print("[ForestMap] " .. msg)
end

---------------------------------------------------------------------------
-- Цвета и материалы
---------------------------------------------------------------------------
local function rgb(r, g, b) return Color3.fromRGB(r, g, b) end
local C = {
	fir = { rgb(46, 68, 51), rgb(55, 77, 55) },
	pine = { rgb(68, 86, 53), rgb(60, 80, 50) },
	trunkFir = rgb(76, 60, 47),
	trunkPine = rgb(118, 84, 60),
	dead = rgb(110, 103, 94),
	bush = { rgb(58, 78, 50), rgb(70, 86, 56), rgb(64, 74, 48) },
	rock = { rgb(108, 106, 100), rgb(94, 93, 89), rgb(121, 117, 108) },
	log = rgb(92, 75, 60),
	roots = rgb(82, 68, 54),
	wood = rgb(98, 78, 60),
	plank = rgb(112, 92, 70),
	darkwood = rgb(70, 56, 44),
	roof = rgb(74, 66, 58),
	logs = { rgb(104, 80, 60), rgb(94, 74, 58) },
	floor = rgb(96, 78, 62),
	stone = rgb(104, 100, 94),
	concrete = rgb(128, 125, 118),
	concrete2 = rgb(112, 110, 104),
	brick = rgb(116, 78, 62),
	rubble = rgb(100, 96, 90),
	charred = rgb(42, 38, 35),
	burnt = rgb(66, 56, 48),
	burnt2 = rgb(54, 48, 44),
	olive = rgb(78, 84, 58),
	tents = { rgb(86, 92, 64), rgb(120, 112, 86), rgb(72, 78, 58) },
	sand = rgb(146, 134, 104),
	crate = rgb(118, 96, 66),
	barrel = rgb(72, 82, 60),
	rust = rgb(110, 72, 50),
	tire = rgb(34, 34, 34),
	glass = rgb(40, 48, 52),
	black = rgb(22, 22, 22),
	metal = rgb(70, 70, 68),
	wire = rgb(60, 60, 58),
	red = rgb(150, 54, 44),
	white = rgb(205, 202, 192),
	ash = rgb(58, 56, 54),
	canvas = rgb(96, 98, 72),
}

local M = Enum.Material
local WOOD, PLANKS, GRASS_M, SLATE = M.Wood, M.WoodPlanks, M.Grass, M.Slate
local CONCRETE, BRICK, METAL, FABRIC = M.Concrete, M.Brick, M.Metal, M.Fabric
local COBBLE, SMOOTH, GLASS = M.Cobblestone, M.SmoothPlastic, M.Glass
local CYL = Enum.PartType.Cylinder

-- материалы рельефа
local TM = { M.Grass, M.LeafyGrass, M.Ground, M.Mud, M.Rock, M.Slate, M.Sand, M.Asphalt }
local T_GRASS, T_LEAFY, T_GROUND, T_MUD, T_ROCK, T_SLATE, T_SAND, T_ASPHALT = 1, 2, 3, 4, 5, 6, 7, 8
local TERRAIN_COLORS = {
	{ M.Grass, rgb(92, 106, 66) },
	{ M.LeafyGrass, rgb(76, 90, 56) },
	{ M.Ground, rgb(100, 86, 66) },
	{ M.Mud, rgb(76, 66, 54) },
	{ M.Rock, rgb(112, 110, 104) },
	{ M.Slate, rgb(98, 98, 94) },
	{ M.Sand, rgb(138, 126, 100) },
	{ M.Asphalt, rgb(74, 74, 72) },
}

---------------------------------------------------------------------------
-- Рельеф: базовые функции высоты
---------------------------------------------------------------------------
local function largeAt(x, z)
	local h = 30 + 34 * nz(x / 700, z / 700, 1) + 10 * nz(x / 210, z / 210, 2)
	if h < 18 then h = 18 - (18 - h) * 0.2 end
	local de = HALF - max(abs(x), abs(z))
	if de < 170 then
		local t = 1 - max(de, 0) / 170
		h = h + t * t * 50
	end
	return h
end

-- плотность леса: >1 — густой лес, <0 — открытый луг
local function forestDensity(x, z)
	return 0.5 + 2.2 * nz(x / 320, z / 320, 60) + 0.5 * nz(x / 90, z / 90, 61)
end

local function detailAt(x, z)
	return 2.4 * nz(x / 55, z / 55, 3) + 0.8 * nz(x / 17, z / 17, 4)
end

---------------------------------------------------------------------------
-- Пути (дороги, реки): сплайн Catmull-Rom через опорные точки
---------------------------------------------------------------------------
local function buildPath(wp, wiggle, step)
	local ctrl = { { wp[1][1], wp[1][2] } }
	for k = 1, #wp - 1 do
		local ax, az = wp[k][1], wp[k][2]
		local bx, bz = wp[k + 1][1], wp[k + 1][2]
		local dx, dz = bx - ax, bz - az
		local L = sqrt(dx * dx + dz * dz)
		if L > 1 then
			local n = max(1, floor(L / 110))
			local px, pz = -dz / L, dx / L
			for s = 1, n - 1 do
				local t = s / n
				local off = rng.num(-1, 1) * (L / n) * wiggle
				ctrl[#ctrl + 1] = { ax + dx * t + px * off, az + dz * t + pz * off }
			end
			ctrl[#ctrl + 1] = { bx, bz }
		end
	end
	local pts = {}
	for k = 1, #ctrl - 1 do
		local p0 = ctrl[max(1, k - 1)]
		local p1 = ctrl[k]
		local p2 = ctrl[k + 1]
		local p3 = ctrl[min(#ctrl, k + 2)]
		local dx, dz = p2[1] - p1[1], p2[2] - p1[2]
		local n = max(1, math.ceil(sqrt(dx * dx + dz * dz) / step))
		for s = 0, n - 1 do
			local t = s / n
			local t2, t3 = t * t, t * t * t
			local x = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
				+ (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
				+ (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
			local z = 0.5 * ((2 * p1[2]) + (-p0[2] + p2[2]) * t
				+ (2 * p0[2] - 5 * p1[2] + 4 * p2[2] - p3[2]) * t2
				+ (-p0[2] + 3 * p1[2] - 3 * p2[2] + p3[2]) * t3)
			pts[#pts + 1] = { x, z }
		end
	end
	pts[#pts + 1] = { ctrl[#ctrl][1], ctrl[#ctrl][2] }
	return pts
end

local function smoothPath(pts, iters)
	for _ = 1, iters do
		local out = { pts[1] }
		for k = 2, #pts - 1 do
			local a, b, c = pts[k - 1], pts[k], pts[k + 1]
			out[k] = { (a[1] + 2 * b[1] + c[1]) / 4, (a[2] + 2 * b[2] + c[2]) / 4 }
		end
		out[#pts] = pts[#pts]
		pts = out
	end
	return pts
end

local lakes, rivers, clearings, roads = {}, {}, {}, {}

local function pushOutOfLakes(pts)
	for _, p in ipairs(pts) do
		for _, L in ipairs(lakes) do
			local dx, dz = p[1] - L.x, p[2] - L.z
			local d = sqrt(dx * dx + dz * dz)
			local R = L.r * 1.25 + 6
			if d < R then
				if d < 0.01 then dx, dz, d = 1, 0, 1 end
				p[1] = L.x + dx / d * R
				p[2] = L.z + dz / d * R
			end
		end
	end
	return pts
end

local function makeRoute(wp, wiggle)
	local pts = buildPath(wp, wiggle, 8)
	pts = pushOutOfLakes(pts)
	pts = smoothPath(pts, 3)
	return pushOutOfLakes(pts)
end

---------------------------------------------------------------------------
-- 1. Озёра, реки, поляны
---------------------------------------------------------------------------
log("Планирование карты (seed " .. tostring(CONFIG.SEED) .. ")...")

for _ = 1, 400 do
	if #lakes >= 3 then break end
	local r = rng.num(105, 165)
	local x = rng.num(-HALF + 340, HALF - 340)
	local z = rng.num(-HALF + 320, HALF - 320)
	local ok = true
	for _, o in ipairs(lakes) do
		local dx, dz = o.x - x, o.z - z
		if sqrt(dx * dx + dz * dz) < r + o.r + 220 then ok = false end
	end
	if ok then lakes[#lakes + 1] = { x = x, z = z, r = r } end
end
table.sort(lakes, function(a, b) return a.z < b.z end)

if #lakes >= 2 then
	local wp = {
		{ rng.num(-HALF * 0.5, HALF * 0.5), -HALF - 40 },
		{ lakes[1].x, lakes[1].z },
		{ lakes[2].x, lakes[2].z },
		{ clamp(lakes[2].x + rng.num(-300, 300), -HALF + 200, HALF - 200), HALF + 40 },
	}
	rivers[#rivers + 1] = smoothPath(buildPath(wp, 0.38, 8), 2)
end
if #lakes >= 3 then
	local L3 = lakes[3]
	local side = (L3.x > 0) and 1 or -1
	local wp = {
		{ L3.x, L3.z },
		{ L3.x + side * (HALF - abs(L3.x)) * 0.5, L3.z + rng.num(-150, 150) },
		{ side * (HALF + 40), clamp(L3.z + rng.num(-250, 250), -HALF + 200, HALF - 200) },
	}
	rivers[#rivers + 1] = smoothPath(buildPath(wp, 0.38, 8), 2)
end

local function minDistToRivers(x, z)
	local best = math.huge
	for _, rv in ipairs(rivers) do
		for k = 1, #rv, 2 do
			local dx, dz = rv[k][1] - x, rv[k][2] - z
			local d = dx * dx + dz * dz
			if d < best then best = d end
		end
	end
	return sqrt(best)
end

for _ = 1, 700 do
	if #clearings >= 15 then break end
	local r = rng.num(50, 105)
	local x = rng.num(-HALF + 240, HALF - 240)
	local z = rng.num(-HALF + 240, HALF - 240)
	local ok = true
	for _, L in ipairs(lakes) do
		local dx, dz = L.x - x, L.z - z
		if sqrt(dx * dx + dz * dz) < L.r * 1.3 + r + 30 then ok = false end
	end
	if ok then
		for _, o in ipairs(clearings) do
			local dx, dz = o.x - x, o.z - z
			if sqrt(dx * dx + dz * dz) < r + o.r + 60 then ok = false end
		end
	end
	if ok and minDistToRivers(x, z) < r + 40 then ok = false end
	if ok then
		clearings[#clearings + 1] = { x = x, z = z, r = r, rot = rng.num(0, 2 * pi) }
	end
end
table.sort(clearings, function(a, b) return a.r > b.r end)

local KINDS = { "village", "camp", "camp", "camp", "ruins", "ruins", "sawmill", "cabin", "cabin", "cabin" }
local byKind = { village = {}, camp = {}, ruins = {}, sawmill = {}, cabin = {}, empty = {} }
for k, c in ipairs(clearings) do
	c.kind = KINDS[k] or "empty"
	c.poi = c.kind ~= "empty"
	if c.kind == "empty" then
		c.code = 1
	elseif c.kind == "camp" or c.kind == "village" or c.kind == "sawmill" then
		c.code = 2
	else
		c.code = 3
	end
	c.h0 = largeAt(c.x, c.z)
	table.insert(byKind[c.kind], c)
end

---------------------------------------------------------------------------
-- 2. Дороги
---------------------------------------------------------------------------
local ROAD_TYPES = {
	[1] = { hw = 7, sh = 6 },     -- трасса
	[2] = { hw = 4, sh = 4 },     -- грунтовка
	[3] = { hw = 2.4, sh = 2.5 }, -- тропа
}
local allRoadPts = {}
local function addRoad(pts, kind)
	roads[#roads + 1] = { pts = pts, kind = kind }
	for _, p in ipairs(pts) do allRoadPts[#allRoadPts + 1] = p end
end
local function nearestRoadPt(x, z)
	local best, bp = math.huge, nil
	for _, p in ipairs(allRoadPts) do
		local dx, dz = p[1] - x, p[2] - z
		local d = dx * dx + dz * dz
		if d < best then best = d; bp = p end
	end
	return bp
end
local function sortedBy(list, key)
	local t = {}
	for _, v in ipairs(list) do t[#t + 1] = v end
	table.sort(t, function(a, b) return a[key] < b[key] end)
	return t
end

do -- трасса запад-восток
	local on = {}
	if byKind.village[1] then on[#on + 1] = byKind.village[1] end
	if byKind.camp[1] then on[#on + 1] = byKind.camp[1] end
	on = sortedBy(on, "x")
	local z0 = on[1] and on[1].z or 0
	local z1 = on[#on] and on[#on].z or 0
	local wp = { { -HALF - 30, clamp(z0 + rng.num(-250, 250), -HALF + 300, HALF - 300) } }
	for _, c in ipairs(on) do wp[#wp + 1] = { c.x, c.z }; c.onRoad = true end
	wp[#wp + 1] = { HALF + 30, clamp(z1 + rng.num(-250, 250), -HALF + 300, HALF - 300) }
	addRoad(makeRoute(wp, 0.22), 1)
end
do -- трасса север-юг
	local on = {}
	if byKind.camp[2] then on[#on + 1] = byKind.camp[2] end
	if byKind.ruins[1] then on[#on + 1] = byKind.ruins[1] end
	on = sortedBy(on, "z")
	local x0 = on[1] and on[1].x or 0
	local x1 = on[#on] and on[#on].x or 0
	local wp = { { clamp(x0 + rng.num(-250, 250), -HALF + 300, HALF - 300), -HALF - 30 } }
	for _, c in ipairs(on) do wp[#wp + 1] = { c.x, c.z }; c.onRoad = true end
	wp[#wp + 1] = { clamp(x1 + rng.num(-250, 250), -HALF + 300, HALF - 300), HALF + 30 }
	addRoad(makeRoute(wp, 0.22), 1)
end
-- точка на пути от центра поляны к цели (дорога заходит на площадку, но не в её центр)
local function edgePoint(c, tx, tz, frac)
	local dx, dz = tx - c.x, tz - c.z
	local d = max(sqrt(dx * dx + dz * dz), 1)
	local s = min(c.r * frac, d * 0.5)
	return { c.x + dx / d * s, c.z + dz / d * s }
end
for _, c in ipairs(clearings) do -- подъезды к объектам
	if c.poi and not c.onRoad then
		local p = nearestRoadPt(c.x, c.z)
		if p then
			addRoad(makeRoute({ edgePoint(c, p[1], p[2], 0.45), { p[1], p[2] } }, 0.3), (c.kind == "cabin") and 3 or 2)
			c.onRoad = true
		end
	end
end
if byKind.camp[3] and byKind.ruins[2] then
	local a, b = byKind.camp[3], byKind.ruins[2]
	addRoad(makeRoute({ edgePoint(a, b.x, b.z, 0.5), edgePoint(b, a.x, a.z, 0.5) }, 0.3), 2)
end
for _, c in ipairs(clearings) do -- тропы к пустым полянам
	if not c.poi and rng.chance(0.8) then
		local p = nearestRoadPt(c.x, c.z)
		if p then addRoad(makeRoute({ { c.x, c.z }, { p[1], p[2] } }, 0.35), 3) end
	end
end
for _, L in ipairs(lakes) do -- тропы к озёрам
	local best, bc = math.huge, nil
	for _, c in ipairs(clearings) do
		local dx, dz = c.x - L.x, c.z - L.z
		local d = sqrt(dx * dx + dz * dz)
		if d < best then best = d; bc = c end
	end
	if bc then
		local dx, dz = (bc.x - L.x) / best, (bc.z - L.z) / best
		L.dirX, L.dirZ = dx, dz
		addRoad(makeRoute({ { bc.x, bc.z }, { L.x + dx * L.r, L.z + dz * L.r } }, 0.3), 3)
	end
end

---------------------------------------------------------------------------
-- 3. Пространственная сетка для быстрых запросов к дорогам и рекам
---------------------------------------------------------------------------
local GCELL = 64
local GN = CONFIG.MAP_SIZE / GCELL
local roadGrid, riverGrid = {}, {}

local function gridAdd(grid, seg, infl)
	local cx0 = clamp(floor((min(seg[1], seg[3]) - infl + HALF) / GCELL), 0, GN - 1)
	local cx1 = clamp(floor((max(seg[1], seg[3]) + infl + HALF) / GCELL), 0, GN - 1)
	local cz0 = clamp(floor((min(seg[2], seg[4]) - infl + HALF) / GCELL), 0, GN - 1)
	local cz1 = clamp(floor((max(seg[2], seg[4]) + infl + HALF) / GCELL), 0, GN - 1)
	for cx = cx0, cx1 do
		for cz = cz0, cz1 do
			local key = cx * GN + cz
			local b = grid[key]
			if not b then b = {}; grid[key] = b end
			b[#b + 1] = seg
		end
	end
end
local function gridGet(grid, x, z)
	local cx = clamp(floor((x + HALF) / GCELL), 0, GN - 1)
	local cz = clamp(floor((z + HALF) / GCELL), 0, GN - 1)
	return grid[cx * GN + cz]
end
local function segDist(s, x, z)
	local ax, az = s[1], s[2]
	local dx, dz = s[3] - ax, s[4] - az
	local L2 = dx * dx + dz * dz
	local t = 0
	if L2 > 0 then t = clamp(((x - ax) * dx + (z - az) * dz) / L2, 0, 1) end
	local px, pz = ax + dx * t - x, az + dz * t - z
	return sqrt(px * px + pz * pz)
end

for _, rd in ipairs(roads) do
	local T = ROAD_TYPES[rd.kind]
	local pts = rd.pts
	for k = 1, #pts - 1 do
		local seg = { pts[k][1], pts[k][2], pts[k + 1][1], pts[k + 1][2], T.hw, T.sh, rd.kind }
		gridAdd(roadGrid, seg, T.hw + T.sh + 16)
	end
end
for ri, rv in ipairs(rivers) do
	for k = 1, #rv - 1 do
		local hw = 9 + 4 * nz(k * 0.045, 0.37, 20 + ri)
		local seg = { rv[k][1], rv[k][2], rv[k + 1][1], rv[k + 1][2], hw }
		gridAdd(riverGrid, seg, hw + 32)
	end
end

local function roadQuery(x, z)
	local list = gridGet(roadGrid, x, z)
	local best, bestKind = 0, 0
	if list then
		for _, s in ipairs(list) do
			local hw, sh = s[5], s[6]
			local d = segDist(s, x, z)
			if d < hw + sh then
				local m = 1 - smoothstep(hw, hw + sh, d)
				if m > best + 1e-6 or (m > best - 1e-6 and (bestKind == 0 or s[7] < bestKind)) then
					best = max(best, m)
					bestKind = s[7]
				end
			end
		end
	end
	return best, bestKind
end
local function roadEdgeDist(x, z)
	local list = gridGet(roadGrid, x, z)
	local best = 1e9
	if list then
		for _, s in ipairs(list) do
			local d = segDist(s, x, z) - s[5]
			if d < best then best = d end
		end
	end
	return best
end
local function riverQuery(x, z)
	local list = gridGet(riverGrid, x, z)
	local best = 1e9
	if list then
		for _, s in ipairs(list) do
			local d = segDist(s, x, z) - s[5]
			if d < best then best = d end
		end
	end
	return best
end

---------------------------------------------------------------------------
-- 4. Карта высот и материалов
---------------------------------------------------------------------------
log("Расчёт рельефа " .. tostring(floor(N)) .. "x" .. tostring(floor(N)) .. " колонок...")
local H, RM, RK, RV, CM, CK, LW, SL, MAT = {}, {}, {}, {}, {}, {}, {}, {}, {}

for i = 1, N do
	local x = -HALF + (i - 0.5) * RES
	for j = 1, N do
		local z = -HALF + (j - 0.5) * RES
		local id = (i - 1) * N + j
		local large = largeAt(x, z)
		local base = large
		local att, cmax, ckind = 0, 0, 0
		for _, c in ipairs(clearings) do
			local dx, dz = x - c.x, z - c.z
			local d2 = dx * dx + dz * dz
			local R = c.r * 1.25
			if d2 < R * R then
				local t = sqrt(d2) / c.r + 0.12 * nz(x / 40, z / 40, 30)
				local m = 1 - smoothstep(0.72, 1.05, t)
				if m > 0 then
					if c.poi then base = base + (c.h0 - base) * m end
					if m > att then att = m end
					if m > cmax then cmax = m; ckind = c.code end
				end
			end
		end
		local h = base + detailAt(x, z) * (1 - att * 0.85)
		local rm, rk = roadQuery(x, z)
		if rm > 0 then h = h + (base - 0.35 - h) * rm end
		if h < WATER_Y + 2.5 then h = WATER_Y + 2.5 end

		local nearLake = false
		for li, L in ipairs(lakes) do
			local dx, dz = x - L.x, z - L.z
			local d2 = dx * dx + dz * dz
			local R = L.r * 1.4
			if d2 < R * R then
				local t = sqrt(d2) / L.r + 0.18 * nz(x / 60, z / 60, 40 + li)
				if t < 1.25 then nearLake = true end
				if t < 1.2 then
					local target = WATER_Y - 2 - 6.5 * clamp(1 - t / 0.65, 0, 1) ^ 0.8
					local hl = target + (h - target) * smoothstep(0.65, 1.2, t)
					if hl < h then h = hl end
				end
			end
		end

		local rv = riverQuery(x, z)
		if rv < 16 then
			local hr
			if rv < 0 then
				hr = WATER_Y - 1.5 - min(4, -rv * 0.6)
			else
				hr = (WATER_Y - 1.5) + (h - (WATER_Y - 1.5)) * smoothstep(0, 16, rv)
			end
			if hr < h then h = hr end
		end

		H[id], RM[id], RK[id], RV[id], CM[id], CK[id], LW[id] = h, rm, rk, rv, cmax, ckind, nearLake
	end
	if i % 16 == 0 then yieldTick(1500) end
end

local function idx(i, j) return (i - 1) * N + j end
for i = 1, N do
	local x = -HALF + (i - 0.5) * RES
	for j = 1, N do
		local z = -HALF + (j - 0.5) * RES
		local id = idx(i, j)
		local h = H[id]
		local hl, hr = H[idx(max(i - 1, 1), j)], H[idx(min(i + 1, N), j)]
		local hd, hu = H[idx(i, max(j - 1, 1))], H[idx(i, min(j + 1, N))]
		local slope = max(abs(hr - hl), abs(hu - hd)) / (2 * RES)
		SL[id] = slope
		local m
		if h < WATER_Y - 0.2 then
			m = (WATER_Y - h > 3) and T_MUD or T_SAND
		elseif (LW[id] or RV[id] < 18) and h < WATER_Y + 1.6 then
			m = T_SAND
		elseif RM[id] > 0.93 then
			local k = RK[id]
			m = (k == 1) and T_ASPHALT or ((k == 2) and T_GROUND or T_MUD)
		elseif RM[id] > 0.3 then
			m = T_GROUND
		elseif slope > 0.85 then
			m = T_ROCK
		elseif slope > 0.6 then
			m = (nz(x / 20, z / 20, 52) > 0) and T_SLATE or T_GROUND
		elseif CM[id] > 0.35 then
			if CK[id] == 2 and nz(x / 22, z / 22, 50) > -0.05 then m = T_GROUND else m = T_GRASS end
		else
			local n = nz(x / 48, z / 48, 51)
			local fd = forestDensity(x, z) + 0.25 * nz(x / 30, z / 30, 53)
			if fd < 0.15 then
				m = (n > 0.42) and T_GROUND or T_GRASS
			elseif n > 0.38 then m = T_GROUND
			elseif n < -0.32 then m = T_GRASS
			else m = T_LEAFY end
		end
		MAT[id] = m
	end
	if i % 32 == 0 then yieldTick(1500) end
end

---------------------------------------------------------------------------
-- 5. Запись вокселей
---------------------------------------------------------------------------
if CONFIG.CLEAR_EXISTING then
	Terrain:Clear()
	local old = Workspace:FindFirstChild("ForestMap")
	if old then old:Destroy() end
	local bp = Workspace:FindFirstChild("Baseplate")
	if bp then bp:Destroy() end
end

log("Запись террейна...")
do
	local AIR, WATER = M.Air, M.Water
	local ROCK_M, GROUND_M = M.Rock, M.Ground
	local nC = N / CHUNK
	for ci = 0, nC - 1 do
		for cj = 0, nC - 1 do
			local minH, maxH, wet = math.huge, -math.huge, false
			for i = ci * CHUNK + 1, ci * CHUNK + CHUNK do
				for j = cj * CHUNK + 1, cj * CHUNK + CHUNK do
					local h = H[(i - 1) * N + j]
					if h < minH then minH = h end
					if h > maxH then maxH = h end
					if h < WATER_Y then wet = true end
				end
			end
			local y0 = floor((minH - 12) / 4) * 4
			local top = maxH
			if wet and WATER_Y > top then top = WATER_Y end
			local y1 = math.ceil(top / 4) * 4 + 4
			local ny = (y1 - y0) / 4
			local mats, occs = {}, {}
			for a = 1, CHUNK do
				local i = ci * CHUNK + a
				local mx, ox = {}, {}
				mats[a], occs[a] = mx, ox
				for b = 1, ny do mx[b] = {}; ox[b] = {} end
				for c = 1, CHUNK do
					local id = (i - 1) * N + cj * CHUNK + c
					local h = H[id]
					local code = MAT[id]
					local surf = TM[code]
					local deep = (code == T_ROCK) and ROCK_M or GROUND_M
					local submerged = h < WATER_Y
					for b = 1, ny do
						local yb = y0 + (b - 1) * 4
						local yt = yb + 4
						local mat, occ
						if yt <= h then
							local depth = h - yt
							if depth < 4 then mat = surf elseif depth < 10 then mat = deep else mat = ROCK_M end
							occ = 1
						elseif yb < h then
							occ = (h - yb) / 4
							mat = surf
							if submerged and occ < 0.5 then mat = WATER; occ = 1
							elseif submerged then occ = 1 end
						elseif submerged and yb < WATER_Y then
							mat = WATER; occ = 1
						else
							mat = AIR; occ = 0
						end
						mx[b][c] = mat
						ox[b][c] = occ
					end
				end
			end
			local x0 = -HALF + ci * CHUNK * RES
			local z0 = -HALF + cj * CHUNK * RES
			local region = Region3.new(V(x0, y0, z0), V(x0 + CHUNK * RES, y1, z0 + CHUNK * RES))
			Terrain:WriteVoxels(region, RES, mats, occs)
			yieldTick(1500)
		end
	end
end

for _, tc in ipairs(TERRAIN_COLORS) do Terrain:SetMaterialColor(tc[1], tc[2]) end
Terrain.WaterColor = rgb(46, 70, 70)
Terrain.WaterTransparency = 0.35
Terrain.WaterReflectance = 0.25
Terrain.WaterWaveSize = 0.06
Terrain.WaterWaveSpeed = 6
pcall(function() Terrain.Decoration = false end)

---------------------------------------------------------------------------
-- 6. Помощники для объектов
---------------------------------------------------------------------------
local function getHeight(x, z)
	local fx = clamp((x + HALF) / RES + 0.5, 1, N)
	local fz = clamp((z + HALF) / RES + 0.5, 1, N)
	local i0, j0 = floor(fx), floor(fz)
	local i1, j1 = min(i0 + 1, N), min(j0 + 1, N)
	local tx, tz = fx - i0, fz - j0
	local h00, h10 = H[(i0 - 1) * N + j0], H[(i1 - 1) * N + j0]
	local h01, h11 = H[(i0 - 1) * N + j1], H[(i1 - 1) * N + j1]
	return (h00 * (1 - tx) + h10 * tx) * (1 - tz) + (h01 * (1 - tx) + h11 * tx) * tz
end
local function colOf(x, z)
	local i = clamp(floor((x + HALF) / RES) + 1, 1, N)
	local j = clamp(floor((z + HALF) / RES) + 1, 1, N)
	return (i - 1) * N + j
end

local BLK = {}
local function block(x, z, r)
	local s = math.ceil(r / RES)
	local ci = clamp(floor((x + HALF) / RES) + 1, 1, N)
	local cj = clamp(floor((z + HALF) / RES) + 1, 1, N)
	for i = max(1, ci - s), min(N, ci + s) do
		for j = max(1, cj - s), min(N, cj + s) do
			BLK[(i - 1) * N + j] = true
		end
	end
end

local stats = { parts = 0 }
local function part(parent, size, cf, color, mat, shape, collide)
	local p = Instance.new("Part")
	p.Anchored = true
	p.Size = size
	p.CFrame = cf
	p.Color = color
	p.Material = mat or SMOOTH
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	if shape then p.Shape = shape end
	if collide == false then
		p.CanCollide = false
		p.CanTouch = false
	end
	p.Parent = parent
	stats.parts = stats.parts + 1
	yieldTick(1)
	return p
end
local function newModel(name, parent)
	local m = Instance.new("Model")
	m.Name = name
	if parent then m.Parent = parent end
	return m
end
local function newFolder(name, parent)
	local f = Instance.new("Folder")
	f.Name = name
	f.Parent = parent
	return f
end
local function beam(parent, p1, p2, t, color, mat)
	local mid = (p1 + p2) / 2
	part(parent, V(t, t, (p2 - p1).Magnitude), CFrame.lookAt(mid, p2), color, mat)
end
local function l2w(o, lx, lz)
	local cs, sn = cos(o.rot), sin(o.rot)
	return o.x + lx * cs + lz * sn, o.z - lx * sn + lz * cs
end
local function gcf(o, lx, lz, yaw, dy)
	local wx, wz = l2w(o, lx, lz)
	return CFrame.new(wx, getHeight(wx, wz) + (dy or 0), wz) * CFrame.Angles(0, o.rot + (yaw or 0), 0)
end
-- свободно ли место (нет дороги, воды и уже занятых построек этой локации)
local function freeSpot(o, lx, lz, rad)
	if o.r and lx * lx + lz * lz > (o.r * 0.85) ^ 2 then return false end
	local wx, wz = l2w(o, lx, lz)
	if roadEdgeDist(wx, wz) <= rad or riverQuery(wx, wz) <= rad + 4 or getHeight(wx, wz) <= WATER_Y + 1 then
		return false
	end
	if o.occ then
		for _, q in ipairs(o.occ) do
			local dx, dz = q[1] - lx, q[2] - lz
			if dx * dx + dz * dz < (q[3] + rad) ^ 2 then return false end
		end
	end
	return true
end
-- ищет свободное место рядом с желаемым (спираль), резервирует его
local function findSpot(o, lx, lz, rad, spread)
	local x, z = lx, lz
	for k = 0, 30 do
		if k > 0 then
			local a = k * 2.39996
			local d = spread * sqrt(k / 30)
			x, z = lx + cos(a) * d, lz + sin(a) * d
		end
		if freeSpot(o, x, z, rad) then
			o.occ = o.occ or {}
			o.occ[#o.occ + 1] = { x, z, rad }
			return x, z
		end
	end
	return nil
end

local map = Instance.new("Model")
map.Name = "ForestMap"
local fTrees = newFolder("Trees", map)
local fVeg = newFolder("Vegetation", map)
local fRocks = newFolder("Rocks", map)
local fPOI = newFolder("Locations", map)
local fInfra = newFolder("Infrastructure", map)

---------------------------------------------------------------------------
-- 7. Постройки
---------------------------------------------------------------------------
-- двускатная крыша: конёк вдоль локальной X, ширина W по Z
local function slabRoof(parent, base, L, W, Hh, thick, color, mat, y0, skipSide)
	local s = W / 2
	local len = sqrt(s * s + Hh * Hh)
	local th = atan2(Hh, s)
	if skipSide ~= -1 then
		part(parent, V(L, thick, len), base * CFrame.new(0, y0 + Hh / 2, -s / 2) * CFrame.Angles(-th, 0, 0), color, mat)
	end
	if skipSide ~= 1 then
		part(parent, V(L, thick, len), base * CFrame.new(0, y0 + Hh / 2, s / 2) * CFrame.Angles(th, 0, 0), color, mat)
	end
end

local function wallSeg(parent, cf, a, b, y0, y1, thick, color, mat)
	if y1 - y0 > 0.1 then
		part(parent, V(b - a, y1 - y0, thick), cf * CFrame.new((a + b) / 2, (y0 + y1) / 2, 0), color, mat)
	end
end
-- стена вдоль локальной X с проёмами {x0, x1, y0, y1}; ruin = рваный верх
local function wallOpen(parent, cf, length, height, thick, openings, color, mat, ruin)
	local xs = { -length / 2, length / 2 }
	for _, o in ipairs(openings) do xs[#xs + 1] = o[1]; xs[#xs + 1] = o[2] end
	if ruin then
		local x = -length / 2 + rng.num(1.5, 3)
		while x < length / 2 - 0.8 do xs[#xs + 1] = x; x = x + rng.num(1.8, 3.2) end
	end
	table.sort(xs)
	for k = 1, #xs - 1 do
		local a, b = xs[k], xs[k + 1]
		if b - a > 0.05 then
			local mid = (a + b) / 2
			local ops = {}
			for _, o in ipairs(openings) do
				if mid > o[1] and mid < o[2] then ops[#ops + 1] = o end
			end
			table.sort(ops, function(p, q) return p[3] < q[3] end)
			local top = height
			if ruin then
				if rng.chance(0.12) then top = 0 else top = height * rng.num(0.3, 1) end
			end
			local y = 0
			for _, o in ipairs(ops) do
				wallSeg(parent, cf, a, b, y, min(o[3], top), thick, color, mat)
				if o[4] > y then y = o[4] end
			end
			wallSeg(parent, cf, a, b, y, top, thick, color, mat)
		end
	end
end

local function tent(parent, base, L, W, Hh, color, collapsed)
	part(parent, V(L, 0.2, W), base * CFrame.new(0, 0.1, 0), C.darkwood, FABRIC)
	if collapsed then
		part(parent, V(L, 0.3, W * 0.9), base * CFrame.new(0, 0.5, 0.4) * CFrame.Angles(0.08, 0, 0.05), color, FABRIC)
		part(parent, V(0.35, Hh, 0.35), base * CFrame.new(L / 2 - 0.4, Hh * 0.35, 0) * CFrame.Angles(0, 0, 0.9), C.wood, WOOD)
	else
		slabRoof(parent, base, L, W, Hh, 0.3, color, FABRIC, 0)
		part(parent, V(0.35, Hh, 0.35), base * CFrame.new(-L / 2 + 0.3, Hh / 2, 0), C.wood, WOOD)
		part(parent, V(0.35, Hh, 0.35), base * CFrame.new(L / 2 - 0.3, Hh / 2, 0), C.wood, WOOD)
	end
end

local function watchtower(parent, base, hgt, w, col)
	local a = w / 2
	for _, p in ipairs({ { -a, -a }, { a, -a }, { -a, a }, { a, a } }) do
		part(parent, V(0.9, hgt + 2, 0.9), base * CFrame.new(p[1], (hgt + 2) / 2 - 2, p[2]), col, WOOD)
	end
	beam(parent, base * V(-a, 1, a), base * V(a, hgt - 1, a), 0.45, col, WOOD)
	beam(parent, base * V(a, 1, a), base * V(-a, hgt - 1, a), 0.45, col, WOOD)
	beam(parent, base * V(-a, 1, -a), base * V(-a, hgt - 1, a), 0.45, col, WOOD)
	beam(parent, base * V(a, 1, a), base * V(a, hgt - 1, -a), 0.45, col, WOOD)
	local P = w + 1.6
	part(parent, V(P, 0.6, P), base * CFrame.new(0, hgt, 0), C.plank, PLANKS)
	local ry, e = hgt + 1.7, P / 2 - 0.17
	part(parent, V(P, 2.8, 0.35), base * CFrame.new(0, ry, e), col, PLANKS)
	part(parent, V(0.35, 2.8, P), base * CFrame.new(-e, ry, 0), col, PLANKS)
	part(parent, V(0.35, 2.8, P), base * CFrame.new(e, ry, 0), col, PLANKS)
	local half = P / 2 - 1
	part(parent, V(half, 2.8, 0.35), base * CFrame.new(-(1 + half / 2), ry, -e), col, PLANKS)
	part(parent, V(half, 2.8, 0.35), base * CFrame.new(1 + half / 2, ry, -e), col, PLANKS)
	for _, p in ipairs({ { -1, -1 }, { 1, -1 }, { -1, 1 }, { 1, 1 } }) do
		part(parent, V(0.4, 4, 0.4), base * CFrame.new(p[1] * (a + 0.5), hgt + 2.3, p[2] * (a + 0.5)), col, WOOD)
	end
	slabRoof(parent, base, w + 2.6, w + 2.6, 2.2, 0.35, C.roof, PLANKS, hgt + 4.3)
	local lz = -(P / 2 + 0.3)
	part(parent, V(0.3, hgt + 1, 0.3), base * CFrame.new(-0.9, (hgt + 1) / 2 - 0.5, lz), col, WOOD)
	part(parent, V(0.3, hgt + 1, 0.3), base * CFrame.new(0.9, (hgt + 1) / 2 - 0.5, lz), col, WOOD)
	local y = 1.5
	while y < hgt - 0.3 do
		part(parent, V(1.8, 0.25, 0.25), base * CFrame.new(0, y, lz), col, WOOD)
		y = y + 1.8
	end
end

local function sandbags(parent, base, length, layers)
	local n = max(1, floor(length / 2 + 0.5))
	for k = 0, layers - 1 do
		local odd = k % 2
		for s = 0, n - 1 - odd do
			local x = -length / 2 + 1 + s * 2 + odd
			part(parent, V(1.9, 0.9, 1.4), base * CFrame.new(x, 0.42 + k * 0.85, 0), C.sand, FABRIC)
		end
	end
end

local function crate(parent, cf, s)
	part(parent, V(s, s, s), cf * CFrame.new(0, s / 2, 0), C.crate, PLANKS)
end
local function ammoBox(parent, cf)
	part(parent, V(2.6, 1.2, 1.2), cf * CFrame.new(0, 0.6, 0), C.olive, METAL)
end
local function barrel(parent, cf, lying)
	if lying then
		part(parent, V(3, 2.2, 2.2), cf * CFrame.new(0, 1.1, 0), C.rust, METAL, CYL)
	else
		part(parent, V(3, 2.2, 2.2), cf * CFrame.new(0, 1.5, 0) * CFrame.Angles(0, 0, pi / 2), C.barrel, METAL, CYL)
	end
end

local function truck(parent, base, wrecked)
	local body = wrecked and C.burnt or C.olive
	local t = base * CFrame.Angles(0, 0, wrecked and 0.06 or 0.015)
	part(parent, V(4.6, 1, 15), t * CFrame.new(0, 2.3, 0), C.metal, METAL)
	part(parent, V(5, 3.4, 4), t * CFrame.new(0, 4.5, -4.6), body, METAL)
	part(parent, V(4.2, 1.3, 0.2), t * CFrame.new(0, 5.3, -6.65), C.glass, GLASS)
	part(parent, V(4.6, 2.2, 3.2), t * CFrame.new(0, 3.9, -8.1), body, METAL)
	part(parent, V(5.2, 0.4, 9), t * CFrame.new(0, 3, 2.6), body, METAL)
	part(parent, V(0.3, 1.4, 9), t * CFrame.new(-2.5, 3.9, 2.6), body, METAL)
	part(parent, V(0.3, 1.4, 9), t * CFrame.new(2.5, 3.9, 2.6), body, METAL)
	part(parent, V(5.2, 1.4, 0.3), t * CFrame.new(0, 3.9, 7.05), body, METAL)
	if not wrecked then
		part(parent, V(5.4, 3.6, 8.6), t * CFrame.new(0, 6.4, 2.8), C.canvas, FABRIC)
	end
	for _, wz in ipairs({ -7.4, 1.2, 4.8 }) do
		for _, sx in ipairs({ -1, 1 }) do
			if not (wrecked and wz == 4.8 and sx == 1) then
				part(parent, V(1.1, 3.2, 3.2), t * CFrame.new(sx * 2.6, 1.6, wz), C.tire, SMOOTH, CYL)
			end
		end
	end
end

local function bunker(parent, base)
	part(parent, V(12, 6, 10), base * CFrame.new(0, 1.8, 0), C.concrete, CONCRETE)
	part(parent, V(13.5, 1, 11.5), base * CFrame.new(0, 5.2, 0), C.concrete2, CONCRETE)
	part(parent, V(7, 0.9, 0.3), base * CFrame.new(0, 3.4, -5.05), C.black, SMOOTH)
	part(parent, V(2.4, 3.8, 0.3), base * CFrame.new(0, 1.9, 5.05), C.black, SMOOTH)
	sandbags(parent, base * CFrame.new(0, 5.7, -4.6), 12, 1)
end

local function campfire(parent, base)
	for k = 0, 6 do
		local a = k / 7 * 2 * pi
		part(parent, V(0.9, 0.6, 0.9), base * CFrame.new(cos(a) * 1.6, 0.25, sin(a) * 1.6) * CFrame.Angles(0, a, 0), C.rock[1], SLATE)
	end
	part(parent, V(2.4, 0.1, 2.4), base * CFrame.new(0, 0.08, 0), C.ash, SLATE)
	part(parent, V(3, 0.5, 0.5), base * CFrame.new(0, 0.35, 0) * CFrame.Angles(0, 0.4, 0.1), C.charred, WOOD)
	part(parent, V(3, 0.5, 0.5), base * CFrame.new(0, 0.4, 0) * CFrame.Angles(0, -0.8, -0.1), C.charred, WOOD)
	part(parent, V(5, 1.2, 1.2), base * CFrame.new(0, 0.6, 4), C.log, WOOD, CYL)
	part(parent, V(5, 1.2, 1.2), base * CFrame.new(0, 0.6, -4), C.log, WOOD, CYL)
end

local function fence(parent, base, length, broken)
	local n = floor(length / 5)
	for k = 0, n do
		local lean = rng.num(-0.05, 0.05)
		if broken and rng.chance(0.25) then lean = rng.num(-0.5, 0.5) end
		part(parent, V(0.35, 4.5, 0.35), base * CFrame.new(-length / 2 + k * 5, 1.7, 0) * CFrame.Angles(lean, 0, 0), C.wood, WOOD)
	end
	for _, y in ipairs({ 1.6, 3.1 }) do
		part(parent, V(length, 0.12, 0.12), base * CFrame.new(0, y, 0), C.wire, METAL, nil, false)
	end
end

local function hedgehog(parent, base)
	local cf = base * CFrame.new(0, 1.6, 0)
	part(parent, V(0.5, 0.5, 5), cf * CFrame.Angles(0.7, 0, 0), C.metal, METAL)
	part(parent, V(0.5, 0.5, 5), cf * CFrame.Angles(-0.7, pi / 2, 0), C.metal, METAL)
	part(parent, V(5, 0.5, 0.5), cf * CFrame.Angles(0, pi / 4, 0.7), C.metal, METAL)
end

local function logPile(parent, base, len)
	for r, n in ipairs({ 4, 3, 2, 1 }) do
		for k = 0, n - 1 do
			part(parent, V(len, 1.6, 1.6), base * CFrame.new(0, 0.8 + (r - 1) * 1.4, (k - (n - 1) / 2) * 1.7), C.log, WOOD, CYL)
		end
	end
end

local function cabin(parent, base, w, d, damaged)
	local wallH, t, y = 8, 0.8, 0.3
	local col = rng.pick(C.logs)
	part(parent, V(w + 1, 3, d + 1), base * CFrame.new(0, -1.2, 0), C.stone, COBBLE)
	part(parent, V(w, 0.4, d), base * CFrame.new(0, 0.4, 0), C.floor, PLANKS)
	wallOpen(parent, base * CFrame.new(0, y, -d / 2 + t / 2), w, wallH, t,
		{ { -1.6, 1.6, 0, 6.6 }, { w / 2 - 4.5, w / 2 - 2, 3, 5.6 } }, col, PLANKS, false)
	wallOpen(parent, base * CFrame.new(0, y, d / 2 - t / 2), w, wallH, t, { { -1.4, 1.4, 3, 5.6 } }, col, PLANKS, false)
	wallOpen(parent, base * CFrame.new(-w / 2 + t / 2, y, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, wallH, t,
		{ { -1.3, 1.3, 3, 5.6 } }, col, PLANKS, false)
	wallOpen(parent, base * CFrame.new(w / 2 - t / 2, y, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, wallH, t, {}, col, PLANKS, false)
	local roofBase = base * CFrame.new(0, y + wallH, 0)
	if damaged then
		slabRoof(parent, roofBase, w + 2, d + 2, 4, 0.5, C.roof, PLANKS, 0, 1)
		part(parent, V(w * 0.8, 0.5, d * 0.6), base * CFrame.new(0, 2.5, d * 0.15) * CFrame.Angles(0.45, 0, 0.1), C.roof, PLANKS)
	else
		slabRoof(parent, roofBase, w + 2, d + 2, 4, 0.5, C.roof, PLANKS, 0)
		part(parent, V(2, 7, 2), base * CFrame.new(w / 2 - 2.5, y + wallH + 2.5, 1.5), C.stone, COBBLE)
	end
	for _, sx in ipairs({ -1, 1 }) do
		for k = 0, 2 do
			local gw = (d - 2 * t) * (1 - (k + 0.5) / 3.2)
			part(parent, V(t, 1.3, gw), base * CFrame.new(sx * (w / 2 - t / 2), y + wallH + 0.65 + k * 1.3, 0), col, PLANKS)
		end
	end
	part(parent, V(w, 0.4, 3), base * CFrame.new(0, 0.4, -d / 2 - 1.5), C.floor, PLANKS)
end

local function ruin(parent, base, w, d, floors)
	local brick = rng.chance(0.5)
	local col = brick and C.brick or C.concrete
	local mat = brick and BRICK or CONCRETE
	local wallH, t, y = floors * 9, 1, 0.3
	part(parent, V(w + 1, 2.4, d + 1), base * CFrame.new(0, -0.9, 0), C.concrete2, CONCRETE)
	local function opens(len, door)
		local o = {}
		if door then o[#o + 1] = { -1.8, 1.8, 0, 7 } end
		for f = 0, floors - 1 do
			local x = -len / 2 + 2.5
			while x + 2.4 < len / 2 - 2 do
				if not (door and f == 0 and x + 2.4 > -2.6 and x < 2.6) then
					o[#o + 1] = { x, x + 2.4, f * 9 + 3, f * 9 + 6.5 }
				end
				x = x + 5
			end
		end
		return o
	end
	wallOpen(parent, base * CFrame.new(0, y, -d / 2 + t / 2), w, wallH, t, opens(w, true), col, mat, true)
	wallOpen(parent, base * CFrame.new(0, y, d / 2 - t / 2), w, wallH, t, opens(w, false), col, mat, true)
	wallOpen(parent, base * CFrame.new(-w / 2 + t / 2, y, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, wallH, t, opens(d - 2 * t, false), col, mat, true)
	wallOpen(parent, base * CFrame.new(w / 2 - t / 2, y, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, wallH, t, opens(d - 2 * t, false), col, mat, true)
	if floors > 1 then
		part(parent, V(w - 2 * t, 0.8, d * 0.45), base * CFrame.new(0, y + 9, d * 0.25 - t), C.concrete2, CONCRETE)
		part(parent, V(w * 0.6, 0.8, d * 0.5), base * CFrame.new(-w * 0.1, y + 4.2, -d * 0.15) * CFrame.Angles(0.75, 0.1, 0.05), C.concrete2, CONCRETE)
	end
	for _ = 1, rng.int(10, 18) do
		local s = rng.num(0.8, 3)
		local c2 = rng.chance(0.5) and col or C.rubble
		local m2 = rng.chance(0.5) and mat or SLATE
		part(parent, V(s * rng.num(0.8, 1.6), s * rng.num(0.5, 1), s),
			base * CFrame.new(rng.num(-w / 2 - 4, w / 2 + 4), y + s * 0.2, rng.num(-d / 2 - 4, d / 2 + 4))
			* CFrame.Angles(rng.num(-0.5, 0.5), rng.num(0, 6.28), rng.num(-0.5, 0.5)), c2, m2)
	end
	for _ = 1, 3 do
		part(parent, V(0.7, 0.7, rng.num(5, 9)), base * CFrame.new(rng.num(-w / 3, w / 3), y + 1.2, rng.num(-d / 3, d / 3))
			* CFrame.Angles(rng.num(-0.4, 0.4), rng.num(0, 3.14), 0), C.charred, WOOD)
	end
end

local function carWreck(parent, base)
	local t = base * CFrame.Angles(rng.num(-0.06, 0.06), 0, rng.num(-0.1, 0.1))
	part(parent, V(4.6, 1.8, 9.5), t * CFrame.new(0, 1.5, 0), C.burnt, METAL)
	part(parent, V(4.2, 1.5, 4.6), t * CFrame.new(0, 3.1, 0.6), C.burnt2, METAL)
	part(parent, V(0.9, 2.2, 2.2), t * CFrame.new(-2.3, 0.9, -3.2), C.tire, SMOOTH, CYL)
	part(parent, V(0.9, 2.2, 2.2), t * CFrame.new(2.3, 0.9, 3.2), C.tire, SMOOTH, CYL)
end

local function outhouse(parent, base)
	part(parent, V(3.2, 7, 3.2), base * CFrame.new(0, 3.5, 0), C.plank, PLANKS)
	part(parent, V(4, 0.4, 4), base * CFrame.new(0, 7.3, 0) * CFrame.Angles(0.15, 0, 0), C.roof, PLANKS)
	part(parent, V(1.6, 5, 0.2), base * CFrame.new(0, 2.7, -1.65), C.darkwood, WOOD)
end

local function shed(parent, base, w, d, collapsed)
	for ix = 0, 3 do
		for iz = 0, 2 do
			if not (collapsed and ix == 3 and iz ~= 1) then
				part(parent, V(0.9, 10.5, 0.9), base * CFrame.new(-w / 2 + ix * w / 3, 5, -d / 2 + iz * d / 2), C.wood, WOOD)
			end
		end
	end
	if collapsed then
		part(parent, V(w + 2, 0.5, d + 2), base * CFrame.new(-1, 7, 0) * CFrame.Angles(0.12, 0, -0.28), C.roof, PLANKS)
	else
		part(parent, V(w + 2, 0.5, d + 2), base * CFrame.new(0, 10.6, 0) * CFrame.Angles(0.12, 0, 0), C.roof, PLANKS)
	end
	part(parent, V(w, 6, 0.4), base * CFrame.new(0, 3, d / 2), C.plank, PLANKS)
	part(parent, V(3, 2.6, 10), base * CFrame.new(0, 1.3, -1), C.darkwood, PLANKS)
	part(parent, V(0.2, 3.4, 3.4), base * CFrame.new(0, 2.8, -1), C.metal, METAL, CYL)
end

local function addModel(name, parent)
	return newModel(name, parent)
end

---------------------------------------------------------------------------
-- 8. Локации
---------------------------------------------------------------------------
log("Постройка локаций...")
local poiCount = { camp = 0, village = 0, ruins = 0, sawmill = 0, cabin = 0 }

local function buildCamp(c, n)
	local m = addModel("MilitaryCamp_" .. n, fPOI)
	local R = c.r * 0.6
	local sp = c.r * 0.35
	local x, z = findSpot(c, R * 0.7, R * 0.55, 6, sp)
	if x then watchtower(m, gcf(c, x, z, 0.3), 14, 6, C.wood) end
	if n % 2 == 1 then
		x, z = findSpot(c, -R * 0.75, R * 0.55, 8, sp)
		if x then bunker(m, gcf(c, x, z, 0.5)) end
	end
	x, z = findSpot(c, R * 0.15, R * 0.1, 9, sp)
	if x then truck(m, gcf(c, x, z, rng.num(0, 6.28)), rng.chance(0.4)) end
	for k = 1, rng.int(3, 4) do
		x, z = findSpot(c, -R * 0.55 + (k - 1) * 11, -R * 0.4, 6.5, sp)
		if x then tent(m, gcf(c, x, z, 0), 9, 8, 5.5, rng.pick(C.tents), rng.chance(0.25)) end
	end
	for k = 1, 3 do
		x, z = findSpot(c, -R * 0.5 + k * R * 0.28, R * 0.45, 5, sp)
		if x then
			local cf = gcf(c, x, z, rng.num(0, 6.28))
			crate(m, cf, 3)
			crate(m, cf * CFrame.new(3.2, 0, 0.3), 3)
			crate(m, cf * CFrame.new(1.6, 3, 0) * CFrame.Angles(0, 0.3, 0), 3)
			ammoBox(m, cf * CFrame.new(-2.4, 0, 1.5))
		end
	end
	x, z = findSpot(c, -R * 0.3, R * 0.05, 5, sp)
	if x then campfire(m, gcf(c, x, z, 0)) end
	x, z = findSpot(c, R * 0.4, -R * 0.75, 2, sp)
	if x then
		local cf = gcf(c, x, z, 0)
		part(m, V(0.3, 14, 0.3), cf * CFrame.new(0, 7, 0), C.metal, METAL)
		part(m, V(0.1, 2.4, 4), cf * CFrame.new(0, 12.5, 2.1), C.olive, FABRIC, nil, false)
	end
	for _ = 1, 6 do
		x, z = findSpot(c, rng.num(-R * 0.7, R * 0.7), rng.num(-R * 0.2, R * 0.8), 1.8, sp)
		if x then barrel(m, gcf(c, x, z, rng.num(0, 6.28)), rng.chance(0.3)) end
	end
	for k = 0, 5 do -- кольцо из мешков с песком
		local a = k / 6 * 2 * pi + rng.num(-0.2, 0.2)
		local rr = R * 1.1
		local lx, lz = cos(a) * rr, sin(a) * rr
		if rng.chance(0.75) and freeSpot(c, lx, lz, 6) then
			sandbags(m, gcf(c, lx, lz, -a - pi / 2), rng.num(8, 14), 3)
		end
	end
	if freeSpot(c, 0, -R * 1.25, 3) then fence(m, gcf(c, 0, -R * 1.25, 0), R * 1.4, true) end
end

local function buildVillage(c)
	local m = addModel("RuinedVillage", fPOI)
	local n = rng.int(6, 8)
	local R = c.r * 0.55
	for k = 0, n - 1 do
		local a = k / n * 2 * pi + rng.num(-0.15, 0.15)
		local x, z = findSpot(c, cos(a) * R, sin(a) * R, 11, 10)
		if x then
			ruin(m, gcf(c, x, z, pi / 2 - a), rng.num(12, 18), rng.num(10, 14), rng.chance(0.35) and 2 or 1)
		end
	end
	for _ = 1, 3 do
		local x, z = findSpot(c, rng.num(-R * 0.6, R * 0.6), rng.num(-R * 0.6, R * 0.6), 6, R * 0.4)
		if x then carWreck(m, gcf(c, x, z, rng.num(0, 6.28))) end
	end
	local x, z = findSpot(c, R * 0.25, -R * 0.2, 3, R * 0.4)
	if x then
		local cf = gcf(c, x, z, 0)
		part(m, V(4, 2.4, 4), cf * CFrame.new(0, 1, 0), C.stone, COBBLE)
		part(m, V(2.8, 0.2, 2.8), cf * CFrame.new(0, 2.25, 0), C.black, SMOOTH)
	end
end

local function buildRuins(c, n)
	local m = addModel("Ruins_" .. n, fPOI)
	local R = c.r * 0.4
	for k = 1, rng.int(2, 3) do
		local a = k * 2.2 + rng.num(-0.4, 0.4)
		local x, z = findSpot(c, cos(a) * R, sin(a) * R, 11, c.r * 0.4)
		if x then
			ruin(m, gcf(c, x, z, rng.num(0, 6.28)), rng.num(14, 20), rng.num(10, 14), rng.chance(0.4) and 2 or 1)
		end
	end
	local x, z = findSpot(c, 0, 0, 6, c.r * 0.4)
	if x then carWreck(m, gcf(c, x, z, rng.num(0, 6.28))) end
	for _ = 1, 4 do
		x, z = findSpot(c, rng.num(-R, R), rng.num(-R, R), 2, R)
		if x then barrel(m, gcf(c, x, z, rng.num(0, 6.28)), true) end
	end
end

local function buildSawmill(c)
	local m = addModel("AbandonedSawmill", fPOI)
	local R = c.r * 0.45
	local sp = c.r * 0.35
	local x, z = findSpot(c, 0, R * 0.3, 14, sp)
	if x then shed(m, gcf(c, x, z, 0), 22, 14, rng.chance(0.5)) end
	for k = 1, 3 do
		x, z = findSpot(c, -R * 0.8 + k * R * 0.4, -R * 0.45, 7, sp)
		if x then logPile(m, gcf(c, x, z, 0), 12) end
	end
	x, z = findSpot(c, R * 0.9, -R * 0.1, 9, sp)
	if x then truck(m, gcf(c, x, z, rng.num(0, 6.28)), true) end
	x, z = findSpot(c, -R * 1.1, R * 0.4, 9, sp)
	if x then cabin(m, gcf(c, x, z, 0.4), 12, 9, true) end
end

local function buildCabinSite(c, n)
	local m = addModel("HunterCabin_" .. n, fPOI)
	local cx, cz = findSpot(c, 0, 0, 10, c.r * 0.45)
	if not cx then return end
	cabin(m, gcf(c, cx, cz, 0), rng.num(12, 15), rng.num(9, 11), rng.chance(0.5))
	local x, z = findSpot(c, cx + 12, cz + 4, 3.5, 8)
	if x then logPile(m, gcf(c, x, z, pi / 2), 5) end
	x, z = findSpot(c, cx - 12, cz + 9, 2.5, 8)
	if x then outhouse(m, gcf(c, x, z, 0.3)) end
	x, z = findSpot(c, cx + 6, cz - 12, 3, 8)
	if x then campfire(m, gcf(c, x, z, 0)) end
	if freeSpot(c, cx, cz + 16, 3) then fence(m, gcf(c, cx, cz + 16, 0), 20, true) end
end

for _, c in ipairs(clearings) do
	if c.kind == "camp" then
		poiCount.camp = poiCount.camp + 1; buildCamp(c, poiCount.camp)
	elseif c.kind == "village" then
		poiCount.village = poiCount.village + 1; buildVillage(c)
	elseif c.kind == "ruins" then
		poiCount.ruins = poiCount.ruins + 1; buildRuins(c, poiCount.ruins)
	elseif c.kind == "sawmill" then
		poiCount.sawmill = poiCount.sawmill + 1; buildSawmill(c)
	elseif c.kind == "cabin" then
		poiCount.cabin = poiCount.cabin + 1; buildCabinSite(c, poiCount.cabin)
	end
end

-- блокпост на трассе
local function pointFarFromPOIs(x, z, pad)
	for _, c in ipairs(clearings) do
		local dx, dz = c.x - x, c.z - z
		if sqrt(dx * dx + dz * dz) < c.r + pad then return false end
	end
	return true
end
do
	local main = roads[1]
	if main then
		local pts = main.pts
		for _, frac in ipairs({ 0.3, 0.4, 0.6, 0.7, 0.2, 0.8 }) do
			local k = clamp(floor(#pts * frac), 2, #pts - 1)
			local x, z = pts[k][1], pts[k][2]
			if riverQuery(x, z) > 40 and pointFarFromPOIs(x, z, 40) then
				local dx, dz = pts[k + 1][1] - pts[k - 1][1], pts[k + 1][2] - pts[k - 1][2]
				local o = { x = x, z = z, rot = atan2(dx, dz) }
				local m = addModel("Checkpoint", fPOI)
				local hw = ROAD_TYPES[1].hw
				local booth = gcf(o, hw + 5, 2, 0)
				part(m, V(5, 7, 5), booth * CFrame.new(0, 3.5, 0), C.plank, PLANKS)
				part(m, V(6.4, 0.5, 6.4), booth * CFrame.new(0, 7.2, 0), C.roof, PLANKS)
				part(m, V(0.2, 2, 3.5), booth * CFrame.new(-2.55, 4.6, 0), C.glass, GLASS)
				part(m, V(3.5, 2, 0.2), booth * CFrame.new(0, 4.6, -2.55), C.glass, GLASS)
				local post = gcf(o, hw + 1, 6, 0)
				part(m, V(0.8, 3.5, 0.8), post * CFrame.new(0, 1.75, 0), C.metal, METAL)
				for s = 0, 3 do
					part(m, V(2, 0.5, 0.5), post * CFrame.new(-1 - s * 2, 3, 0), (s % 2 == 0) and C.red or C.white, SMOOTH)
				end
				part(m, V(2, 2.6, 6), gcf(o, -hw * 0.4, -16, 0.2) * CFrame.new(0, 1.3, 0), C.concrete, CONCRETE)
				part(m, V(2, 2.6, 6), gcf(o, hw * 0.4, -28, -0.15) * CFrame.new(0, 1.3, 0), C.concrete, CONCRETE)
				sandbags(m, gcf(o, -hw - 4, -2, pi / 2), 8, 3)
				sandbags(m, gcf(o, hw + 9, -4, pi / 2), 6, 3)
				hedgehog(m, gcf(o, -hw - 8, 12, 0.3))
				hedgehog(m, gcf(o, hw + 10, -14, 0.8))
				hedgehog(m, gcf(o, -hw - 7, -22, 1.2))
				local sign = gcf(o, -hw - 3, 14, 0)
				part(m, V(0.4, 5, 0.4), sign * CFrame.new(0, 2.5, 0), C.wood, WOOD)
				part(m, V(4, 2, 0.2), sign * CFrame.new(0, 4.5, 0), C.white, PLANKS)
				block(x, z, 40)
				break
			end
		end
	end
end

-- мосты
log("Мосты и пирсы...")
local bridgeCount = 0
local function buildBridge(ax, az, bx, bz, kind)
	local hw = ROAD_TYPES[kind].hw
	local width = (kind == 3) and 3.4 or (hw * 2 + 1)
	local ya = max(getHeight(ax, az), WATER_Y + 1.6) + 0.25
	local yb = max(getHeight(bx, bz), WATER_Y + 1.6) + 0.25
	local A, B = V(ax, ya, az), V(bx, yb, bz)
	local mid = (A + B) / 2
	local L = (B - A).Magnitude
	if L < 4 or L > 90 then return end
	bridgeCount = bridgeCount + 1
	local m = addModel("Bridge_" .. bridgeCount, fInfra)
	local cf = CFrame.lookAt(mid, B)
	local yaw = atan2(bx - ax, bz - az)
	local concrete = kind == 1
	if concrete then
		part(m, V(width, 1.4, L + 2), cf * CFrame.new(0, -0.7, 0), C.concrete, CONCRETE)
		part(m, V(0.6, 1.4, L + 2), cf * CFrame.new(-width / 2 + 0.3, 0.7, 0), C.concrete2, CONCRETE)
		part(m, V(0.6, 1.4, L + 2), cf * CFrame.new(width / 2 - 0.3, 0.7, 0), C.concrete2, CONCRETE)
	else
		part(m, V(width, 0.7, L + 2), cf * CFrame.new(0, -0.35, 0), C.plank, PLANKS)
		for _, sx in ipairs({ -1, 1 }) do
			part(m, V(0.8, 1, L + 2), cf * CFrame.new(sx * (width / 2 - 0.6), -1.2, 0), C.darkwood, WOOD)
			part(m, V(0.3, 0.3, L + 2), cf * CFrame.new(sx * (width / 2 - 0.2), 2.6, 0), C.wood, WOOD)
			for k = 0, floor(L / 4) do
				part(m, V(0.35, 3, 0.35), cf * CFrame.new(sx * (width / 2 - 0.2), 1.3, -L / 2 + k * 4), C.wood, WOOD)
			end
		end
	end
	local np = max(1, floor(L / 12))
	for k = 1, np do
		local p = A + (B - A) * (k / (np + 1))
		local top = p.Y - (concrete and 1.4 or 1.0)
		local hgt = top - getHeight(p.X, p.Z) + 2
		if hgt > 0.5 then
			local rot = CFrame.new(p.X, top - hgt / 2, p.Z) * CFrame.Angles(0, yaw, 0)
			if concrete then
				part(m, V(width * 0.8, hgt, 2.4), rot, C.concrete2, CONCRETE)
			else
				part(m, V(0.9, hgt, 0.9), rot * CFrame.new(-(width / 2 - 0.6), 0, 0), C.darkwood, WOOD)
				part(m, V(0.9, hgt, 0.9), rot * CFrame.new(width / 2 - 0.6, 0, 0), C.darkwood, WOOD)
			end
		end
	end
	block(mid.X, mid.Z, L / 2 + 4)
end
for _, rd in ipairs(roads) do
	local pts = rd.pts
	local n = #pts
	local k = 1
	while k <= n do
		if riverQuery(pts[k][1], pts[k][2]) < 3 then
			local s = k
			while k <= n and riverQuery(pts[k][1], pts[k][2]) < 3 do k = k + 1 end
			local e = k - 1
			local a, b = s, e
			while a > 1 and riverQuery(pts[a][1], pts[a][2]) < 12 do a = a - 1 end
			while b < n and riverQuery(pts[b][1], pts[b][2]) < 12 do b = b + 1 end
			buildBridge(pts[a][1], pts[a][2], pts[b][1], pts[b][2], rd.kind)
		end
		k = k + 1
	end
end

-- пирсы на озёрах
for li, L in ipairs(lakes) do
	local dx, dz = L.dirX or 1, L.dirZ or 0
	local sx, sz = L.x, L.z
	local found = false
	for d = 0, L.r * 1.4, 2 do
		sx, sz = L.x + dx * d, L.z + dz * d
		if getHeight(sx, sz) > WATER_Y + 0.4 then found = true; break end
	end
	if found then
		local m = addModel("Pier_" .. li, fInfra)
		local p1 = V(sx + dx * 3, WATER_Y + 1.6, sz + dz * 3)
		local p2 = V(sx - dx * 18, WATER_Y + 1.6, sz - dz * 18)
		local cf = CFrame.lookAt((p1 + p2) / 2, p2)
		local L2 = (p2 - p1).Magnitude
		part(m, V(4, 0.5, L2), cf, C.plank, PLANKS)
		for k = 0, floor(L2 / 5) do
			for _, s in ipairs({ -1, 1 }) do
				local pp = cf * V(s * 1.7, 0, -L2 / 2 + k * 5)
				local g = getHeight(pp.X, pp.Z)
				local hgt = WATER_Y + 1.4 - g + 1
				if hgt > 0.5 then part(m, V(0.6, hgt, 0.6), CFrame.new(pp.X, g - 1 + hgt / 2, pp.Z), C.darkwood, WOOD) end
			end
		end
		part(m, V(3, 1.2, 8), cf * CFrame.new(4, -1.2, -L2 / 2 + 5) * CFrame.Angles(0, 0.2, 0.05), C.wood, PLANKS)
		block(sx, sz, 14)
	end
end

-- охотничьи вышки по краям полян
local standCount = 0
for _ = 1, CONFIG.HUNTING_STANDS * 10 do
	if standCount >= CONFIG.HUNTING_STANDS or #clearings == 0 then break end
	local c = rng.pick(clearings)
	local a = rng.num(0, 2 * pi)
	local x, z = c.x + cos(a) * c.r * 1.02, c.z + sin(a) * c.r * 1.02
	if roadEdgeDist(x, z) > 8 and riverQuery(x, z) > 10 and getHeight(x, z) > WATER_Y + 1 and not BLK[colOf(x, z)] then
		standCount = standCount + 1
		local m = addModel("HuntingStand_" .. standCount, fInfra)
		watchtower(m, CFrame.new(x, getHeight(x, z), z) * CFrame.Angles(0, -a - pi / 2, 0), 8, 3.4, C.darkwood)
		block(x, z, 5)
	end
end

---------------------------------------------------------------------------
-- 9. Растительность и камни
---------------------------------------------------------------------------
log("Шаблоны деревьев...")
local function makeFir(Ht, col)
	local m = newModel("Fir")
	local k = Ht / 30
	part(m, V(1.5 * k, Ht * 0.5, 1.5 * k), CFrame.new(0, Ht * 0.25, 0), C.trunkFir, WOOD)
	local y0 = Ht * 0.14
	local span = Ht - y0
	local W = Ht * 0.44
	for t = 0, 2 do
		local w = W * (1 - t / 3 * 0.72)
		local th = span / 3 * 1.35
		if t == 2 then w = w * 0.85; th = th * 1.15 end
		part(m, V(w, th, w), CFrame.new(0, y0 + (t + 0.5) * span / 3, 0) * CFrame.Angles(0, (t % 2) * pi / 4, 0), col, GRASS_M, nil, false)
	end
	m.WorldPivot = CFrame.new()
	return m
end
local function makePine(Ht, col)
	local m = newModel("Pine")
	local k = Ht / 34
	part(m, V(1.3 * k, Ht * 0.86, 1.3 * k), CFrame.new(0, Ht * 0.43, 0), C.trunkPine, WOOD)
	local W = Ht * 0.34
	part(m, V(W, Ht * 0.2, W * 0.85), CFrame.new(0, Ht * 0.8, 0) * CFrame.Angles(0, 0.3, 0), col, GRASS_M, nil, false)
	part(m, V(W * 0.7, Ht * 0.17, W * 0.62), CFrame.new(W * 0.12, Ht * 0.94, -W * 0.08) * CFrame.Angles(0, 1.0, 0), col, GRASS_M, nil, false)
	part(m, V(W * 0.55, Ht * 0.12, W * 0.5), CFrame.new(-W * 0.22, Ht * 0.7, W * 0.15) * CFrame.Angles(0, 0.7, 0), col, GRASS_M, nil, false)
	m.WorldPivot = CFrame.new()
	return m
end
local function makeDead(Ht)
	local m = newModel("DeadTree")
	local k = Ht / 25
	part(m, V(1.1 * k, Ht, 1.1 * k), CFrame.new(0, Ht / 2, 0), C.dead, WOOD)
	part(m, V(0.45, Ht * 0.28, 0.45), CFrame.new(0.9, Ht * 0.62, 0) * CFrame.Angles(0, 0, -0.7), C.dead, WOOD, nil, false)
	part(m, V(0.4, Ht * 0.22, 0.4), CFrame.new(-0.6, Ht * 0.78, 0.4) * CFrame.Angles(0.6, 0, 0.5), C.dead, WOOD, nil, false)
	m.WorldPivot = CFrame.new()
	return m
end
local function makeBush(s, col)
	local m = newModel("Bush")
	part(m, V(s, s * 0.7, s * 0.9), CFrame.new(0, s * 0.3, 0) * CFrame.Angles(0, 0.4, 0), col, GRASS_M, nil, false)
	part(m, V(s * 0.7, s * 0.6, s * 0.75), CFrame.new(s * 0.35, s * 0.35, s * 0.2) * CFrame.Angles(0.2, 1.1, 0.1), col, GRASS_M, nil, false)
	m.WorldPivot = CFrame.new()
	return m
end

local structParts = stats.parts
local TPL = { fir = {}, pine = {}, dead = {}, young = {}, bush = {}, rock = {}, boulder = {} }
for _, h in ipairs({ 18, 24, 30, 36 }) do
	for _, col in ipairs(C.fir) do TPL.fir[#TPL.fir + 1] = makeFir(h, col) end
end
for _, h in ipairs({ 26, 33, 40 }) do
	for _, col in ipairs(C.pine) do TPL.pine[#TPL.pine + 1] = makePine(h, col) end
end
TPL.dead = { makeDead(20), makeDead(28) }
TPL.young = { makeFir(8, C.fir[1]), makeFir(11, C.fir[2]) }
for _, s in ipairs({ 3, 4, 5 }) do
	for _, col in ipairs(C.bush) do TPL.bush[#TPL.bush + 1] = makeBush(s, col) end
end
for _, sz in ipairs({ V(2, 1.5, 2.2), V(3, 2.2, 2.6), V(4, 2.8, 3.4), V(5.5, 3.5, 4.5), V(4.5, 3, 6.5), V(7, 4.5, 5.5) }) do
	for _, col in ipairs(C.rock) do
		local p = part(nil, sz, CFrame.new(), col, SLATE)
		TPL.rock[#TPL.rock + 1] = p
	end
end
for _, sz in ipairs({ V(10, 7, 9), V(13, 8, 11), V(9, 9, 12) }) do
	TPL.boulder[#TPL.boulder + 1] = part(nil, sz, CFrame.new(), C.rock[2], SLATE)
end
local stumpTpl = part(nil, V(1.4, 2.2, 2.2), CFrame.new(), C.trunkFir, WOOD, CYL)

-- пространственный хеш для расстояний между деревьями
local function newHash() return {} end
local function hashFree(hash, cell, x, z, minD)
	local cx, cz = floor(x / cell), floor(z / cell)
	local md2 = minD * minD
	for a = cx - 1, cx + 1 do
		for b = cz - 1, cz + 1 do
			local lst = hash[a * 100000 + b]
			if lst then
				for _, p in ipairs(lst) do
					local dx, dz = p[1] - x, p[2] - z
					if dx * dx + dz * dz < md2 then return false end
				end
			end
		end
	end
	return true
end
local function hashAdd(hash, cell, x, z)
	local key = floor(x / cell) * 100000 + floor(z / cell)
	local lst = hash[key]
	if not lst then lst = {}; hash[key] = lst end
	lst[#lst + 1] = { x, z }
end

log("Посадка леса (" .. CONFIG.TREE_COUNT .. " деревьев)...")
local treeHash = newHash()
local placedTrees, attempts = 0, 0
while placedTrees < CONFIG.TREE_COUNT and attempts < CONFIG.TREE_COUNT * 14 do
	attempts = attempts + 1
	local x = rng.num(-HALF + 8, HALF - 8)
	local z = rng.num(-HALF + 8, HALF - 8)
	local id = colOf(x, z)
	local h = getHeight(x, z)
	local ok = h > WATER_Y + 1.2 and RM[id] < 0.02 and SL[id] < 1.25 and not BLK[id] and RV[id] > 4
	if ok and CM[id] > 0.3 then
		ok = (CK[id] == 1) and rng.chance(0.05)
	end
	if ok then
		ok = rng.next() < forestDensity(x, z)
	end
	if ok and hashFree(treeHash, 8, x, z, 6.5) then
		local tn = nz(x / 220, z / 220, 62)
		local r = rng.next()
		local tpl
		if r < 0.05 then
			tpl = rng.pick(TPL.dead)
		elseif r < 0.13 then
			tpl = rng.pick(TPL.young)
		elseif (tn > 0.08 and r < 0.8) or (tn <= 0.08 and r < 0.3) then
			tpl = rng.pick(TPL.pine)
		else
			tpl = rng.pick(TPL.fir)
		end
		local t = tpl:Clone()
		t:PivotTo(CFrame.new(x, h - 0.8, z) * CFrame.Angles(rng.num(-0.04, 0.04), rng.num(0, 2 * pi), rng.num(-0.04, 0.04)))
		t.Parent = fTrees
		hashAdd(treeHash, 8, x, z)
		placedTrees = placedTrees + 1
		yieldTick(4)
	end
end

log("Кусты, камни, поваленные деревья...")
local bushHash = newHash()
local placedBushes = 0
for _ = 1, CONFIG.BUSH_COUNT * 8 do
	if placedBushes >= CONFIG.BUSH_COUNT then break end
	local x = rng.num(-HALF + 6, HALF - 6)
	local z = rng.num(-HALF + 6, HALF - 6)
	local id = colOf(x, z)
	local h = getHeight(x, z)
	local ok = h > WATER_Y + 0.8 and RM[id] < 0.25 and SL[id] < 1.1 and not BLK[id]
	if ok and CM[id] > 0.45 then ok = (CK[id] == 1) and rng.chance(0.3) end
	if ok and hashFree(bushHash, 6, x, z, 3.5) and hashFree(treeHash, 8, x, z, 2.5) then
		local b = rng.pick(TPL.bush):Clone()
		b:PivotTo(CFrame.new(x, h - 0.4, z) * CFrame.Angles(0, rng.num(0, 2 * pi), 0))
		b.Parent = fVeg
		hashAdd(bushHash, 6, x, z)
		placedBushes = placedBushes + 1
		yieldTick(2)
	end
end

local function placeRock(tpl, x, z, sink)
	local h = getHeight(x, z)
	local r = tpl:Clone()
	r.CFrame = CFrame.new(x, h - tpl.Size.Y * sink, z) * CFrame.Angles(rng.num(-0.6, 0.6), rng.num(0, 2 * pi), rng.num(-0.6, 0.6))
	r.Parent = fRocks
	yieldTick(1)
end
local rockCount = 0
for _ = 1, CONFIG.ROCK_CLUSTERS * 6 do
	if rockCount >= CONFIG.ROCK_CLUSTERS then break end
	local x = rng.num(-HALF + 10, HALF - 10)
	local z = rng.num(-HALF + 10, HALF - 10)
	local id = colOf(x, z)
	local ok = getHeight(x, z) > WATER_Y - 1 and RM[id] < 0.05 and not BLK[id]
		and not (CM[id] > 0.4 and CK[id] ~= 1)
	if ok and rng.next() < 0.35 + SL[id] then
		rockCount = rockCount + 1
		for _ = 1, rng.int(1, 4) do
			local px, pz = x + rng.num(-6, 6), z + rng.num(-6, 6)
			if RM[colOf(px, pz)] < 0.05 then placeRock(rng.pick(TPL.rock), px, pz, 0.35) end
		end
	end
end
local boulders = 0
for _ = 1, CONFIG.BOULDERS * 10 do
	if boulders >= CONFIG.BOULDERS then break end
	local x = rng.num(-HALF + 20, HALF - 20)
	local z = rng.num(-HALF + 20, HALF - 20)
	local id = colOf(x, z)
	if getHeight(x, z) > WATER_Y + 1 and roadEdgeDist(x, z) > 12 and not BLK[id] and CM[id] < 0.2 then
		boulders = boulders + 1
		placeRock(rng.pick(TPL.boulder), x, z, 0.3)
	end
end

local fallen = 0
for _ = 1, CONFIG.FALLEN_TREES * 10 do
	if fallen >= CONFIG.FALLEN_TREES then break end
	local x = rng.num(-HALF + 30, HALF - 30)
	local z = rng.num(-HALF + 30, HALF - 30)
	local L = rng.num(14, 26)
	local yaw = rng.num(0, 2 * pi)
	local ex, ez = cos(yaw) * L / 2, -sin(yaw) * L / 2
	local ok = true
	for _, p in ipairs({ { x, z }, { x + ex, z + ez }, { x - ex, z - ez } }) do
		local id = colOf(p[1], p[2])
		if getHeight(p[1], p[2]) < WATER_Y + 1 or RM[id] > 0.02 or BLK[id] or CM[id] > 0.3 then ok = false end
	end
	if ok then
		fallen = fallen + 1
		local hA, hB = getHeight(x - ex, z - ez), getHeight(x + ex, z + ez)
		local pitch = atan2(hB - hA, L)
		local cf = CFrame.new(x, (hA + hB) / 2 + 0.7, z) * CFrame.Angles(0, yaw, 0) * CFrame.Angles(0, 0, pitch)
		local m = newModel("FallenTree", fVeg)
		part(m, V(L, 1.7, 1.7), cf, C.log, WOOD, CYL)
		part(m, V(0.8, 4.5, 4.5), cf * CFrame.new(-L / 2 - 0.2, 0.9, 0) * CFrame.Angles(0.3, 0, 0), C.roots, WOOD)
		part(m, V(0.4, 3, 0.4), cf * CFrame.new(L * 0.15, 1.2, 0.6) * CFrame.Angles(0.5, 0, 0.4), C.log, WOOD, nil, false)
		part(m, V(0.4, 2.4, 0.4), cf * CFrame.new(L * 0.3, 0.8, -0.8) * CFrame.Angles(-0.7, 0, 0.3), C.log, WOOD, nil, false)
	end
end

local stumps = 0
for _ = 1, CONFIG.STUMPS * 8 do
	if stumps >= CONFIG.STUMPS then break end
	local x = rng.num(-HALF + 10, HALF - 10)
	local z = rng.num(-HALF + 10, HALF - 10)
	local id = colOf(x, z)
	if getHeight(x, z) > WATER_Y + 1 and RM[id] < 0.05 and not BLK[id] and (CM[id] < 0.4 or CK[id] == 1) then
		stumps = stumps + 1
		local s = stumpTpl:Clone()
		s.CFrame = CFrame.new(x, getHeight(x, z) + 0.4, z) * CFrame.Angles(0, rng.num(0, 2 * pi), pi / 2)
		s.Parent = fVeg
	end
end

---------------------------------------------------------------------------
-- 10. Спавн, границы, свет, камера
---------------------------------------------------------------------------
do
	local sc = byKind.camp[1] or clearings[1]
	local sx, sz = 0, 0
	if sc then sx, sz = l2w(sc, -sc.r * 0.2, -sc.r * 0.1) end
	local sp = Instance.new("SpawnLocation")
	sp.Name = "Spawn"
	sp.Anchored = true
	sp.Size = V(8, 1, 8)
	sp.CFrame = CFrame.new(sx, getHeight(sx, sz) + 0.6, sz)
	sp.Transparency = 1
	sp.CanCollide = false
	sp.Neutral = true
	sp.Parent = map

	local walls = newFolder("Boundary", map)
	for _, w in ipairs({ { 0, HALF + 2, 0 }, { 0, -HALF - 2, 0 }, { HALF + 2, 0, pi / 2 }, { -HALF - 2, 0, pi / 2 } }) do
		local p = Instance.new("Part")
		p.Name = "Wall"
		p.Anchored = true
		p.Size = V(CONFIG.MAP_SIZE + 8, 600, 4)
		p.CFrame = CFrame.new(w[1], 250, w[2]) * CFrame.Angles(0, w[3], 0)
		p.Transparency = 1
		p.Parent = walls
	end
end

if CONFIG.SET_LIGHTING then
	pcall(function()
		Lighting.ClockTime = 14.5
		Lighting.GeographicLatitude = 48
		Lighting.Brightness = 2.2
		Lighting.Ambient = rgb(88, 92, 96)
		Lighting.OutdoorAmbient = rgb(122, 126, 130)
		Lighting.EnvironmentDiffuseScale = 0.45
		Lighting.EnvironmentSpecularScale = 0.25
		Lighting.GlobalShadows = true
		Lighting.ShadowSoftness = 0.3
	end)
	pcall(function() Lighting.Technology = Enum.Technology.ShadowMap end)
	for _, ch in ipairs(Lighting:GetChildren()) do
		if ch:IsA("Atmosphere") or string.sub(ch.Name, 1, 9) == "ForestMap" then ch:Destroy() end
	end
	local atm = Instance.new("Atmosphere")
	atm.Name = "ForestMap_Atmosphere"
	atm.Density = 0.36
	atm.Offset = 0.12
	atm.Color = rgb(186, 194, 198)
	atm.Decay = rgb(108, 118, 122)
	atm.Glare = 0
	atm.Haze = 1.8
	atm.Parent = Lighting
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "ForestMap_Color"
	cc.Saturation = -0.18
	cc.Contrast = 0.05
	cc.TintColor = rgb(242, 246, 240)
	cc.Parent = Lighting
	pcall(function() StarterPlayer.CameraMaxZoomDistance = 220 end)
end

map.Parent = Workspace

pcall(function()
	local cam = Workspace.CurrentCamera
	if cam then
		cam.CFrame = CFrame.lookAt(V(-HALF * 0.55, 420, -HALF * 0.55), V(0, 40, 0))
	end
end)

for _, list in pairs(TPL) do
	for _, t in ipairs(list) do t:Destroy() end
end
stumpTpl:Destroy()

log(string.format(
	"Готово! Деревьев: %d, кустов: %d, групп камней: %d, валунов: %d, поваленных деревьев: %d, пней: %d, мостов: %d, деталей в постройках: %d",
	placedTrees, placedBushes, rockCount, boulders, fallen, stumps, bridgeCount, structParts))
log(string.format("Локации: лагерей %d, деревня %d, руин %d, лесопилка %d, избушек %d, озёр %d, рек %d, дорог %d",
	poiCount.camp, poiCount.village, poiCount.ruins, poiCount.sawmill, poiCount.cabin, #lakes, #rivers, #roads))
