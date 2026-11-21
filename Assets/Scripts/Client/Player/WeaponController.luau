--!strict
-- Infantry weapons on the client: first-person viewmodel (Blender weapon
-- models + team sleeves), firing with spread/recoil, reload, weapon switching,
-- grenades / demolition charges, rocket launcher and class tools.
-- Shots are predicted locally and validated by the server (CombatService).

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local TweenService = game:GetService("TweenService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local Hits = require(ReplicatedStorage.Shared.Hits)
local Net = require(ReplicatedStorage.Shared.Net)
local Rig = require(ReplicatedStorage.Shared.Rig)
local ClientState = require(script.Parent.Parent.ClientState)
local CameraController = require(script.Parent.CameraController)
local Effects = require(script.Parent.Parent.Effects.Effects)

local WeaponController = {}
WeaponController.onShot = nil :: ((weaponId: string) -> ())?

local player = Players.LocalPlayer
local loadout: { string } = {}
local ammo: { [string]: { mag: number, reserve: number } } = {}
local equipped = 1
local mouseDown = false
local aimDown = false
local aimAlpha = 0
local fireAcc = 0
local bloom = 0
local reloadUntil = 0
local lastShot = 0
local pendingShots: { any } = {}
local viewmodel: Model? = nil
local vmWeapon: Model? = nil
local vmArms: { BasePart } = {}
local sightOffset = CFrame.identity
local leftHandOffset = CFrame.new(0, 0.6, 0)
local bobT = 0
local swayX, swayY = 0, 0
local magGroup: Model? = nil
local remotes: { [string]: RemoteEvent } = {}

local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude
rayParams.IgnoreWater = true

local modelCache: { [string]: Model } = {}
local function weaponModel(name: string): Model?
	if modelCache[name] then
		return modelCache[name]
	end
	for _, d in ReplicatedStorage:WaitForChild("Assets"):WaitForChild("Models"):GetDescendants() do
		if d:IsA("Model") and d.Name == name and d:GetAttribute("Category") == "Weapons" then
			modelCache[name] = d
			return d
		end
	end
	return nil
end

local function currentId(): string
	return loadout[equipped] or ""
end

local function currentDef(): { [string]: any }?
	return Defs.Weapons[currentId()]
end

local function publish()
	local w = currentDef()
	local id = currentId()
	ClientState.equipped = equipped
	ClientState.weaponName = if w then string.upper(w.name) else ""
	local a = ammo[id]
	if w and w.kind == "hitscan" and a then
		ClientState.ammoMag = a.mag
		ClientState.ammoReserve = a.reserve
	elseif w and (w.kind == "projectile") and a then
		ClientState.ammoMag = a.mag
		ClientState.ammoReserve = a.reserve
	elseif w and w.kind == "throw" and a then
		ClientState.ammoMag = a.mag
		ClientState.ammoReserve = -1
	else
		ClientState.ammoMag = if a then a.mag else 0
		ClientState.ammoReserve = -1
	end
	local g = ammo[loadout[4] or ""]
	ClientState.weaponName ..= if g then string.format("   [%s x%d]", if loadout[4] == "c4" then "C4" else "G", g.mag) else ""
end

-- ---------------------------------------------------------------------------
-- Viewmodel
-- ---------------------------------------------------------------------------
local function clearViewmodel()
	if viewmodel then
		viewmodel:Destroy()
	end
	viewmodel = nil
	vmWeapon = nil
	vmArms = {}
	magGroup = nil
end

local function buildViewmodel()
	clearViewmodel()
	local w = currentDef()
	if not w or not w.model then
		return
	end
	local template = weaponModel(w.model)
	if not template then
		return
	end
	local vm = Instance.new("Model")
	vm.Name = "Viewmodel"
	local gun = template:Clone()
	Rig.anchorAll(gun, false)
	for _, d in gun:GetDescendants() do
		if d:IsA("BasePart") then
			d.CanQuery = false
			d.CanTouch = false
			d.CastShadow = false
		end
	end
	gun.Parent = vm
	vmWeapon = gun
	local pivot = gun:FindFirstChild("Pivot") :: BasePart
	local sight = Rig.findAttachment(gun, "Sight")
	sightOffset = if sight then pivot.CFrame:ToObjectSpace(sight.WorldCFrame) else CFrame.new(0, 0.35, -0.2)
	local lh = Rig.findAttachment(gun, "LeftHand")
	leftHandOffset = if lh then pivot.CFrame:ToObjectSpace(lh.WorldCFrame) else CFrame.new(0, 0, -0.8)
	magGroup = Rig.findGroup(gun, "Mag")
	local uniform = if ClientState.team == 2 then Color3.fromRGB(110, 104, 70) else Color3.fromRGB(88, 98, 84)
	for i = 1, 4 do
		local p = Instance.new("Part")
		p.Anchored = true
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.CastShadow = false
		p.Material = Enum.Material.Fabric
		p.Color = if i <= 2 then uniform else Color3.fromRGB(46, 44, 40)
		p.Size = if i <= 2 then Vector3.new(0.5, 0.5, 2.2) else Vector3.new(0.42, 0.42, 0.55)
		p.Parent = vm
		vmArms[i] = p
	end
	-- team armband on the left sleeve
	local band = Instance.new("Part")
	band.Anchored = true
	band.CanCollide = false
	band.CanQuery = false
	band.CastShadow = false
	band.Material = Enum.Material.Fabric
	band.Color = Constants.TEAM_COLOR[ClientState.team] or Color3.new(1, 1, 1)
	band.Size = Vector3.new(0.53, 0.53, 0.3)
	band.Name = "Band"
	band.Parent = vm
	vmArms[5] = band
	vm.Parent = workspace.CurrentCamera
	viewmodel = vm
end

local function placeArm(sleeve: BasePart, glove: BasePart, shoulder: Vector3, hand: Vector3)
	local d = hand - shoulder
	local len = d.Magnitude
	sleeve.Size = Vector3.new(0.5, 0.5, math.max(0.5, len - 0.25))
	sleeve.CFrame = CFrame.lookAt(shoulder + d * 0.45, hand)
	glove.CFrame = CFrame.lookAt(hand, hand + d)
end

local function updateViewmodel(dt: number)
	local vm = viewmodel
	local gun = vmWeapon
	local show = ClientState.deployed and not ClientState.vehicleId and not CameraController.thirdPerson and gun ~= nil
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	if hum and hum.Health <= 0 then
		show = false
	end
	if not vm or not gun then
		return
	end
	for _, d in vm:GetDescendants() do
		if d:IsA("BasePart") and d.Name ~= "Pivot" then
			d.LocalTransparencyModifier = if show then 0 else 1
		end
	end
	if not show then
		return
	end
	local cam = workspace.CurrentCamera
	local camCF = cam.CFrame
	aimAlpha += ((if aimDown and reloadUntil < os.clock() then 1 else 0) - aimAlpha) * math.min(1, dt * 14)
	-- bob + sway
	local speed = if hum then hum.MoveDirection.Magnitude * hum.WalkSpeed else 0
	bobT += dt * (2 + speed * 0.35)
	local bobAmt = (1 - aimAlpha) * math.clamp(speed / 16, 0, 1.4)
	local bob = CFrame.new(math.sin(bobT) * 0.05 * bobAmt, math.abs(math.cos(bobT)) * 0.06 * bobAmt, 0)
	local md = UserInputService:GetMouseDelta()
	swayX += (-md.X * 0.0015 - swayX) * math.min(1, dt * 8)
	swayY += (-md.Y * 0.0015 - swayY) * math.min(1, dt * 8)
	local sway = CFrame.Angles(swayY * (1 - aimAlpha * 0.7), swayX * (1 - aimAlpha * 0.7), 0)
	local reloadTilt = if reloadUntil > os.clock() then CFrame.Angles(-0.35, 0.25, 0.4) * CFrame.new(0, -0.25, 0) else CFrame.identity
	local hip = camCF * CFrame.new(0.62, -0.62, -1.35) * sway * bob * reloadTilt
	local ads = camCF * CFrame.new(0, 0, -0.55) * sightOffset:Inverse() * sway
	local cf = hip:Lerp(ads, aimAlpha)
	gun:PivotTo(cf)
	-- arms
	local right = camCF * CFrame.new(0.9, -1.5, 0.4)
	local left = camCF * CFrame.new(-0.9, -1.5, 0.2)
	placeArm(vmArms[1], vmArms[3], right.Position, cf.Position + cf.UpVector * -0.05)
	placeArm(vmArms[2], vmArms[4], left.Position, (cf * leftHandOffset).Position)
	vmArms[5].CFrame = vmArms[2].CFrame * CFrame.new(0, 0, vmArms[2].Size.Z * 0.3)
end

-- ---------------------------------------------------------------------------
-- Firing
-- ---------------------------------------------------------------------------
local function muzzlePosition(): Vector3
	if vmWeapon and not CameraController.thirdPerson then
		local m = Rig.findAttachment(vmWeapon, "Muzzle")
		if m then
			return m.WorldPosition
		end
	end
	local char = player.Character
	local held = char and char:FindFirstChild("HeldWeapon")
	if held then
		local m = Rig.findAttachment(held, "Muzzle")
		if m then
			return m.WorldPosition
		end
	end
	return workspace.CurrentCamera.CFrame.Position
end

local function excludeList(): { Instance }
	local list: { Instance } = { workspace.CurrentCamera }
	if player.Character then
		table.insert(list, player.Character)
	end
	local fx = workspace:FindFirstChild("LocalEffects")
	if fx then
		table.insert(list, fx)
	end
	return list
end

local function aimPoint(spread: number, range: number): (Vector3, RaycastResult?)
	local cam = workspace.CurrentCamera
	local dir = cam.CFrame.LookVector
	if spread > 0 then
		local a = math.random() * math.pi * 2
		local r = math.sqrt(math.random()) * spread
		dir = (CFrame.lookAt(Vector3.zero, dir) * CFrame.Angles(math.cos(a) * r, math.sin(a) * r, 0)).LookVector
	end
	rayParams.FilterDescendantsInstances = excludeList()
	local res = workspace:Raycast(cam.CFrame.Position, dir * range, rayParams)
	return if res then res.Position else cam.CFrame.Position + dir * range, res
end

local function shoot(w: { [string]: any }, id: string)
	local a = ammo[id]
	if not a or a.mag <= 0 then
		return false
	end
	local char = player.Character
	local head = char and char:FindFirstChild("Head") :: BasePart?
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	if not head or not hum then
		return false
	end
	a.mag -= 1
	local moving = hum.MoveDirection.Magnitude > 0.1
	local stanceMul = if ClientState.stance == 2 then 0.55 elseif ClientState.stance == 1 then 0.8 else 1
	local spread = ((if aimDown then w.adsSpread else w.spread) * (if moving then 2.2 else 1) * stanceMul) + bloom
	ClientState.spread = spread
	local target = aimPoint(spread, w.range)
	local origin = head.Position
	local dir = (target - origin).Unit
	rayParams.FilterDescendantsInstances = excludeList()
	local res = workspace:Raycast(origin, dir * w.range, rayParams)
	local hitPos = if res then res.Position else origin + dir * w.range
	local muzzle = muzzlePosition()
	Effects.tracer(muzzle, hitPos)
	Effects.muzzle(muzzle, dir, false)
	if res then
		local info = Hits.classify(res.Instance)
		Effects.impact(res.Position, res.Normal, res.Material.Name, info.kind == "soldier")
	end
	table.insert(pendingShots, { o = origin, d = dir, h = if res then res.Instance else nil, p = if res then res.Position else nil })
	local kick = w.recoil * (if aimDown then 0.65 else 1) * stanceMul
	CameraController.addRecoil(kick, (math.random() - 0.5) * kick * 0.6)
	bloom = math.min(0.03, bloom + kick * 0.25)
	lastShot = os.clock()
	if WeaponController.onShot then
		WeaponController.onShot(id)
	end
	publish()
	return true
end

local function reload()
	local w = currentDef()
	local id = currentId()
	local a = ammo[id]
	if not w or not a or w.kind ~= "hitscan" or a.reserve <= 0 or a.mag >= w.mag or reloadUntil > os.clock() then
		return
	end
	reloadUntil = os.clock() + (w.reload or 2)
	ClientState.reloading = true
	remotes.Reload:FireServer()
	if magGroup then
		local pv = magGroup:FindFirstChild("Pivot") :: BasePart?
		local _ = pv
	end
	task.delay(w.reload or 2, function()
		if currentId() == id and reloadUntil > 0 then
			local take = math.min(w.mag - a.mag, a.reserve)
			a.mag += take
			a.reserve -= take
			reloadUntil = 0
			ClientState.reloading = false
			publish()
		end
	end)
end

local function equip(slot: number)
	if slot == equipped or not loadout[slot] or loadout[slot] == "" then
		return
	end
	local w = Defs.Weapons[loadout[slot]]
	if not w or w.kind == "throw" then
		return
	end
	equipped = slot
	reloadUntil = 0
	ClientState.reloading = false
	remotes.SwitchWeapon:FireServer(slot)
	buildViewmodel()
	publish()
end

local function throwItem()
	local id = loadout[4]
	local a = ammo[id or ""]
	if not id or not a or a.mag <= 0 then
		return
	end
	a.mag -= 1
	local cam = workspace.CurrentCamera
	local dir = (cam.CFrame.LookVector + Vector3.new(0, 0.12, 0)).Unit
	remotes.Throw:FireServer({ slot = 4, d = dir, power = 1 })
	publish()
end

local function useTool(primary: boolean)
	local id = currentId()
	local w = currentDef()
	if not w then
		return
	end
	if id == "binoculars" then
		local target = aimPoint(0, w.spotRange or 1800)
		if primary then
			remotes.UseTool:FireServer({ p = target })
			ClientState.notify:Fire("ENEMIES SPOTTED", Color3.fromRGB(240, 196, 80))
		end
		return
	end
	if id == "repair" then
		local _, res = aimPoint(0, 20)
		remotes.UseTool:FireServer({ part = if res then res.Instance else nil })
		return
	end
	-- medkit / ammo: target the teammate under the crosshair, else yourself
	local _, res = aimPoint(0, 16)
	local targetId = nil
	if res then
		local info = Hits.classify(res.Instance)
		if info.kind == "soldier" then
			targetId = info.soldierId
		end
	end
	remotes.UseTool:FireServer({ target = targetId })
end

-- ---------------------------------------------------------------------------
function WeaponController.onSpawn()
	local role = Defs.Roles[ClientState.role] or Defs.Roles.rifleman
	local list = role.loadout[ClientState.team] or role.loadout[1]
	loadout = {}
	ammo = {}
	for slot = 1, 4 do
		local id = list[slot] or ""
		loadout[slot] = id
		local w = Defs.Weapons[id]
		if w then
			if w.kind == "hitscan" then
				ammo[id] = { mag = w.mag, reserve = w.reserve }
			elseif w.kind == "projectile" then
				ammo[id] = { mag = w.mag or 1, reserve = w.reserve or 3 }
			elseif w.kind == "throw" then
				ammo[id] = { mag = w.count or 1, reserve = 0 }
			else
				ammo[id] = { mag = w.uses or 99, reserve = 0 }
			end
		end
	end
	equipped = 1
	reloadUntil = 0
	bloom = 0
	ClientState.reloading = false
	buildViewmodel()
	publish()
end

function WeaponController.clear()
	clearViewmodel()
end

function WeaponController.init()
	for _, n in { "Fire", "Reload", "SwitchWeapon", "Throw", "Detonate", "UseTool", "ArtilleryCall" } do
		remotes[n] = Net.event(n)
	end
	UserInputService.InputBegan:Connect(function(input, processed)
		if processed or not ClientState.deployed or ClientState.vehicleId or ClientState.inMenu then
			return
		end
		local t = input.UserInputType
		local k = input.KeyCode
		if t == Enum.UserInputType.MouseButton1 then
			mouseDown = true
			local w = currentDef()
			if w and w.kind == "projectile" then
				local a = ammo[currentId()]
				if a and a.mag > 0 then
					a.mag -= 1
					local cam = workspace.CurrentCamera
					remotes.Throw:FireServer({ slot = equipped, d = cam.CFrame.LookVector })
					CameraController.addRecoil(0.05, 0)
					task.delay(w.reload or 3, function()
						if a.reserve > 0 and a.mag == 0 then
							a.reserve -= 1
							a.mag = 1
							publish()
						end
					end)
					publish()
				end
			elseif w and w.kind == "tool" then
				useTool(true)
			elseif w and w.kind == "hitscan" and not w.auto then
				if os.clock() - lastShot >= 60 / w.rpm and reloadUntil < os.clock() then
					shoot(w, currentId())
				end
			end
		elseif t == Enum.UserInputType.MouseButton2 then
			aimDown = true
			ClientState.aiming = true
			local w = currentDef()
			CameraController.setZoom(if w and w.scope then w.scope elseif w and w.zoom then w.zoom else 1.35)
		elseif k == Enum.KeyCode.R then
			reload()
		elseif k == Enum.KeyCode.One then
			equip(1)
		elseif k == Enum.KeyCode.Two then
			equip(2)
		elseif k == Enum.KeyCode.Three then
			equip(3)
		elseif k == Enum.KeyCode.G then
			throwItem()
		elseif k == Enum.KeyCode.X then
			remotes.Detonate:FireServer()
		elseif k == Enum.KeyCode.F and currentId() == "binoculars" then
			local target = aimPoint(0, 1800)
			remotes.ArtilleryCall:FireServer(target)
			ClientState.notify:Fire("ROCKET ARTILLERY REQUESTED", Color3.fromRGB(255, 170, 40))
		end
	end)
	UserInputService.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 then
			mouseDown = false
		elseif input.UserInputType == Enum.UserInputType.MouseButton2 then
			aimDown = false
			ClientState.aiming = false
			CameraController.setZoom(1)
		end
	end)
	UserInputService.InputChanged:Connect(function(input, processed)
		if processed or not ClientState.deployed or ClientState.vehicleId then
			return
		end
		if input.UserInputType == Enum.UserInputType.MouseWheel then
			local dir = if input.Position.Z > 0 then -1 else 1
			for step = 1, 3 do
				local slot = ((equipped - 1 + dir * step) % 3) + 1
				if loadout[slot] and loadout[slot] ~= "" then
					equip(slot)
					break
				end
			end
		end
	end)
	Net.event("MatchEvent").OnClientEvent:Connect(function(e)
		if type(e) == "table" and e.kind == "ammo" and ammo[e.weapon] then
			ammo[e.weapon].mag = e.mag
			ammo[e.weapon].reserve = e.reserve
			publish()
		end
	end)
	local repairAcc = 0
	RunService.RenderStepped:Connect(function(dt)
		bloom = math.max(0, bloom - dt * 0.05)
		if not mouseDown then
			fireAcc = 0
		end
		local w = currentDef()
		local id = currentId()
		if mouseDown and w and w.kind == "hitscan" and w.auto and ClientState.deployed and not ClientState.vehicleId and reloadUntil < os.clock() then
			fireAcc += dt
			local interval = 60 / w.rpm
			if os.clock() - lastShot >= interval then
				fireAcc = interval
			end
			local n = 0
			while fireAcc >= interval and n < 4 do
				fireAcc -= interval
				n += 1
				if not shoot(w, id) then
					mouseDown = false
					reload()
					break
				end
			end
		elseif mouseDown and id == "repair" then
			repairAcc += dt
			if repairAcc > 0.25 then
				repairAcc = 0
				useTool(true)
			end
		end
		if #pendingShots > 0 then
			remotes.Fire:FireServer({ shots = pendingShots })
			pendingShots = {}
		end
		if not mouseDown then
			ClientState.spread = math.max(0, ClientState.spread - dt * 0.02)
		end
		updateViewmodel(dt)
	end)
end

return WeaponController
