-- Loading screen shown while the server builds the battlefield (terrain,
-- structures, vehicles). Reads progress from ReplicatedStorage.MatchState.

local Players = game:GetService("Players")
local ReplicatedFirst = game:GetService("ReplicatedFirst")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

ReplicatedFirst:RemoveDefaultLoadingScreen()

local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "LoadingScreen"
gui.IgnoreGuiInset = true
gui.DisplayOrder = 100
gui.ResetOnSpawn = false

local bg = Instance.new("Frame")
bg.Size = UDim2.fromScale(1, 1)
bg.BackgroundColor3 = Color3.fromRGB(8, 10, 13)
bg.BorderSizePixel = 0
bg.Parent = gui

local grad = Instance.new("UIGradient")
grad.Color = ColorSequence.new({
	ColorSequenceKeypoint.new(0, Color3.fromRGB(14, 30, 64)),
	ColorSequenceKeypoint.new(0.5, Color3.fromRGB(8, 10, 13)),
	ColorSequenceKeypoint.new(1, Color3.fromRGB(64, 14, 12)),
})
grad.Rotation = 0
grad.Parent = bg

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, 0, 0, 90)
title.Position = UDim2.new(0, 0, 0.32, 0)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBlack
title.TextSize = 72
title.RichText = true
title.Text = '<font color="#2F7BFF">BLUE</font> <font color="#C8CCD2">vs</font> <font color="#FF3B30">RED</font>'
title.TextColor3 = Color3.new(1, 1, 1)
title.Parent = bg

local sub = Instance.new("TextLabel")
sub.Size = UDim2.new(1, 0, 0, 30)
sub.Position = UDim2.new(0, 0, 0.32, 92)
sub.BackgroundTransparency = 1
sub.Font = Enum.Font.GothamBold
sub.TextSize = 22
sub.Text = "THREE FLAGS  -  DOMINATION"
sub.TextColor3 = Color3.fromRGB(200, 205, 212)
sub.Parent = bg

local barBg = Instance.new("Frame")
barBg.Size = UDim2.new(0.4, 0, 0, 6)
barBg.Position = UDim2.new(0.3, 0, 0.62, 0)
barBg.BackgroundColor3 = Color3.fromRGB(40, 46, 54)
barBg.BorderSizePixel = 0
barBg.Parent = bg
local bar = Instance.new("Frame")
bar.Size = UDim2.new(0, 0, 1, 0)
bar.BackgroundColor3 = Color3.fromRGB(240, 196, 80)
bar.BorderSizePixel = 0
bar.Parent = barBg

local stage = Instance.new("TextLabel")
stage.Size = UDim2.new(0.4, 0, 0, 24)
stage.Position = UDim2.new(0.3, 0, 0.62, 12)
stage.BackgroundTransparency = 1
stage.Font = Enum.Font.GothamMedium
stage.TextSize = 16
stage.TextXAlignment = Enum.TextXAlignment.Left
stage.Text = "Connecting to the front..."
stage.TextColor3 = Color3.fromRGB(170, 178, 188)
stage.Parent = bg

local tip = Instance.new("TextLabel")
tip.Size = UDim2.new(0.6, 0, 0, 40)
tip.Position = UDim2.new(0.2, 0, 0.84, 0)
tip.BackgroundTransparency = 1
tip.Font = Enum.Font.Gotham
tip.TextSize = 15
tip.TextWrapped = true
tip.TextColor3 = Color3.fromRGB(140, 150, 162)
tip.Parent = bg
local TIPS = {
	"Holding one, two or three flags all earn exactly one second per second - but holding none stops your clock.",
	"A contested flag earns nobody time. Clear the enemy out of the zone to resume.",
	"Engineers carry rocket launchers and demolition charges: walls, bridges and tanks are all fair game.",
	"Buildings collapse when their supports are destroyed. Take out the ground floor to bring the storeys down.",
	"Recon soldiers can call in rocket artillery with their binoculars (F).",
	"Supply trucks re-arm nearby infantry, ambulances heal them, recovery vehicles repair armour.",
	"Capturing the military base gives your team its motor pool: a tank, an IFV and a jeep.",
}
tip.Text = TIPS[math.random(1, #TIPS)]

gui.Parent = player:WaitForChild("PlayerGui")

local state = ReplicatedStorage:WaitForChild("MatchState", 120)
local t = 0
while true do
	t += RunService.RenderStepped:Wait()
	if state then
		-- plain type checks: ReplicatedFirst runs before Shared modules replicate
		local pv, sv = state:GetAttribute("LoadProgress"), state:GetAttribute("LoadStage")
		local p: number = if type(pv) == "number" then pv else 0
		local stageText: string = if type(sv) == "string" then sv else "Preparing battlefield"
		bar.Size = UDim2.new(p, 0, 1, 0)
		stage.Text = stageText .. string.format("   %d%%", math.floor(p * 100))
		if state:GetAttribute("Ready") then
			break
		end
	end
	if t > 6 then
		t = 0
		tip.Text = TIPS[math.random(1, #TIPS)]
	end
end
task.wait(0.5)
for i = 0, 1, 0.05 do
	bg.BackgroundTransparency = i
	title.TextTransparency = i
	sub.TextTransparency = i
	stage.TextTransparency = i
	tip.TextTransparency = i
	barBg.BackgroundTransparency = i
	bar.BackgroundTransparency = i
	task.wait(0.02)
end
gui:Destroy()
