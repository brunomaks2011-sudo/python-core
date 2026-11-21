--!strict
-- Behaviour of one AI soldier: perception, combat, cover, roles, orders.
-- Thinks at ~5 Hz (staggered); aims and fires every frame while engaging.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local SoldierRegistry = require(script.Parent.Parent.Game.SoldierRegistry)
local CombatService = require(script.Parent.Parent.Game.CombatService)
local SpawnService = require(script.Parent.Parent.Game.SpawnService)
local Navigator = require(script.Parent.Navigator)

type Soldier = SoldierRegistry.Soldier

local BotBrain = {}
BotBrain.__index = BotBrain

-- default R15 animations (public Roblox assets used by the stock Animate script)
local ANIMS = {
	idle = "rbxassetid://507766666",
	walk = "rbxassetid://507777826",
	run = "rbxassetid://507767714",
	jump = "rbxassetid://507765000",
	fall = "rbxassetid://507767968",
	sit = "rbxassetid://2506281703",
}

BotBrain.difficulty = 1 -- 0 easy, 1 normal, 2 hard
local ACCURACY = { [0] = 0.03, [1] = 0.017, [2] = 0.009 }
local REACTION = { [0] = 0.9, [1] = 0.55, [2] = 0.3 }

export type Brain = {
	s: Soldier,
	nav: any,
	target: Soldier?,
	targetVehicle: any,
	targetSeen: number,
	lastKnown: Vector3?,
	reactionUntil: number,
	burstLeft: number,
	nextBurst: number,
	coverUntil: number,
	coverPos: Vector3?,
	threatPos: Vector3?,
	threatTime: number,
	orderPos: Vector3?,
	orderKind: string,
	orderPoint: string?,
	grenadeCooldown: number,
	retreatUntil: number,
	thinkOffset: number,
	tracks: { [string]: AnimationTrack },
	current: string?,
	reloadUntil: number,
	healTarget: Soldier?,
	vehicleRole: string?,
}

function BotBrain.new(s: Soldier)
	local self = setmetatable({
		s = s,
		nav = nil,
		target = nil,
		targetVehicle = nil,
		targetSeen = 0,
		lastKnown = nil,
		reactionUntil = 0,
		burstLeft = 0,
		nextBurst = 0,
		coverUntil = 0,
		coverPos = nil,
		threatPos = nil,
		threatTime = 0,
		orderPos = nil,
		orderKind = "capture",
		orderPoint = nil,
		grenadeCooldown = 0,
		retreatUntil = 0,
		thinkOffset = math.random() * 0.2,
		tracks = {},
		current = nil,
		reloadUntil = 0,
		healTarget = nil,
		vehicleRole = nil,
	}, BotBrain)
	s.brain = self
	return self
end

-- ---------------------------------------------------------------------------
-- Animation
-- ---------------------------------------------------------------------------
function BotBrain.setupBody(self: any)
	local s = self.s
	local hum = s.humanoid
	if not hum or not s.root then
		return
	end
	self.nav = Navigator.new(hum, s.root)
	self.tracks = {}
	self.current = nil
	local animator = hum:FindFirstChildOfClass("Animator")
	if animator then
		for name, id in ANIMS do
			local a = Instance.new("Animation")
			a.AnimationId = id :: string
			local ok, track = pcall(function()
				return animator:LoadAnimation(a)
			end)
			if ok and track then
				track.Priority = if name == "sit" then Enum.AnimationPriority.Action else Enum.AnimationPriority.Core
				track.Looped = name ~= "jump"
				self.tracks[name] = track
			end
		end
	end
	hum.Running:Connect(function(speed)
		self:animate(if speed < 0.6 then "idle" elseif speed < 13 then "walk" else "run", speed)
	end)
	hum.StateChanged:Connect(function(_, new)
		if new == Enum.HumanoidStateType.Jumping then
			self:animate("jump", 0)
		elseif new == Enum.HumanoidStateType.Freefall then
			self:animate("fall", 0)
		elseif new == Enum.HumanoidStateType.Seated then
			self:animate("sit", 0)
		elseif new == Enum.HumanoidStateType.Landed or new == Enum.HumanoidStateType.Running then
			self:animate("idle", 0)
		end
	end)
	self:animate("idle", 0)
end

function BotBrain.animate(self: any, name: string, speed: number)
	local track = self.tracks[name]
	if not track then
		return
	end
	if self.current ~= name then
		local old = self.current and self.tracks[self.current]
		if old then
			old:Stop(0.2)
		end
		track:Play(0.2)
		self.current = name
	end
	if name == "walk" then
		track:AdjustSpeed(math.clamp(speed / 12, 0.4, 1.4))
	elseif name == "run" then
		track:AdjustSpeed(math.clamp(speed / 18, 0.7, 1.4))
	end
