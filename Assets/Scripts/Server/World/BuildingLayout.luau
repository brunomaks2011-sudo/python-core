--!strict
-- Turns a building archetype into kit pieces plus a structural support graph.
--
-- Building-local frame: origin = footprint centre at pad level, +Z = front.
-- Module M = 9 studs (3 m), storey RH = 9 studs, slab SL = 0.75, walls T = 0.9.
-- Outer size: W = w*M + 2T, D = d*M + 2T (corner pillars close the corners).
--
-- Support rules (a piece stands while ANY of its supports stands):
--   ground-floor walls/corners/interior walls/stairs -> ground
--   ring beam (band) of storey r -> wall below it;  wall of storey r -> its band
--   slab cell -> adjacent bands, interior walls / columns below, or (within two
--   hops) a neighbouring slab that is supported; roof pieces -> top band / attic
--   slab; balconies -> band; glass -> its window wall.

local BuildingLayout = {}

export type Piece = {
	kind: string,
	kit: string?, -- kit model name (ReplicatedStorage.Assets.Models.Buildings.Kit.*)
	cf: CFrame, -- building-local
	size: Vector3?, -- procedural pieces
	shape: string?, -- "box" | "wedge"
	material: Enum.Material?,
	color: Color3?,
	mat: string, -- durability class
	hp: number,
	supports: { number },
	lateral: { number },
	grounded: boolean,
	row: number,
	glass: string?, -- kit name of the glass pane fitted in this opening
	structural: boolean,
}

local M, RH, SL, T = 9, 9, 0.75, 0.9
local WH = RH - SL

local STYLE_MAT = { plaster = "plaster", brick = "brick", panel = "panel", concrete = "concrete", metal = "metal", wood = "wood" }
local HP = { plaster = 450, brick = 520, panel = 650, concrete = 700, metal = 320, wood = 220, glass = 4, steel = 900, tile = 250 }
local KIND_HP = { wall = 1.0, window = 0.75, door = 0.65, bigdoor = 0.6, shopwindow = 0.6, frenchwindow = 0.65, corner = 1.3, band = 1.0, slab = 1.0, parapet = 0.5, roofslope = 1.0, gable = 0.8, balcony = 0.6, int_wall = 0.45, int_door = 0.4, stairs = 0.9, column = 1.0 }

local ROOF_COLORS = {
	plaster = { mat = Enum.Material.ClayRoofTiles, color = Color3.fromRGB(148, 72, 52) },
	wood = { mat = Enum.Material.CorrodedMetal, color = Color3.fromRGB(96, 92, 86) },
	concrete = { mat = Enum.Material.CorrodedMetal, color = Color3.fromRGB(150, 152, 148) }, -- corrugated asbestos sheets
	brick = { mat = Enum.Material.CorrodedMetal, color = Color3.fromRGB(110, 104, 96) },
	panel = { mat = Enum.Material.Slate, color = Color3.fromRGB(70, 70, 72) },
	metal = { mat = Enum.Material.CorrodedMetal, color = Color3.fromRGB(120, 126, 128) },
}
local SLAB_COLOR = Color3.fromRGB(150, 148, 142)
local FLAT_ROOF = Color3.fromRGB(60, 60, 62)

