--[[
	ConquestCityBuilder.lua
	Добавляет на готовую карту ForestMap режим «Захват точек»:
	  • большой советский город: сетка 3x3 квартала, широкие проспекты с разметкой,
	    тротуары с бордюрами, кирпичные хрущёвки 5–6 этажей с подъездами, лестницами,
	    квартирами и выходом на крышу, балконы, дворы с детскими площадками, гаражи,
	    школа со стадионом, магазин «Продукты», Дом культуры на площади,
	    разрушенная хрущёвка, машины, фонари, баррикады;
	  • 3 точки захвата: A (у базы команды 1), B (площадь города), C (у базы команды 2);
	  • 2 команды с базами и точками появления;
	  • серверный скрипт захвата и счёта (ServerScriptService.ConquestServer);
	  • интерфейс игрока (StarterPlayerScripts.ConquestHUD).

	ЗАПУСК: сначала ForestMapGenerator.lua, потом этот файл.
	  Studio → View → Command Bar → вставить весь файл → Run.
	Повторный запуск пересобирает всё заново (старый город убирается).
]]

local CONFIG = {
	SEED = 777,
	MAP_SIZE = 2048,
	TEAM1 = "Синие",
	TEAM2 = "Красные",
	WIN_SCORE = 600,     -- очков для победы (каждая своя точка даёт 1 очко в секунду)
	CAPTURE_TIME = 12,   -- секунд, за которые один игрок захватывает нейтральную точку
	RESTART_DELAY = 15,  -- пауза после победы перед новым раундом
	FLOORS = { 5, 5, 5, 6 }, -- этажность хрущёвок (выбирается случайно)
	INTERIORS = true,    -- подъезды, лестницы и квартиры внутри домов
	FURNITURE = true,    -- простая мебель в квартирах
	STREET_TREES = true, -- деревья вдоль проспектов
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
	bricks = { rgb(198, 178, 142), rgb(190, 186, 174), rgb(180, 158, 126), rgb(204, 190, 160) },
	inner = rgb(178, 172, 158),
	slab = rgb(132, 128, 120),
	roofTop = rgb(66, 66, 68),
	step = rgb(140, 136, 128),
	glassWin = rgb(70, 92, 104),
	sill = rgb(204, 202, 194),
	plinth = rgb(108, 106, 100),
	balcony = { rgb(62, 112, 74), rgb(52, 122, 116), rgb(88, 136, 166), rgb(196, 196, 186) },
	frame = rgb(226, 226, 220),
	sofa = { rgb(120, 60, 50), rgb(70, 90, 110), rgb(110, 100, 70) },
	bed = rgb(172, 162, 142),
	kitchen = rgb(210, 208, 200),
	garage = { rgb(110, 116, 112), rgb(96, 104, 118), rgb(128, 108, 88), rgb(84, 96, 80) },
	dk = rgb(198, 186, 158),
	dk2 = rgb(176, 166, 140),
	signBg = rgb(36, 64, 112),
	concrete = rgb(128, 125, 118),
	concrete2 = rgb(112, 110, 104),
	curb = rgb(160, 158, 150),
	line = rgb(220, 220, 214),
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
	leaves = { rgb(96, 122, 64), rgb(84, 110, 58), rgb(106, 128, 70) },
	trunk = rgb(86, 68, 52),
	birch = rgb(222, 220, 212),
	white = rgb(230, 230, 230),
	cars = { rgb(200, 198, 190), rgb(168, 50, 44), rgb(52, 76, 110), rgb(196, 176, 130), rgb(72, 96, 70), rgb(90, 90, 96) },
	play = { rgb(196, 70, 54), rgb(60, 120, 180), rgb(220, 180, 60) },
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
local function glassify(p, tr)
	if p then
		p.Transparency = tr or 0.4
		p.Reflectance = 0.12
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.CastShadow = false
	end
	return p
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

-- надпись на детали (вывеска)
local function sign(p, text, color)
	local g = Instance.new("SurfaceGui")
	g.Face = Enum.NormalId.Front
	g.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	g.PixelsPerStud = 20
	g.LightInfluence = 0.3
	local t = Instance.new("TextLabel")
	t.Size = UDim2.new(1, 0, 1, 0)
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextScaled = true
	t.TextColor3 = color or C.white
	t.Text = text
	t.Parent = g
	g.Parent = p
end

---------------------------------------------------------------------------
-- Стены из прямоугольных блоков в локальных координатах здания
---------------------------------------------------------------------------
-- box(x0,x1,y0,y1,z0,z1,...) — деталь по границам. clip = обрушение: всё, что
-- правее clip.x, обрезается по высоте clip.y (с рваным краем).
local function newBoxer(m, base, clip)
	return function(x0, x1, y0, y1, z0, z1, col, mat, shape, collide)
		if clip and (x0 + x1) / 2 > clip.x then
			local top = clip.y + rng.num(-3, 4)
			if y1 > top then y1 = top end
		end
		if x1 - x0 < 0.05 or y1 - y0 < 0.05 or z1 - z0 < 0.05 then return nil end
		return part(m, V(x1 - x0, y1 - y0, z1 - z0), base * CFrame.new((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), col, mat, shape, collide)
	end
end
local function axisBox(box, axis, a0, a1, y0, y1, c0, c1, col, mat)
	if axis == "x" then return box(a0, a1, y0, y1, c0, c1, col, mat) end
	return box(c0, c1, y0, y1, a0, a1, col, mat)
end

-- стена с проёмами {a0, a1, y0, y1}: вдоль оси axis от a0 до a1, толщина c0..c1
local function openWall(box, axis, a0, a1, c0, c1, yBase, yTop, openings, col, mat)
	local xs = { a0, a1 }
	for _, o in ipairs(openings) do xs[#xs + 1] = o[1]; xs[#xs + 1] = o[2] end
	table.sort(xs)
	for k = 1, #xs - 1 do
		local a, b = xs[k], xs[k + 1]
		if b - a > 0.05 and a >= a0 - 0.01 and b <= a1 + 0.01 then
			local mid = (a + b) / 2
			local ops = {}
			for _, o in ipairs(openings) do
				if mid > o[1] and mid < o[2] then ops[#ops + 1] = o end
			end
			table.sort(ops, function(p, q) return p[3] < q[3] end)
			local y = yBase
			for _, o in ipairs(ops) do
				if o[3] - y > 0.05 then axisBox(box, axis, a, b, y, o[3], c0, c1, col, mat) end
				if o[4] > y then y = o[4] end
			end
			if yTop - y > 0.05 then axisBox(box, axis, a, b, y, yTop, c0, c1, col, mat) end
		end
	end
end

-- фасад с сеткой окон: простенки на всю высоту + пояса между окнами;
-- соседние колонки с одинаковым рисунком окон объединяются (меньше деталей)
local function gridFacade(box, axis, a0, a1, c0, c1, H, cols, col, mat, sills)
	local x = a0
	for _, c in ipairs(cols) do
		if c.a0 - x > 0.05 then axisBox(box, axis, x, c.a0, 0, H, c0, c1, col, mat) end
		x = c.a1
	end
	if a1 - x > 0.05 then axisBox(box, axis, x, a1, 0, H, c0, c1, col, mat) end
	local thin = (c1 - c0) * 0.03
	local k = 1
	while k <= #cols do
		local j = k
		while j < #cols and cols[j + 1].key == cols[k].key do j = j + 1 end
		local ra, rb = cols[k].a0, cols[j].a1
		local ops = cols[k].ops
		local y = 0
		for _, o in ipairs(ops) do
			if o[1] - y > 0.05 then axisBox(box, axis, ra, rb, y, o[1], c0 + thin, c1 - thin, col, mat) end
			y = o[2]
		end
		if H - y > 0.05 then axisBox(box, axis, ra, rb, y, H, c0 + thin, c1 - thin, col, mat) end
		local cm = (c0 + c1) / 2
		glassify(axisBox(box, axis, ra, rb, cols[k].glassFrom or ops[1][1], ops[#ops][2], cm - 0.08, cm + 0.08, C.glassWin, GLASS), 0.35)
		if sills and cols[k].key ~= "S" and string.sub(cols[k].key, 1, 1) == "W" then
			for _, o in ipairs(ops) do
				axisBox(box, axis, ra - 0.3, rb + 0.3, o[1] - 0.3, o[1], c0 - 0.3, c1 + 0.3, C.sill, CONCRETE)
			end
		end
		k = j + 1
	end
end

---------------------------------------------------------------------------
-- Хрущёвка: N подъездов, F этажей. Фасад с подъездами смотрит в локальную -Z.
---------------------------------------------------------------------------
local SEC, DEP, FH = 36, 28, 10
local function floorY(k) return 2.6 + k * FH end

local function khrushchevka(m, base, N, F, o)
	local S, D, fh, t, ti = SEC, DEP, FH, 1, 0.6
	local L = N * S
	local yk = floorY
	local Ht = yk(F) + 1.2
	local box = newBoxer(m, base, o.clip)
	local col, mat = o.color, o.mat or BRICK
	local winW, winH = o.winW or 3.6, o.winH or 4.4
	local xs = {}
	for s = 1, N do xs[s] = -L / 2 + S * (s - 0.5) end
	local function key(x, k)
		if o.clip and x > o.clip.x then return k .. "c" end
		return k
	end
	local W = {}
	for k = 0, F - 1 do W[#W + 1] = { yk(k) + 3, yk(k) + 3 + winH } end

	-- цоколь
	box(-L / 2 - 0.3, L / 2 + 0.3, -1.5, 0.6, -D / 2 - 0.3, D / 2 + 0.3, C.plinth, CONCRETE)

	-- фасады
	local front, back, ends = {}, {}, {}
	for s = 1, N do
		local x = xs[s]
		for _, dx in ipairs({ -13, -7 }) do
			front[#front + 1] = { a0 = x + dx - winW / 2, a1 = x + dx + winW / 2, ops = W, key = key(x + dx, "W") }
		end
		local sops = { { 0, 6.5 } }
		for k = 0, F - 1 do
			local mid = yk(k) + fh / 2
			sops[#sops + 1] = { mid + 2, mid + 5.2 }
		end
		front[#front + 1] = { a0 = x - 2.2, a1 = x + 2.2, ops = sops, key = "S", glassFrom = 7.5 }
		for _, dx in ipairs({ 7, 13 }) do
			front[#front + 1] = { a0 = x + dx - winW / 2, a1 = x + dx + winW / 2, ops = W, key = key(x + dx, "W") }
		end
		for _, dx in ipairs({ -13, -7, 0, 7, 13 }) do
			back[#back + 1] = { a0 = x + dx - winW / 2, a1 = x + dx + winW / 2, ops = W, key = key(x + dx, "W") }
		end
	end
	for _, dz in ipairs({ -6, 6 }) do
		ends[#ends + 1] = { a0 = dz - winW / 2, a1 = dz + winW / 2, ops = W, key = "W" }
	end
	gridFacade(box, "x", -L / 2, L / 2, -D / 2, -D / 2 + t, Ht, front, col, mat, true)
	gridFacade(box, "x", -L / 2, L / 2, D / 2 - t, D / 2, Ht, back, col, mat, true)
	gridFacade(box, "z", -D / 2 + t, D / 2 - t, -L / 2, -L / 2 + t, Ht, ends, col, mat, true)
	gridFacade(box, "z", -D / 2 + t, D / 2 - t, L / 2 - t, L / 2, Ht, ends, col, mat, true)

	local zf = -D / 2 + t     -- внутренняя грань фасада с подъездами
	local zfl = zf + 11       -- начало этажной площадки
	local zb = zf + 17        -- задняя стена лестничной клетки
	local ziw = D / 2 - t

	-- перекрытия (уровень 0 — сплошной пол над подвалом, уровень F — крыша)
	local function slab(xa, xb, y0, y1, za, zb2, c)
		if o.clip and xa < o.clip.x and xb > o.clip.x then
			box(xa, o.clip.x, y0, y1, za, zb2, c, CONCRETE)
			box(o.clip.x, xb, y0, y1, za, zb2, c, CONCRETE)
		else
			box(xa, xb, y0, y1, za, zb2, c, CONCRETE)
		end
	end
	for k = 0, F do
		local y = yk(k)
		local y0 = (k == 0) and 0.6 or (y - 0.8)
		local c = (k == F) and C.roofTop or C.slab
		for s = 0, N do
			local xa = (s == 0) and (-L / 2 + t) or (xs[s] + 5)
			local xb = (s == N) and (L / 2 - t) or (xs[s + 1] - 5)
			slab(xa, xb, y0, y, -D / 2 + t, D / 2 - t, c)
		end
		for s = 1, N do
			box(xs[s] - 5, xs[s] + 5, y0, y, zfl, ziw, c, CONCRETE)
		end
	end

	for s = 1, N do
		local x = xs[s]
		-- вход: ступенька, козырёк, стойки, открытая дверь, лавочка
		box(x - 2.8, x + 2.8, 0, 0.6, -D / 2 - 1.4, -D / 2, C.step, CONCRETE)
		box(x - 3.6, x + 3.6, 7, 7.4, -D / 2 - 3.2, -D / 2, C.concrete2, CONCRETE)
		box(x - 3.4, x - 3.1, 0, 7, -D / 2 - 3.1, -D / 2 - 2.8, C.metal, METAL)
		box(x + 3.1, x + 3.4, 0, 7, -D / 2 - 3.1, -D / 2 - 2.8, C.metal, METAL)
		part(m, V(2.1, 6.2, 0.2), base * CFrame.new(x - 2.2, 3.7, -D / 2 - 0.1) * CFrame.Angles(0, -1.7, 0) * CFrame.new(1.05, 0, 0), C.garage[2], METAL)

		-- лестница: вход 0.6 → площадка 1-го этажа 2.6, далее марши с промежуточными площадками
		box(x + 0.4, x + 5, 0.6, 1.6, zfl - 2.8, zfl - 1.4, C.step, CONCRETE)
		box(x + 0.4, x + 5, 0.6, 2.6, zfl - 1.4, zfl, C.step, CONCRETE)
		for k = 0, F - 1 do
			local y = yk(k)
			box(x - 5, x + 5, y + fh / 2 - 0.8, y + fh / 2, zf, zf + 4, C.slab, CONCRETE)
			for j = 1, 5 do
				box(x - 5, x - 0.4, y + j - 1, y + j, zfl - j * 1.4, zfl - (j - 1) * 1.4, C.step, CONCRETE)
				box(x + 0.4, x + 5, y + 5 + j - 1, y + 5 + j, zf + 4 + (j - 1) * 1.4, zf + 4 + j * 1.4, C.step, CONCRETE)
			end
		end

		-- стены лестничной клетки и квартир
		if CONFIG.INTERIORS then
			local dSide, dBack = {}, {}
			for k = 0, F - 1 do
				dSide[#dSide + 1] = { zfl + 1, zfl + 4, yk(k), yk(k) + 7 }
				dBack[#dBack + 1] = { x - 1.5, x + 1.5, yk(k), yk(k) + 7 }
			end
			openWall(box, "z", zf, zb + ti, x - 5.6, x - 5, 0, yk(F), dSide, C.inner, CONCRETE)
			openWall(box, "z", zf, zb + ti, x + 5, x + 5.6, 0, yk(F), dSide, C.inner, CONCRETE)
			openWall(box, "x", x - 5, x + 5, zb, zb + ti, 0, yk(F), dBack, C.inner, CONCRETE)
			local xl0 = (s == 1) and (-L / 2 + t) or (x - S / 2 + ti / 2)
			local xr1 = (s == N) and (L / 2 - t) or (x + S / 2 - ti / 2)
			local dl, dr = {}, {}
			for k = 0, F - 1 do
				dl[#dl + 1] = { x - 10, x - 7.4, yk(k), yk(k) + 7 }
				dl[#dl + 1] = { xl0 + 2, xl0 + 4.6, yk(k), yk(k) + 7 }
				dr[#dr + 1] = { x + 7.4, x + 10, yk(k), yk(k) + 7 }
				dr[#dr + 1] = { xr1 - 4.6, xr1 - 2, yk(k), yk(k) + 7 }
			end
			openWall(box, "x", xl0, x - 5.6, zb, zb + ti, 0, yk(F), dl, C.inner, CONCRETE)
			openWall(box, "x", x + 5.6, xr1, zb, zb + ti, 0, yk(F), dr, C.inner, CONCRETE)
			local xml, xmr = (xl0 + x - 5.6) / 2, (x + 5.6 + xr1) / 2
			box(xml - 0.3, xml + 0.3, 0, yk(F), zb + ti, ziw, C.inner, CONCRETE)
			box(xmr - 0.3, xmr + 0.3, 0, yk(F), zb + ti, ziw, C.inner, CONCRETE)
			if s < N then box(x + S / 2 - ti / 2, x + S / 2 + ti / 2, 0, yk(F), -D / 2 + t, D / 2 - t, C.inner, CONCRETE) end

			if CONFIG.FURNITURE then
				for k = 0, F - 1 do
					local y = yk(k)
					for _, sd in ipairs({ -1, 1 }) do
						local outer = (sd < 0) and xl0 or xr1
						local function X(a, b) -- координаты от внешней стены квартиры внутрь
							if sd < 0 then return outer + a, outer + b end
							return outer - b, outer - a
						end
						if rng.chance(0.4) then
							local a, b = X(0.4, 3)
							box(a, b, y, y + 2.2, zf + 3, zf + 9, rng.pick(C.sofa), FABRIC)
						end
						if rng.chance(0.3) then
							local a, b = X(5, 8)
							box(a, b, y, y + 2.6, zf + 5, zf + 7.5, C.wood, WOOD)
						end
						if rng.chance(0.4) then
							local a, b = X(0.4, 4.4)
							box(a, b, y, y + 1.8, zb + ti + 1, zb + ti + 7, C.bed, FABRIC)
						end
						if rng.chance(0.35) then
							local a, b = X(6.6, 11.6)
							box(a, b, y, y + 3, ziw - 2, ziw, C.kitchen, SMOOTH)
						end
					end
				end
			end
		end

		-- выход на крышу (будка над лестницей)
		local yr = yk(F)
		box(x - 5.6, x - 5, yr, yr + 8, zf, zb + ti, col, mat)
		box(x + 5, x + 5.6, yr, yr + 8, zf, zb + ti, col, mat)
		box(x - 5, x + 5, yr + 1.2, yr + 8, -D / 2, zf, col, mat)
		openWall(box, "x", x - 5, x + 5, zb, zb + ti, yr, yr + 8, { { x - 1.5, x + 1.5, yr, yr + 7 } }, col, mat)
		box(x - 6, x + 6, yr + 8, yr + 8.5, -D / 2 - 0.4, zb + ti + 0.4, C.roofTop, CONCRETE)
		-- вентшахты
		box(x + 10, x + 12, yr, yr + 2.6, -D / 2 + 2, -D / 2 + 3.6, col, mat)
		box(x - 12, x - 10, yr, yr + 2.6, D / 2 - 3.6, D / 2 - 2, col, mat)

		-- балконы
		for _, dx in ipairs({ -7, 7 }) do
			for k = 1, F - 1 do
				if rng.chance(o.balcony or 0.55) then
					local bx, y = x + dx, yk(k)
					local bc = rng.pick(C.balcony)
					box(bx - 3, bx + 3, y - 0.4, y, -D / 2 - 3, -D / 2, C.slab, CONCRETE)
					box(bx - 3, bx + 3, y, y + 3.2, -D / 2 - 3, -D / 2 - 2.75, bc, METAL)
					box(bx - 3, bx - 2.75, y, y + 3.2, -D / 2 - 2.75, -D / 2, bc, METAL)
					box(bx + 2.75, bx + 3, y, y + 3.2, -D / 2 - 2.75, -D / 2, bc, METAL)
					if rng.chance(0.4) then
						glassify(box(bx - 3, bx + 3, y + 3.2, y + 6.3, -D / 2 - 3, -D / 2 - 2.85, C.glassWin, GLASS), 0.3)
						box(bx - 3.1, bx + 3.1, y + 6.3, y + 6.7, -D / 2 - 3.1, -D / 2, C.frame, SMOOTH)
					end
				end
			end
		end
		if rng.chance(0.65) then
			part(m, V(5, 0.4, 1.6), base * CFrame.new(x + 6, 1.6, -D / 2 - 5), C.plank, PLANKS)
			part(m, V(5, 1.2, 0.3), base * CFrame.new(x + 6, 2.4, -D / 2 - 4.25), C.plank, PLANKS)
			part(m, V(4.4, 1.4, 1.2), base * CFrame.new(x + 6, 0.7, -D / 2 - 5), C.metal, METAL)
		end
	end

	-- антенна
	local ax = xs[rng.int(1, N)] + 12
	box(ax - 0.1, ax + 0.1, yk(F), yk(F) + 7, 4, 4.2, C.metal, METAL)
	box(ax - 2, ax + 2, yk(F) + 6, yk(F) + 6.2, 4, 4.2, C.metal, METAL)

	-- копоть на фасаде
	if o.burn then
		for _ = 1, 7 do
			local s = rng.int(1, N)
			local dx = rng.pick({ -13, -7, 7, 13 })
			local k = rng.int(0, F - 1)
			local side = rng.chance(0.5) and -1 or 1
			local zc = side * (D / 2 + 0.06)
			local p = box(xs[s] + dx - 3.5, xs[s] + dx + 3.5, yk(k) + 1.5, yk(k) + fh + 1, zc - 0.05, zc + 0.05, C.charred, SLATE)
			if p then p.CanCollide = false; p.CanQuery = false end
		end
	end
	-- завал у обрушенной части
	if o.clip then
		local cx0 = o.clip.x
		for _ = 1, 30 do
			local s = rng.num(1, 5)
			local px = rng.num(cx0 - 4, L / 2 + 6)
			local pz = rng.pick({ -1, 1 }) * rng.num(D / 2 - 4, D / 2 + 9)
			part(m, V(s * rng.num(1, 2.2), s * rng.num(0.4, 0.9), s), base * CFrame.new(px, s * 0.25, pz)
				* CFrame.Angles(rng.num(-0.5, 0.5), rng.num(0, 6.28), rng.num(-0.5, 0.5)), rng.chance(0.6) and col or C.rubble, rng.chance(0.6) and mat or SLATE)
		end
		for _ = 1, 3 do
			part(m, V(rng.num(10, 16), 0.8, rng.num(8, 12)), base * CFrame.new(rng.num(cx0 + 4, L / 2 - 6), rng.num(4, 9), rng.num(-6, 6))
				* CFrame.Angles(rng.num(-0.6, 0.6), rng.num(-0.3, 0.3), rng.num(-0.7, 0.7)), C.slab, CONCRETE)
		end
	end
	return L, D
end

---------------------------------------------------------------------------
-- Прочие постройки и объекты
---------------------------------------------------------------------------
local function sandbags(parent, base, length, layers)
	local n = max(1, floor(length / 2 + 0.5))
	for k = 0, layers - 1 do
		local odd = k % 2
		for s = 0, n - 1 - odd do
			part(parent, V(1.9, 0.9, 1.4), base * CFrame.new(-length / 2 + 1 + s * 2 + odd, 0.42 + k * 0.85, 0), C.sand, FABRIC)
		end
	end
end
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
	part(parent, V(0.45, 13, 0.45), base * CFrame.new(0, 6.5, 0), C.metal, METAL)
	part(parent, V(3.6, 0.35, 0.35), base * CFrame.new(-1.7, 12.8, 0), C.metal, METAL)
	part(parent, V(1.4, 0.4, 0.8), base * CFrame.new(-3.4, 12.6, 0), C.lamp, SMOOTH)
end
local function tree(parent, base, birch)
	local h = rng.num(13, 20)
	local col = rng.pick(C.leaves)
	if birch then
		part(parent, V(0.8, h * 0.75, 0.8), base * CFrame.new(0, h * 0.37, 0), C.birch, WOOD)
		part(parent, V(h * 0.38, h * 0.45, h * 0.38), base * CFrame.new(0, h * 0.72, 0) * CFrame.Angles(0, rng.num(0, 1.5), 0), col, GRASS_M, nil, false)
		part(parent, V(h * 0.26, h * 0.28, h * 0.26), base * CFrame.new(0.3, h * 0.98, -0.2) * CFrame.Angles(0, rng.num(0, 1.5), 0), col, GRASS_M, nil, false)
	else
		part(parent, V(1, h * 0.55, 1), base * CFrame.new(0, h * 0.27, 0), C.trunk, WOOD)
		part(parent, V(h * 0.5, h * 0.42, h * 0.5), base * CFrame.new(0, h * 0.66, 0) * CFrame.Angles(0, rng.num(0, 1.5), 0), col, GRASS_M, nil, false)
		part(parent, V(h * 0.34, h * 0.3, h * 0.34), base * CFrame.new(0.4, h * 0.92, -0.3) * CFrame.Angles(0, rng.num(0, 1.5), 0), col, GRASS_M, nil, false)
	end
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
local function playground(m, cf)
	local c1, c2, c3 = C.play[1], C.play[2], C.play[3]
	-- песочница
	local sb = cf * CFrame.new(-10, 0, 0)
	part(m, V(8, 0.7, 0.5), sb * CFrame.new(0, 0.35, -3.75), C.plank, PLANKS)
	part(m, V(8, 0.7, 0.5), sb * CFrame.new(0, 0.35, 3.75), C.plank, PLANKS)
	part(m, V(0.5, 0.7, 7), sb * CFrame.new(-3.75, 0.35, 0), C.plank, PLANKS)
	part(m, V(0.5, 0.7, 7), sb * CFrame.new(3.75, 0.35, 0), C.plank, PLANKS)
	part(m, V(7, 0.3, 7), sb * CFrame.new(0, 0.2, 0), C.sand, FABRIC)
	-- качели
	local sw = cf * CFrame.new(2, 0, -2)
	part(m, V(0.4, 7, 0.4), sw * CFrame.new(-3, 3.5, 0), c2, METAL)
	part(m, V(0.4, 7, 0.4), sw * CFrame.new(3, 3.5, 0), c2, METAL)
	part(m, V(6.4, 0.4, 0.4), sw * CFrame.new(0, 7, 0), c2, METAL)
	part(m, V(2, 0.3, 1.2), sw * CFrame.new(0, 2, 0), c1, PLANKS)
	-- горка
	local sl = cf * CFrame.new(10, 0, 2)
	part(m, V(3, 0.4, 3), sl * CFrame.new(0, 5, -3), c3, METAL)
	part(m, V(2.4, 0.3, 8), sl * CFrame.new(0, 2.6, 2.4) * CFrame.Angles(-0.62, 0, 0), c1, METAL)
	part(m, V(0.3, 5, 0.3), sl * CFrame.new(-1.3, 2.5, -4.3), c2, METAL)
	part(m, V(0.3, 5, 0.3), sl * CFrame.new(1.3, 2.5, -4.3), c2, METAL)
	-- турник
	local tb = cf * CFrame.new(2, 0, 8)
	part(m, V(0.3, 6, 0.3), tb * CFrame.new(-2.5, 3, 0), C.metal, METAL)
	part(m, V(0.3, 6, 0.3), tb * CFrame.new(2.5, 3, 0), C.metal, METAL)
	part(m, V(5.3, 0.25, 0.25), tb * CFrame.new(0, 6, 0), C.metal, METAL)
end
local function garages(m, cf, n)
	for k = 0, n - 1 do
		local g = cf * CFrame.new((k - (n - 1) / 2) * 7, 0, 0)
		part(m, V(6.9, 7, 11), g * CFrame.new(0, 3.5, 0), C.concrete, CONCRETE)
		part(m, V(5.6, 5.6, 0.2), g * CFrame.new(0, 2.8, -5.55), rng.pick(C.garage), METAL)
		part(m, V(7.3, 0.4, 11.6), g * CFrame.new(0, 7.2, 0.2), C.roofTop, CONCRETE)
	end
end
local function trashSpot(m, cf)
	part(m, V(10, 0.3, 4), cf * CFrame.new(0, 0.15, 0), C.concrete2, CONCRETE)
	for k = -1, 1 do part(m, V(2.6, 3.4, 2.6), cf * CFrame.new(k * 3.1, 1.85, 0), C.garage[4], METAL) end
end
local function shop(m, base, w, d, text)
	local box = newBoxer(m, base, nil)
	local h, t = 7.5, 0.8
	box(-w / 2, w / 2, -1, 0.6, -d / 2, d / 2, C.plinth, CONCRETE)
	local wins = { { -w / 2 + 2, -3, 1.6, 6 }, { -2, 2, 0.6, 6.6 }, { 3, w / 2 - 2, 1.6, 6 } }
	openWall(box, "x", -w / 2, w / 2, -d / 2, -d / 2 + t, 0, h, wins, C.bricks[2], BRICK)
	openWall(box, "x", -w / 2, w / 2, d / 2 - t, d / 2, 0, h, { { -2, 2, 0.6, 6.6 } }, C.bricks[2], BRICK)
	box(-w / 2, -w / 2 + t, 0, h, -d / 2 + t, d / 2 - t, C.bricks[2], BRICK)
	box(w / 2 - t, w / 2, 0, h, -d / 2 + t, d / 2 - t, C.bricks[2], BRICK)
	box(-w / 2 - 0.4, w / 2 + 0.4, h, h + 0.6, -d / 2 - 0.4, d / 2 + 0.4, C.roofTop, CONCRETE)
	glassify(box(-w / 2 + 2, -3, 1.6, 6, -d / 2 + 0.3, -d / 2 + 0.45, C.glassWin, GLASS), 0.35)
	glassify(box(3, w / 2 - 2, 1.6, 6, -d / 2 + 0.3, -d / 2 + 0.45, C.glassWin, GLASS), 0.35)
	box(-w / 2 + 2, w / 2 - 2, 0.6, 3.6, d / 2 - 4, d / 2 - 2.5, C.kitchen, SMOOTH)
	local sg = box(-w / 2 + 3, w / 2 - 3, h + 0.6, h + 3, -d / 2 - 0.3, -d / 2 + 0.2, C.signBg, SMOOTH)
	if sg then sign(sg, text) end
end
local function palace(m, base)
	local box = newBoxer(m, base, nil)
	box(-27, 27, -1, 20, -10, 14, C.dk, CONCRETE)
	box(-28, 28, 20, 21.6, -11, 15, C.dk2, CONCRETE)
	for _, y in ipairs({ 4, 12 }) do
		glassify(box(-25, -14, y, y + 5, -10.25, -10, C.glassWin, GLASS), 0)
		glassify(box(14, 25, y, y + 5, -10.25, -10, C.glassWin, GLASS), 0)
	end
	box(-15, 15, 0, 0.8, -20, -10, C.step, CONCRETE)
	box(-15, 15, 0.8, 1.6, -18, -10, C.step, CONCRETE)
	box(-4, 4, 1.6, 9, -10.3, -10, C.black, SMOOTH)
	for k = 0, 5 do
		part(m, V(16.4, 1.7, 1.7), base * CFrame.new(-11 + k * 4.4, 1.6 + 8.2, -16.5) * CFrame.Angles(0, 0, pi / 2), C.white, CONCRETE, CYL)
	end
	box(-13.5, 13.5, 18, 19.6, -18, -10, C.dk2, CONCRETE)
	box(-11, 11, 19.6, 21, -17.5, -10, C.dk2, CONCRETE)
	box(-7, 7, 21, 22.4, -17, -10, C.dk2, CONCRETE)
	local sg = box(-12, 12, 18.2, 19.4, -18.3, -18, C.signBg, SMOOTH)
	if sg then sign(sg, "ДОМ КУЛЬТУРЫ") end
end
local function busStop(m, cf)
	part(m, V(8, 0.3, 3), cf * CFrame.new(0, 6, 0), C.concrete2, CONCRETE)
	part(m, V(8, 5.8, 0.2), cf * CFrame.new(0, 3, 1.4), C.glassWin, GLASS).Transparency = 0.4
	part(m, V(0.3, 6, 0.3), cf * CFrame.new(-3.8, 3, -1.2), C.metal, METAL)
	part(m, V(0.3, 6, 0.3), cf * CFrame.new(3.8, 3, -1.2), C.metal, METAL)
	part(m, V(6, 0.4, 1.2), cf * CFrame.new(0, 1.6, 0.6), C.plank, PLANKS)
end

---------------------------------------------------------------------------
-- 1. Выбор места для города
---------------------------------------------------------------------------
local NB, PITCH = 3, 200
local CITY_HALF = NB * PITCH / 2 + 12
local MARGIN = 50
local FULL = CITY_HALF + MARGIN
local SIDEWALK = 6
local USABLE = PITCH / 2 - 16 - SIDEWALK
local LINES = {}
for k = 0, NB do
	LINES[#LINES + 1] = { -NB * PITCH / 2 + k * PITCH, (k > 0 and k < NB) and 16 or 12 }
end

local locFolder = map:FindFirstChild("Locations")
local infraFolder = map:FindFirstChild("Infrastructure")
local function modelBox(m)
	if not m:FindFirstChildWhichIsA("BasePart", true) then return nil end
	local ok, cf, size = pcall(function() return m:GetBoundingBox() end)
	if ok then return cf, size end
	return nil
end

local function siteCheck(cx, cz, n, pad)
	local hs = {}
	local R = FULL + pad
	for a = 0, n do
		for b = 0, n do
			local h, m = groundAt(cx - R + a * 2 * R / n, cz - R + b * 2 * R / n)
			if not h or m == M.Water then return nil end
			hs[#hs + 1] = h
		end
	end
	table.sort(hs)
	local k = floor(#hs * 0.1) + 1
	local spread = hs[#hs - k + 1] - hs[k]
	return spread + 0.01 * sqrt(cx * cx + cz * cz), hs[floor(#hs / 2) + 1]
end

local cityX, cityZ, cityY
local oldCenter, oldHalf = map:GetAttribute("CityCenter"), map:GetAttribute("CityHalf")
if oldCenter and oldHalf == FULL then
	cityX, cityY, cityZ = oldCenter.X, oldCenter.Y, oldCenter.Z
	log("Город пересобирается на прежнем месте")
else
	log("Ищу место для города...")
	local cands = {}
	local lim = HALF - FULL - 90
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
		local s, h = siteCheck(c[2], c[3], 56, 20) -- точная проверка на воду (шаг ~14 studs)
		if s then cityX, cityZ, cityY = c[2], c[3], h; break end
	end
	assert(cityX, "[Conquest] Не нашлось ровного места без воды для города. Попробуй другой SEED карты.")
	cityY = floor(cityY + 0.5)
end
log(string.format("Город: центр (%d, %d), высота %d", floor(cityX), floor(cityZ), floor(cityY)))

---------------------------------------------------------------------------
-- 2. План кварталов
---------------------------------------------------------------------------
local rects = {} -- прямоугольники материалов рельефа в координатах города
local blocks = {}
for i = 0, NB - 1 do
	for j = 0, NB - 1 do
		blocks[#blocks + 1] = {
			cx = -NB * PITCH / 2 + PITCH / 2 + i * PITCH,
			cz = -NB * PITCH / 2 + PITCH / 2 + j * PITCH,
			rot = rng.chance(0.5),
			center = (i == floor(NB / 2) and j == floor(NB / 2)),
		}
	end
end
do
	local kinds = { "yard4", "yard4", "yard3", "destroyed", "school", "garages", "shops", "yard4" }
	for k = #kinds, 2, -1 do
		local r = rng.int(1, k)
		kinds[k], kinds[r] = kinds[r], kinds[k]
	end
	local n = 0
	for _, b in ipairs(blocks) do
		if b.center then
			b.kind = "square"
		else
			n = n + 1
			b.kind = kinds[n] or "yard4"
		end
	end
end

local function B2C(b, u, v)
	if b.rot then return b.cx + v, b.cz - u end
	return b.cx + u, b.cz + v
end
local function bRect(b, u0, u1, v0, v1, mat)
	if b.rot then
		rects[#rects + 1] = { b.cx + v0, b.cx + v1, b.cz - u1, b.cz - u0, mat }
	else
		rects[#rects + 1] = { b.cx + u0, b.cx + u1, b.cz + v0, b.cz + v1, mat }
	end
end
local function bCF(b, u, v, yaw)
	local x, z = B2C(b, u, v)
	return CFrame.new(cityX + x, cityY, cityZ + z) * CFrame.Angles(0, (yaw or 0) + (b.rot and pi / 2 or 0), 0)
end
local function pickFloors() return CONFIG.FLOORS[rng.int(1, #CONFIG.FLOORS)] end

-- дом в квартале: центр (u, v), разворот yaw; добавляет прямоугольники под домом и проездом
local function planHouse(b, u, v, yaw, N, F, extra)
	local h = { u = u, v = v, yaw = yaw, N = N, F = F, color = rng.pick(C.bricks) }
	if extra then for k2, v2 in pairs(extra) do h[k2] = v2 end end
	b.houses = b.houses or {}
	b.houses[#b.houses + 1] = h
	local L = N * SEC
	local rotated = abs(sin(yaw)) > 0.5
	local hu, hv = L / 2 + 1, DEP / 2 + 1
	if rotated then hu, hv = hv, hu end
	bRect(b, u - hu, u + hu, v - hv, v + hv, M.Concrete)
	-- тротуар и проезд перед подъездами (подъезды смотрят по локальной -Z дома)
	local fx, fz = -sin(yaw), -cos(yaw)
	if abs(fz) > 0.5 then
		local e = v + fz * (DEP / 2)
		bRect(b, u - hu, u + hu, min(e, e + fz * 5), max(e, e + fz * 5), M.Pavement)
		bRect(b, -USABLE, USABLE, min(e + fz * 6, e + fz * 14), max(e + fz * 6, e + fz * 14), M.Asphalt)
	else
		local e = u + fx * (DEP / 2)
		bRect(b, min(e, e + fx * 5), max(e, e + fx * 5), v - hv, v + hv, M.Pavement)
		bRect(b, min(e + fx * 6, e + fx * 14), max(e + fx * 6, e + fx * 14), -USABLE, USABLE, M.Asphalt)
	end
	return h
end

for _, b in ipairs(blocks) do
	if b.kind == "square" then
		bRect(b, -USABLE, USABLE, -USABLE, USABLE, M.Pavement)
		bRect(b, -50, -20, -60, -30, M.Grass)
		bRect(b, 20, 50, -60, -30, M.Grass)
		bRect(b, -60, -36, 0, 30, M.Grass)
		bRect(b, 36, 60, 0, 30, M.Grass)
	elseif b.kind == "yard4" or b.kind == "destroyed" or b.kind == "garages" or b.kind == "shops" or b.kind == "school" then
		if b.kind == "school" then
			planHouse(b, 0, -46, pi, 3, 3, { school = true, color = rgb(204, 192, 160) })
			bRect(b, -52, 52, 6, 66, M.Ground)
			bRect(b, -44, 44, 14, 58, M.Grass)
		elseif b.kind == "shops" then
			planHouse(b, -14, -48, pi, 3, pickFloors())
			bRect(b, -40, 40, 12, 34, M.Asphalt)
		else
			local back = planHouse(b, 0, -48, pi, 4, pickFloors())
			if b.kind == "destroyed" then back.clip = true end
			if b.kind == "garages" then
				bRect(b, -66, 66, 30, 58, M.Asphalt)
			else
				local fr = planHouse(b, 0, 48, 0, 4, pickFloors())
				if b.kind == "destroyed" then fr.burn = true end
				bRect(b, -16, 16, -10, 10, M.Sand)
			end
		end
	elseif b.kind == "yard3" then
		planHouse(b, -20, -48, pi, 3, pickFloors())
		planHouse(b, -20, 48, 0, 3, pickFloors())
		planHouse(b, 56, 0, pi / 2, 3, pickFloors())
		bRect(b, -34, -6, -10, 10, M.Sand)
	end
end

---------------------------------------------------------------------------
-- 3. Рельеф: выравнивание площадки, улицы
---------------------------------------------------------------------------
local function lineDist(v)
	local best = 1e9
	for _, ln in ipairs(LINES) do
		local d = abs(v - ln[1]) - ln[2]
		if d < best then best = d end
	end
	return best
end
local function cityMat(lx, lz)
	local dx, dz = lineDist(lx), lineDist(lz)
	if dx <= 0 or dz <= 0 then return M.Asphalt end
	if dx <= SIDEWALK or dz <= SIDEWALK then return M.Pavement end
	for k = #rects, 1, -1 do
		local r = rects[k]
		if lx >= r[1] and lx <= r[2] and lz >= r[3] and lz <= r[4] then return r[5] end
	end
	if math.noise(lx / 20, lz / 20, 5.3) > 0.35 then return M.Ground end
	return M.Grass
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
-- локации и постройки, попавшие на место города, убираются
for _, f in ipairs({ locFolder, infraFolder }) do
	if f then
		for _, m in ipairs(f:GetChildren()) do
			local cf = nil
			if m:IsA("Model") then cf = modelBox(m) end
			if cf and abs(cf.Position.X - cityX) < FULL + 10 and abs(cf.Position.Z - cityZ) < FULL + 10 then
				m:Destroy()
			end
		end
	end
end

log("Убираю лес и выравниваю площадку города (это самый долгий шаг)...")
clearVegetation(cityX, cityZ, FULL + 6)
Terrain:SetMaterialColor(M.Pavement, rgb(122, 120, 114))
Terrain:SetMaterialColor(M.Concrete, rgb(118, 116, 110))
flattenSquare(cityX, cityZ, CITY_HALF, MARGIN, cityY, cityMat)

-- следы старого города (если он стоял в другом месте) зарастают травой
if oldCenter and oldHalf ~= FULL then
	local R = oldHalf or 211
	local x = floor((oldCenter.X - R) / 4) * 4
	while x < oldCenter.X + R do
		local z = floor((oldCenter.Z - R) / 4) * 4
		while z < oldCenter.Z + R do
			local px, pz = x + 2, z + 2
			if abs(px - cityX) > FULL or abs(pz - cityZ) > FULL then
				local h, m0 = groundAt(px, pz)
				if h and (m0 == M.Asphalt or m0 == M.Pavement or m0 == M.Concrete) then
					Terrain:FillBlock(CFrame.new(px, h - 1, pz), V(4, 2, 4), M.Grass)
				end
			end
			yieldTick(1)
			z = z + 4
		end
		x = x + 4
	end
end
map:SetAttribute("CityCenter", V(cityX, cityY, cityZ))
map:SetAttribute("CityHalf", FULL)

---------------------------------------------------------------------------
-- 4. Город
---------------------------------------------------------------------------
log("Строю город...")
local city = newModel("City", locFolder or map)
local function at(lx, lz, yaw)
	return CFrame.new(cityX + lx, cityY, cityZ + lz) * CFrame.Angles(0, yaw or 0, 0)
end

local houseCount = 0
for _, b in ipairs(blocks) do
	local m = newModel("Block_" .. b.kind, city)
	for _, h in ipairs(b.houses or {}) do
		houseCount = houseCount + 1
		local hm = newModel(h.school and "School" or ("Khrushchevka_" .. houseCount), m)
		local L = h.N * SEC
		local o = { color = h.color, burn = h.burn }
		if h.clip then o.clip = { x = L / 2 - SEC, y = floorY(2) } end
		if h.school then
			o.mat = CONCRETE
			o.winW = 5
			o.winH = 5.2
			o.balcony = 0
		end
		local base = bCF(b, h.u, h.v, h.yaw)
		khrushchevka(hm, base, h.N, h.F, o)
		if h.school then
			local sg = part(hm, V(16, 2.4, 0.3), base * CFrame.new(0, floorY(h.F) - 1.2, -DEP / 2 - 0.25), C.signBg, SMOOTH)
			sign(sg, "ШКОЛА №1")
		end
		-- деревья за домом
		for k = -2, 2 do
			if rng.chance(0.7) then
				local bu = h.u + k * L / 5 + rng.num(-3, 3)
				local bv = h.v + (DEP / 2 + 7) * (cos(h.yaw) > 0 and 1 or -1)
				if abs(sin(h.yaw)) < 0.5 and abs(bv) < USABLE - 2 then tree(m, bCF(b, bu, bv, 0), rng.chance(0.6)) end
			end
		end
	end
	if b.kind == "yard4" or b.kind == "yard3" or b.kind == "destroyed" then
		local pu = (b.kind == "yard3") and -20 or 0
		playground(m, bCF(b, pu, 0, 0))
		trashSpot(m, bCF(b, pu + 40, 14, 0))
		for k = 1, 5 do tree(m, bCF(b, pu + rng.num(-40, 40), rng.pick({ -14, 14 }) + rng.num(-2, 2), 0), rng.chance(0.6)) end
		for _ = 1, 4 do
			local side = rng.chance(0.5) and -1 or 1
			car(m, bCF(b, rng.num(-60, 60), side * 30, pi / 2), b.kind == "destroyed" and rng.chance(0.6))
		end
		if b.kind == "destroyed" then
			tank(m, bCF(b, 20, 6, 0.7))
			sandbags(m, bCF(b, -24, 8, 0.3), 12, 3)
			jersey(m, bCF(b, 34, -6, 1.2))
			rubble(m, bCF(b, 50, -30, 0), 10, 14, C.bricks[1], BRICK)
		end
	elseif b.kind == "school" then
		for _, gu in ipairs({ -40, 40 }) do
			local g = bCF(b, gu, 36, pi / 2)
			part(m, V(0.4, 4, 0.4), g * CFrame.new(-4, 2, 0), C.white, METAL)
			part(m, V(0.4, 4, 0.4), g * CFrame.new(4, 2, 0), C.white, METAL)
			part(m, V(8.4, 0.4, 0.4), g * CFrame.new(0, 4, 0), C.white, METAL)
		end
		for k = -3, 3 do tree(m, bCF(b, k * 14, 70, 0), true) end
	elseif b.kind == "garages" then
		garages(m, bCF(b, 0, 26, pi), 14)
		garages(m, bCF(b, 0, 64, 0), 14)
		trashSpot(m, bCF(b, -50, -16, 0))
		for _ = 1, 3 do car(m, bCF(b, rng.num(-50, 50), 44, rng.num(0, 6.28)), rng.chance(0.4)) end
		for k = 1, 4 do tree(m, bCF(b, rng.num(-60, 60), rng.num(-14, 14), 0), true) end
	elseif b.kind == "shops" then
		shop(m, bCF(b, 0, 48, 0), 34, 18, "ПРОДУКТЫ")
		shop(m, bCF(b, 52, -46, pi), 20, 14, "АПТЕКА")
		for k = -2, 2 do
			if rng.chance(0.7) then car(m, bCF(b, k * 12, 22, 0), rng.chance(0.3)) end
		end
		for k = 1, 3 do part(m, V(4, 5, 4), bCF(b, -30 + k * 8, 4, 0) * CFrame.new(0, 2.5, 0), rng.pick(C.balcony), METAL) end
	elseif b.kind == "square" then
		palace(m, bCF(b, 0, 58, 0))
		local mon = bCF(b, 0, 26, 0)
		part(m, V(8, 4, 8), mon * CFrame.new(0, 2, 0), C.concrete2, CONCRETE)
		part(m, V(6, 1, 6), mon * CFrame.new(0, 4.5, 0), C.concrete, CONCRETE)
		part(m, V(2.4, 6.5, 1.8), mon * CFrame.new(0, 8.25, 0), C.metal, METAL)
		part(m, V(1.6, 1.6, 1.6), mon * CFrame.new(0, 12.3, 0), C.metal, METAL)
		part(m, V(0.6, 3.4, 0.6), mon * CFrame.new(1.4, 10.6, -0.6) * CFrame.Angles(0.5, 0, -0.7), C.metal, METAL)
		local fo = bCF(b, -40, -40, 0)
		for k = 0, 7 do
			local a = k / 8 * 2 * pi
			part(m, V(5.4, 1.4, 1), fo * CFrame.new(cos(a) * 6.6, 0.7, sin(a) * 6.6) * CFrame.Angles(0, -a - pi / 2, 0), C.concrete, CONCRETE)
		end
		glassify(part(m, V(0.4, 12, 12), fo * CFrame.new(0, 0.6, 0) * CFrame.Angles(0, 0, pi / 2), rgb(70, 110, 120), GLASS, CYL), 0.3)
		for k = 0, 7 do
			local a = k / 8 * 2 * pi + pi / 8
			bench(m, bCF(b, cos(a) * 34, sin(a) * 34, -a - pi / 2))
		end
		for _, p in ipairs({ { -35, -45 }, { 35, -45 }, { -48, 15 }, { 48, 15 }, { -30, -52 }, { 30, -52 }, { -52, 25 }, { 52, 25 } }) do
			tree(m, bCF(b, p[1], p[2], 0), false)
		end
		tank(m, bCF(b, 18, -14, 0.9))
		sandbags(m, bCF(b, -16, 10, 0.3), 10, 3)
		sandbags(m, bCF(b, 14, 16, -0.6), 8, 3)
		jersey(m, bCF(b, 0, -20, pi / 2))
		jersey(m, bCF(b, -10, -22, pi / 2 + 0.2))
		for k = 1, 3 do part(m, V(4, 5, 4), bCF(b, 44 + k * 6, -10, 0) * CFrame.new(0, 2.5, 0), rng.pick(C.balcony), METAL) end
	end
	yieldTick(50)
end

do -- улицы: разметка, бордюры, фонари, деревья, машины, остановки, баррикады
	local props = newModel("Streets", city)
	local len = NB * PITCH + 24
	for _, ln in ipairs(LINES) do
		local pos, hw = ln[1], ln[2]
		part(props, V(0.35, 0.12, len), at(pos, 0) * CFrame.new(0, 0.1, 0), C.line, SMOOTH, nil, false)
		part(props, V(len, 0.12, 0.35), at(0, pos) * CFrame.new(0, 0.1, 0), C.line, SMOOTH, nil, false)
		-- бордюры по сторонам улиц между перекрёстками
		for k = 1, #LINES - 1 do
			local a = LINES[k][1] + LINES[k][2]
			local bnd = LINES[k + 1][1] - LINES[k + 1][2]
			for _, sd in ipairs({ -1, 1 }) do
				local e = pos + sd * (hw + 0.3)
				if abs(e) < CITY_HALF then
					part(props, V(0.6, 0.5, bnd - a), at(e, (a + bnd) / 2) * CFrame.new(0, 0.2, 0), C.curb, CONCRETE)
					part(props, V(bnd - a, 0.5, 0.6), at((a + bnd) / 2, e) * CFrame.new(0, 0.2, 0), C.curb, CONCRETE)
				end
			end
		end
		-- фонари
		local v = -NB * PITCH / 2 + 24
		while v <= NB * PITCH / 2 - 24 do
			if lineDist(v) > 10 then
				if abs(pos + hw + 3) < CITY_HALF then lamp(props, at(pos + hw + 3, v, 0)) end
				if abs(pos - hw - 3) < CITY_HALF then lamp(props, at(v, pos - hw - 3, pi / 2)) end
				if CONFIG.STREET_TREES and hw > 12 and rng.chance(0.8) then
					tree(props, at(pos - hw - 3.5, v + 20, 0), false)
					tree(props, at(v + 20, pos + hw + 3.5, 0), false)
				end
			end
			v = v + 48
		end
	end
	local placed = 0
	for _ = 1, 300 do
		if placed >= 30 then break end
		local ln = rng.pick(LINES)
		local v = rng.num(-NB * PITCH / 2 + 20, NB * PITCH / 2 - 20)
		if lineDist(v) > 14 then
			local side = rng.chance(0.5) and 1 or -1
			local off = ln[1] + side * (ln[2] - 3.5)
			local wr = rng.chance(0.4)
			if abs(off) < CITY_HALF - 3 then
				if rng.chance(0.5) then
					car(props, at(off, v, rng.chance(0.5) and 0 or pi), wr)
				else
					car(props, at(v, off, pi / 2 + (rng.chance(0.5) and 0 or pi)), wr)
				end
				placed = placed + 1
			end
		end
	end
	for k = 1, 4 do
		local ln = LINES[2 + (k % 2)]
		local v = (k <= 2) and -150 or 150
		if k % 2 == 1 then
			busStop(props, at(ln[1] + ln[2] + 3, v, pi / 2))
		else
			busStop(props, at(v, ln[1] + ln[2] + 3, 0))
		end
	end
	local used = {}
	for _ = 1, 7 do
		local ix, iz = rng.pick(LINES)[1], rng.pick(LINES)[1]
		local key = ix * 10000 + iz
		if not used[key] then
			used[key] = true
			local bc = at(ix, iz, rng.num(0, 6.28))
			jersey(props, bc * CFrame.new(-4, 0, 3))
			jersey(props, bc * CFrame.new(4, 0, -4) * CFrame.Angles(0, 0.4, 0))
			sandbags(props, bc * CFrame.new(0, 0, 7), 10, 2)
			hedgehog(props, bc * CFrame.new(8, 0, 7))
			hedgehog(props, bc * CFrame.new(-9, 0, -6))
		end
	end
end
log(string.format("Город построен: %d домов, деталей: %d", houseCount, partCount))


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
	cam.CFrame = CFrame.lookAt(V(cityX - 430, cityY + 300, cityZ - 430), V(cityX, cityY, cityZ))
end)

log(string.format("Готово! Деталей в городе и базах: %d. Нажми Play, чтобы проверить захват точек.", partCount))
