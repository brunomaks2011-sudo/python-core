-- BLUE vs RED - Three Flags Domination: client entry point.
-- Flow: loading screen -> main menu -> deployment -> battle (HUD) -> death ->
-- deployment ... -> victory screen -> restart.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UserInputService = game:GetService("UserInputService")

local Defs = require(ReplicatedStorage.Shared.Defs)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Net = require(ReplicatedStorage.Shared.Net)

local Client = script.Parent
local ClientState = require(Client.ClientState)
local Theme = require(Client.UI.Theme)
local HUD = require(Client.UI.HUD)
local Minimap = require(Client.UI.Minimap)
local MainMenu = require(Client.UI.MainMenu)
local DeployScreen = require(Client.UI.DeployScreen)
local Scoreboard = require(Client.UI.Scoreboard)
local VictoryScreen = require(Client.UI.VictoryScreen)
local CameraController = require(Client.Player.CameraController)
local CharacterController = require(Client.Player.CharacterController)
local WeaponController = require(Client.Player.WeaponController)
local InteractController = require(Client.Player.InteractController)
local VehicleController = require(Client.Vehicles.VehicleController)
local Effects = require(Client.Effects.Effects)
local VehicleAnimator = require(Client.Effects.VehicleAnimator)
local FlagAnimator = require(Client.Effects.FlagAnimator)
local StanceAnimator = require(Client.Effects.StanceAnimator)
local Weather = require(Client.Effects.Weather)
local SupportAirVisuals = require(Client.Effects.SupportAirVisuals)
local AudioController = require(Client.Audio.AudioController)

local player = Players.LocalPlayer

-- hide default Roblox UI that clashes with the game HUD
pcall(function()
	StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.Health, false)
	StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.Backpack, false)
	StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.PlayerList, false)
end)

-- wait for the server to finish building the battlefield
local state = Net.matchState()
while not state:GetAttribute("Ready") do
	state:GetAttributeChangedSignal("Ready"):Wait()
end
MapInfo.load()

Effects.init()
AudioController.init()
Effects.onSound = AudioController.play
Minimap.init()
HUD.init()
MainMenu.init()
DeployScreen.init()
Scoreboard.init()
VictoryScreen.init()
CameraController.init()
CharacterController.init()
WeaponController.init()
InteractController.init()
VehicleController.init()
VehicleAnimator.init()
FlagAnimator.init()
StanceAnimator.init()
Weather.init()
Weather.onThunder = AudioController.thunder
SupportAirVisuals.init()
WeaponController.onShot = function(id)
	local w = Defs.Weapons[id]
	if w then
		AudioController.play(w.sound or "rifle", nil, 0.7)
	end
end
Theme.onClick = function()
	AudioController.play("ui_click", nil, 0.5)
end

-- corner minimap + full map (M)
local mapGui = Theme.screen("Map", 4)
mapGui.Enabled = false
mapGui.Parent = player:WaitForChild("PlayerGui")
local corner = Minimap.new(mapGui, UDim2.fromOffset(250, 250), UDim2.new(1, -266, 0, 16), 0.075, true)
local info = MapInfo.get()
local extent = math.max(info.playable.maxX, info.playable.maxZ) + 300
local bigGui = Theme.screen("BigMap", 22)
bigGui.Enabled = false
bigGui.Parent = player:WaitForChild("PlayerGui")
local big = Minimap.new(bigGui, UDim2.fromOffset(760, 760), UDim2.new(0.5, -380, 0.5, -380), 760 / (extent * 2), false)
local _ = big

local function inBattle(on: boolean)
	HUD.setVisible(on)
	mapGui.Enabled = on and ClientState.settings.showMinimap
	CameraController.enable(on)
end

local function openDeploy()
	MainMenu.close()
	inBattle(false)
	UserInputService.MouseBehavior = Enum.MouseBehavior.Default
	UserInputService.MouseIconEnabled = true
	DeployScreen.open()
end

local function alive(): boolean
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	return hum ~= nil and hum.Health > 0
end

-- PLAY: from the pause menu (P) while still alive, go straight back to the
-- fight (the server refuses a second deployment); otherwise pick a spawn.
MainMenu.onPlay = function()
	if ClientState.deployed and alive() then
		MainMenu.close()
		ClientState.inMenu = false
		inBattle(true)
		AudioController.stopMusic()
	else
		openDeploy()
	end
