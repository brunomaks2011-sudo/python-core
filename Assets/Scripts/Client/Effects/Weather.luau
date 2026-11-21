--!strict
-- Local weather rendering for the server-chosen conditions: rain streaks
-- around the camera, lightning flashes with delayed thunder during storms,
-- street lights and floodlights at night.

local Lighting = game:GetService("Lighting")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Net = require(ReplicatedStorage.Shared.Net)
local ClientState = require(script.Parent.Parent.ClientState)

local Weather = {}
Weather.onThunder = nil :: ((delay: number) -> ())?

local state: Folder
local rainPart: Part
local rain: ParticleEmitter
local splash: ParticleEmitter
local flash: ColorCorrectionEffect
local nextLightning = 0
local lampsOn: boolean? = nil

local function setLamps(on: boolean)
	if lampsOn == on then
		return
	end
	lampsOn = on
	local map = workspace:FindFirstChild("Map")
	if not map then
		return
	end
	for _, d in map:GetDescendants() do
		if d:IsA("BasePart") and d.Name == "LampGlass" then
			d.Material = if on then Enum.Material.Neon else Enum.Material.Glass
		elseif (d:IsA("SpotLight") or d:IsA("PointLight")) and d.Parent and (d.Parent.Name == "Light" or d.Parent.Name == "Floodlight" or d.Parent.Name == "Lamp" or d.Parent.Name == "CanopyLight") then
			d.Enabled = on
		end
	end
end

function Weather.init()
	state = Net.matchState()
	rainPart = Instance.new("Part")
	rainPart.Name = "RainEmitter"
	rainPart.Anchored = true
	rainPart.CanCollide = false
	rainPart.CanQuery = false
	rainPart.CanTouch = false
	rainPart.Transparency = 1
	rainPart.Size = Vector3.new(160, 1, 160)
	rainPart.Parent = workspace.CurrentCamera
	rain = Instance.new("ParticleEmitter")
	rain.Texture = "rbxasset://textures/particles/sparkles_main.dds"
	rain.Orientation = Enum.ParticleOrientation.VelocityParallel
	rain.Rate = 0
	rain.Lifetime = NumberRange.new(1.1, 1.4)
	rain.Speed = NumberRange.new(110, 130)
	rain.SpreadAngle = Vector2.new(4, 4)
	rain.EmissionDirection = Enum.NormalId.Bottom
	rain.Size = NumberSequence.new(0.12)
	rain.Squash = NumberSequence.new(3.5)
	rain.Transparency = NumberSequence.new(0.45)
	rain.Color = ColorSequence.new(Color3.fromRGB(190, 200, 210))
	rain.LightInfluence = 1
	rain.Parent = rainPart
	local low = Instance.new("Part")
	low.Name = "SplashEmitter"
	low.Anchored = true
	low.CanCollide = false
	low.CanQuery = false
	low.Transparency = 1
	low.Size = Vector3.new(60, 1, 60)
	low.Parent = workspace.CurrentCamera
	splash = Instance.new("ParticleEmitter")
	splash.Texture = "rbxasset://textures/particles/smoke_main.dds"
	splash.Rate = 0
	splash.Lifetime = NumberRange.new(0.2, 0.35)
	splash.Speed = NumberRange.new(1, 3)
	splash.Size = NumberSequence.new(0.3, 0.8)
	splash.Transparency = NumberSequence.new(0.6, 1)
	splash.Color = ColorSequence.new(Color3.fromRGB(200, 210, 220))
	splash.EmissionDirection = Enum.NormalId.Top
	splash.Parent = low
	flash = Instance.new("ColorCorrectionEffect")
	flash.Name = "LightningFlash"
	flash.Brightness = 0
	flash.Parent = Lighting

	RunService.RenderStepped:Connect(function(dt)
		local cam = workspace.CurrentCamera.CFrame.Position
		local weather = state:GetAttribute("Weather") or "clear"
		local wind = (state:GetAttribute("Wind") or 0.3) :: number
		local windDir = (state:GetAttribute("WindDir") or Vector3.new(1, 0, 0)) :: Vector3
		local raining = weather == "rain" or weather == "storm"
		local q = ClientState.settings.quality
		local qm = if q == "low" then 0.35 elseif q == "medium" then 0.65 else 1
		rainPart.CFrame = CFrame.new(cam + Vector3.new(0, 70, 0) - windDir * wind * 30)
		rain.Rate = if raining then (if weather == "storm" then 2600 else 1500) * qm else 0
		rain.Acceleration = windDir * wind * 60
		local ground = workspace:Raycast(cam, Vector3.new(0, -60, 0))
		low.CFrame = CFrame.new(if ground then ground.Position else cam - Vector3.new(0, 5, 0))
		splash.Rate = if raining then 300 * qm else 0
		-- lightning
		if weather == "storm" then
			if os.clock() > nextLightning then
				nextLightning = os.clock() + 6 + math.random() * 14
				local dist = 300 + math.random() * 2500
				task.spawn(function()
					for _ = 1, math.random(1, 3) do
						flash.Brightness = 0.45 + math.random() * 0.35
						task.wait(0.05 + math.random() * 0.08)
						flash.Brightness = 0
						task.wait(0.05 + math.random() * 0.1)
					end
				end)
				if Weather.onThunder then
					Weather.onThunder(dist / 1030)
				end
			end
		end
		-- night lighting
		local h = Lighting.ClockTime
		setLamps(h < 6.3 or h > 18.6)
		local _ = dt
	end)
end

return Weather
