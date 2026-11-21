--!strict
-- Infantry movement: sprint (Shift, stamina), crouch (C), prone (Z), jump
-- (Space, standing only). Stance changes are sent to the server so others see them.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local ClientState = require(script.Parent.Parent.ClientState)

local CharacterController = {}

local SOLDIER = Constants.SOLDIER
local player = Players.LocalPlayer
local sprintHeld = false
local stance = 0
local baseHip = 2
local stanceRemote: RemoteEvent

local function humanoid(): Humanoid?
	local c = player.Character
	return c and c:FindFirstChildOfClass("Humanoid")
end

local function setStance(s: number)
	if s == stance then
		return
	end
	stance = s
	ClientState.stance = s
	stanceRemote:FireServer(s)
	local hum = humanoid()
	if hum then
		hum.HipHeight = if s == 0 then baseHip elseif s == 1 then baseHip * 0.6 else baseHip * 0.2
		hum.JumpHeight = if s == 0 then 3.5 else 0
	end
end
CharacterController.setStance = setStance

function CharacterController.onSpawn(character: Model)
	local hum = character:WaitForChild("Humanoid") :: Humanoid
	baseHip = if hum.HipHeight > 0.5 then hum.HipHeight else 2
	stance = 0
	ClientState.stance = 0
	ClientState.stamina = 1
end

function CharacterController.init()
	stanceRemote = Net.event("Stance")
	UserInputService.InputBegan:Connect(function(input, processed)
		if processed or not ClientState.deployed or ClientState.vehicleId then
			return
		end
		local k = input.KeyCode
		if k == Enum.KeyCode.LeftShift then
			sprintHeld = true
			if stance ~= 0 then
				setStance(0)
			end
		elseif k == Enum.KeyCode.C or k == Enum.KeyCode.LeftControl then
			setStance(if stance == 1 then 0 else 1)
		elseif k == Enum.KeyCode.Z then
			setStance(if stance == 2 then 0 else 2)
		elseif k == Enum.KeyCode.Space and stance ~= 0 then
			setStance(0)
		end
	end)
	UserInputService.InputEnded:Connect(function(input)
		if input.KeyCode == Enum.KeyCode.LeftShift then
			sprintHeld = false
		end
	end)
	player.CharacterAdded:Connect(CharacterController.onSpawn)
	RunService.Heartbeat:Connect(function(dt)
		local hum = humanoid()
		if not hum or hum.Health <= 0 or hum.Sit then
			return
		end
		local role = Defs.Roles[ClientState.role]
		local mult = if role then role.speed else 1
		local moving = hum.MoveDirection.Magnitude > 0.1
		local sprinting = sprintHeld and moving and stance == 0 and not ClientState.aiming and not ClientState.reloading and ClientState.stamina > 0.02
		if sprinting then
			ClientState.stamina = math.max(0, ClientState.stamina - dt / SOLDIER.STAMINA)
		else
			ClientState.stamina = math.min(1, ClientState.stamina + dt * SOLDIER.STAMINA_REGEN * (if moving then 0.5 else 1))
		end
		local speed
		if stance == 2 then
			speed = SOLDIER.PRONE_SPEED
		elseif stance == 1 then
			speed = SOLDIER.CROUCH_SPEED
		elseif sprinting then
			speed = SOLDIER.SPRINT_SPEED
		elseif ClientState.aiming then
			speed = SOLDIER.WALK_SPEED
		else
			speed = SOLDIER.RUN_SPEED
		end
		hum.WalkSpeed = speed * mult
		ClientState.sprinting = sprinting
	end)
end

return CharacterController
