-- Builds the place with Rojo and opens it the way Studio will: checks the
-- scripts are the right classes in the right services, every script compiles,
-- the map data and Blender models are inside, and the service settings the
-- game depends on (teams, streaming, gravity, no auto character) are set.
-- Skipped when the rojo CLI is not installed.
local fs = require("@lune/fs")
local luau = require("@lune/luau")
local process = require("@lune/process")
local roblox = require("@lune/roblox")
local T = require("../TestLib")

local OUT = "Build/.placefile-test.rbxl"
local ok, built = pcall(process.exec, "rojo", { "build", "default.project.json", "-o", OUT })
if not ok or not built.ok then
	print("  skip  rojo is not available: " .. tostring(if ok then built.stderr else built))
	return
end

local game = roblox.deserializePlace(fs.readFile(OUT))
fs.removeFile(OUT)

local function at(root: any, path: string): any
	local node = root
	for name in string.gmatch(path, "[^%.]+") do
		node = node and node:FindFirstChild(name)
	end
	return node
end

local function count(root: any, className: string): number
	local n = 0
	for _, d in root:GetDescendants() do
		if d.ClassName == className then
			n += 1
		end
	end
	return n
end

T.test("entry scripts are the right classes in the right places", function()
	local server = at(game, "ServerScriptService.Server.Main")
	T.truthy(server, "ServerScriptService.Server.Main")
	T.eq(server and server.ClassName, "Script")
	local client = at(game, "StarterPlayer.StarterPlayerScripts.Client.Main")
	T.truthy(client, "StarterPlayerScripts.Client.Main")
	T.eq(client and client.ClassName, "LocalScript")
	local loading = at(game, "ReplicatedFirst.Loading.LoadingScreen")
	T.truthy(loading, "ReplicatedFirst.Loading.LoadingScreen")
	T.eq(loading and loading.ClassName, "LocalScript")
end)

T.test("every script in the place compiles", function()
	local n = 0
	for _, d in game:GetDescendants() do
		if d.ClassName == "Script" or d.ClassName == "LocalScript" or d.ClassName == "ModuleScript" then
			n += 1
			local src = d.Source
			T.truthy(#src > 0, d:GetFullName() .. " is empty")
			local compiled, err = pcall(luau.compile, src)
			T.truthy(compiled, d:GetFullName() .. ": " .. tostring(err))
		end
	end
	T.truthy(n >= 60, "expected the full code base, found " .. n .. " scripts")
end)

T.test("every Shared module is replicated", function()
	local shared = at(game, "ReplicatedStorage.Shared")
	T.truthy(shared, "ReplicatedStorage.Shared")
	for _, name in fs.readDir("Assets/Scripts/Shared") do
		local mod = string.match(name, "^(.+)%.luau$")
		if mod then
			local inst = shared:FindFirstChild(mod)
			T.truthy(inst and inst.ClassName == "ModuleScript", "Shared." .. mod)
		end
	end
end)

T.test("map data and generated audio regions are inside", function()
	local mapData = at(game, "ReplicatedStorage.MapData")
	T.truthy(mapData, "ReplicatedStorage.MapData")
	T.truthy(mapData:FindFirstChild("Info"), "MapData.Info")
	T.truthy(mapData:FindFirstChild("Height01"), "MapData.Height01")
	T.truthy(mapData:FindFirstChild("Vegetation"), "MapData.Vegetation")
	T.truthy(at(game, "ReplicatedStorage.Shared.AudioSprites"), "Shared.AudioSprites")
end)

T.test("Blender-built models are inside with their rig parts and attributes", function()
	local models = at(game, "ReplicatedStorage.Assets.Models")
	T.truthy(models, "ReplicatedStorage.Assets.Models")
	T.truthy(count(models, "Model") >= 150, "expected the model library")
	local mbt
	for _, d in models:GetDescendants() do
		if d.Name == "MBT_Blue" and d.ClassName == "Model" then
			mbt = d
		end
	end
	T.truthy(mbt, "MBT_Blue")
	if mbt then
		local hit = mbt:FindFirstChild("Hitbox")
		T.truthy(hit and hit:GetAttribute("hitbox") ~= nil, "MBT_Blue.Hitbox carries its hitbox attribute")
		T.truthy(mbt:FindFirstChild("Pivot"), "MBT_Blue.Pivot")
		T.truthy(mbt:FindFirstChild("Turret", true), "MBT_Blue turret group")
	end
end)

T.test("service settings the game depends on", function()
	local blue = at(game, "Teams.Blue Army")
	local red = at(game, "Teams.Red Army")
	T.truthy(blue and blue.ClassName == "Team", "Teams.Blue Army")
	T.truthy(red and red.ClassName == "Team", "Teams.Red Army")
	T.truthy(at(game, "Teams.Deploying"), "Teams.Deploying")
	local players = game:GetService("Players")
	T.eq(players.CharacterAutoLoads, false, "characters spawn only through the deploy screen")
	local ws = game:GetService("Workspace")
	T.eq(ws.StreamingEnabled, true, "StreamingEnabled")
	T.eq(ws.Gravity, 50, "Gravity")
	local lighting = game:GetService("Lighting")
	T.eq(lighting.Technology, roblox.Enum.Technology.Future, "Lighting.Technology")
end)
