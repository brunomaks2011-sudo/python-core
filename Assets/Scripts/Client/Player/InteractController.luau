--!strict
-- Context interactions: [E] enter the nearest friendly vehicle, [E] climb a
-- ladder (watchtowers, water tower). Shows a prompt on screen.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local Defs = require(ReplicatedStorage.Shared.Defs)
local Net = require(ReplicatedStorage.Shared.Net)
local Theme = require(script.Parent.Parent.UI.Theme)
local ClientState = require(script.Parent.Parent.ClientState)

local InteractController = {}

local player = Players.LocalPlayer
local prompt: TextLabel
type Target = { kind: string, id: number?, to: Vector3?, name: string }
local target: Target? = nil

local function scan()
	target = nil
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root or ClientState.vehicleId or not ClientState.deployed then
		return
	end
	local pos = root.Position
	local best: Target?, bd: number = nil, math.huge
	local vehicles = workspace:FindFirstChild("Vehicles")
	if vehicles then
		for _, m in vehicles:GetChildren() do
			local hull = m:FindFirstChild("Hitbox") :: BasePart?
			if hull and not m:GetAttribute("Destroyed") and m:GetAttribute("Team") == ClientState.team then
				local kind = m:GetAttribute("Kind") :: string?
				local def = kind and Defs.Vehicles[kind]
				local reach = if def then def.size.Magnitude * 0.5 + 10 else 16
				local d = (hull.Position - pos).Magnitude
				if d < reach and d < bd then
					best = { kind = "vehicle", id = m:GetAttribute("VehicleId") :: number, name = if kind then Defs.vehicleName(kind, ClientState.team) else "vehicle" }
					bd = d
				end
			end
		end
	end
	-- ladders
	local map = workspace:FindFirstChild("Map")
	local props = map and map:FindFirstChild("Props")
	if props then
		for _, m in props:GetChildren() do
			local kind = m:GetAttribute("PropKind")
			if kind == "watchtower" or kind == "water_tower" then
				local bottom = m:FindFirstChild("LadderBottom", true) :: Attachment?
				local top = m:FindFirstChild("LadderTop", true) :: Attachment?
				if bottom and top then
					local db = (bottom.WorldPosition - pos).Magnitude
					local dt = (top.WorldPosition - pos).Magnitude
					if db < 6 and db < bd then
						best = { kind = "ladder", to = top.WorldPosition + Vector3.new(0, 3, 0), name = "Climb up" }
						bd = db
					elseif dt < 6 and dt < bd then
						best = { kind = "ladder", to = bottom.WorldPosition + Vector3.new(0, 3, 0), name = "Climb down" }
						bd = dt
					end
				end
			end
		end
	end
	target = best
end

function InteractController.init()
	local gui = Theme.screen("Interact", 6)
	prompt = Theme.label(gui, "Prompt", "", UDim2.new(0, 400, 0, 30), UDim2.new(0.5, -200, 0.62, 30), 18, Theme.Text, Theme.FontBold)
	prompt.TextXAlignment = Enum.TextXAlignment.Center
	prompt.TextStrokeTransparency = 0.4
	gui.Parent = player:WaitForChild("PlayerGui")
	local interact = Net.event("Interact")
	local acc = 0
	RunService.Heartbeat:Connect(function(dt)
		acc += dt
		if acc > 0.2 then
			acc = 0
			scan()
		end
		local t = target
		if t then
			prompt.Text = if t.kind == "vehicle" then "[E]  Enter " .. t.name else "[E]  " .. t.name
		else
			prompt.Text = ""
		end
	end)
	UserInputService.InputBegan:Connect(function(input, processed)
		if processed or input.KeyCode ~= Enum.KeyCode.E or ClientState.vehicleId or not ClientState.deployed then
			return
		end
		local t = target
		if not t then
			return
		end
		if t.kind == "vehicle" then
			interact:FireServer({ action = "enter", id = t.id })
		elseif t.kind == "ladder" then
			-- the server moves the character (client-side teleports are pulled back)
			interact:FireServer({ action = "ladder" })
		end
	end)
end

return InteractController
