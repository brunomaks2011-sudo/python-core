--!strict
-- Dresses an R15 character as a Blue Army or Red Army soldier: uniform body
-- colours, Blender-made helmet / vest / backpack / armband gear welded to the
-- body parts, a slung weapon model, and identification attributes.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Rig = require(ReplicatedStorage.Shared.Rig)

local CharacterStyle = {}

local UNIFORM = {
	[1] = { torso = Color3.fromRGB(88, 98, 84), legs = Color3.fromRGB(76, 86, 72), boots = Color3.fromRGB(40, 38, 34) },
	[2] = { torso = Color3.fromRGB(110, 104, 70), legs = Color3.fromRGB(96, 90, 62), boots = Color3.fromRGB(46, 40, 34) },
}
local SKIN = {
	Color3.fromRGB(234, 192, 160), Color3.fromRGB(214, 170, 136), Color3.fromRGB(190, 146, 112), Color3.fromRGB(156, 112, 84),
	Color3.fromRGB(240, 206, 178), Color3.fromRGB(204, 160, 126),
}

local gearIndex: { [string]: Model } = {}

local function gear(name: string): Model?
	if not next(gearIndex) then
		local models = ReplicatedStorage:WaitForChild("Assets"):WaitForChild("Models")
		for _, d in models:GetDescendants() do
			if d:IsA("Model") and d:FindFirstChild("Pivot") then
				gearIndex[d.Name] = d
			end
		end
	end
	return gearIndex[name]
end
CharacterStyle.model = gear

local function weldTo(model: Model, part: BasePart, offset: CFrame?)
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") then
			d.Anchored = false
			d.CanCollide = false
			d.CanQuery = d.Name ~= "Pivot"
			d.CanTouch = false
			d.Massless = true
		end
	end
	local pivot = model:FindFirstChild("Pivot") :: BasePart
	model.PrimaryPart = pivot
	model:PivotTo(part.CFrame * (offset or CFrame.identity))
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") and d ~= pivot then
			local w = Instance.new("WeldConstraint")
			w.Part0 = pivot
			w.Part1 = d
			w.Parent = pivot
		end
	end
	local w = Instance.new("WeldConstraint")
	w.Part0 = part
	w.Part1 = pivot
	w.Parent = pivot
end

local function attachGear(character: Model, name: string, partName: string, team: number, offset: CFrame?, refSize: number?)
	local template = gear(name)
	local part = character:FindFirstChild(partName) :: BasePart?
	if not template or not part then
		return
	end
	local m = template:Clone()
	m.Name = "Gear_" .. name
	if refSize then
		local scale = math.clamp(part.Size.Y / refSize, 0.75, 1.5)
		if math.abs(scale - 1) > 0.03 then
			m:ScaleTo(scale)
		end
	end
	Rig.tint(m, "Team", Constants.TEAM_COLOR[team])
	weldTo(m, part, offset)
	m.Parent = character
end

function CharacterStyle.apply(character: Model, team: number, role: string, rng: Random?)
	local r = rng or Random.new()
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	-- strip avatar clothing / accessories / face
	for _, d in character:GetDescendants() do
		if d:IsA("Accessory") or d:IsA("Shirt") or d:IsA("Pants") or d:IsA("ShirtGraphic") or d:IsA("CharacterMesh") then
			d:Destroy()
		elseif d:IsA("Decal") and d.Name == "face" then
			d.Transparency = 0.6
		end
	end
	local uni = UNIFORM[team] or UNIFORM[1]
	local skin = SKIN[r:NextInteger(1, #SKIN)]
	local bc = character:FindFirstChildOfClass("BodyColors")
	if not bc then
		local b = Instance.new("BodyColors")
		b.Parent = character
		bc = b
	end
	local colors = bc :: BodyColors
	colors.HeadColor3 = skin
	colors.TorsoColor3 = uni.torso
	colors.LeftArmColor3 = uni.torso
	colors.RightArmColor3 = uni.torso
	colors.LeftLegColor3 = uni.legs
	colors.RightLegColor3 = uni.legs
	-- hands and feet: gloves / boots
	for _, n in { "LeftHand", "RightHand" } do
		local p = character:FindFirstChild(n)
		if p and p:IsA("BasePart") then
			p.Color = Color3.fromRGB(52, 50, 46)
		end
	end
	for _, n in { "LeftFoot", "RightFoot" } do
		local p = character:FindFirstChild(n)
		if p and p:IsA("BasePart") then
			p.Color = uni.boots
		end
	end
	local side = if team == 2 then "Red" else "Blue"
	if role == "recon" then
		attachGear(character, "Boonie_" .. side, "Head", team, nil, 1.2)
	elseif role == "crew" then
		attachGear(character, "TankerHelmet_" .. side, "Head", team, nil, 1.2)
	else
		attachGear(character, "Helmet_" .. side, "Head", team, nil, 1.2)
	end
	attachGear(character, "Vest_" .. side, "UpperTorso", team, CFrame.new(0, -0.1, 0), nil)
	if role ~= "crew" then
		attachGear(character, "Backpack_" .. side, "UpperTorso", team, nil, nil)
	end
	attachGear(character, "Armband_team", "LeftUpperArm", team, CFrame.new(0, 0.15, 0), nil)
	if role == "medic" then
		attachGear(character, "Armband_medic", "RightUpperArm", team, CFrame.new(0, 0.15, 0), nil)
	end
	if humanoid then
		humanoid.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
		humanoid.HealthDisplayType = Enum.HumanoidHealthDisplayType.AlwaysOff
		humanoid.BreakJointsOnDeath = false
	end
	character:SetAttribute("Team", team)
	character:SetAttribute("Role", role)
end

-- Third-person weapon in the right hand (visible to everyone).
function CharacterStyle.holdWeapon(character: Model, modelName: string?)
	local old = character:FindFirstChild("HeldWeapon")
	if old then
		old:Destroy()
	end
	if not modelName then
		return
	end
	local template = gear(modelName)
	local hand = character:FindFirstChild("RightHand") :: BasePart?
	if not template or not hand then
		return
	end
	local m = template:Clone()
	m.Name = "HeldWeapon"
	m:SetAttribute("Weapon", modelName)
	-- the gun's +Y (Blender front) is Roblox -Z: point it along the hand's forward
	weldTo(m, hand, CFrame.new(0, -0.15, -0.1) * CFrame.Angles(-math.pi / 2, 0, 0))
	for _, d in m:GetDescendants() do
		if d:IsA("BasePart") then
			d.CanQuery = false
		end
	end
	m.Parent = character
end

return CharacterStyle