function BuildingLayout.generate(arch: { [string]: any }, style: string, seed: number): ({ Piece }, Vector3)
	local rng = Random.new(seed)
	local w, d, rows = arch.w, arch.d, arch.rows
	local W, D = w * M + 2 * T, d * M + 2 * T
	local mat = STYLE_MAT[style] or "plaster"
	local pieces: { Piece } = {}
	local function add(p: Piece): number
		table.insert(pieces, p)
		return #pieces
	end
	local function hpOf(kind: string, m: string): number
		return math.floor((HP[m] or 400) * (KIND_HP[kind] or 1))
	end

	local hall = arch.slabs == false
	-- index helpers -------------------------------------------------------------
	-- walls[r][side][k] -> piece index ; sides: "F","B","R","L"
	local walls: { [number]: { [string]: { [number]: number } } } = {}
	local bands: { [number]: { [string]: { [number]: number } } } = {}
	local corners: { [number]: { number } } = {}
	local slabs: { [number]: { [number]: { [number]: number } } } = {}
	local intWalls: { [number]: { [number]: number } } = {}

	local function sideCFrame(side: string, k: number, y: number): CFrame
		if side == "F" then
			return CFrame.new(-W / 2 + T + M * (k + 0.5), y, D / 2 - T / 2) * CFrame.Angles(0, math.pi, 0)
		elseif side == "B" then
			return CFrame.new(-W / 2 + T + M * (k + 0.5), y, -D / 2 + T / 2)
		elseif side == "R" then
			return CFrame.new(W / 2 - T / 2, y, -D / 2 + T + M * (k + 0.5)) * CFrame.Angles(0, -math.pi / 2, 0)
		else
			return CFrame.new(-W / 2 + T / 2, y, -D / 2 + T + M * (k + 0.5)) * CFrame.Angles(0, math.pi / 2, 0)
		end
	end
	local function sideCount(side: string): number
		return if side == "F" or side == "B" then w else d
	end

	-- choose the module type for each wall slot ----------------------------------
	local doorF = w // 2
	local function moduleKind(r: number, side: string, k: number): string?
		local n = sideCount(side)
		if arch.openFront and side == "F" and r < rows - 1 then
			return nil -- hangar: open front
		end
		if r == 0 then
			if side == "F" then
				if arch.bigDoor and (k == 1 or k == n - 2) then
					return "bigdoor"
				end
				if k == doorF then
					return "door"
				end
				if arch.shopfront then
					return "shopwindow"
				end
			elseif side == "B" and (arch.hall or arch.bigDoor) and k == n // 2 then
				return if arch.bigDoor then "bigdoor" else "door"
			elseif side == "B" and w >= 6 and k == n // 2 and not arch.hall then
				return "door"
			end
			if arch.hall then
				return if (k % 3 == 1) and side ~= "F" and arch.category ~= "military" then "window" else "wall"
			end
		end
		if arch.hall then
			-- industrial halls: a band of windows high up
			if r == rows - 1 or (rows >= 3 and r >= 1) then
				return if k % 4 ~= 0 then "window" else "wall"
			end
			return "wall"
		end
		if arch.balconies and side == "F" and r >= 1 and k % 2 == 0 then
			return "frenchwindow"
		end
		if side == "R" or side == "L" then
			if arch.category == "house" or arch.category == "farm" then
				return if k % 2 == 1 or n <= 2 then "window" else "wall"
			end
			if arch.category == "military" then
				return if k % 2 == 0 then "window" else "wall"
			end
		end
		if arch.category == "house" and rng:NextNumber() < 0.12 then
			return "wall"
		end
		return "window"
	end

	-- storeys ------------------------------------------------------------------
	for r = 0, rows - 1 do
		walls[r] = { F = {}, B = {}, R = {}, L = {} }
		bands[r] = { F = {}, B = {}, R = {}, L = {} }
		local baseY = r * RH + SL
		-- ring beam at the bottom of storeys >= 1
		if r >= 1 then
			for _, side in { "F", "B", "R", "L" } do
				for k = 0, sideCount(side) - 1 do
					local below = walls[r - 1][side][k]
					local cf = sideCFrame(side, k, r * RH + SL / 2)
					-- over an open front (hangar) the band is a lintel carried by the corner pillars
					local sup = if below then { below } else { corners[r - 1][1], corners[r - 1][2] }
					bands[r][side][k] = add({
						kind = "band", cf = cf, size = Vector3.new(M, SL, T), shape = "box",
						material = Enum.Material.Concrete, color = SLAB_COLOR, mat = "concrete",
						hp = hpOf("band", "concrete"), supports = sup, lateral = {},
						grounded = false, row = r, structural = true,
					})
				end
			end
		end
		for _, side in { "F", "B", "R", "L" } do
			for k = 0, sideCount(side) - 1 do
				local kind = moduleKind(r, side, k)
				if kind then
					local sup = if r >= 1 then { bands[r][side][k] } else {}
					local kit = "Kit_" .. style .. "_" .. kind
					local glass = if kind == "window" then "Kit_glass_window" elseif kind == "shopwindow" then "Kit_glass_shop" elseif kind == "frenchwindow" then "Kit_glass_tall" else nil
					local idx = add({
						kind = kind, kit = kit, cf = sideCFrame(side, k, baseY + WH / 2), mat = mat, hp = hpOf(kind, mat),
						supports = sup, lateral = {}, grounded = r == 0, row = r, glass = glass, structural = true,
					})
					walls[r][side][k] = idx
					if glass then
						-- glass sits in the opening (sill offset per opening type)
						local sill = if kind == "window" then 0.9 elseif kind == "shopwindow" then 0.5 else 0
						local oh = if kind == "window" then 1.4 elseif kind == "shopwindow" then 1.9 else 2.2
						local gy = -WH / 2 + (sill + oh / 2) * 3
						add({
							kind = "glass", kit = glass, cf = sideCFrame(side, k, baseY + WH / 2) * CFrame.new(0, gy, 0),
							mat = "glass", hp = HP.glass, supports = { idx }, lateral = {}, grounded = false, row = r, structural = false,
						})
					end
					if kind == "frenchwindow" and arch.balconies then
						add({
							kind = "balcony", kit = "Kit_balcony", cf = sideCFrame(side, k, baseY + SL / 2 - 0.4),
							mat = "concrete", hp = hpOf("balcony", "concrete"), supports = { idx }, lateral = {}, grounded = false, row = r, structural = false,
						})
					end
				end
			end
		end
		-- corners
		corners[r] = {}
		for ci, c in { { 1, 1 }, { -1, 1 }, { 1, -1 }, { -1, -1 } } do
			local below = if r >= 1 then corners[r - 1][ci] else nil
			corners[r][ci] = add({
				kind = "corner", kit = "Kit_" .. style .. "_corner",
				cf = CFrame.new(c[1] * (W / 2 - T / 2), baseY + WH / 2, c[2] * (D / 2 - T / 2)),
				mat = mat, hp = hpOf("corner", mat), supports = if below then { below } else {}, lateral = {},
				grounded = r == 0, row = r, structural = true,
			})
		end
		-- interior partition (houses with 2+ storeys, apartments, offices)
		intWalls[r] = {}
		if (arch.interior or (arch.category == "house" and w >= 4)) and not hall then
			local zLine = -D / 2 + T + M * (d // 2)
			for k = 0, w - 1 do
				local kind = if k % 2 == 1 then "int_door" else "int_wall"
				local sup: { number } = {}
				local below = if r >= 1 then intWalls[r - 1][k] else nil
				if below then
					table.insert(sup, below)
				end
				intWalls[r][k] = add({
					kind = kind, kit = "Kit_" .. kind, cf = CFrame.new(-W / 2 + T + M * (k + 0.5), baseY + WH / 2, zLine),
					mat = "plaster", hp = hpOf(kind, "plaster"), supports = sup, lateral = {}, grounded = r == 0, row = r, structural = true,
				})
			end
		end
	end

	-- top ring beam (carries the roof)
	bands[rows] = { F = {}, B = {}, R = {}, L = {} }
	for _, side in { "F", "B", "R", "L" } do
		for k = 0, sideCount(side) - 1 do
			local below = walls[rows - 1][side][k]
			bands[rows][side][k] = add({
				kind = "band", cf = sideCFrame(side, k, rows * RH + SL / 2), size = Vector3.new(M, SL, T), shape = "box",
				material = Enum.Material.Concrete, color = SLAB_COLOR, mat = "concrete", hp = hpOf("band", "concrete"),
				supports = if below then { below } else {}, lateral = {}, grounded = false, row = rows, structural = true,
			})
		end
	end

	-- columns for open halls (every second module node) -------------------------
	local columns: { [string]: number } = {}
	if hall then
		for i = 2, w - 2, 2 do
			for j = 2, d - 2, 2 do
				local x = -W / 2 + T + M * i
				local z = -D / 2 + T + M * j
				local h = rows * RH
				columns[i .. "," .. j] = add({
					kind = "column", cf = CFrame.new(x, h / 2 + SL / 2, z), size = Vector3.new(1.2, h - SL, 1.2), shape = "box",
					material = Enum.Material.Metal, color = Color3.fromRGB(70, 74, 78), mat = "steel", hp = hpOf("column", "steel"),
					supports = {}, lateral = {}, grounded = true, row = 0, structural = true,
				})
			end
		end
	end

	-- slabs (upper floors + roof deck) ---------------------------------------------
	local stairI, stairJ = 1, 0
	local hasStairs = not hall and rows >= 2
	local slabRows = {}
	if not hall then
		for r = 1, rows - 1 do
			table.insert(slabRows, r)
		end
	end
	table.insert(slabRows, rows) -- roof deck / attic floor
	for _, r in slabRows do
		slabs[r] = {}
		local isRoof = r == rows
		for i = 0, w - 1 do
			slabs[r][i] = {}
			for j = 0, d - 1 do
				if hasStairs and not isRoof and i == stairI and j == stairJ then
					continue -- stairwell
				end
				local sup: { number } = {}
				local function sb(side: string, k: number)
					local b = bands[r][side][k]
					if b then
						table.insert(sup, b)
					end
				end
				if j == d - 1 then
					sb("F", i)
				end
				if j == 0 then
					sb("B", i)
				end
				if i == w - 1 then
					sb("R", j)
				end
				if i == 0 then
					sb("L", j)
				end
				local iw = intWalls[r - 1] and intWalls[r - 1][i]
				if iw and (j == d // 2 or j == d // 2 - 1) then
					table.insert(sup, iw)
				end
				for _, key in { i .. "," .. j, (i + 1) .. "," .. j, i .. "," .. (j + 1), (i + 1) .. "," .. (j + 1) } do
					if columns[key] then
						table.insert(sup, columns[key])
					end
				end
				local roofFlat = isRoof and arch.roof == "flat"
				slabs[r][i][j] = add({
					kind = "slab", cf = CFrame.new(-W / 2 + T + M * (i + 0.5), r * RH + SL / 2, -D / 2 + T + M * (j + 0.5)),
					size = Vector3.new(M, SL, M), shape = "box",
					material = if roofFlat then Enum.Material.Slate else Enum.Material.Concrete,
					color = if roofFlat then FLAT_ROOF else SLAB_COLOR, mat = "concrete", hp = hpOf("slab", "concrete"),
					supports = sup, lateral = {}, grounded = false, row = r, structural = true,
				})
			end
		end
		-- lateral links
		for i = 0, w - 1 do
			for j = 0, d - 1 do
				local p = slabs[r][i][j]
				if p then
					for _, n in { { i + 1, j }, { i - 1, j }, { i, j + 1 }, { i, j - 1 } } do
						local q = slabs[r][n[1]] and slabs[r][n[1]][n[2]]
						if q then
							table.insert(pieces[p].lateral, q)
						end
					end
				end
			end
		end
	end

	-- stairs
	if hasStairs then
		for r = 0, rows - 2 do
			local x = -W / 2 + T + M * (stairI + 0.5)
			local z = -D / 2 + T + M * (stairJ + 0.5)
			local sup: { number } = {}
			if r >= 1 then
				local nb = slabs[r][stairI + 1] and slabs[r][stairI + 1][stairJ]
				if nb then
					table.insert(sup, nb)
				end
			end
			add({
				kind = "stairs", kit = "Kit_stairs", cf = CFrame.new(x, r * RH + SL + RH / 2, z) * CFrame.Angles(0, -math.pi / 2, 0),
				mat = "concrete", hp = hpOf("stairs", "concrete"), supports = sup, lateral = {}, grounded = r == 0, row = r, structural = false,
			})
		end
	end

	-- roof -----------------------------------------------------------------------
	local topY = rows * RH + SL
	local roofMat = ROOF_COLORS[style] or ROOF_COLORS.plaster
	if arch.roof == "flat" then
		for _, side in { "F", "B", "R", "L" } do
			for k = 0, sideCount(side) - 1 do
				add({
					kind = "parapet", cf = sideCFrame(side, k, topY + 1.2), size = Vector3.new(M, 2.4, 0.75), shape = "box",
					material = if style == "metal" then Enum.Material.CorrodedMetal else Enum.Material.Concrete,
					color = if style == "brick" then Color3.fromRGB(140, 72, 54) else Color3.fromRGB(160, 160, 154),
					mat = "concrete", hp = hpOf("parapet", "concrete"), supports = { bands[rows][side][k] }, lateral = {},
					grounded = false, row = rows, structural = false,
				})
			end
		end
	else
		-- gable roof: ridge along X, slopes facing +Z and -Z, gable ends at +-X
		local over = 1.2
		local halfD = D / 2 + over
		local rise = halfD * math.tan(math.rad(34))
		local slopeLen = halfD / math.cos(math.rad(34))
		local angle = math.rad(34)
		for k = 0, w - 1 do
			local x = -W / 2 + T + M * (k + 0.5)
			for _, s in { 1, -1 } do
				-- slope panel centre: halfway between eave (z=s*halfD, y=topY) and ridge (z=0, y=topY+rise)
				local cz = s * halfD / 2
				local cy = topY + rise / 2 + 0.35
				local cf = CFrame.new(x, cy, cz) * CFrame.Angles(s * angle, 0, 0)
				local sup = { bands[rows][if s > 0 then "F" else "B"][k] }
				local attic = slabs[rows] and slabs[rows][k] and slabs[rows][k][if s > 0 then d - 1 else 0]
				if attic then
					table.insert(sup, attic)
				end
				local extraW = if k == 0 or k == w - 1 then T + over else 0
				local sx = M + extraW
				local ox = if k == 0 then -extraW / 2 elseif k == w - 1 then extraW / 2 else 0
				add({
					kind = "roofslope", cf = cf * CFrame.new(ox, 0, 0), size = Vector3.new(sx, 0.6, slopeLen), shape = "box",
					material = roofMat.mat, color = roofMat.color, mat = "tile", hp = hpOf("roofslope", "tile"),
					supports = sup, lateral = {}, grounded = false, row = rows, structural = false,
				})
			end
		end
		-- ridge cap
		add({
			kind = "roofslope", cf = CFrame.new(0, topY + rise + 0.45, 0), size = Vector3.new(W + 2 * over, 0.5, 1.2), shape = "box",
			material = roofMat.mat, color = roofMat.color, mat = "tile", hp = 200, supports = { bands[rows].R[0], bands[rows].L[0] },
			lateral = {}, grounded = false, row = rows, structural = false,
		})
		-- gable ends: two wedges per side forming the triangle
		for _, sx in { 1, -1 } do
			local side = if sx > 0 then "R" else "L"
			local sup = {}
			for k = 0, d - 1 do
				table.insert(sup, bands[rows][side][k])
			end
			local gx = sx * (W / 2 - T / 2)
			local inner = D / 2 - T / 2
			local gh = rise * (inner / halfD)
			for _, s in { 1, -1 } do
				-- WedgePart: the vertical face (local +Z) must face the ridge and the
				-- slope descend toward the eave, so the +Z half is turned around.
				local cf = CFrame.new(gx, topY + gh / 2, s * inner / 2) * CFrame.Angles(0, if s > 0 then math.pi else 0, 0)
				add({
					kind = "gable", cf = cf, size = Vector3.new(T, gh, inner), shape = "wedge",
					material = if style == "plaster" then Enum.Material.Plaster elseif style == "wood" then Enum.Material.WoodPlanks else Enum.Material.Brick,
					color = nil, mat = mat, hp = hpOf("gable", mat), supports = sup, lateral = {}, grounded = false, row = rows, structural = false,
				})
			end
		end
	end
	return pieces, Vector3.new(W, topY, D)
end

-- Structural evaluation: returns the set of piece indices that still stand.
-- alive[i] = false for destroyed pieces.
function BuildingLayout.stable(pieces: { Piece }, alive: { boolean }): { boolean }
	local stable = table.create(#pieces, false)
	local changed = true
	local iter = 0
	while changed and iter < 40 do
		changed = false
		iter += 1
		for i, p in pieces do
			if stable[i] or not alive[i] then
				continue
			end
			local ok = p.grounded
			if not ok then
				for _, s in p.supports do
					if stable[s] then
						ok = true
						break
					end
				end
			end
			if not ok and p.kind == "slab" then
				-- lateral span: up to two hops through neighbouring slabs
				for _, n in p.lateral do
					if stable[n] and alive[n] then
						local direct = false
						for _, s in pieces[n].supports do
							if stable[s] and pieces[s].kind ~= "slab" then
								direct = true
								break
							end
						end
						if direct then
							ok = true
							break
						end
						for _, n2 in pieces[n].lateral do
							if n2 ~= i and stable[n2] then
								for _, s2 in pieces[n2].supports do
									if stable[s2] and pieces[s2].kind ~= "slab" then
										ok = true
										break
									end
								end
							end
							if ok then
								break
							end
						end
					end
					if ok then
						break
					end
				end
			end
			if ok then
				stable[i] = true
				changed = true
			end
		end
	end
	return stable
end

BuildingLayout.MODULE = M
BuildingLayout.ROW = RH
BuildingLayout.SLAB = SL
BuildingLayout.WALL = T

return BuildingLayout
