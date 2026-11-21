--!strict
-- Custom camera: first person (default) and over-the-shoulder third person
-- (V), aim-down-sights zoom, recoil, explosion shake. Vehicles plug their own
-- camera in through CameraController.override.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local ClientState = require(script.Parent.Parent.ClientState)

local CameraController = {}

local player = Players.LocalPlayer
local yaw = 0
local pitch = 0
local recoilPitch = 0
local recoilYaw = 0
local shake = 0
local fov = 80
local zoom = 1
CameraController.thirdPerson = false
CameraController.override = nil :: ((dt: number, cam: Camera, yaw: number, pitch: number) -> CFrame?)?
CameraController.enabled = false

local params = RaycastParams.new()
params.FilterType = Enum.RaycastFilterType.Exclude

function CameraController.angles(): (number, number)
	return yaw, pitch
end

function CameraController.setAngles(y: number, p: number)
	yaw, pitch = y, p
end

function CameraController.addRecoil(up: number, side: number)
	recoilPitch += up
	recoilYaw += side
end

function CameraController.setZoom(z: number)
	zoom = z
end

local function setCharacterVisibility(char: Model, firstPerson: boolean)
	for _, d in char:GetDescendants() do
		if d:IsA("BasePart") then
			-- hide own body + gear in first person (the viewmodel replaces it)
			d.LocalTransparencyModifier = if firstPerson then 1 else 0
		end
	end
end

function CameraController.enable(on: boolean)
	CameraController.enabled = on
	local cam = workspace.CurrentCamera
	if on then
		cam.CameraType = Enum.CameraType.Scriptable
		UserInputService.MouseBehavior = Enum.MouseBehavior.LockCenter
		UserInputService.MouseIconEnabled = false
		local char = player.Character
		local root = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		if root then
			local look = root.CFrame.LookVector
			yaw = math.atan2(-look.X, -look.Z)
			pitch = 0
		end
	else
		UserInputService.MouseBehavior = Enum.MouseBehavior.Default
		UserInputService.MouseIconEnabled = true
	end
end

function CameraController.init()
	UserInputService.InputChanged:Connect(function(input, processed)
		if not CameraController.enabled or processed then
			return
		end
		if input.UserInputType == Enum.UserInputType.MouseMovement then
			local s = ClientState.settings
			local sens = s.sensitivity * (if ClientState.aiming then s.adsSensitivity / math.max(1, zoom * 0.6) else 1) * 0.01
			yaw -= input.Delta.X * sens
			pitch -= input.Delta.Y * sens * (if s.invertY then -1 else 1)
			pitch = math.clamp(pitch, -1.45, 1.45)
		end
	end)
	UserInputService.InputBegan:Connect(function(input, processed)
		if processed or not CameraController.enabled then
			return
		end
		if input.KeyCode == Enum.KeyCode.V and not ClientState.vehicleId then
			CameraController.thirdPerson = not CameraController.thirdPerson
		end
	end)
	ClientState.cameraShake:Connect(function(intensity: number)
		shake = math.min(1.5, shake + intensity)
	end)
	RunService:BindToRenderStep("BVR_Camera", Enum.RenderPriority.Camera.Value + 1, function(dt)
		if not CameraController.enabled then
			return
		end
		local cam = workspace.CurrentCamera
		cam.CameraType = Enum.CameraType.Scriptable
		-- recoil recovery
		local kickP = recoilPitch * math.min(1, dt * 18)
		local kickY = recoilYaw * math.min(1, dt * 18)
		pitch = math.clamp(pitch + kickP, -1.45, 1.45)
		yaw += kickY
		recoilPitch -= kickP
		recoilYaw -= kickY
		shake = math.max(0, shake - dt * 1.8)
		local shakeCF = CFrame.Angles((math.random() - 0.5) * shake * 0.03, (math.random() - 0.5) * shake * 0.03, (math.random() - 0.5) * shake * 0.02)
		local targetFov = ClientState.settings.fov / zoom
		fov += (targetFov - fov) * math.min(1, dt * 14)
		cam.FieldOfView = fov
		local rot = CFrame.Angles(0, yaw, 0) * CFrame.Angles(pitch, 0, 0)
		if CameraController.override then
			local cf = CameraController.override(dt, cam, yaw, pitch)
			if cf then
				cam.CFrame = cf * shakeCF
				return
			end
		end
		local char = player.Character
		local head = char and char:FindFirstChild("Head") :: BasePart?
		local root = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		local hum = char and char:FindFirstChildOfClass("Humanoid")
		if not char or not head or not root or not hum or hum.Health <= 0 then
			return
		end
		-- the body follows the view direction
		hum.AutoRotate = false
		local flat = CFrame.Angles(0, yaw, 0)
		if not hum.Sit then
			root.CFrame = CFrame.new(root.Position) * flat
		end
		local eye = head.Position + Vector3.new(0, 0.25, 0)
		local firstPerson = not CameraController.thirdPerson or ClientState.aiming
		if firstPerson then
			cam.CFrame = CFrame.new(eye) * rot * shakeCF
		else
			local offset = rot * Vector3.new(2.4, 0.8, 8)
			params.FilterDescendantsInstances = { char }
			local hit = workspace:Raycast(eye, offset, params)
			local dist = if hit then math.max(0.5, (hit.Position - eye).Magnitude - 0.6) else offset.Magnitude
			cam.CFrame = CFrame.new(eye + offset.Unit * dist) * rot * shakeCF
		end
		setCharacterVisibility(char, firstPerson)
	end)
end

return CameraController
