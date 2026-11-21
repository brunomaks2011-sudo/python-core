--!strict
-- BLUE vs RED - Three Flags Domination: server entry point.
-- Team-vs-team PvP between real players (no AI combatants).
-- Boot order: remotes -> map data -> terrain -> structures -> match systems ->
-- vehicles. Loading progress is published on MatchState for the loading screen.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Lighting = game:GetService("Lighting")

local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)

local Server = script.Parent
local EffectsBus = require(Server.Game.EffectsBus)
local DestructionService = require(Server.Game.DestructionService)
local MatchService = require(Server.Game.MatchService)
local SpawnService = require(Server.Game.SpawnService)
local CombatService = require(Server.Game.CombatService)
local VehicleService = require(Server.Game.VehicleService)
local MovementGuard = require(Server.Game.MovementGuard)
local RadarService = require(Server.Game.RadarService)
local EnvironmentService = require(Server.Game.EnvironmentService)
local TerrainBuilder = require(Server.World.TerrainBuilder)
local MapBuilder = require(Server.World.MapBuilder)

Net.setupServer()
local state = Net.matchState()
state:SetAttribute("Ready", false)
local function progress(stage: string, p: number)
	state:SetAttribute("LoadStage", stage)
	state:SetAttribute("LoadProgress", math.clamp(p, 0, 1))
end

local t0 = os.clock()
progress("Reading map data", 0.01)
MapInfo.load()
EffectsBus.init()

-- world -----------------------------------------------------------------------
MapBuilder.buildStatic(function(stage, p)
	progress(stage, 0.02 + p * 0.01)
end)
DestructionService.init(MapBuilder.structuresFolder(), MapBuilder.debrisFolder())
TerrainBuilder.build(function(p)
	progress("Shaping terrain", 0.03 + p * 0.5)
end)
MapBuilder.buildStructures(function(stage, p)
	progress(stage, 0.55 + p * 0.35)
end)

-- systems -----------------------------------------------------------------------
progress("Mobilising forces", 0.92)
MatchService.init()
SpawnService.init()
CombatService.init()
VehicleService.init()
SpawnService.vehicles = VehicleService
MovementGuard.vehicles = VehicleService
MovementGuard.init()
RadarService.vehicles = VehicleService.all
RadarService.init()
EnvironmentService.init()
VehicleService.spawnAll()

-- match restart: rebuild destroyed structures, vehicles, soldiers
table.insert(MatchService.onRestart, function()
	SpawnService.killAll()
	CombatService.reset()
	MapBuilder.buildStructures(function(stage, p)
		progress(stage, p)
	end)
	VehicleService.resetAll()
end)

-- battle settings (time of day, weather) ------------------------------------------
-- Allowed in Studio, for a player alone in the server, for the owner (or first
-- player) of a private server, and for the place's creator. Strangers in a
-- public server cannot change the battle for everyone.
local host: Player? = nil
Players.PlayerAdded:Connect(function(p)
	host = host or p
end)
for _, p in Players:GetPlayers() do
	host = host or p
end
Players.PlayerRemoving:Connect(function(p)
	if host == p then
		host = Players:GetPlayers()[1]
	end
end)
local function canChangeSettings(player: Player): boolean
	if RunService:IsStudio() or #Players:GetPlayers() <= 1 then
		return true
	end
	if game.PrivateServerId ~= "" then
		return player.UserId == game.PrivateServerOwnerId or player == host
	end
	return game.CreatorType == Enum.CreatorType.User and player.UserId == game.CreatorId
end
local settingsLimiter = Net.rateLimiter(4)
Net.event("ChangeSettings").OnServerEvent:Connect(function(player, payload)
	if type(payload) ~= "table" then
		return
	end
	if not settingsLimiter(player) or not canChangeSettings(player) then
		return
	end
	local req = payload :: any
	local clock = Util.finiteNumber(req.time)
	if clock then
		EnvironmentService.setTime(clock % 24)
	end
	if type(req.cycle) == "boolean" then
		EnvironmentService.cycle = req.cycle
	end
	if type(req.weather) == "string" and EnvironmentService.PRESETS[req.weather] then
		EnvironmentService.dynamicWeather = false
		EnvironmentService.setWeather(req.weather, false)
	end
end)

state:SetAttribute("Ready", true)
progress("Ready", 1)
print(string.format("[BlueVsRed] server ready in %.1f s - %d players connected", os.clock() - t0, #Players:GetPlayers()))
local _ = Lighting