end
DeployScreen.onDeployed = function()
	inBattle(true)
	AudioController.stopMusic()
	AudioController.play("radio_click", nil, 0.6)
end
VictoryScreen.onClosed = function()
	ClientState.deployed = false
	openDeploy()
end

ClientState.changed:Connect(function(what)
	if what == "minimap" then
		mapGui.Enabled = ClientState.deployed and ClientState.settings.showMinimap
	end
end)

player.CharacterAdded:Connect(function(character)
	local hum = character:WaitForChild("Humanoid") :: Humanoid
	task.wait()
	WeaponController.onSpawn()
	hum.Died:Connect(function()
		ClientState.deployed = false
		WeaponController.clear()
		VehicleController.exit()
		-- brief look at the battlefield, then back to deployment
		task.delay(3, function()
			if not ClientState.deployed then
				openDeploy()
			end
		end)
	end)
end)

-- match events -> HUD notifications
local NAMES = { A = "ALPHA", B = "BRAVO", C = "CHARLIE" }
Net.event("MatchEvent").OnClientEvent:Connect(function(e)
	if type(e) ~= "table" then
		return
	end
	local team = ClientState.team
	if e.kind == "captured" then
		local mine = e.team == team
		ClientState.notify:Fire(string.format("%s %s - %s", NAMES[e.point] or e.point, if mine then "CAPTURED" else "LOST", e.name or ""), Theme.team(e.team))
	elseif e.kind == "neutralized" then
		ClientState.notify:Fire(string.format("%s NEUTRALIZED", NAMES[e.point] or e.point), Theme.team(e.by))
	elseif e.kind == "contested" and e.owner == team then
		ClientState.notify:Fire(string.format("%s IS CONTESTED", NAMES[e.point] or e.point), Theme.Warn)
	elseif e.kind == "kill" or e.kind == "vehicleKill" then
		ClientState.killfeed:Fire(e)
		if e.kind == "kill" and e.victimId == player:GetAttribute("SoldierId") then
			ClientState.notify:Fire(string.format("KILLED BY %s", string.upper(e.killer or "UNKNOWN")), Theme.Red)
		end
	elseif e.kind == "artillery" then
		ClientState.notify:Fire(if e.team == team then "ROCKET ARTILLERY INBOUND ON TARGET" else "INCOMING ARTILLERY!", Theme.Warn)
	elseif e.kind == "suddenDeath" then
		ClientState.notify:Fire("SUDDEN DEATH", Theme.Warn)
	elseif e.kind == "notice" then
		ClientState.notify:Fire(e.text or "", Theme.TextDim)
	elseif e.kind == "victory" then
		inBattle(false)
		UserInputService.MouseBehavior = Enum.MouseBehavior.Default
		UserInputService.MouseIconEnabled = true
	elseif e.kind == "restarting" then
		ClientState.notify:Fire("REBUILDING THE BATTLEFIELD...", Theme.Gold)
	end
end)
Net.event("Hitmarker").OnClientEvent:Connect(function(e)
	if type(e) == "table" then
		ClientState.hit:Fire(e.kill == true, e.head == true)
	end
end)
Net.event("DamageTaken").OnClientEvent:Connect(function(e)
	if type(e) == "table" then
		ClientState.damaged:Fire(e.amount or 0, e.from)
	end
end)

-- full map toggle
UserInputService.InputBegan:Connect(function(input, processed)
	if processed then
		return
	end
	if input.KeyCode == Enum.KeyCode.M and ClientState.deployed then
		bigGui.Enabled = not bigGui.Enabled
	elseif input.KeyCode == Enum.KeyCode.Escape and ClientState.deployed then
		-- leave a moment to the Roblox menu; P opens our menu
	elseif input.KeyCode == Enum.KeyCode.P and ClientState.deployed then
		inBattle(false)
		MainMenu.open()
		ClientState.inMenu = true
		AudioController.music("music_menu")
	end
end)

game:GetService("RunService").RenderStepped:Connect(function()
	if mapGui.Enabled then
		corner:update()
	end
	if bigGui.Enabled then
		big:update()
	end
end)

-- start at the main menu
if state:GetAttribute("State") == "ended" then
	inBattle(false)
else
	MainMenu.open()
	AudioController.music("music_menu")
end
