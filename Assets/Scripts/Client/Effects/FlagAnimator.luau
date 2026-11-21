--!strict
-- Control-point flags: the cloth rises/lowers with capture progress, takes the
-- colour of the side the meter is moving toward (owner colour when held) and
-- waves in the wind. Zone markers and the floating letter show the owner,
-- pulsing amber when contested. HQ flags wave too.

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Net = require(ReplicatedStorage.Shared.Net)

local FlagAnimator = {}

type Cloth = { part: BasePart, base: CFrame, index: number }
type FlagRec = { model: Model, id: string?, cloths: { Cloth }, poleTop: number, poleBottom: number, caps: { BasePart }, label: TextLabel? }

local flags: { FlagRec } = {}
local state: Folder
local t = 0
local AMBER = Color3.fromRGB(255, 170, 40)

local function register(model: Model, pointId: string?)
	local cloths: { Cloth } = {}
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") and string.sub(d.Name, 1, 5) == "Cloth" then
			local idx = tonumber(string.match(d.Name, "%d+")) or 0
			table.insert(cloths, { part = d, base = d.CFrame, index = idx })
		end
	end
	table.sort(cloths, function(a, b)
		return a.index < b.index
	end)
	local caps = {}
	local markers = model:FindFirstChild("ZoneMarkers")
	if markers then
		for _, p in markers:GetChildren() do
			if p:IsA("BasePart") and p.Name == "Cap" then
				table.insert(caps, p)
			end
		end
	end
	local label = model:FindFirstChild("Letter", true) :: TextLabel?
	local top = if #cloths > 0 then cloths[1].base.Position.Y else 0
	table.insert(flags, { model = model, id = pointId, cloths = cloths, poleTop = top, poleBottom = top - 11, caps = caps, label = label })
end

local function update(dt: number)
	t += dt
	local wind = (state:GetAttribute("Wind") or 0.3) :: number
	for i = #flags, 1, -1 do
		local f = flags[i]
		if not f.model.Parent then
			table.remove(flags, i)
			continue
		end
		local height = 1
		local color: Color3? = nil
		local contested = false
		if f.id then
			local progress = (state:GetAttribute("P_" .. f.id .. "_Progress") or 0) :: number
			local owner = (state:GetAttribute("P_" .. f.id .. "_Owner") or 0) :: number
			contested = state:GetAttribute("P_" .. f.id .. "_Contested") == true
			height = math.abs(progress)
			color = if progress > 0.001 then Constants.TEAM_COLOR[1] elseif progress < -0.001 then Constants.TEAM_COLOR[2] else Constants.TEAM_COLOR[0]
			local ownerColor = Constants.TEAM_COLOR[owner]
			local pulse = 0.5 + 0.5 * math.sin(t * 8)
			for _, cap in f.caps do
				cap.Color = if contested then AMBER:Lerp(ownerColor, pulse) else ownerColor
			end
			if f.label then
				f.label.BackgroundColor3 = if contested then AMBER else ownerColor
			end
		end
		local drop = (1 - height) * (f.poleTop - f.poleBottom)
		local cum = CFrame.identity
		for _, c in f.cloths do
			local k = c.index
			local a = math.sin(t * (2.2 + wind * 3) - k * 0.7) * (0.12 + wind * 0.35) * (k + 1) / 8
			cum = cum * CFrame.Angles(0, a * 0.35, 0)
			c.part.CFrame = (c.base - Vector3.new(0, drop, 0)) * cum
			if color then
				c.part.Color = color
			end
		end
	end
end

function FlagAnimator.init()
	state = Net.matchState()
	task.spawn(function()
		local map = workspace:WaitForChild("Map")
		local flagFolder = map:WaitForChild("Flags")
		local function add(m: Instance)
			if m:IsA("Model") then
				task.wait(0.2)
				register(m, m:GetAttribute("PointId") :: string?)
			end
		end
		for _, m in flagFolder:GetChildren() do
			task.spawn(add, m)
		end
		flagFolder.ChildAdded:Connect(add)
		local props = map:WaitForChild("Props")
		local function addHq(m: Instance)
			if m:IsA("Model") and m:GetAttribute("PropKind") == "flagpole_hq" then
				task.wait(0.2)
				register(m, nil)
			end
		end
		for _, m in props:GetChildren() do
			task.spawn(addHq, m)
		end
		props.ChildAdded:Connect(addHq)
	end)
	RunService.RenderStepped:Connect(update)
end

return FlagAnimator
