--!strict
-- Renders the AI support aircraft (recon drones and observation planes) from
-- the orbit parameters published by the server. Smooth, no replication cost.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Rig = require(ReplicatedStorage.Shared.Rig)

local SupportAirVisuals = {}

type Craft = { cfg: Instance, model: Model?, rig: any }
local crafts: { Craft } = {}

local function template(name: string): Model?
	for _, d in ReplicatedStorage.Assets.Models:GetDescendants() do
		if d:IsA("Model") and d.Name == name then
			return d
		end
	end
	return nil
end

local function add(cfg: Instance)
	local name = cfg:GetAttribute("Model")
	local t = if type(name) == "string" then template(name) else nil
	local c: Craft = { cfg = cfg, model = nil, rig = nil }
	if t then
		local m = t:Clone()
		local rig = Rig.assemble(m, true)
		for _, d in m:GetDescendants() do
			if d:IsA("BasePart") then
				d.CanCollide = false
				d.CanQuery = false
				d.CanTouch = false
			end
		end
		m:ScaleTo(1.0)
		m.Parent = workspace
		c.model = m
		c.rig = rig
	end
	table.insert(crafts, c)
end

function SupportAirVisuals.init()
	task.spawn(function()
		local folder = ReplicatedStorage:WaitForChild("SupportAir")
		for _, cfg in folder:GetChildren() do
			add(cfg)
		end
		folder.ChildAdded:Connect(add)
	end)
	local spin = 0
	RunService.RenderStepped:Connect(function(dt)
		spin += dt * 50
		local now = workspace:GetServerTimeNow()
		for _, c in crafts do
			local m = c.model
			if not m then
				continue
			end
			local cfg = c.cfg
			local centre = (cfg:GetAttribute("Center") or Vector3.zero) :: Vector3
			local radius = (cfg:GetAttribute("Radius") or 400) :: number
			local speed = (cfg:GetAttribute("Speed") or 90) :: number
			local alt = (cfg:GetAttribute("Altitude") or 300) :: number
			local phase = (cfg:GetAttribute("Phase") or 0) :: number
			local since = (cfg:GetAttribute("Since") or now) :: number
			local t = now - since
			local a = phase + t * speed / radius
			local pos = Vector3.new(centre.X + math.cos(a) * radius, alt, centre.Z + math.sin(a) * radius)
			local a2 = a + 0.01
			local ahead = Vector3.new(centre.X + math.cos(a2) * radius, alt, centre.Z + math.sin(a2) * radius)
			-- bank into the turn
			m:PivotTo(CFrame.lookAt(pos, ahead) * CFrame.Angles(0, 0, 0.35))
			local prop = c.rig and c.rig.joints.Prop
			if prop then
				prop.Transform = CFrame.Angles(0, 0, spin)
			end
		end
	end)
end

return SupportAirVisuals
