--!strict
-- 3D spatial audio: positional one-shots with distance roll-off and a
-- speed-of-sound delay for distant events, engine loops on nearby vehicles,
-- wind / rain / battle ambience, radio voice lines and music stings.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local SoundService = game:GetService("SoundService")

local AudioIds = require(ReplicatedStorage.Shared.AudioIds)
local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local ClientState = require(script.Parent.Parent.ClientState)

local AudioController = {}

local player = Players.LocalPlayer
local SPEED_OF_SOUND = 1030 -- studs per second (343 m/s at 3 studs/m)
local pool: { Attachment } = {}
local busy: { [Attachment]: number } = {}
local loops: { [string]: Sound } = {}
local engines: { [Model]: Sound } = {}
local sfxGroup: SoundGroup
local musicGroup: SoundGroup

local RANGES: { [string]: { number } } = {
	rifle = { 25, 1800 }, smg = { 20, 1300 }, lmg = { 25, 1900 }, sniper = { 30, 2600 }, pistol = { 15, 900 },
	mg = { 25, 1900 }, hmg = { 35, 2400 }, autocannon = { 45, 3000 }, tank_gun = { 70, 4500 }, howitzer = { 80, 5000 },
	rocket = { 40, 2500 }, rpg = { 35, 2200 }, mlrs_launch = { 70, 4500 }, grenade = { 15, 600 },
	explosion = { 60, 4000 }, explosion_big = { 90, 6000 }, debris = { 30, 1600 }, glass = { 12, 500 }, impact = { 6, 200 },
}

local function attachment(): Attachment
	local now = os.clock()
	for _, a in pool do
		if (busy[a] or 0) < now then
			return a
		end
	end
	local a = Instance.new("Attachment")
	a.Name = "SfxPoint"
	a.Parent = workspace.Terrain
	table.insert(pool, a)
	return a
end

local function playAt(id: string, pos: Vector3, volume: number, range: { number }, pitch: number)
	local a = attachment()
	a.WorldPosition = pos
	local s = a:FindFirstChildOfClass("Sound")
	if not s then
		local ns = Instance.new("Sound")
		ns.Parent = a
		s = ns
	end
	local snd = s :: Sound
	snd.SoundId = id
	snd.Volume = volume
	snd.PlaybackSpeed = pitch
	snd.RollOffMode = Enum.RollOffMode.InverseTapered
	snd.RollOffMinDistance = range[1]
	snd.RollOffMaxDistance = range[2]
	snd.SoundGroup = sfxGroup
	snd.TimePosition = 0
	snd:Play()
	busy[a] = os.clock() + math.max(1.5, snd.TimeLength + 0.2)
end

-- Positional one-shot (public).
function AudioController.play(name: string, pos: Vector3?, volume: number?)
	local id = AudioIds.get(name)
	if not id then
		return
	end
	local vol = (volume or 1) * 0.9
	if not pos then
		local s = Instance.new("Sound")
		s.SoundId = id
		s.Volume = vol
		s.SoundGroup = sfxGroup
		s.Parent = SoundService
		s:Play()
		s.Ended:Connect(function()
			s:Destroy()
		end)
		return
	end
	local range = RANGES[name] or { 20, 1500 }
	local cam = workspace.CurrentCamera.CFrame.Position
	local dist = (pos - cam).Magnitude
	if dist > range[2] then
		return
	end
	local pitch = 0.92 + math.random() * 0.16
	local delay = if dist > 150 then dist / SPEED_OF_SOUND else 0
	if delay > 0 then
		task.delay(delay, playAt, id, pos, vol, range, pitch * (if dist > 1200 then 0.85 else 1))
	else
		playAt(id, pos, vol, range, pitch)
	end
end

local function loop(name: string, group: SoundGroup?): Sound?
	local id = AudioIds.get(name)
	if not id then
		return nil
	end
	local s = loops[name]
	if not s then
		local ns = Instance.new("Sound")
		ns.Looped = true
		ns.SoundId = id
		ns.Volume = 0
		ns.SoundGroup = group or sfxGroup
		ns.Parent = SoundService
		ns:Play()
		loops[name] = ns
		s = ns
	end
	return s
end

function AudioController.music(name: string)
	for _, n in { "music_menu", "music_victory", "music_defeat" } do
		local s = loops[n]
		if s then
			s.Volume = 0
		end
	end
	local s = loop(name, musicGroup)
	if s then
		s.Looped = name == "music_menu"
		s.TimePosition = 0
		s.Volume = 0.8
		s:Play()
	end
end

-- Radio voice line from the player's own army HQ.
local PHONETIC = { A = "Alpha", B = "Bravo", C = "Charlie" }
function AudioController.radio(line: string)
	local team = ClientState.team
	if team == 0 then
		return
	end
	local key = "voice_" .. team .. "_" .. line
	local id = AudioIds.voice[key]
	AudioController.play("radio_click", nil, 0.6)
	if id and id ~= "" then
		task.delay(0.15, function()
			local s = Instance.new("Sound")
			s.SoundId = id
			s.Volume = 1.2
			s.SoundGroup = sfxGroup
			local eq = Instance.new("EqualizerSoundEffect")
			eq.LowGain = -18
			eq.MidGain = 4
			eq.HighGain = -8
			eq.Parent = s
			local dist = Instance.new("DistortionSoundEffect")
			dist.Level = 0.22
			dist.Parent = s
			s.Parent = SoundService
			s:Play()
			s.Ended:Connect(function()
				s:Destroy()
			end)
		end)
	end
	local _ = PHONETIC
