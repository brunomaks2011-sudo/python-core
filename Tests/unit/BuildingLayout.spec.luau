-- Structural graph tests for destructible buildings (runs under Lune).
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local T = require("../TestLib")
local Shim = require("../RobloxShim")

local BuildingLayout = Shim.load("Assets/Scripts/Server/World/BuildingLayout")
local specs = serde.decode("json", fs.readFile("Assets/Models/Buildings/building_specs.json")).archetypes

local function allAlive(n)
	local a = {}
	for i = 1, n do
		a[i] = true
	end
	return a
end

local function count(t)
	local n = 0
	for _, v in t do
		if v then
			n += 1
		end
	end
	return n
end

T.test("every archetype generates pieces with valid support references", function()
	local total = 0
	for name, arch in specs do
		local pieces, size = BuildingLayout.generate(arch, arch.style, 42)
		T.truthy(#pieces > 20, name .. " has pieces")
		total += #pieces
		for i, p in pieces do
			for _, s in p.supports do
				T.truthy(pieces[s] ~= nil, name .. " piece " .. i .. " support " .. tostring(s))
				T.truthy(s ~= i, name .. " self support")
			end
			for _, l in p.lateral do
				T.truthy(pieces[l] ~= nil and pieces[l].kind == "slab", name .. " lateral")
			end
			T.truthy(p.hp > 0, name .. " hp")
			T.truthy(p.kit ~= nil or p.size ~= nil, name .. " geometry")
		end
		T.truthy(size.X > arch.w * 9 and size.Z > arch.d * 9, name .. " size")
	end
	print("       total pieces across archetypes: " .. total)
end)

T.test("intact buildings are fully stable (nothing floats at spawn)", function()
	for name, arch in specs do
		local pieces = BuildingLayout.generate(arch, arch.style, 7)
		local stable = BuildingLayout.stable(pieces, allAlive(#pieces))
		local unstable = {}
		for i, p in pieces do
			if not stable[i] then
				table.insert(unstable, p.kind .. "@" .. p.row)
			end
		end
		T.eq(#unstable, 0, name .. " unstable: " .. table.concat(unstable, ","))
	end
end)

T.test("removing a ground-floor wall drops what it carries, not the whole house", function()
	local arch = specs.apartment_block
	local pieces = BuildingLayout.generate(arch, "panel", 3)
	local alive = allAlive(#pieces)
	-- destroy the front ground-floor wall module #2 (index by search)
	local target
	for i, p in pieces do
		if p.row == 0 and p.structural and p.kind ~= "corner" and p.kind ~= "int_wall" and p.kind ~= "int_door" and p.cf.Position.Z > 10 and math.abs(p.cf.Position.X - (-36 + 0.9 + 9 * 2.5)) < 1 then
			target = i
		end
	end
	T.truthy(target, "found target wall")
	alive[target] = false
	local stable = BuildingLayout.stable(pieces, alive)
	-- the band above it must fall, but the walls above are still held? (band supported only by that wall)
	local fallen = 0
	for i, p in pieces do
		if alive[i] and not stable[i] then
			fallen += 1
		end
	end
	T.truthy(fallen >= 1, "something above the hole falls")
	T.truthy(fallen < #pieces * 0.2, "not the whole building: " .. fallen)
end)

T.test("removing every ground-floor wall collapses the upper storeys", function()
	local arch = specs.house_medium
	local pieces = BuildingLayout.generate(arch, "plaster", 9)
	local alive = allAlive(#pieces)
	for i, p in pieces do
		if p.row == 0 and p.grounded and p.kind ~= "stairs" then
			alive[i] = false
		end
	end
	local stable = BuildingLayout.stable(pieces, alive)
	local standing = 0
	for i, p in pieces do
		if alive[i] and stable[i] and p.row >= 1 then
			standing += 1
		end
	end
	T.eq(standing, 0, "upper storeys must collapse")
end)

T.test("halls keep their roof on internal columns", function()
	local arch = specs.factory_hall
	local pieces = BuildingLayout.generate(arch, "brick", 5)
	local alive = allAlive(#pieces)
	local stable = BuildingLayout.stable(pieces, alive)
	T.eq(count(stable), #pieces)
	-- knock out the columns: the centre of the roof must fall
	for i, p in pieces do
		if p.kind == "column" then
			alive[i] = false
		end
	end
	stable = BuildingLayout.stable(pieces, alive)
	local fallenRoof = 0
	for i, p in pieces do
		if p.kind == "slab" and alive[i] and not stable[i] then
			fallenRoof += 1
		end
	end
	T.truthy(fallenRoof > 4, "centre roof slabs fall without columns: " .. fallenRoof)
end)

return nil