end

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude
rayParams.IgnoreWater = true

local function headOf(s: Soldier): Vector3?
	local m = s.model
	if not m then
		return nil
	end
	local h = m:FindFirstChild("Head") :: BasePart?
	if h then
		return h.Position
	end
	return if s.root then s.root.Position + Vector3.new(0, 1.6, 0) else nil
end

local function torsoOf(s: Soldier): Vector3?
	local m = s.model
	if not m then
		return nil
	end
	local t = m:FindFirstChild("UpperTorso") :: BasePart?
	return if t then t.Position else (if s.root then s.root.Position else nil)
end

function BotBrain.canSee(self: any, from: Vector3, to: Vector3, targetModel: Instance?): boolean
	rayParams.FilterDescendantsInstances = { self.s.model :: Instance }
	local d = to - from
	local hit = workspace:Raycast(from, d, rayParams)
	if not hit then
		return true
	end
	if targetModel and hit.Instance:IsDescendantOf(targetModel) then
		return true
	end
	return (hit.Position - to).Magnitude < 2
end

function BotBrain.onDamaged(self: any, attacker: Soldier?, fromPos: Vector3?)
	self.threatTime = os.clock()
	local p = fromPos or (attacker and attacker.root and attacker.root.Position)
	if p then
		self.threatPos = p
		if not self.target and attacker and attacker.alive then
			self.target = attacker
			self.lastKnown = p
			self.reactionUntil = os.clock() + REACTION[BotBrain.difficulty] * 0.6
		end
	end
end

function BotBrain.setOrder(self: any, kind: string, pos: Vector3, pointId: string?)
	self.orderKind = kind
	self.orderPos = pos
	self.orderPoint = pointId
end

local function setStance(s: Soldier, stance: number)
	if s.stance == stance then
		return
	end
	s.stance = stance
	if s.model then
		s.model:SetAttribute("Stance", stance)
	end
	local hum = s.humanoid
	if hum then
		local base = (Defs.Roles[s.role] or Defs.Roles.rifleman).speed or 1
		hum.WalkSpeed = (if stance == 0 then Constants.SOLDIER.RUN_SPEED elseif stance == 1 then Constants.SOLDIER.CROUCH_SPEED else Constants.SOLDIER.PRONE_SPEED) * base
	end
end
BotBrain.setStance = setStance

-- ---------------------------------------------------------------------------
-- Perception
-- ---------------------------------------------------------------------------
function BotBrain.perceive(self: any)
	local s = self.s
	local head = headOf(s)
	if not head or not s.root then
		return
	end
	local range = if s.role == "recon" then 1500 else 900
	local fwd = s.root.CFrame.LookVector
	local alert = os.clock() - self.threatTime < 5
	local best, bestScore = nil, math.huge
	local checks = 0
	local candidates = {}
	for _, e in SoldierRegistry.alive(Constants.enemyOf(s.team)) do
		local er = e.root
		if er then
			local d = (er.Position - s.root.Position).Magnitude
			if d < range then
				table.insert(candidates, { e = e, d = d })
			end
		end
	end
	table.sort(candidates, function(a, b)
		return a.d < b.d
	end)
	for _, c in candidates do
		if checks >= 4 then
			break
		end
		local e: Soldier = c.e
		local tp = torsoOf(e)
		if tp then
			local dir = (tp - head)
			local facing = dir.Unit:Dot(fwd)
			if alert or facing > -0.2 or c.d < 40 then
				checks += 1
				local visible = self:canSee(head, tp, if e.vehicleId then nil else e.model)
				if visible then
					-- prefer close threats and whoever is shooting at us
					local score = c.d * (if self.threatPos and (tp - self.threatPos).Magnitude < 30 then 0.5 else 1)
					if score < bestScore then
						best, bestScore = e, score
					end
				end
			end
		end
	end
	if best then
		if self.target ~= best then
			self.reactionUntil = os.clock() + REACTION[BotBrain.difficulty] * (0.7 + math.random() * 0.6)
		end
		self.target = best
		self.targetSeen = os.clock()
		self.lastKnown = torsoOf(best)
	elseif self.target and (os.clock() - self.targetSeen > 4 or not self.target.alive) then
		self.target = nil
	end
end

