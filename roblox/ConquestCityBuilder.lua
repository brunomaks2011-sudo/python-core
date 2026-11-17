--[[
	ConquestCityBuilder.lua
	Добавляет на готовую карту ForestMap режим «Захват точек»:
	  • большой город (сетка улиц 5x5 кварталов): многоэтажки, дома с заходом внутрь
	    и выходом на крышу, руины, завод, парки, парковка, площадь, фонари, машины, баррикады;
	  • 3 точки захвата: A (у базы команды 1), B (площадь города), C (у базы команды 2);
	  • 2 команды с базами и точками появления;
	  • серверный скрипт захвата и счёта (ServerScriptService.ConquestServer);
	  • интерфейс игрока (StarterPlayerScripts.ConquestHUD).

	ЗАПУСК: сначала ForestMapGenerator.lua, потом этот файл.
	  Studio → View → Command Bar → вставить весь файл → Run.
	Повторный запуск пересобирает город на том же месте и обновляет скрипты.
]]

local CONFIG = {
	SEED = 777,
	MAP_SIZE = 2048,
	TEAM1 = "Синие",
	TEAM2 = "Красные",
	WIN_SCORE = 600,     -- очков для победы (каждая своя точка даёт 1 очко в секунду)
	CAPTURE_TIME = 12,   -- секунд, за которые один игрок захватывает нейтральную точку
	RESTART_DELAY = 15,  -- пауза после победы перед новым раундом
	YIELD = true,
}

local Workspace = game:GetService("Workspace")
local Teams = game:GetService("Teams")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")
local StarterPlayer = game:GetService("StarterPlayer")
local Terrain = Workspace.Terrain

local map = Workspace:FindFirstChild("ForestMap")
assert(map, "[Conquest] Сначала запусти ForestMapGenerator.lua — модель ForestMap не найдена")

local HALF = CONFIG.MAP_SIZE / 2
local floor, sqrt, abs, min, max = math.floor, math.sqrt, math.abs, math.min, math.max
local cos, sin, pi = math.cos, math.sin, math.pi
local V = Vector3.new

local function clamp(v, a, b)
	if v < a then return a elseif v > b then return b end
	return v
end
local function smoothstep(a, b, x)
	local t = clamp((x - a) / (b - a), 0, 1)
	return t * t * (3 - 2 * t)
end
local function log(msg) print("[Conquest] " .. msg) end

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

local opCount = 0
local function yieldTick(n)
	opCount = opCount + (n or 1)
	if opCount >= 400 then
		opCount = 0
		if CONFIG.YIELD then task.wait() end
	end
end

---------------------------------------------------------------------------
-- Цвета, материалы, детали
---------------------------------------------------------------------------
local function rgb(r, g, b) return Color3.fromRGB(r, g, b) end
local C = {
	panels = { rgb(150, 146, 136), rgb(138, 132, 120), rgb(160, 152, 138), rgb(124, 128, 126), rgb(146, 128, 112) },
	walls = { rgb(156, 146, 128), rgb(132, 120, 104), rgb(118, 78, 62), rgb(140, 136, 128), rgb(104, 110, 96) },
	window = rgb(38, 46, 52),
	concrete = rgb(128, 125, 118),
	concrete2 = rgb(112, 110, 104),
	brick = rgb(116, 78, 62),
	rubble = rgb(100, 96, 90),
	charred = rgb(42, 38, 35),
	burnt = rgb(66, 56, 48),
	burnt2 = rgb(54, 48, 44),
	olive = rgb(78, 84, 58),
	sand = rgb(146, 134, 104),
	crate = rgb(118, 96, 66),
	tire = rgb(34, 34, 34),
	glass = rgb(40, 48, 52),
	black = rgb(22, 22, 22),
	metal = rgb(70, 70, 68),
	lamp = rgb(200, 196, 170),
	wood = rgb(98, 78, 60),
	plank = rgb(112, 92, 70),
	roof = rgb(74, 66, 58),
	leaves = { rgb(84, 104, 60), rgb(72, 94, 54) },
	trunk = rgb(86, 68, 52),
	white = rgb(230, 230, 230),
	cars = { rgb(120, 40, 36), rgb(52, 70, 96), rgb(150, 146, 136), rgb(70, 82, 60), rgb(160, 130, 70), rgb(60, 60, 64) },
	blue = rgb(60, 125, 235),
	red = rgb(225, 65, 55),
}
local M = Enum.Material
local WOOD, PLANKS, SLATE, CONCRETE, BRICK = M.Wood, M.WoodPlanks, M.Slate, M.Concrete, M.Brick
local METAL, FABRIC, SMOOTH, GLASS, NEON, GRASS_M = M.Metal, M.Fabric, M.SmoothPlastic, M.Glass, M.Neon, M.Grass
local CYL = Enum.PartType.Cylinder

local partCount = 0
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
	partCount = partCount + 1
	yieldTick(1)
	return p
end
local function newModel(name, parent)
	local m = Instance.new("Model")
	m.Name = name
	m.Parent = parent
	return m
end
local function newFolder(name, parent)
	local f = Instance.new("Folder")
	f.Name = name
	f.Parent = parent
	return f
end

local rayParams = RaycastParams.new()
pcall(function() rayParams.FilterType = Enum.RaycastFilterType.Include end)
rayParams.FilterDescendantsInstances = { Terrain }
rayParams.IgnoreWater = false
local function groundAt(x, z)
	local r = Workspace:Raycast(V(x, 700, z), V(0, -1200, 0), rayParams)
	if r then return r.Position.Y, r.Material end
	return nil, nil
end

---------------------------------------------------------------------------
-- Строительные блоки
---------------------------------------------------------------------------
local function slabRoof(parent, base, L, W, Hh, thick, color, mat, y0, skipSide)
	local s = W / 2
	local len = sqrt(s * s + Hh * Hh)
	local th = math.atan(Hh / s)
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
-- стена вдоль локальной X; openings = { {x0, x1, y0, y1}, ... }; ruin = рваный верх
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

