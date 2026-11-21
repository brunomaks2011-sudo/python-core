--!strict
-- Procedural poses layered on top of the stock R15 animations, for every
-- soldier near the camera (players and AI): weapon held at the shoulder,
-- crouch (knees bent, torso low) and prone (lying flat). Driven by the
-- replicated "Stance" and "Equipped" character attributes, so every client
-- sees the same thing.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local StanceAnimator = {}

type Rig = { model: Model, joints: { [string]: Motor6D } }
local rigs: { [Model]: Rig } = {}
local JOINTS = { "Root", "Waist", "Neck", "RightShoulder", "RightElbow", "LeftShoulder", "LeftElbow", "RightHip", "RightKnee", "LeftHip", "LeftKnee" }

local function register(model: Model)
	if rigs[model] then
		return
	end
	local joints = {}
	for _, d in model:GetDescendants() do
		if d:IsA("Motor6D") and table.find(JOINTS, d.Name) then
			joints[d.Name] = d
		end
	end
	if joints.RightShoulder and joints.LeftShoulder then
		rigs[model] = { model = model, joints = joints }
	end
end

local A = CFrame.Angles
local rad = math.rad

local function pose(r: Rig)
	local m = r.model
	local stance = (m:GetAttribute("Stance") or 0) :: number
	local j = r.joints
	local hum = m:FindFirstChildOfClass("Humanoid")
	if not hum or hum.Health <= 0 or hum.Sit then
		return
	end
	-- arms: rifle at the shoulder
	if m:FindFirstChild("HeldWeapon") then
		j.RightShoulder.Transform = A(rad(80), rad(-12), rad(-8))
		if j.RightElbow then
			j.RightElbow.Transform = A(rad(25), 0, 0)
		end
		j.LeftShoulder.Transform = A(rad(85), rad(38), rad(10))
		if j.LeftElbow then
			j.LeftElbow.Transform = A(rad(30), 0, 0)
		end
	end
	if stance == 1 then
		-- crouch: bend knees and hips, lean the torso forward a little
		if j.RightHip then
			j.RightHip.Transform = j.RightHip.Transform * A(rad(70), 0, 0)
		end
		if j.LeftHip then
			j.LeftHip.Transform = j.LeftHip.Transform * A(rad(20), 0, 0)
		end
		if j.RightKnee then
			j.RightKnee.Transform = j.RightKnee.Transform * A(rad(-95), 0, 0)
		end
		if j.LeftKnee then
			j.LeftKnee.Transform = j.LeftKnee.Transform * A(rad(-60), 0, 0)
		end
		if j.Waist then
			j.Waist.Transform = A(rad(-12), 0, 0)
		end
	elseif stance == 2 then
		-- prone: the whole body lies forward, head up to look ahead
		if j.Root then
			j.Root.Transform = CFrame.new(0, -1.2, 0) * A(rad(-85), 0, 0)
		end
		if j.Neck then
			j.Neck.Transform = A(rad(70), 0, 0)
		end
		for _, n in { "RightHip", "LeftHip", "RightKnee", "LeftKnee" } do
			if j[n] then
				j[n].Transform = A(rad(if string.find(n, "Hip") then 4 else 0), 0, 0)
			end
		end
		j.RightShoulder.Transform = A(rad(160), rad(-10), 0)
		j.LeftShoulder.Transform = A(rad(160), rad(25), 0)
	end
end

function StanceAnimator.init()
	local function watchCharacter(c: Model)
		task.wait(0.5)
		register(c)
	end
	for _, p in Players:GetPlayers() do
		if p.Character then
			task.spawn(watchCharacter, p.Character)
		end
		p.CharacterAdded:Connect(watchCharacter)
	end
	Players.PlayerAdded:Connect(function(p)
		p.CharacterAdded:Connect(watchCharacter)
	end)
	task.spawn(function()
		local soldiers = workspace:WaitForChild("Soldiers")
		for _, c in soldiers:GetChildren() do
			if c:IsA("Model") then
				task.spawn(watchCharacter, c)
			end
		end
		soldiers.ChildAdded:Connect(function(c)
			if c:IsA("Model") then
				watchCharacter(c)
			end
		end)
	end)
	-- after animations have been applied this frame
	RunService.Stepped:Connect(function()
		local cam = workspace.CurrentCamera.CFrame.Position
		for model, r in rigs do
			if not model.Parent then
				rigs[model] = nil
				continue
			end
			local root = model:FindFirstChild("HumanoidRootPart") :: BasePart?
			if root and (root.Position - cam).Magnitude < 260 then
				pose(r)
			end
		end
	end)
end

return StanceAnimator
