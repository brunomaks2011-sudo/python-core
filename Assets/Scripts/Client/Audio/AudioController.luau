--!strict
-- 3D spatial audio: positional one-shots with distance roll-off and a
-- speed-of-sound delay for distant events, engine loops on nearby vehicles,
-- wind / rain / distant-battle ambience, HQ radio voice lines and music.
--
-- Every sound is a region of one of five uploaded sheets (see AudioIds), played
-- with Sound.PlaybackRegion / LoopRegion.

local Debris = game:GetService("Debris")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local SoundService = game:GetService("SoundService")

local AudioIds = require(ReplicatedStorage.Shared.AudioIds)
local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local ClientState = require(script.Parent.Parent.ClientState)

local AudioController = {}

type Clip = AudioIds.Clip

local SPEED_OF_SOUND = 1030 -- studs per second (343 m/s at 3 studs per metre)
local pool: { Attachment } = {}
local busy: { [Attachment]: number } = {}
local ambience: { [string]: Sound } = {}
local engines: { [Model]: Sound } = {}
local musicSound: Sound? = nil
local sfxGroup: SoundGroup
local musicGroup: SoundGroup
local voiceGroup: SoundGroup

-- roll-off {min, max} in studs per sound
local RANGES: { [string]: { number } } = {
	rifle = { 25, 1800 }, smg = { 20, 1300 }, lmg = { 25, 1900 }, sniper = { 30, 2600 }, pistol = { 15, 900 },
	mg = { 25, 1900 }, hmg = { 35, 2400 }, autocannon = { 45, 3000 }, tank_gun = { 70, 4500 }, howitzer = { 80, 5000 },
	rocket = { 40, 2500 }, rpg = { 35, 2200 }, mlrs_launch = { 70, 4500 }, grenade = { 15, 600 },
	explosion = { 60, 4000 }, explosion_big = { 90, 6000 }, debris = { 30, 1600 }, glass = { 12, 500 }, impact = { 6, 200 },
}

-- Point a Sound at a clip (a region of a sheet, or a whole built-in file).
local function apply(snd: Sound, c: Clip)
	snd.SoundId = c.id
	if c.length > 0 then
		local region = NumberRange.new(c.start, c.start + c.length)
		snd.PlaybackRegionsEnabled = true
		snd.PlaybackRegion = region
		snd.LoopRegion = region
	else
		snd.PlaybackRegionsEnabled = false
	end
	snd.Looped = c.loop
	snd.TimePosition = c.start
end

-- How long a one-shot keeps its Sound busy.
local function seconds(c: Clip, snd: Sound): number
	local len = if c.length > 0 then c.length elseif snd.TimeLength > 0 then snd.TimeLength else 2
	return len / math.max(0.1, snd.PlaybackSpeed)
end

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

local function playAt(c: Clip, pos: Vector3, volume: number, range: { number }, pitch: number)
	local a = attachment()
	a.WorldPosition = pos
	local snd = a:FindFirstChildOfClass("Sound")
	if not snd then
		local s = Instance.new("Sound")
		s.RollOffMode = Enum.RollOffMode.InverseTapered
		s.SoundGroup = sfxGroup
		s.Parent = a
		snd = s
	end
	local s = snd :: Sound
	s:Stop()
	s.Volume = volume
	s.PlaybackSpeed = pitch
	s.RollOffMinDistance = range[1]
	s.RollOffMaxDistance = range[2]
	apply(s, c)
	s:Play()
	busy[a] = os.clock() + seconds(c, s) + 0.2
end

local function play2D(c: Clip, volume: number, group: SoundGroup)
	local s = Instance.new("Sound")
	s.Volume = volume
	s.SoundGroup = group
	apply(s, c)
	s.Parent = SoundService
	s:Play()
	Debris:AddItem(s, seconds(c, s) + 0.5)
end

-- Play a sound by name. With a position it is 3D: rolled off with distance
-- and delayed by the speed of sound; without one it plays flat (UI, own gun).
function AudioController.play(name: string, pos: Vector3?, volume: number?)
	local c = AudioIds.clip(name)
	if not c then
		return
	end
	local vol = (volume or 1) * 0.9
	if not pos then
		play2D(c, vol, sfxGroup)
		return
	end
	local range = RANGES[name] or { 20, 1500 }
	local cam = workspace.CurrentCamera.CFrame.Position
	local dist = (pos - cam).Magnitude
	if dist > range[2] then
		return
	end
	local pitch = 0.94 + math.random() * 0.12
	if dist > 150 then
		-- far away: arrives late and sounds duller / lower
		task.delay(dist / SPEED_OF_SOUND, playAt, c, pos, vol, range, if dist > 1200 then pitch * 0.88 else pitch)
	else
		playAt(c, pos, vol, range, pitch)
	end
end

