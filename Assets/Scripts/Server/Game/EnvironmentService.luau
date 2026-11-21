--!strict
-- Day/night cycle and weather, driven by the server so every player sees the
-- same sky. Lighting/Atmosphere/Clouds changes replicate automatically; the
-- MatchState attributes tell clients which rain/fog/lightning effects to run.
-- Weather: clear, cloudy, rain, fog, storm (+ wind strength/direction).

local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local Net = require(ReplicatedStorage.Shared.Net)

local EnvironmentService = {}

EnvironmentService.cycle = true -- day/night progresses
EnvironmentService.dayMinutes = 48 -- real minutes per 24 h
EnvironmentService.dynamicWeather = true

local PRESETS = {
	clear = { cover = 0.35, density = 0.4, atmo = 0.28, haze = 1.2, wind = 0.25, bright = 3.0 },
	cloudy = { cover = 0.75, density = 0.6, atmo = 0.34, haze = 1.8, wind = 0.45, bright = 2.4 },
	rain = { cover = 0.9, density = 0.85, atmo = 0.42, haze = 2.4, wind = 0.6, bright = 1.8 },
	fog = { cover = 0.8, density = 0.5, atmo = 0.62, haze = 3.4, wind = 0.1, bright = 2.0 },
	storm = { cover = 0.98, density = 0.95, atmo = 0.5, haze = 2.8, wind = 1.0, bright = 1.4 },
}
EnvironmentService.PRESETS = PRESETS

local current = "clear"
local state: Folder

function EnvironmentService.setWeather(name: string, instant: boolean?)
	local p = PRESETS[name]
	if not p then
		return
	end
	current = name
	local t = TweenInfo.new(if instant then 0.1 else 45, Enum.EasingStyle.Sine)
	local clouds = workspace.Terrain:FindFirstChildOfClass("Clouds")
	if clouds then
		TweenService:Create(clouds, t, { Cover = p.cover, Density = p.density }):Play()
	end
	local atmo = Lighting:FindFirstChildOfClass("Atmosphere")
	if atmo then
		TweenService:Create(atmo, t, { Density = p.atmo, Haze = p.haze }):Play()
	end
	state:SetAttribute("Weather", name)
	state:SetAttribute("Wind", p.wind)
	state:SetAttribute("WeatherBrightness", p.bright)
end

function EnvironmentService.setTime(hour: number)
	Lighting.ClockTime = hour % 24
end

function EnvironmentService.weather(): string
	return current
end

function EnvironmentService.init()
	state = Net.matchState()
	state:SetAttribute("WindDir", Vector3.new(0.8, 0, 0.6).Unit)
	EnvironmentService.setWeather("cloudy", true)
	local weatherTimer = 480
	local order = { "clear", "cloudy", "cloudy", "rain", "fog", "clear", "storm", "cloudy" }
	RunService.Heartbeat:Connect(function(dt)
		if EnvironmentService.cycle then
			Lighting.ClockTime = (Lighting.ClockTime + dt * 24 / (EnvironmentService.dayMinutes * 60)) % 24
		end
		-- darker exposure at night, brightness follows the weather
		local h = Lighting.ClockTime
		local day = math.clamp(math.sin((h - 6) / 12 * math.pi), 0, 1)
		local p = PRESETS[current]
		Lighting.Brightness = 0.6 + (p.bright - 0.6) * day
		Lighting.ExposureCompensation = -0.2 + 0.3 * day
		if EnvironmentService.dynamicWeather then
			weatherTimer -= dt
			if weatherTimer <= 0 then
				weatherTimer = 360 + math.random() * 300
				EnvironmentService.setWeather(order[math.random(1, #order)], false)
			end
		end
	end)
end

return EnvironmentService