-- окна по этажам (+ двери на первом этаже)
local function facadeOpenings(len, floors, fh, door, spacing)
	local o = {}
	for f = 0, floors - 1 do
		local x = -len / 2 + 2.5
		while x + 2.6 < len / 2 - 1.5 do
			if not (door and f == 0 and x + 2.6 > -2.6 and x < 2.6) then
				o[#o + 1] = { x, x + 2.6, f * fh + 3, f * fh + 6.4 }
			end
			x = x + spacing
		end
	end
	if door then o[#o + 1] = { -2, 2, 0, 7 } end
	return o
end

local function sandbags(parent, base, length, layers)
	local n = max(1, floor(length / 2 + 0.5))
	for k = 0, layers - 1 do
		local odd = k % 2
		for s = 0, n - 1 - odd do
			part(parent, V(1.9, 0.9, 1.4), base * CFrame.new(-length / 2 + 1 + s * 2 + odd, 0.42 + k * 0.85, 0), C.sand, FABRIC)
		end
	end
end
local function crate(parent, cf, s)
	part(parent, V(s, s, s), cf * CFrame.new(0, s / 2, 0), C.crate, PLANKS)
end
local function hedgehog(parent, base)
	local cf = base * CFrame.new(0, 1.6, 0)
	part(parent, V(0.5, 0.5, 5), cf * CFrame.Angles(0.7, 0, 0), C.metal, METAL)
	part(parent, V(0.5, 0.5, 5), cf * CFrame.Angles(-0.7, pi / 2, 0), C.metal, METAL)
	part(parent, V(5, 0.5, 0.5), cf * CFrame.Angles(0, pi / 4, 0.7), C.metal, METAL)
end
local function jersey(parent, base)
	part(parent, V(2, 2.6, 6), base * CFrame.new(0, 1.3, 0), C.concrete, CONCRETE)
end
local function car(parent, base, wrecked)
	local col = wrecked and C.burnt or rng.pick(C.cars)
	local t = base * CFrame.Angles(0, 0, wrecked and rng.num(-0.08, 0.08) or 0)
	part(parent, V(4.4, 1.7, 9.4), t * CFrame.new(0, 1.55, 0), col, METAL)
	part(parent, V(4, 1.4, 4.6), t * CFrame.new(0, 3.1, 0.5), wrecked and C.burnt2 or col, METAL)
	if not wrecked then
		part(parent, V(3.8, 1.1, 0.2), t * CFrame.new(0, 3.1, -1.85), C.glass, GLASS)
	end
	for _, p in ipairs({ { -2.2, -3 }, { 2.2, -3 }, { -2.2, 3 }, { 2.2, 3 } }) do
		if not (wrecked and p[1] > 0 and p[2] > 0) then
			part(parent, V(0.8, 2, 2), t * CFrame.new(p[1], 1, p[2]), C.tire, SMOOTH, CYL)
		end
	end
end
local function tank(parent, base)
	local t = base * CFrame.Angles(0, 0, 0.03)
	part(parent, V(7, 2.6, 13), t * CFrame.new(0, 2.1, 0), C.olive, METAL)
	part(parent, V(1.8, 2.6, 14), t * CFrame.new(-4.3, 1.3, 0), C.metal, METAL)
	part(parent, V(1.8, 2.6, 14), t * CFrame.new(4.3, 1.3, 0), C.metal, METAL)
	local tur = t * CFrame.new(0, 4.3, 1) * CFrame.Angles(0, 0.6, 0)
	part(parent, V(5.5, 1.9, 6), tur, C.burnt, METAL)
	part(parent, V(0.7, 0.7, 8), tur * CFrame.new(0, 0.2, -6.5) * CFrame.Angles(0.08, 0, 0), C.burnt2, METAL)
end
local function lamp(parent, base)
	part(parent, V(0.45, 12, 0.45), base * CFrame.new(0, 6, 0), C.metal, METAL)
	part(parent, V(3, 0.35, 0.35), base * CFrame.new(-1.4, 11.8, 0), C.metal, METAL)
	part(parent, V(1.2, 0.4, 0.8), base * CFrame.new(-2.8, 11.6, 0), C.lamp, SMOOTH)
end
local function parkTree(parent, base)
	local h = rng.num(10, 15)
	local col = rng.pick(C.leaves)
	part(parent, V(1, h * 0.6, 1), base * CFrame.new(0, h * 0.3, 0), C.trunk, WOOD)
	part(parent, V(h * 0.55, h * 0.4, h * 0.55), base * CFrame.new(0, h * 0.68, 0) * CFrame.Angles(0, rng.num(0, 1.5), 0), col, GRASS_M, nil, false)
	part(parent, V(h * 0.38, h * 0.3, h * 0.38), base * CFrame.new(0.4, h * 0.92, -0.3) * CFrame.Angles(0, rng.num(0, 1.5), 0), col, GRASS_M, nil, false)
end
local function bench(parent, base)
	part(parent, V(5, 0.4, 1.6), base * CFrame.new(0, 1.6, 0), C.plank, PLANKS)
	part(parent, V(5, 1.2, 0.3), base * CFrame.new(0, 2.4, 0.75), C.plank, PLANKS)
	part(parent, V(4.4, 1.4, 1.2), base * CFrame.new(0, 0.7, 0), C.metal, METAL)
end
local function rubble(parent, base, spread, n, col, mat)
	for _ = 1, n do
		local s = rng.num(0.8, 2.8)
		part(parent, V(s * rng.num(0.8, 1.6), s * rng.num(0.5, 1), s),
			base * CFrame.new(rng.num(-spread, spread), s * 0.2, rng.num(-spread, spread))
			* CFrame.Angles(rng.num(-0.5, 0.5), rng.num(0, 6.28), rng.num(-0.5, 0.5)),
			rng.chance(0.5) and col or C.rubble, rng.chance(0.5) and mat or SLATE)
	end
end

-- панельная многоэтажка (сплошная)
local function apartment(parent, base, w, d, floors, color, damaged)
	local fh = 8
	local H = floors * fh
	part(parent, V(w, H + 2, d), base * CFrame.new(0, H / 2 - 1, 0), color, CONCRETE)
	for f = 0, floors - 1 do
		for _, s in ipairs({ -1, 1 }) do
			part(parent, V(w - 3, 2.6, 0.3), base * CFrame.new(0, f * fh + 4.2, s * (d / 2 + 0.1)), C.window, SMOOTH)
		end
	end
	part(parent, V(w + 0.6, 1.2, d + 0.6), base * CFrame.new(0, H + 0.6, 0), C.concrete2, CONCRETE)
	for _, k in ipairs({ -1, 1 }) do
		part(parent, V(4, 0.4, 2.4), base * CFrame.new(k * w / 4, 3.8, -d / 2 - 1.2), C.concrete2, CONCRETE)
		part(parent, V(3, 3.4, 0.3), base * CFrame.new(k * w / 4, 1.7, -d / 2 - 0.12), C.black, SMOOTH)
	end
	if damaged then
		part(parent, V(w * 0.3, fh * 1.6, 0.4), base * CFrame.new(w * 0.2, H - fh, -d / 2 - 0.2), C.charred, CONCRETE)
		part(parent, V(w * 0.25, fh, 0.4), base * CFrame.new(-w * 0.25, fh * 1.5, d / 2 + 0.2), C.charred, CONCRETE)
		rubble(parent, base * CFrame.new(w * 0.2, 0, -d / 2 - 4), 5, 8, color, CONCRETE)
	end
end

-- здание с заходом внутрь: двери спереди и сзади, окна, перекрытия и пандус до крыши
local function building(parent, base, w, d, floors, col, mat)
	local fh, t = 9, 1
	local H = floors * fh
	part(parent, V(w, 1, d), base * CFrame.new(0, -0.3, 0), C.concrete2, CONCRETE)
	wallOpen(parent, base * CFrame.new(0, 0, -d / 2 + t / 2), w, H, t, facadeOpenings(w, floors, fh, true, 5.5), col, mat, false)
	wallOpen(parent, base * CFrame.new(0, 0, d / 2 - t / 2), w, H, t, facadeOpenings(w, floors, fh, true, 5.5), col, mat, false)
	wallOpen(parent, base * CFrame.new(-w / 2 + t / 2, 0, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, H, t,
		facadeOpenings(d - 2 * t, floors, fh, false, 6), col, mat, false)
	wallOpen(parent, base * CFrame.new(w / 2 - t / 2, 0, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, H, t,
		facadeOpenings(d - 2 * t, floors, fh, false, 6), col, mat, false)
	-- пандус у правой стены, поднимается к задней стене
	local ix0, ix1 = -w / 2 + t, w / 2 - t
	local iz0, iz1 = -d / 2 + t, d / 2 - t
	local rx0 = ix1 - 4
	local zEnd = iz1 - 0.3
	local zStart = zEnd - 12
	local holeZ = zStart + 4
	local run = zEnd - zStart
	local ang = math.atan(fh / run)
	local len = sqrt(run * run + fh * fh)
	for f = 1, floors do
		local y = f * fh
		-- перекрытие (или крыша) с проёмом над пандусом
		part(parent, V(rx0 - ix0, 0.8, iz1 - iz0), base * CFrame.new((ix0 + rx0) / 2, y + 0.4, (iz0 + iz1) / 2), C.concrete2, CONCRETE)
		part(parent, V(ix1 - rx0, 0.8, holeZ - iz0), base * CFrame.new((rx0 + ix1) / 2, y + 0.4, (iz0 + holeZ) / 2), C.concrete2, CONCRETE)
		part(parent, V(3.6, 0.6, len), base * CFrame.new((rx0 + ix1) / 2, (f - 1) * fh + fh / 2, (zStart + zEnd) / 2) * CFrame.Angles(-ang, 0, 0), C.plank, PLANKS)
	end
	-- парапет
	part(parent, V(w, 1.4, 0.6), base * CFrame.new(0, H + 1.5, -d / 2 + 0.3), col, mat)
	part(parent, V(w, 1.4, 0.6), base * CFrame.new(0, H + 1.5, d / 2 - 0.3), col, mat)
	part(parent, V(0.6, 1.4, d - 1.2), base * CFrame.new(-w / 2 + 0.3, H + 1.5, 0), col, mat)
	part(parent, V(0.6, 1.4, d - 1.2), base * CFrame.new(w / 2 - 0.3, H + 1.5, 0), col, mat)
end

local function ruin(parent, base, w, d, floors)
	local brick = rng.chance(0.5)
	local col = brick and C.brick or C.concrete
	local mat = brick and BRICK or CONCRETE
	local fh, t = 9, 1
	local H = floors * fh
	part(parent, V(w + 1, 2.4, d + 1), base * CFrame.new(0, -0.9, 0), C.concrete2, CONCRETE)
	wallOpen(parent, base * CFrame.new(0, 0.3, -d / 2 + t / 2), w, H, t, facadeOpenings(w, floors, fh, true, 5), col, mat, true)
	wallOpen(parent, base * CFrame.new(0, 0.3, d / 2 - t / 2), w, H, t, facadeOpenings(w, floors, fh, false, 5), col, mat, true)
	wallOpen(parent, base * CFrame.new(-w / 2 + t / 2, 0.3, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, H, t, facadeOpenings(d - 2 * t, floors, fh, false, 5), col, mat, true)
	wallOpen(parent, base * CFrame.new(w / 2 - t / 2, 0.3, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, H, t, facadeOpenings(d - 2 * t, floors, fh, false, 5), col, mat, true)
	if floors > 1 then
		part(parent, V(w - 2 * t, 0.8, d * 0.45), base * CFrame.new(0, 9.3, d * 0.25 - t), C.concrete2, CONCRETE)
		part(parent, V(w * 0.6, 0.8, d * 0.5), base * CFrame.new(-w * 0.1, 4.5, -d * 0.15) * CFrame.Angles(0.75, 0.1, 0.05), C.concrete2, CONCRETE)
	end
	rubble(parent, base, w / 2 + 3, rng.int(8, 14), col, mat)
	for _ = 1, 2 do
		part(parent, V(0.7, 0.7, rng.num(5, 9)), base * CFrame.new(rng.num(-w / 3, w / 3), 1.5, rng.num(-d / 3, d / 3))
			* CFrame.Angles(rng.num(-0.4, 0.4), rng.num(0, 3.14), 0), C.charred, WOOD)
	end
end

local function factory(parent, base)
	local w, d, H, t = 40, 30, 14, 1.2
	part(parent, V(w, 1, d), base * CFrame.new(0, -0.3, 0), C.concrete2, CONCRETE)
	local gate = { { -5, 5, 0, 10 } }
	local high = {}
	for x = -16, 12, 7 do high[#high + 1] = { x, x + 4, 9, 12 } end
	wallOpen(parent, base * CFrame.new(0, 0, -d / 2 + t / 2), w, H, t, gate, C.brick, BRICK, false)
	wallOpen(parent, base * CFrame.new(0, 0, d / 2 - t / 2), w, H, t, { { -5, 5, 0, 10 }, { 9, 13, 9, 12 }, { -13, -9, 9, 12 } }, C.brick, BRICK, false)
	wallOpen(parent, base * CFrame.new(-w / 2 + t / 2, 0, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, H, t, { { -2, 2, 0, 7 }, { -11, -7, 9, 12 }, { 7, 11, 9, 12 } }, C.brick, BRICK, false)
	wallOpen(parent, base * CFrame.new(w / 2 - t / 2, 0, 0) * CFrame.Angles(0, pi / 2, 0), d - 2 * t, H, t, { { -11, -7, 9, 12 }, { 7, 11, 9, 12 } }, C.brick, BRICK, false)
	slabRoof(parent, base, w + 1, d + 1, 5, 0.6, C.roof, METAL, H, rng.chance(0.5) and 1 or nil)
	part(parent, V(34, 4, 4), base * CFrame.new(w / 2 - 1, 17, d / 2 + 3) * CFrame.Angles(0, 0, pi / 2), C.brick, BRICK, CYL)
	for k = 1, 4 do crate(parent, base * CFrame.new(-12 + k * 3.2, 0, -6), 3) end
	car(parent, base * CFrame.new(8, 0, 4) * CFrame.Angles(0, 0.3, 0), true)
end

---------------------------------------------------------------------------
-- 1. Выбор места для города
---------------------------------------------------------------------------
local CITY_HALF = 167
local MARGIN = 44
local FULL = CITY_HALF + MARGIN
local STREETS = { -160, -96, -32, 32, 96, 160 }

local locFolder = map:FindFirstChild("Locations")
local infraFolder = map:FindFirstChild("Infrastructure")
-- центр и размер модели (nil, если в модели нет деталей)
local function modelBox(m)
	if not m:FindFirstChildWhichIsA("BasePart", true) then return nil end
	local ok, cf, size = pcall(function() return m:GetBoundingBox() end)
	if ok then return cf, size end
	return nil
end
local obstacles = {}
for _, f in ipairs({ locFolder, infraFolder }) do
	if f then
		for _, m in ipairs(f:GetChildren()) do
			local cf, size = nil, nil
			if m:IsA("Model") and m.Name ~= "City" then cf, size = modelBox(m) end
			if cf then
				obstacles[#obstacles + 1] = { cf.Position.X, cf.Position.Z, max(size.X, size.Z) / 2 + 25 }
			end
		end
	end
end

local function siteCheck(cx, cz, n, pad)
	for _, o in ipairs(obstacles) do
		if max(abs(o[1] - cx), abs(o[2] - cz)) < FULL + o[3] then return nil end
	end
	local hs, asphalt = {}, 0
	local R = FULL + pad
	for a = 0, n do
		for b = 0, n do
			local h, m = groundAt(cx - R + a * 2 * R / n, cz - R + b * 2 * R / n)
			if not h or m == M.Water then return nil end
			hs[#hs + 1] = h
			if m == M.Asphalt then asphalt = asphalt + 1 end
		end
	end
	table.sort(hs)
	local k = floor(#hs * 0.1) + 1
	local spread = hs[#hs - k + 1] - hs[k]
	local score = spread + 0.012 * sqrt(cx * cx + cz * cz) - min(asphalt, 10) * 1.2
	return score, hs[floor(#hs / 2) + 1]
end

local cityX, cityZ, cityY
local saved = map:GetAttribute("CityCenter")
if saved then
	cityX, cityY, cityZ = saved.X, saved.Y, saved.Z
	log("Город пересобирается на прежнем месте")
else
	log("Ищу место для города...")
	local cands = {}
	local lim = HALF - FULL - 140
	local x = -lim
	while x <= lim do
		local z = -lim
		while z <= lim do
			local s, h = siteCheck(x, z, 10, 0)
			if s then cands[#cands + 1] = { s, x, z, h } end
			z = z + 48
		end
		x = x + 48
		yieldTick(100)
	end
	table.sort(cands, function(a, b) return a[1] < b[1] end)
	for k = 1, min(#cands, 25) do
		local c = cands[k]
		local s, h = siteCheck(c[2], c[3], 40, 24) -- точная проверка на воду (шаг ~13 studs)
		if s then cityX, cityZ, cityY = c[2], c[3], h; break end
	end
	assert(cityX, "[Conquest] Не нашлось ровного места без воды для города. Попробуй другой SEED карты.")
	cityY = floor(cityY + 0.5)
	map:SetAttribute("CityCenter", V(cityX, cityY, cityZ))
end
log(string.format("Город: центр (%d, %d), высота %d", floor(cityX), floor(cityZ), floor(cityY)))

---------------------------------------------------------------------------
-- 2. Рельеф: выравнивание площадки, улицы
---------------------------------------------------------------------------
local cellType = {}
local function cellKey(i, j) return i * 10 + j end
local function cellOf(v) return clamp(floor((v + 32) / 64), -2, 2) end
local function streetDist(v)
	local best = 1e9
	for _, s in ipairs(STREETS) do
		local d = abs(v - s)
		if d < best then best = d end
	end
	return best
end

do -- раскладка кварталов
	cellType[cellKey(0, 0)] = "square"
	local cells = {}
	for i = -2, 2 do
		for j = -2, 2 do
			if not (i == 0 and j == 0) then cells[#cells + 1] = { i, j } end
		end
	end
	for k = #cells, 2, -1 do
		local r = rng.int(1, k)
		cells[k], cells[r] = cells[r], cells[k]
	end
	local kinds = { "factory", "park", "park", "parking", "ruins", "ruins", "ruins", "ruins",
		"apartments", "apartments", "apartments", "apartments", "apartments", "apartments", "apartments",
		"houses", "houses", "houses", "houses", "houses", "mixed", "mixed", "mixed", "mixed" }
	for k, c in ipairs(cells) do cellType[cellKey(c[1], c[2])] = kinds[k] or "houses" end
end

local function cityMat(lx, lz)
	local dx, dz = streetDist(lx), streetDist(lz)
	if dx <= 7 or dz <= 7 then return M.Asphalt end
	if dx <= 10 or dz <= 10 then return M.Pavement end
	local i, j = cellOf(lx), cellOf(lz)
	local ct = cellType[cellKey(i, j)]
	if ct == "square" then return M.Pavement end
	if ct == "parking" then return M.Asphalt end
	if ct == "park" then
		if abs(lx - i * 64) < 2.5 or abs(lz - j * 64) < 2.5 then return M.Pavement end
		return M.Grass
	end
	if math.noise(lx / 18, lz / 18, 3.7) > 0.15 then return M.Ground end
	return M.Concrete
end

-- выравнивание квадратной площадки колонками 4x4 с плавным переходом по краям
local function flattenSquare(cx, cz, half, margin, Y, matFn)
	local R = half + margin
	local x = floor((cx - R) / 4) * 4
	while x < cx + R do
		local z = floor((cz - R) / 4) * 4
		while z < cz + R do
			local px, pz = x + 2, z + 2
			local lx, lz = px - cx, pz - cz
			local d = max(abs(lx), abs(lz)) - half
			local h0, m0 = groundAt(px, pz)
			if not h0 then h0 = Y end
			local t, mat
			if d <= 0 then
				t = Y
				mat = matFn(lx, lz)
			else
				t = Y + (h0 - Y) * smoothstep(0, margin, d)
				mat = (m0 and m0 ~= M.Water) and m0 or M.Ground
			end
			Terrain:FillBlock(CFrame.new(px, t + 45, pz), V(4, 90, 4), M.Air)
			local bottom = min(t, h0) - 10
			Terrain:FillBlock(CFrame.new(px, (t + bottom) / 2, pz), V(4, t - bottom, 4), mat)
			yieldTick(2)
			z = z + 4
		end
		x = x + 4
	end
end

local function clearVegetation(cx, cz, half)
	for _, fname in ipairs({ "Trees", "Vegetation", "Rocks" }) do
		local f = map:FindFirstChild(fname)
		if f then
			for _, ch in ipairs(f:GetChildren()) do
				local pos
				if ch:IsA("BasePart") then pos = ch.Position else pos = ch:GetPivot().Position end
				if abs(pos.X - cx) < half and abs(pos.Z - cz) < half then ch:Destroy() end
			end
		end
	end
end

-- удалить старую версию (при повторном запуске)
for _, obj in ipairs({ locFolder and locFolder:FindFirstChild("City"), Workspace:FindFirstChild("ConquestPoints"),
	Workspace:FindFirstChild("ConquestBases"), ReplicatedStorage:FindFirstChild("ConquestState"),
	ServerScriptService:FindFirstChild("ConquestServer") }) do
	if obj then obj:Destroy() end
end
local oldSpawn = map:FindFirstChild("Spawn")
if oldSpawn then oldSpawn:Destroy() end

log("Убираю лес и выравниваю площадку города...")
clearVegetation(cityX, cityZ, FULL + 6)
Terrain:SetMaterialColor(M.Pavement, rgb(122, 120, 114))
Terrain:SetMaterialColor(M.Concrete, rgb(118, 116, 110))
flattenSquare(cityX, cityZ, CITY_HALF, MARGIN, cityY, cityMat)

---------------------------------------------------------------------------
-- 3. Город
---------------------------------------------------------------------------
log("Строю город...")
local city = newModel("City", locFolder or map)
local cityCF = CFrame.new(cityX, cityY, cityZ)
local function at(lx, lz, yaw)
	return cityCF * CFrame.new(lx, 0, lz) * CFrame.Angles(0, yaw or 0, 0)
end

for i = -2, 2 do
	for j = -2, 2 do
		local ct = cellType[cellKey(i, j)]
		local ox, oz = i * 64, j * 64
		local m = newModel("Block_" .. ct .. "_" .. (i + 3) .. (j + 3), city)
		local along = rng.chance(0.5) and 0 or pi / 2
		if ct == "apartments" then
			for _, s in ipairs({ -1, 1 }) do
				local lx, lz = ox, oz
				if along == 0 then lz = oz + s * 13 else lx = ox + s * 13 end
				apartment(m, at(lx, lz, along + (s > 0 and pi or 0)), 40, 12, rng.int(4, 6), rng.pick(C.panels), rng.chance(0.3))
			end
			car(m, at(ox + rng.num(-12, 12), oz + rng.num(-3, 3), along + pi / 2), rng.chance(0.5))
		elseif ct == "houses" then
			for _, q in ipairs({ { -1, -1 }, { 1, -1 }, { -1, 1 }, { 1, 1 } }) do
				local w, d = rng.num(16, 18), rng.num(15, 17)
				local col = rng.pick(C.walls)
				local mat = (col == C.walls[3]) and BRICK or CONCRETE
				building(m, at(ox + q[1] * 11.5, oz + q[2] * 11, q[2] > 0 and pi or 0), w, d, rng.int(2, 3), col, mat)
			end
		elseif ct == "mixed" then
			local s = rng.chance(0.5) and 1 or -1
			building(m, at(ox, oz - s * 12, s > 0 and 0 or pi), 30, 16, 2, rng.pick(C.walls), CONCRETE)
			apartment(m, at(ox, oz + s * 13, s > 0 and pi or 0), 40, 12, rng.int(4, 5), rng.pick(C.panels), rng.chance(0.3))
		elseif ct == "ruins" then
			for _, q in ipairs({ { -1, -1 }, { 1, 1 }, { 1, -1 } }) do
				if rng.chance(0.85) then
					ruin(m, at(ox + q[1] * 11, oz + q[2] * 11, rng.int(0, 3) * pi / 2), rng.num(14, 18), rng.num(12, 15), rng.chance(0.4) and 2 or 1)
				end
			end
			car(m, at(ox - 11, oz + 12, rng.num(0, 6.28)), true)
		elseif ct == "factory" then
			factory(m, at(ox, oz, along))
		elseif ct == "park" then
			for _ = 1, 12 do
				local lx, lz = rng.num(-20, 20), rng.num(-20, 20)
				if abs(lx) > 4 and abs(lz) > 4 then parkTree(m, at(ox + lx, oz + lz, 0)) end
			end
			for k = 0, 3 do
				local a = k * pi / 2
				bench(m, at(ox + cos(a) * 9, oz + sin(a) * 9, -a + pi / 2))
			end
		elseif ct == "parking" then
			for _, row in ipairs({ -9, 9 }) do
				for x = -18, 18, 6 do
					if rng.chance(0.7) then car(m, at(ox + x, oz + row, row > 0 and pi or 0), rng.chance(0.35)) end
				end
			end
		elseif ct == "square" then
			-- памятник, лавки, укрытия; точка B в центре
			local mon = at(-13, -13, pi / 4)
			part(m, V(7, 4, 7), mon * CFrame.new(0, 2, 0), C.concrete2, CONCRETE)
			part(m, V(5, 1, 5), mon * CFrame.new(0, 4.5, 0), C.concrete, CONCRETE)
			part(m, V(2.2, 6, 1.6), mon * CFrame.new(0, 8, 0), C.metal, METAL)
			part(m, V(1.6, 1.6, 1.6), mon * CFrame.new(0, 11.8, 0), C.metal, METAL)
			for k = 0, 3 do
				local a = k * pi / 2 + pi / 4
				bench(m, at(cos(a) * 19, sin(a) * 19, -a - pi / 2))
			end
			tank(m, at(12, -10, 0.9))
			sandbags(m, at(-14, 10, 0.3), 10, 3)
			sandbags(m, at(14, 14, -0.6), 8, 3)
			jersey(m, at(0, 16, pi / 2))
			jersey(m, at(-4, -16, pi / 2 + 0.2))
		end
		yieldTick(20)
	end
end

do -- фонари, машины и баррикады на улицах
	local props = newModel("StreetProps", city)
	for _, s in ipairs(STREETS) do
		local v = -150
		while v <= 150 do
			if streetDist(v) > 12 then
				lamp(props, at(s + 8.6, v, 0))
				lamp(props, at(v, s + 8.6, -pi / 2))
			end
			v = v + 44
		end
	end
	local placed = 0
	for _ = 1, 200 do
		if placed >= 26 then break end
		local s = rng.pick(STREETS)
		local v = rng.num(-150, 150)
		if streetDist(v) > 14 then
			local side = rng.chance(0.5) and 1 or -1
			local wr = rng.chance(0.45)
			if rng.chance(0.5) then
				car(props, at(s + side * 4.2, v, rng.chance(0.5) and 0 or pi), wr)
			else
				car(props, at(v, s + side * 4.2, pi / 2 + (rng.chance(0.5) and 0 or pi)), wr)
			end
			placed = placed + 1
		end
	end
	local used = {}
	for _ = 1, 6 do
		local ix, iz = rng.pick(STREETS), rng.pick(STREETS)
		local key = ix * 1000 + iz
		if not used[key] and not (abs(ix) == 32 and abs(iz) == 32) then
			used[key] = true
			local b = at(ix, iz, rng.num(0, 6.28))
			jersey(props, b * CFrame.new(-3, 0, 2))
			jersey(props, b * CFrame.new(3, 0, -3) * CFrame.Angles(0, 0.4, 0))
			sandbags(props, b * CFrame.new(0, 0, 5), 8, 2)
			hedgehog(props, b * CFrame.new(6, 0, 5))
		end
	end
end

---------------------------------------------------------------------------
-- 4. Точки захвата и базы
---------------------------------------------------------------------------
log("Точки захвата и базы...")
local NAMES = {
	MilitaryCamp = "Военный лагерь", RuinedVillage = "Деревня", Ruins = "Руины",
	AbandonedSawmill = "Лесопилка", HunterCabin = "Избушка", Checkpoint = "Блокпост",
}
local function niceName(n)
	local base = string.match(n, "^(%a+)") or n
	return NAMES[base] or n
end

local B = { x = cityX, z = cityZ, name = "Город" }
local cands = {}
if locFolder then
	for _, m in ipairs(locFolder:GetChildren()) do
		local cf = nil
		if m:IsA("Model") and m ~= city then cf = modelBox(m) end
		if cf then
			cands[#cands + 1] = { x = cf.Position.X, z = cf.Position.Z, name = niceName(m.Name), raw = m.Name }
		end
	end
end
local bestA, bestC, bestS = nil, nil, -1e9
for i = 1, #cands do
	for j = i + 1, #cands do
		local a, c = cands[i], cands[j]
		local ax, az, cx2, cz2 = a.x - B.x, a.z - B.z, c.x - B.x, c.z - B.z
		local da, dc = sqrt(ax * ax + az * az), sqrt(cx2 * cx2 + cz2 * cz2)
		if da > 260 and dc > 260 then
			local cosang = (ax * cx2 + az * cz2) / (da * dc)
			local s = -cosang * 3 - abs(da - dc) / 300 - max(0, da - 850) / 250 - max(0, dc - 850) / 250
			if string.find(a.raw, "Camp") or string.find(a.raw, "Village") then s = s + 0.3 end
			if string.find(c.raw, "Camp") or string.find(c.raw, "Village") then s = s + 0.3 end
			if s > bestS then bestS, bestA, bestC = s, a, c end
		end
	end
end
if not bestA then -- запасной вариант: точки по обе стороны от города
	bestA = { x = clamp(cityX - 500, -HALF + 250, HALF - 250), z = cityZ, name = "Лес" }
	bestC = { x = clamp(cityX + 500, -HALF + 250, HALF - 250), z = cityZ, name = "Лес" }
end

local pointsFolder = newFolder("ConquestPoints", Workspace)
local function makePoint(letter, x, z, radius, label)
	local y = groundAt(x, z) or cityY
	local m = Instance.new("Model")
	m.Name = "Point_" .. letter
	m:SetAttribute("Letter", letter)
	m:SetAttribute("Radius", radius)
	m:SetAttribute("Center", V(x, y, z))
	m:SetAttribute("Label", label)
	local disc = part(m, V(0.3, radius * 2, radius * 2), CFrame.new(x, y + 0.15, z) * CFrame.Angles(0, 0, pi / 2), C.white, SMOOTH, CYL, false)
	disc.Name = "Zone"
	disc.Transparency = 0.82
	disc.CastShadow = false
	disc.CanQuery = false
	for k = 0, 19 do
		local a = k / 20 * 2 * pi
		local px, pz = x + cos(a) * radius, z + sin(a) * radius
		local gy = groundAt(px, pz) or y
		local seg = part(m, V(2 * pi * radius / 20 * 0.75, 0.4, 0.7), CFrame.new(px, gy + 0.25, pz) * CFrame.Angles(0, -a - pi / 2, 0), C.white, NEON, nil, false)
		seg.Name = "Ring"
		seg.CastShadow = false
	end
	local pole = part(m, V(0.6, 26, 0.6), CFrame.new(x, y + 12.5, z), C.metal, METAL)
	pole.Name = "Pole"
	local flag = part(m, V(0.2, 3, 5), CFrame.new(x, y + 2.5, z + 2.8), C.white, FABRIC, nil, false)
	flag.Name = "Flag"
	local bb = Instance.new("BillboardGui")
	bb.Name = "Label"
	bb.Size = UDim2.new(0, 56, 0, 56)
	bb.StudsOffset = V(0, 16, 0)
	bb.AlwaysOnTop = true
	bb.MaxDistance = 3000
	bb.LightInfluence = 0
	bb.Adornee = pole
	local tl = Instance.new("TextLabel")
	tl.Size = UDim2.new(1, 0, 1, 0)
	tl.BackgroundColor3 = rgb(20, 22, 24)
	tl.BackgroundTransparency = 0.25
	tl.Font = Enum.Font.GothamBlack
	tl.TextScaled = true
	tl.Text = letter
	tl.TextColor3 = C.white
	tl.Parent = bb
	bb.Parent = pole
	m.Parent = pointsFolder
	return m
end

makePoint("A", bestA.x, bestA.z, 22, bestA.name)
makePoint("B", cityX, cityZ, 24, "Город")
makePoint("C", bestC.x, bestC.z, 22, bestC.name)
log(string.format("A: %s, B: Город, C: %s", bestA.name, bestC.name))

-- команды
for _, t in ipairs(Teams:GetChildren()) do
	if t.Name == CONFIG.TEAM1 or t.Name == CONFIG.TEAM2 then t:Destroy() end
end
local team1 = Instance.new("Team")
team1.Name = CONFIG.TEAM1
team1.TeamColor = BrickColor.new("Bright blue")
team1.AutoAssignable = true
team1.Parent = Teams
local team2 = Instance.new("Team")
team2.Name = CONFIG.TEAM2
team2.TeamColor = BrickColor.new("Bright red")
team2.AutoAssignable = true
team2.Parent = Teams

-- базы: за точкой A (команда 1) и за точкой C (команда 2)
local basesFolder = newFolder("ConquestBases", Workspace)
local function findBaseSpot(px, pz)
	local dx, dz = px - cityX, pz - cityZ
	local d = max(sqrt(dx * dx + dz * dz), 1)
	dx, dz = dx / d, dz / d
	for _, dist in ipairs({ 170, 140, 200, 110, 230, 90 }) do
		for _, turn in ipairs({ 0, 0.35, -0.35, 0.7, -0.7 }) do
			local rx = dx * cos(turn) - dz * sin(turn)
			local rz = dx * sin(turn) + dz * cos(turn)
			local x = clamp(px + rx * dist, -HALF + 90, HALF - 90)
			local z = clamp(pz + rz * dist, -HALF + 90, HALF - 90)
			local ok, lo, hi = true, 1e9, -1e9
			for a = -2, 2 do
				for b = -2, 2 do
					local h, m = groundAt(x + a * 12, z + b * 12)
					if not h or m == M.Water then ok = false else lo = min(lo, h); hi = max(hi, h) end
				end
			end
			if ok and hi - lo < 10 then return x, z, (lo + hi) / 2 end
		end
	end
	return px, pz, groundAt(px, pz) or cityY
end

local function buildBase(team, color, px, pz)
	local x, z, y = findBaseSpot(px, pz)
	y = floor(y + 0.5)
	clearVegetation(x, z, 46)
	flattenSquare(x, z, 26, 14, y, function() return M.Ground end)
	local m = newModel("Base_" .. team.Name, basesFolder)
	local toCity = math.atan2(cityX - x, cityZ - z)
	local o = CFrame.new(x, y, z) * CFrame.Angles(0, toCity, 0) -- локальная -Z смотрит от города
	for _, p in ipairs({ { -6, -6 }, { 6, -6 }, { -6, 6 }, { 6, 6 } }) do
		local sp = Instance.new("SpawnLocation")
		sp.Name = "Spawn"
		sp.Anchored = true
		sp.Size = V(6, 1, 6)
		sp.CFrame = o * CFrame.new(p[1], 0.5, p[2])
		sp.Color = color
		sp.Material = SMOOTH
		sp.TeamColor = team.TeamColor
		sp.Neutral = false
		sp.AllowTeamChangeOnTouch = false
		sp.Duration = 5
		sp.Parent = m
	end
	local pole = part(m, V(0.6, 20, 0.6), o * CFrame.new(0, 10, -14), C.metal, METAL)
	part(m, V(0.2, 3.5, 6), o * CFrame.new(0, 17.5, -10.8), color, FABRIC, nil, false)
	sandbags(m, o * CFrame.new(0, 0, -22), 30, 3)
	sandbags(m, o * CFrame.new(-20, 0, -6) * CFrame.Angles(0, pi / 2, 0), 26, 3)
	sandbags(m, o * CFrame.new(20, 0, -6) * CFrame.Angles(0, pi / 2, 0), 26, 3)
	for _, sx in ipairs({ -1, 1 }) do
		local tb = o * CFrame.new(sx * 13, 0, -14)
		part(m, V(8, 0.2, 7), tb * CFrame.new(0, 0.1, 0), C.burnt, FABRIC)
		slabRoof(m, tb, 8, 7, 5, 0.3, color:Lerp(rgb(90, 90, 80), 0.55), FABRIC, 0)
	end
	for k = 0, 3 do crate(m, o * CFrame.new(-6 + k * 3.2, 0, 14), 3) end
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.new(0, 200, 0, 40)
	bb.StudsOffset = V(0, 14, 0)
	bb.AlwaysOnTop = true
	bb.MaxDistance = 600
	bb.LightInfluence = 0
	bb.Adornee = pole
	local tl = Instance.new("TextLabel")
	tl.Size = UDim2.new(1, 0, 1, 0)
	tl.BackgroundTransparency = 1
	tl.Font = Enum.Font.GothamBlack
	tl.TextScaled = true
	tl.TextStrokeTransparency = 0.3
	tl.TextColor3 = color
	tl.Text = "БАЗА: " .. team.Name
	tl.Parent = bb
	bb.Parent = pole
end
buildBase(team1, C.blue, bestA.x, bestA.z)
buildBase(team2, C.red, bestC.x, bestC.z)

---------------------------------------------------------------------------
-- 5. Состояние, серверный скрипт, интерфейс
---------------------------------------------------------------------------
local state = Instance.new("Folder")
state.Name = "ConquestState"
state:SetAttribute("Team1", CONFIG.TEAM1)
state:SetAttribute("Team2", CONFIG.TEAM2)
state:SetAttribute("WinScore", CONFIG.WIN_SCORE)
state:SetAttribute("CaptureTime", CONFIG.CAPTURE_TIME)
state:SetAttribute("RestartDelay", CONFIG.RESTART_DELAY)
state.Parent = ReplicatedStorage

local SERVER_SRC = [==[
-- ConquestServer: захват точек и счёт (создано ConquestCityBuilder.lua)
local Players = game:GetService("Players")
local Teams = game:GetService("Teams")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local state = ReplicatedStorage:WaitForChild("ConquestState")
local pointsFolder = workspace:WaitForChild("ConquestPoints")
local WIN_SCORE = state:GetAttribute("WinScore") or 600
local CAPTURE_TIME = state:GetAttribute("CaptureTime") or 12
local RESTART_DELAY = state:GetAttribute("RestartDelay") or 15
local team1 = Teams:WaitForChild(state:GetAttribute("Team1"))
local team2 = Teams:WaitForChild(state:GetAttribute("Team2"))
local TICK = 0.2

local COLORS = {
	Blue = Color3.fromRGB(60, 125, 235),
	Red = Color3.fromRGB(225, 65, 55),
	Neutral = Color3.fromRGB(235, 235, 235),
}

local points = {}
for _, m in ipairs(pointsFolder:GetChildren()) do
	if m:IsA("Model") and m:GetAttribute("Letter") then
		local p = {
			letter = m:GetAttribute("Letter"),
			label = m:GetAttribute("Label") or "",
			radius = m:GetAttribute("Radius") or 20,
			center = m:GetAttribute("Center"),
			progress = 0, owner = "Neutral", blue = 0, red = 0,
			rings = {}, pole = m:FindFirstChild("Pole"), flag = m:FindFirstChild("Flag"),
		}
		for _, ch in ipairs(m:GetChildren()) do
			if ch.Name == "Ring" then p.rings[#p.rings + 1] = ch end
		end
		if p.pole then
			local bb = p.pole:FindFirstChild("Label")
			p.text = bb and bb:FindFirstChildOfClass("TextLabel")
		end
		points[#points + 1] = p
	end
end
table.sort(points, function(a, b) return a.letter < b.letter end)
local letters = ""
for _, p in ipairs(points) do letters = letters .. p.letter end
state:SetAttribute("Letters", letters)

local scores = { Blue = 0, Red = 0 }
local roundOver, restartAt = false, 0

local function teamName(side)
	if side == "Blue" then return team1.Name elseif side == "Red" then return team2.Name end
	return ""
end

local function announce(text)
	state:SetAttribute("Event", text)
	state:SetAttribute("EventTime", os.clock())
end

local function countIn(p)
	local b, r = 0, 0
	for _, plr in ipairs(Players:GetPlayers()) do
		local char = plr.Character
		if char then
			local hum = char:FindFirstChildOfClass("Humanoid")
			local root = char:FindFirstChild("HumanoidRootPart")
			if hum and root and hum.Health > 0 then
				local d = root.Position - p.center
				if math.abs(d.Y) < 35 and d.X * d.X + d.Z * d.Z <= p.radius * p.radius then
					if plr.Team == team1 then b = b + 1 elseif plr.Team == team2 then r = r + 1 end
				end
			end
		end
	end
	return b, r
end

local function updatePoint(p, dt)
	local b, r = countIn(p)
	p.blue, p.red = b, r
	local rate = 100 / CAPTURE_TIME
	local diff = b - r
	if diff ~= 0 then
		local mult = math.min(1 + 0.3 * (math.abs(diff) - 1), 2.5)
		local dir = diff > 0 and 1 or -1
		p.progress = math.clamp(p.progress + dir * rate * mult * dt, -100, 100)
	elseif b == 0 then
		local target = 0
		if p.owner == "Blue" then target = 100 elseif p.owner == "Red" then target = -100 end
		if p.progress < target then
			p.progress = math.min(target, p.progress + rate * 0.5 * dt)
		elseif p.progress > target then
			p.progress = math.max(target, p.progress - rate * 0.5 * dt)
		end
	end
	local prev = p.owner
	if p.progress >= 100 then
		p.owner = "Blue"
	elseif p.progress <= -100 then
		p.owner = "Red"
	elseif (p.owner == "Blue" and p.progress <= 0) or (p.owner == "Red" and p.progress >= 0) then
		p.owner = "Neutral"
	end
	if prev ~= p.owner then
		if p.owner == "Neutral" then
			announce(teamName(prev) .. " потеряли точку " .. p.letter .. " (" .. p.label .. ")")
		else
			announce(teamName(p.owner) .. " захватили точку " .. p.letter .. " (" .. p.label .. ")")
		end
	end
end

local function updateVisual(p)
	local col = COLORS[p.owner]
	for _, ring in ipairs(p.rings) do ring.Color = col end
	if p.text then p.text.TextColor3 = col end
	if p.flag and p.pole then
		local top = p.pole.Position.Y + p.pole.Size.Y / 2 - 2
		local bottom = p.pole.Position.Y - p.pole.Size.Y / 2 + 3
		local y = bottom + (top - bottom) * math.abs(p.progress) / 100
		local fp = p.flag.Position
		p.flag.CFrame = CFrame.new(fp.X, y, fp.Z)
		if p.progress > 0 then
			p.flag.Color = COLORS.Blue
		elseif p.progress < 0 then
			p.flag.Color = COLORS.Red
		else
			p.flag.Color = COLORS.Neutral
		end
	end
	state:SetAttribute(p.letter .. "_Owner", p.owner)
	state:SetAttribute(p.letter .. "_Progress", math.floor(p.progress + 0.5))
	state:SetAttribute(p.letter .. "_Blue", p.blue)
	state:SetAttribute(p.letter .. "_Red", p.red)
end

local function publishScores()
	state:SetAttribute("BlueScore", scores.Blue)
	state:SetAttribute("RedScore", scores.Red)
end

local function resetRound()
	scores.Blue, scores.Red = 0, 0
	for _, p in ipairs(points) do
		p.progress, p.owner, p.blue, p.red = 0, "Neutral", 0, 0
		updateVisual(p)
	end
	roundOver = false
	state:SetAttribute("Winner", "")
	publishScores()
	announce("Новый раунд! Захватывайте точки")
	for _, plr in ipairs(Players:GetPlayers()) do
		pcall(function() plr:LoadCharacter() end)
	end
end

state:SetAttribute("Winner", "")
publishScores()
for _, p in ipairs(points) do updateVisual(p) end

local acc = 0
while true do
	local dt = task.wait(TICK)
	if not roundOver then
		for _, p in ipairs(points) do
			updatePoint(p, dt)
			updateVisual(p)
		end
		acc = acc + dt
		while acc >= 1 do
			acc = acc - 1
			for _, p in ipairs(points) do
				if p.owner == "Blue" or p.owner == "Red" then
					scores[p.owner] = scores[p.owner] + 1
				end
			end
		end
		publishScores()
		if scores.Blue >= WIN_SCORE or scores.Red >= WIN_SCORE then
			local w = scores.Blue >= scores.Red and "Blue" or "Red"
			state:SetAttribute("Winner", teamName(w))
			announce("Победили " .. teamName(w) .. "!")
			roundOver = true
			restartAt = os.clock() + RESTART_DELAY
		end
	elseif os.clock() >= restartAt then
		resetRound()
	end
end
]==]

local CLIENT_SRC = [==[
-- ConquestHUD: интерфейс захвата точек (создано ConquestCityBuilder.lua)
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local player = Players.LocalPlayer
local state = ReplicatedStorage:WaitForChild("ConquestState")
local pointsFolder = workspace:WaitForChild("ConquestPoints")

local BLUE = Color3.fromRGB(60, 125, 235)
local RED = Color3.fromRGB(225, 65, 55)
local NEUTRAL = Color3.fromRGB(235, 235, 235)
local DARK = Color3.fromRGB(20, 22, 24)
local T1 = state:GetAttribute("Team1") or "Team1"
local T2 = state:GetAttribute("Team2") or "Team2"

local function mk(class, props, parent)
	local o = Instance.new(class)
	for k, v in pairs(props) do o[k] = v end
	o.Parent = parent
	return o
end

local gui = mk("ScreenGui", { Name = "ConquestHUD", ResetOnSpawn = false }, player:WaitForChild("PlayerGui"))
local bar = mk("Frame", { Size = UDim2.new(0, 470, 0, 60), Position = UDim2.new(0.5, -235, 0, 6),
	BackgroundColor3 = DARK, BackgroundTransparency = 0.3, BorderSizePixel = 0 }, gui)
mk("UICorner", { CornerRadius = UDim.new(0, 8) }, bar)
local blueScore = mk("TextLabel", { Size = UDim2.new(0, 120, 1, -8), Position = UDim2.new(0, 6, 0, 4), BackgroundTransparency = 1,
	Font = Enum.Font.GothamBlack, TextScaled = true, TextColor3 = BLUE, Text = "0" }, bar)
local redScore = mk("TextLabel", { Size = UDim2.new(0, 120, 1, -8), Position = UDim2.new(1, -126, 0, 4), BackgroundTransparency = 1,
	Font = Enum.Font.GothamBlack, TextScaled = true, TextColor3 = RED, Text = "0" }, bar)

local letters = state:GetAttribute("Letters")
while not letters do
	task.wait(0.5)
	letters = state:GetAttribute("Letters")
end
local badges = {}
for i = 1, #letters do
	local L = string.sub(letters, i, i)
	local f = mk("Frame", { Size = UDim2.new(0, 46, 0, 46), Position = UDim2.new(0.5, (i - (#letters + 1) / 2) * 56 - 23, 0, 7),
		BackgroundColor3 = NEUTRAL, BorderSizePixel = 0 }, bar)
	mk("UICorner", { CornerRadius = UDim.new(0, 6) }, f)
	mk("TextLabel", { Size = UDim2.new(1, 0, 1, 0), BackgroundTransparency = 1, Font = Enum.Font.GothamBlack,
		TextScaled = true, Text = L, TextColor3 = DARK }, f)
	badges[L] = f
end
local teamLabel = mk("TextLabel", { Size = UDim2.new(0, 470, 0, 22), Position = UDim2.new(0.5, -235, 0, 68),
	BackgroundTransparency = 1, Font = Enum.Font.GothamBold, TextScaled = true, TextStrokeTransparency = 0.4,
	TextColor3 = NEUTRAL, Text = "" }, gui)
local toast = mk("TextLabel", { Size = UDim2.new(0, 560, 0, 30), Position = UDim2.new(0.5, -280, 0, 96),
	BackgroundTransparency = 1, Font = Enum.Font.GothamBold, TextScaled = true, TextStrokeTransparency = 0.3,
	TextColor3 = NEUTRAL, Text = "", Visible = false }, gui)
local cap = mk("Frame", { Size = UDim2.new(0, 380, 0, 58), Position = UDim2.new(0.5, -190, 1, -160),
	BackgroundColor3 = DARK, BackgroundTransparency = 0.3, BorderSizePixel = 0, Visible = false }, gui)
mk("UICorner", { CornerRadius = UDim.new(0, 8) }, cap)
local capText = mk("TextLabel", { Size = UDim2.new(1, -12, 0, 26), Position = UDim2.new(0, 6, 0, 4), BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold, TextScaled = true, TextColor3 = NEUTRAL, Text = "" }, cap)
local capBg = mk("Frame", { Size = UDim2.new(1, -12, 0, 16), Position = UDim2.new(0, 6, 0, 36),
	BackgroundColor3 = Color3.fromRGB(60, 60, 60), BorderSizePixel = 0 }, cap)
local capFill = mk("Frame", { Size = UDim2.new(0, 0, 1, 0), BackgroundColor3 = NEUTRAL, BorderSizePixel = 0 }, capBg)
local banner = mk("TextLabel", { Size = UDim2.new(0, 720, 0, 90), Position = UDim2.new(0.5, -360, 0.32, 0),
	BackgroundColor3 = DARK, BackgroundTransparency = 0.25, Font = Enum.Font.GothamBlack, TextScaled = true,
	TextColor3 = NEUTRAL, Text = "", Visible = false }, gui)

local points = {}
for _, m in ipairs(pointsFolder:GetChildren()) do
	if m:GetAttribute("Letter") then
		points[#points + 1] = { letter = m:GetAttribute("Letter"), center = m:GetAttribute("Center"),
			radius = m:GetAttribute("Radius"), label = m:GetAttribute("Label") or "" }
	end
end

local function ownerColor(o)
	if o == "Blue" then return BLUE elseif o == "Red" then return RED end
	return NEUTRAL
end

local lastEvent, toastUntil = nil, 0
while true do
	blueScore.Text = tostring(state:GetAttribute("BlueScore") or 0)
	redScore.Text = tostring(state:GetAttribute("RedScore") or 0)
	for L, f in pairs(badges) do f.BackgroundColor3 = ownerColor(state:GetAttribute(L .. "_Owner")) end
	if player.Team then
		teamLabel.Text = "Твоя команда: " .. player.Team.Name .. "   |   до победы: " .. tostring(state:GetAttribute("WinScore") or "")
		teamLabel.TextColor3 = (player.Team.Name == T1) and BLUE or RED
	end
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	local inside = nil
	if root then
		for _, p in ipairs(points) do
			local d = root.Position - p.center
			if math.abs(d.Y) < 35 and d.X * d.X + d.Z * d.Z <= p.radius * p.radius then inside = p end
		end
	end
	if inside then
		local L = inside.letter
		local prog = state:GetAttribute(L .. "_Progress") or 0
		local b = state:GetAttribute(L .. "_Blue") or 0
		local r = state:GetAttribute(L .. "_Red") or 0
		local txt = "Точка " .. L .. " (" .. inside.label .. ")  " .. tostring(math.abs(prog)) .. "%"
		if b > 0 and b == r then txt = "Точка " .. L .. " — ОСПАРИВАЕТСЯ" end
		capText.Text = txt
		capFill.Size = UDim2.new(math.abs(prog) / 100, 0, 1, 0)
		capFill.BackgroundColor3 = (prog > 0 and BLUE) or (prog < 0 and RED) or NEUTRAL
		cap.Visible = true
	else
		cap.Visible = false
	end
	local et = state:GetAttribute("EventTime")
	if et and et ~= lastEvent then
		if lastEvent ~= nil then
			toast.Text = state:GetAttribute("Event") or ""
			toastUntil = os.clock() + 4
		end
		lastEvent = et
	end
	toast.Visible = os.clock() < toastUntil
	local w = state:GetAttribute("Winner") or ""
	banner.Visible = w ~= ""
	banner.Text = "Победили " .. w .. "!"
	task.wait(0.1)
end
]==]

local server = Instance.new("Script")
server.Name = "ConquestServer"
server.Source = SERVER_SRC
server.Parent = ServerScriptService

local sps = StarterPlayer:FindFirstChildOfClass("StarterPlayerScripts")
if not sps then
	sps = Instance.new("StarterPlayerScripts")
	sps.Parent = StarterPlayer
end
local oldHud = sps:FindFirstChild("ConquestHUD")
if oldHud then oldHud:Destroy() end
local hud = Instance.new("LocalScript")
hud.Name = "ConquestHUD"
hud.Source = CLIENT_SRC
hud.Parent = sps

pcall(function()
	local cam = Workspace.CurrentCamera
	cam.CFrame = CFrame.lookAt(V(cityX - 260, cityY + 190, cityZ - 260), V(cityX, cityY, cityZ))
end)

log(string.format("Готово! Деталей в городе и базах: %d. Нажми Play, чтобы проверить захват точек.", partCount))