local function ambienceLoop(name: string): Sound?
	local s = ambience[name]
	if s then
		return s
	end
	local c = AudioIds.clip(name)
	if not c or not c.loop then
		return nil
	end
	local ns = Instance.new("Sound")
	ns.Name = name
	ns.Volume = 0
	ns.SoundGroup = sfxGroup
	apply(ns, c)
	ns.Parent = SoundService
	ns:Play()
	ambience[name] = ns
	return ns
end

function AudioController.music(name: string)
	local c = AudioIds.clip(name)
	local s = musicSound
	if s then
		s:Stop()
	end
	if not c then
		return
	end
	if not s then
		local ns = Instance.new("Sound")
		ns.Name = "Music"
		ns.SoundGroup = musicGroup
		ns.Parent = SoundService
		musicSound = ns
		s = ns
	end
	local snd = s :: Sound
	snd.Volume = 0.8
	apply(snd, c)
	snd:Play()
end

function AudioController.stopMusic()
	local s = musicSound
	if s then
		s:Stop()
	end
end

-- Radio message from the local player's own HQ (the radio treatment is baked
-- into the voice sheets).
function AudioController.radio(line: string)
	local team = ClientState.team
	if team == 0 then
		return
	end
	local c = AudioIds.clip("voice_" .. team .. "_" .. line)
	if c then
		play2D(c, 1.1, voiceGroup)
	end
end

local function engineSound(m: Model, hull: BasePart): Sound?
	local kind = m:GetAttribute("Kind")
	local def = if type(kind) == "string" then Defs.Vehicles[kind] else nil
	local c = AudioIds.clip(if def and def.engineSound then def.engineSound else "engine_truck")
	if not c or not c.loop then
		return nil
	end
	local s = Instance.new("Sound")
	s.Name = "Engine"
	s.Volume = 0
	s.RollOffMode = Enum.RollOffMode.InverseTapered
	s.RollOffMinDistance = 20
	s.RollOffMaxDistance = 900
	s.SoundGroup = sfxGroup
	apply(s, c)
	s.Parent = hull
	s:Play()
	return s
end

local function updateEngines()
	local cam = workspace.CurrentCamera.CFrame.Position
	local folder = workspace:FindFirstChild("Vehicles")
	if folder then
		for _, m in folder:GetChildren() do
			if not m:IsA("Model") then
				continue
			end
			local hull = m:FindFirstChild("Hitbox")
			if not hull or not hull:IsA("BasePart") then
				continue
			end
			local alive = m:GetAttribute("Destroyed") ~= true
			local near = alive and (hull.Position - cam).Magnitude < 700
			local s: Sound? = engines[m]
			if near and not s then
				s = engineSound(m, hull)
				engines[m] = s
			elseif not near and s then
				s:Destroy()
				engines[m] = nil
				s = nil
			end
			if s then
				local kind = m:GetAttribute("Kind")
				local def = if type(kind) == "string" then Defs.Vehicles[kind] else nil
				local maxSpeed = if def and def.maxSpeed then def.maxSpeed else 60
				local speed = math.clamp(hull.AssemblyLinearVelocity.Magnitude / maxSpeed, 0, 1.2)
				local on = m:GetAttribute("Engine") == true
				s.Volume = if on then 0.45 + speed * 0.45 else 0
				s.PlaybackSpeed = 0.75 + speed * 0.65
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

function AudioController.thunder(delay: number)
	task.delay(delay, function()
		AudioController.play("thunder", nil, 0.9)
	end)
end

function AudioController.init()
	sfxGroup = Instance.new("SoundGroup")
	sfxGroup.Name = "SFX"
	sfxGroup.Parent = SoundService
	musicGroup = Instance.new("SoundGroup")
	musicGroup.Name = "Music"
	musicGroup.Parent = SoundService
	voiceGroup = Instance.new("SoundGroup")
	voiceGroup.Name = "Radio"
	voiceGroup.Parent = SoundService
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
		elseif e.kind == "restarted" then
			AudioController.stopMusic()
		end
	end)

	RunService.Heartbeat:Connect(function()
		local master = ClientState.settings.masterVolume
		sfxGroup.Volume = master
		voiceGroup.Volume = master
		musicGroup.Volume = master * ClientState.settings.musicVolume
		local weather = Util.str(state, "Weather", "clear")
		local windStrength = Util.num(state, "Wind", 0.3)
		local w = ambienceLoop("wind")
		if w then
			w.Volume = 0.12 + windStrength * 0.45 + (if weather == "storm" then 0.25 else 0)
		end
		local r = ambienceLoop("rain")
		if r then
			r.Volume = if weather == "rain" then 0.6 elseif weather == "storm" then 0.85 else 0
		end
		local b = ambienceLoop("battle_ambience")
		if b then
			b.Volume = if ClientState.inMenu then 0.12 elseif ClientState.deployed then 0.3 else 0.2
		end
		updateEngines()
	end)
end

return AudioController