-- ---------------------------------------------------------------------------
-- Cover
-- ---------------------------------------------------------------------------
function BotBrain.findCover(self: any, threat: Vector3): Vector3?
	local s = self.s
	local pos = (s.root :: BasePart).Position
	local bestPos, bestD = nil, math.huge
	local toObj = if self.orderPos then (self.orderPos - pos) * Vector3.new(1, 0, 1) else Vector3.zero
	for k = 1, 10 do
		local a = math.random() * math.pi * 2
		local r = 6 + math.random() * 22
		local c = pos + Vector3.new(math.cos(a) * r, 0, math.sin(a) * r)
		local y = MapInfo.heightAt(c.X, c.Z)
		local probe = Vector3.new(c.X, y + 2.8, c.Z)
		rayParams.FilterDescendantsInstances = { s.model :: Instance }
		local hit = workspace:Raycast(threat, probe - threat, rayParams)
		if hit and (hit.Position - probe).Magnitude < 9 and (hit.Position - probe).Magnitude > 1.2 then
			local d = r - (if toObj.Magnitude > 1 then (c - pos):Dot(toObj.Unit) * 0.3 else 0)
			if d < bestD then
				bestD = d
				bestPos = Vector3.new(c.X, y, c.Z)
			end
		end
		local _ = k
	end
	return bestPos
end

-- ---------------------------------------------------------------------------
-- Think (~5 Hz)
-- ---------------------------------------------------------------------------
function BotBrain.think(self: any)
	local s = self.s
	if not s.alive or not s.root or not s.humanoid or not self.nav then
		return
	end
	if s.vehicleId then
		return -- vehicle behaviour is driven by the AIDirector / VehicleDriver
	end
	local now = os.clock()
	self:perceive()
	local hum = s.humanoid :: Humanoid
	local health = hum.Health / hum.MaxHealth

	-- medic: heal wounded teammates when nothing is shooting at us
	if s.role == "medic" and not self.target then
		local best, bd = nil, 50
		for _, f in SoldierRegistry.alive(s.team) do
			if f ~= s and f.humanoid and f.root and not f.vehicleId and f.humanoid.Health < f.humanoid.MaxHealth * 0.65 then
				local d = (f.root.Position - s.root.Position).Magnitude
				if d < bd then
					best, bd = f, d
				end
			end
		end
		if best and best.root and best.humanoid then
			if bd < 6 and now > s.toolCooldown then
				s.toolCooldown = now + 1
				best.humanoid.Health = math.min(best.humanoid.MaxHealth, best.humanoid.Health + 40)
				SoldierRegistry.addScore(s, "heals", 1, 20)
			else
				self.nav:moveTo(best.root.Position, 4)
				self.nav:update()
				return
			end
		end
	end
	-- support: top up teammates' ammunition now and then
	if s.role == "support" and now > s.toolCooldown and not self.target then
		s.toolCooldown = now + 15
		for _, f in SoldierRegistry.alive(s.team) do
			if f.root and (f.root.Position - s.root.Position).Magnitude < 25 then
				SpawnService.refill(f, 1)
			end
		end
	end

	-- retreat when badly hurt and under fire
	if health < 0.3 and self.target and now - self.threatTime < 3 and self.retreatUntil < now then
		self.retreatUntil = now + 6
		local away = (s.root.Position - (self.lastKnown or s.root.Position))
		away = Vector3.new(away.X, 0, away.Z)
		if away.Magnitude < 1 then
			away = Vector3.new(math.random() - 0.5, 0, math.random() - 0.5)
		end
		self.nav:moveTo(s.root.Position + away.Unit * 50, 6)
		setStance(s, 0)
	end
	if self.retreatUntil > now then
		self.nav:update()
		return
	end

	if self.target and self.target.alive then
		-- in combat: take cover when hit, otherwise hold and shoot
		local threat = self.lastKnown or (self.target.root and self.target.root.Position)
		if threat and now - self.threatTime < 2.5 and self.coverUntil < now and health < 0.85 then
			local cover = self:findCover(threat)
			if cover then
				self.coverPos = cover
				self.coverUntil = now + 5 + math.random() * 4
				setStance(s, 0)
				self.nav:moveTo(cover, 2.5)
			end
		end
		if self.coverPos and self.coverUntil > now then
			if self.nav:arrived() then
				setStance(s, 1)
			end
			self.nav:update()
		else
			self.coverPos = nil
			-- advance slowly toward the objective while fighting at range, stop when close
			local d = (threat - s.root.Position).Magnitude
			if d < 120 or not self.orderPos then
				self.nav:stop()
				setStance(s, if d > 60 then 1 else 0)
			else
				setStance(s, 0)
				self.nav:moveTo(self.orderPos, 10)
				self.nav:update()
			end
		end
		-- grenades at enemies behind cover
		if now > self.grenadeCooldown and s.ammo.grenade and s.ammo.grenade.mag > 0 and threat then
			local d = (threat - s.root.Position).Magnitude
			if d > 14 and d < 45 and now - self.targetSeen > 1.5 then
				self.grenadeCooldown = now + 15
				s.ammo.grenade.mag -= 1
				local head = headOf(s) :: Vector3
				local flat = Vector3.new(threat.X - head.X, 0, threat.Z - head.Z)
				local w = Defs.Weapons.grenade
				local speed = math.clamp(math.sqrt(d * workspace.Gravity) * 0.75, 18, w.speed)
				local vel = flat.Unit * speed * 0.8 + Vector3.new(0, speed * 0.6, 0)
				CombatService.launch(head + flat.Unit * 1.5, vel, w, s, { s.model :: Instance })
			end
		end
		return
	end

	-- no enemy: follow orders
	setStance(s, 0)
	if self.orderPos then
		self.nav:moveTo(self.orderPos, if self.orderKind == "defend" then 8 else 6)
		self.nav:update()
		if self.nav:arrived() and self.orderKind == "defend" then
			setStance(s, 1)
		end
	end
