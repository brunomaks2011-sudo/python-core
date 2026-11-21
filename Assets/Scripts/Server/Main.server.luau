--!strict
-- BLUE vs RED - Three Flags Domination: server entry point.
-- Boot order: remotes -> map data -> terrain -> structures -> match systems ->
-- vehicles -> AI. Loading progress is published on MatchState for the
-- loading screen.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Lighting = game:GetService("Lighting")

local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Constants = require(ReplicatedStorage.Shared.Constants)

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
local SoldierRegistry = require(Server.Game.SoldierRegistry)
local TerrainBuilder = require(Server.World.TerrainBuilder)
local MapBuilder = require(Server.World.MapBuilder)
local AIDirector = require(Server.AI.AIDirector)
local SupportAir = require(Server.AI.SupportAir)

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
AIDirector.init()
SupportAir.init()

-- bots that end up in vehicles need a driver controller for gunnery
SpawnService.onSpawn = function(s)
	if s.isBot and s.vehicleId then
		local v = VehicleService.get(s.vehicleId)
		if v then
			AIDirector.trackVehicle(v)
		end
	end
end

-- match restart: rebuild destroyed structures, vehicles, soldiers
table.insert(MatchService.onRestart, function()
	SpawnService.killAll()
	CombatService.reset()
	MapBuilder.buildStructures(function(stage, p)
		progress(stage, p)
	end)
	VehicleService.resetAll()
	AIDirector.reset()
end)

-- battle settings (bots, difficulty, time of day, weather) ------------------------
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
state:SetAttribute("BotsPerTeam", AIDirector.botsPerTeam)
state:SetAttribute("Difficulty", 1)
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
	local bots = Util.finiteNumber(req.bots)
	if bots then
		AIDirector.botsPerTeam = math.clamp(math.floor(bots), 0, Constants.BOTS_PER_TEAM_MAX)
		state:SetAttribute("BotsPerTeam", AIDirector.botsPerTeam)
		AIDirector.balance()
	end
	local difficulty = Util.finiteNumber(req.difficulty)
	if difficulty then
		difficulty = math.clamp(math.floor(difficulty), 0, 2)
		AIDirector.setDifficulty(difficulty)
		state:SetAttribute("Difficulty", difficulty)
	end
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
print(string.format("[BlueVsRed] server ready in %.1f s - %d soldiers registered", os.clock() - t0, #SoldierRegistry.alive()))
local _ = Lighting