end

local function updateEngines()
	local cam = workspace.CurrentCamera.CFrame.Position
	local folder = workspace:FindFirstChild("Vehicles")
	if not folder then
		return
	end
	for _, m in folder:GetChildren() do
		if not m:IsA("Model") then
			continue
		end
		local hull = m:FindFirstChild("Hitbox") :: BasePart?
		if not hull then
			continue
		end
		local near = (hull.Position - cam).Magnitude < 700
		local s = engines[m]
		if near and not s and not m:GetAttribute("Destroyed") then
			local kind = m:GetAttribute("Kind") :: string?
			local def = kind and Defs.Vehicles[kind]
			local id = def and AudioIds.get(def.engineSound or "engine_truck")
			if id then
				local ns = Instance.new("Sound")
				ns.SoundId = id
				ns.Looped = true
				ns.Volume = 0
				ns.RollOffMode = Enum.RollOffMode.InverseTapered
				ns.RollOffMinDistance = 20
				ns.RollOffMaxDistance = 900
				ns.SoundGroup = sfxGroup
				ns.Parent = hull
				ns:Play()
				engines[m] = ns
				s = ns
			end
		end
		if s then
			if not near or m:GetAttribute("Destroyed") then
				s:Destroy()
				engines[m] = nil
			else
				local on = m:GetAttribute("Engine") == true
				local kind = m:GetAttribute("Kind") :: string?
				local def = kind and Defs.Vehicles[kind]
				local speed = hull.AssemblyLinearVelocity.Magnitude / (if def then def.maxSpeed else 60)
				s.Volume = if on then 0.5 + speed * 0.5 else 0
				s.PlaybackSpeed = 0.7 + speed * 0.8
			end
		end
	end
	for m, s in engines do
		if not m.Parent then
			s:Destroy()
			engines[m] = nil
		end
	end
end

function AudioController.init()
	sfxGroup = Instance.new("SoundGroup")
	sfxGroup.Name = "SFX"
	sfxGroup.Parent = SoundService
	musicGroup = Instance.new("SoundGroup")
	musicGroup.Name = "Music"
	musicGroup.Parent = SoundService
	local state = Net.matchState()
	Net.event("MatchEvent").OnClientEvent:Connect(function(e)
		if type(e) ~= "table" then
			return
		end
		local team = ClientState.team
		if e.kind == "captured" then
			AudioController.play("capture", nil, 0.7)
			AudioController.radio(if e.team == team then "captured_" .. e.point else "lost_" .. e.point)
		elseif e.kind == "neutralized" then
			if e.from == team then
				AudioController.radio("losing_" .. e.point)
			end
		elseif e.kind == "contested" then
			if e.owner == team then
				AudioController.radio("contested_" .. e.point)
			end
		elseif e.kind == "victory" then
			local won = e.team == team
			AudioController.music(if won then "music_victory" else "music_defeat")
			AudioController.radio(if won then "victory" else "defeat")
		elseif e.kind == "artillery" then
			AudioController.radio(if e.team == team then "artillery_out" else "artillery_incoming")
		elseif e.kind == "suddenDeath" then
			AudioController.radio("sudden_death")
		end
	end)
	local ambienceTimer = 8
	RunService.Heartbeat:Connect(function(dt)
		sfxGroup.Volume = ClientState.settings.masterVolume
		musicGroup.Volume = ClientState.settings.masterVolume * ClientState.settings.musicVolume
		local weather = state:GetAttribute("Weather") or "clear"
		local wind = (state:GetAttribute("Wind") or 0.3) :: number
		local w = loop("wind")
		if w then
			w.Volume = 0.15 + wind * 0.5
		end
		local r = loop("rain")
		if r then
			r.Volume = if weather == "rain" then 0.6 elseif weather == "storm" then 0.9 else 0
		end
		local amb = loop("battle_ambience")
		if amb then
			amb.Volume = if ClientState.inMenu then 0.15 else 0.35
		end
		-- distant battle: occasional far explosions / bursts when no ambience loop exists
		ambienceTimer -= dt
		if ambienceTimer <= 0 then
			ambienceTimer = 6 + math.random() * 14
			if not amb and ClientState.deployed then
				local cam = workspace.CurrentCamera.CFrame.Position
				local a = math.random() * math.pi * 2
				local d = 1400 + math.random() * 1600
				AudioController.play(if math.random() < 0.5 then "explosion" else "hmg", cam + Vector3.new(math.cos(a) * d, 0, math.sin(a) * d), 0.6)
			end
		end
		updateEngines()
	end)
	local _ = player
end

function AudioController.thunder(delay: number)
	task.delay(delay, function()
		AudioController.play("thunder", nil, 0.9)
	end)
end

return AudioController