end

-- ---------------------------------------------------------------------------
-- Per-frame: face the target and fire bursts
-- ---------------------------------------------------------------------------
function BotBrain.combatStep(self: any, dt: number)
	local s = self.s
	local target = self.target
	if not s.alive or not target or not target.alive or s.vehicleId or not s.root or not s.humanoid then
		if s.humanoid and not s.humanoid.AutoRotate and not s.vehicleId then
			s.humanoid.AutoRotate = true
		end
		return
	end
	local now = os.clock()
	local tp = torsoOf(target)
	local head = headOf(s)
	if not tp or not head then
		return
	end
	-- face the target (keeps moving with AutoRotate off)
	local hum = s.humanoid :: Humanoid
	local root = s.root :: BasePart
	hum.AutoRotate = false
	local flat = Vector3.new(tp.X - root.Position.X, 0, tp.Z - root.Position.Z)
	if flat.Magnitude > 0.5 then
		local want = CFrame.lookAt(root.Position, root.Position + flat)
		root.CFrame = root.CFrame:Lerp(want, math.min(1, dt * 8))
	end
	if now < self.reactionUntil or now - self.targetSeen > 1.2 then
		return
	end
	-- weapon: rocket launcher against vehicles for engineers
	if target.vehicleId and s.role == "engineer" and s.ammo.rpg and s.ammo.rpg.mag > 0 and now > (s.lastShot.rpg or 0) + 4 then
		local d = (tp - head).Magnitude
		if d < 900 then
			s.lastShot.rpg = now
			s.ammo.rpg.mag -= 1
			local w = Defs.Weapons.rpg
			local aim = (tp - head).Unit
			CombatService.launch(head + aim * 2.5, aim * w.speed, w, s, { s.model :: Instance })
			task.delay(4, function()
				if s.ammo.rpg and s.ammo.rpg.reserve > 0 then
					s.ammo.rpg.reserve -= 1
					s.ammo.rpg.mag = 1
				end
			end)
		end
		return
	end
	local weaponId = s.loadout[1]
	local w = Defs.Weapons[weaponId]
	if not w then
		return
	end
	local ammo = s.ammo[weaponId]
	if ammo and ammo.mag <= 0 then
		if self.reloadUntil == 0 then
			self.reloadUntil = now + (w.reload or 2.2)
		elseif now >= self.reloadUntil then
			self.reloadUntil = 0
			local take = math.min(w.mag, math.max(ammo.reserve, w.mag)) -- bots carry plenty
			ammo.mag = take
			ammo.reserve = math.max(0, ammo.reserve - take)
		end
		return
	end
	if self.burstLeft <= 0 then
		if now < self.nextBurst then
			return
		end
		self.burstLeft = if w.auto then math.random(3, 7) else 1
	end
	local d = (tp - head).Magnitude
	local moving = root.AssemblyLinearVelocity.Magnitude > 4
	local spread = ACCURACY[BotBrain.difficulty] * (1 + d / 400) * (if moving then 1.6 else 1) * (if target.stance >= 1 then 0.85 else 1)
	-- aim a little ahead of moving targets
	local tv = if target.root then target.root.AssemblyLinearVelocity else Vector3.zero
	local aimPoint = tp + tv * (d / 900) + Vector3.new(0, -0.3 + math.random() * 0.9, 0)
	local muzzle = head + root.CFrame.LookVector * 1.2 + root.CFrame.RightVector * 0.5 - Vector3.new(0, 0.3, 0)
	if CombatService.serverFire(s, weaponId, muzzle, aimPoint - muzzle, spread) then
		self.burstLeft -= 1
		if self.burstLeft <= 0 then
			self.nextBurst = now + 0.25 + math.random() * 0.6
		end
	end
end

return BotBrain
