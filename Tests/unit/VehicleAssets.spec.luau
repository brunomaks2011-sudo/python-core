-- Every vehicle and weapon definition in Defs must match the
-- Blender-built models in Assets/Models: both team variants exist, each has a
-- top-level Pivot and Hitbox (Rig.assemble roots the vehicle on them), a seat
-- for every crew position, every muzzle its weapons fire from (exactly once, as
-- the rig indexes attachments by name) and the joints that seats aim or the
-- animators spin.
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local T = require("../TestLib")
local Shim = require("../RobloxShim")

local Defs = Shim.load("Assets/Scripts/Shared/Defs")

type Node = { Name: string?, ClassName: string?, Children: { Node }? }
type Info = { seats: number, groups: { [string]: boolean }, attachments: { [string]: number } }

local files: { [string]: string } = {}
local function scan(dir: string)
	for _, name in fs.readDir(dir) do
		local p = dir .. "/" .. name
		if fs.isDir(p) then
			scan(p)
		elseif string.match(name, "%.model%.json$") then
			files[(string.gsub(name, "%.model%.json$", ""))] = p
		end
	end
end
scan("Assets/Models")

local cache: { [string]: Node | false } = {}
local function load(name: string): Node?
	if cache[name] == nil then
		local p = files[name]
		cache[name] = if p then serde.decode("json", fs.readFile(p)) else false
	end
	local n = cache[name]
	return if n then n else nil
end

local function collect(n: Node, out: Info): Info
	local name = n.Name or ""
	if n.ClassName == "Seat" or n.ClassName == "VehicleSeat" then
		out.seats += 1
	elseif n.ClassName == "Model" then
		out.groups[name] = true
	elseif n.ClassName == "Attachment" then
		out.attachments[name] = (out.attachments[name] or 0) + 1
	end
	for _, c in n.Children or {} do
		collect(c, out)
	end
	return out
end

local function info(n: Node): Info
	return collect(n, { seats = 0, groups = {}, attachments = {} })
end

local function hasChild(n: Node, name: string): boolean
	for _, c in n.Children or {} do
		if c.Name == name then
			return true
		end
	end
	return false
end

-- muzzle attachments a vehicle's weapons fire from (shared and per-seat)
local function muzzles(def: any): { string }
	local out = {}
	local function add(w: any)
		if type(w) == "table" and type(w.muzzle) == "string" then
			table.insert(out, w.muzzle)
		end
	end
	for _, w in def.weapons or {} do
		add(w)
	end
	for _, s in def.seats do
		for _, w in s.weapons or {} do
			add(w)
		end
	end
	return out
end

local function eachVehicleModel(fn: (kind: string, def: any, team: number, name: string, m: Node) -> ())
	for kind, def in Defs.Vehicles do
		for team = 1, 2 do
			local name = def.model[team]
			local m = load(name)
			T.truthy(m ~= nil, kind .. ": model file for " .. tostring(name) .. " is missing")
			if m then
				fn(kind, def, team, name, m)
			end
		end
	end
end

T.test("every vehicle has both team models with a top-level Pivot and Hitbox", function()
	local count = 0
	eachVehicleModel(function(kind, _def, _team, name, m)
		count += 1
		T.truthy(hasChild(m, "Pivot"), name .. " has no top-level Pivot")
		T.truthy(hasChild(m, "Hitbox"), name .. " has no top-level Hitbox")
	end)
	T.truthy(count >= 20, "expected at least 10 vehicle kinds x 2 teams, got " .. count)
end)

T.test("vehicle models have a seat for every crew position", function()
	eachVehicleModel(function(kind, def, _team, name, m)
		local i = info(m)
		T.truthy(i.seats >= #def.seats, string.format("%s: %d seats in model, %d crew positions in Defs", name, i.seats, #def.seats))
	end)
end)

T.test("every weapon muzzle exists exactly once in both team models", function()
	eachVehicleModel(function(kind, def, _team, name, m)
		local i = info(m)
		for _, mz in muzzles(def) do
			T.truthy(i.attachments[mz] == 1, string.format("%s: muzzle %q found %d times", name, mz, i.attachments[mz] or 0))
		end
	end)
end)

T.test("aimed seats and turrets have their joints", function()
	eachVehicleModel(function(kind, def, _team, name, m)
		local i = info(m)
		if def.turret then
			T.truthy(i.groups.Turret or i.groups.ChinTurret, name .. ": turret defined but no Turret/ChinTurret joint")
		end
		for idx, s in def.seats do
			if s.aimNode then
				T.truthy(i.groups[s.aimNode], string.format("%s: seat %d aims %q, which is not a joint", name, idx, s.aimNode))
			end
		end
	end)
end)

T.test("helicopters have main and tail rotor joints", function()
	eachVehicleModel(function(kind, def, _team, name, m)
		if def.drive == "heli" then
			local i = info(m)
			T.truthy(i.groups.Rotor, name .. ": no Rotor joint")
			T.truthy(i.groups.TailRotor, name .. ": no TailRotor joint")
		end
	end)
end)

T.test("hand weapon models exist", function()
	for id, w in Defs.Weapons do
		if type(w.model) == "string" and w.model ~= "" then
			T.truthy(load(w.model) ~= nil, id .. ": missing weapon model " .. w.model)
		end
	end
end)
