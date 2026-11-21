--!strict
-- Deployment and respawning for players and AI bots.
-- Deploy screen choices: faction (BLUE/RED), infantry class, spawn location
-- (HQ, an owned & uncontested control point, or a friendly mobile-spawn
-- vehicle) and optionally a vehicle from the motor pool.
-- Spawn protection: invulnerable for a few seconds (ends early when firing).

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Teams = game:GetService("Teams")

local AntiCheat = require(ReplicatedStorage.Shared.AntiCheat)
local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Net = require(ReplicatedStorage.Shared.Net)
local SoldierRegistry = require(script.Parent.SoldierRegistry)
local CharacterStyle = require(script.Parent.CharacterStyle)
local MatchService = require(script.Parent.MatchService)

local SpawnService = {}

local TEAM = Constants.TEAM
local SOLDIER = Constants.SOLDIER

-- hooks wired by Main (avoid circular requires)
SpawnService.vehicles = nil :: any -- VehicleService
SpawnService.onDeath = nil :: ((SoldierRegistry.Soldier) -> ())?
SpawnService.onSpawn = nil :: ((SoldierRegistry.Soldier) -> ())?

local soldiersFolder: Folder

local function teamObject(team: number): Team?
	return Teams:FindFirstChild(Constants.TEAM_OBJECT_NAME[team]) :: Team?
end

-- ---------------------------------------------------------------------------
-- Loadouts
-- ---------------------------------------------------------------------------
function SpawnService.giveLoadout(s: SoldierRegistry.Soldier)
	local role = Defs.Roles[s.role] or Defs.Roles.rifleman
	local list = role.loadout[s.team] or role.loadout[1]
	s.loadout = {}
	s.ammo = {}
	for slot = 1, 4 do
		local id = list[slot] or ""
		s.loadout[slot] = id
		local w = Defs.Weapons[id]
		if w then
			if w.kind == "hitscan" then
				s.ammo[id] = { mag = w.mag, reserve = w.reserve }
			elseif w.kind == "projectile" then
				s.ammo[id] = { mag = w.mag or 1, reserve = w.reserve or (w.count or 4) - 1 }
			elseif w.kind == "throw" then
				s.ammo[id] = { mag = w.count or 1, reserve = 0 }
			elseif w.kind == "tool" then
				s.ammo[id] = { mag = w.uses or 999, reserve = 0 }
			end
		end
	end
	s.equipped = 1
	s.lastShot = {}
end

function SpawnService.refill(s: SoldierRegistry.Soldier, fraction: number): boolean
	local changed = false
	for id, a in s.ammo do
		local w = Defs.Weapons[id]
		if w and (w.kind == "hitscan") then
			local cap = w.reserve
			if a.reserve < cap then
				a.reserve = math.min(cap, a.reserve + math.ceil(w.mag * fraction))
				changed = true
			end
		elseif w and (w.kind == "throw" or w.kind == "projectile") then
			local cap = if w.kind == "throw" then (w.count or 1) else (w.reserve or 3)
			if w.kind == "throw" and a.mag < cap then
				a.mag += 1
				changed = true
			elseif w.kind == "projectile" and a.reserve < cap then
				a.reserve += 1
				changed = true
			end
		end
	end
	return changed
end

-- ---------------------------------------------------------------------------
-- Spawn locations
-- ---------------------------------------------------------------------------
export type SpawnOption = { id: string, kind: string, label: string, x: number, z: number, available: boolean, reason: string? }

function SpawnService.options(team: number): { SpawnOption }
	local info = MapInfo.get()
	local out: { SpawnOption } = {}
	local hq
	for _, h in info.hqs do
		if h.team == team then
			hq = h
		end
	end
	if hq then
		table.insert(out, { id = "HQ", kind = "hq", label = hq.name, x = hq.x, z = hq.z, available = true })
	end
	local mode = MatchService.mode()
	for _, p in info.points do
		local pt = mode and mode:pointById(p.id)
		local owned = pt and pt.owner == team
		local contested = pt and pt.contested
		table.insert(out, {
			id = "P" .. p.id, kind = "point", label = p.id .. " - " .. p.name, x = p.x, z = p.z,
			available = owned == true and not contested,
			reason = if not owned then "Not held" elseif contested then "Contested" else nil,
		})
	end
	if SpawnService.vehicles then
		for _, v in SpawnService.vehicles.mobileSpawns(team) do
			table.insert(out, { id = "V" .. v.id, kind = "vehicle", label = v.name, x = v.x, z = v.z, available = v.available, reason = v.reason })
		end
	end
	return out
end

local function spawnCFrame(team: number, spawnId: string): CFrame?
	local info = MapInfo.get()
	if spawnId == "HQ" then
		local list = info.hqSpawns[tostring(team)]
		local sp = list[math.random(1, #list)]
		local y = MapInfo.heightAt(sp.x, sp.z) + 3.5
		return CFrame.new(sp.x + math.random() * 4 - 2, y, sp.z + math.random() * 4 - 2) * CFrame.Angles(0, sp.yaw, 0)
	end
	local pid = string.match(spawnId, "^P(%a)$")
	if pid then
		local mode = MatchService.mode()
		local pt = mode:pointById(pid)
		if not pt or pt.owner ~= team or pt.contested then
			return nil
		end
		local list = info.pointSpawns[pid]
		if not list or #list == 0 then
			return nil
		end
		local sp = list[math.random(1, #list)]
		return CFrame.new(sp.x, MapInfo.heightAt(sp.x, sp.z) + 3.5, sp.z) * CFrame.Angles(0, sp.yaw, 0)
	end
	return nil
end

-- ---------------------------------------------------------------------------
-- Characters
-- ---------------------------------------------------------------------------
local function setupCharacter(s: SoldierRegistry.Soldier, character: Model)
	local humanoid = character:WaitForChild("Humanoid") :: Humanoid
	local root = character:WaitForChild("HumanoidRootPart") :: BasePart
	s.model = character
	s.humanoid = humanoid
	s.root = root
	s.alive = true
	s.deployed = true
	s.stance = 0
	s.damagers = {}
	s.outOfBoundsSince = nil
	character:SetAttribute("SoldierId", s.id)
	character:SetAttribute("SoldierName", s.name)
	humanoid.MaxHealth = SOLDIER.MAX_HEALTH
	humanoid.Health = SOLDIER.MAX_HEALTH
	humanoid.WalkSpeed = SOLDIER.RUN_SPEED * ((Defs.Roles[s.role] or Defs.Roles.rifleman).speed or 1)
	humanoid.UseJumpPower = false
	humanoid.JumpHeight = 3.5
	humanoid.RequiresNeck = true
	for _, d in character:GetDescendants() do
		if d:IsA("BasePart") then
			d.CollisionGroup = "Soldiers"
		end
	end
	CharacterStyle.apply(character, s.team, s.role)
	SpawnService.giveLoadout(s)
	local first = Defs.Weapons[s.loadout[1]]
	CharacterStyle.holdWeapon(character, first and first.model)
	character:SetAttribute("Equipped", 1)
	character:SetAttribute("Stance", 0)
	-- spawn protection
	s.spawnProtUntil = os.clock() + SOLDIER.SPAWN_PROTECTION
	character:SetAttribute("Protected", true)
	local ff = Instance.new("ForceField")
	ff.Visible = true
	ff.Parent = character
	task.delay(SOLDIER.SPAWN_PROTECTION, function()
		if ff.Parent then
			ff:Destroy()
		end
		if character.Parent then
			character:SetAttribute("Protected", false)
		end
	end)
	humanoid.Died:Connect(function()
		SpawnService.handleDeath(s, character)
	end)
	if s.player then
		SoldierRegistry.publish(s)
	end
	if SpawnService.onSpawn then
		SpawnService.onSpawn(s)
	end
end

-- Ends spawn protection early (called when the soldier fires).
function SpawnService.dropProtection(s: SoldierRegistry.Soldier)
	if s.spawnProtUntil > os.clock() then
		s.spawnProtUntil = 0
		local c = s.model
		if c then
			c:SetAttribute("Protected", false)
			local ff = c:FindFirstChildOfClass("ForceField")
			if ff then
				ff:Destroy()
			end
		end
	end
end

function SpawnService.isProtected(s: SoldierRegistry.Soldier): boolean
	return s.spawnProtUntil > os.clock()
end

function SpawnService.handleDeath(s: SoldierRegistry.Soldier, character: Model)
	if not s.alive or s.model ~= character then
		return
	end
	s.alive = false
	s.respawnAt = os.clock() + SOLDIER.RESPAWN_DELAY
	if SpawnService.vehicles and s.vehicleId then
		SpawnService.vehicles.ejectSoldier(s, true)
	end
	if SpawnService.onDeath then
		SpawnService.onDeath(s)
	end
	-- leave the body for a while, then clean up
	task.delay(if s.isBot then 12 else 8, function()
		if character.Parent and not (s.alive and s.model == character) then
			character:Destroy()
		end
	end)
end

-- Bot body: an R15 rig built once from a plain HumanoidDescription (no avatar
-- assets) and cloned for every spawn, so bot respawns never yield.
local botTemplate: Model? = nil
local function botModel(s: SoldierRegistry.Soldier): Model?
	if not botTemplate then
		local d = Instance.new("HumanoidDescription")
		d.HeightScale = 1
		d.WidthScale = 1
		d.DepthScale = 1
		d.HeadScale = 1
		d.BodyTypeScale = 0
		d.ProportionScale = 0
		local ok, result = pcall(function()
			return Players:CreateHumanoidModelFromDescriptionAsync(d, Enum.HumanoidRigType.R15)
		end)
		if not ok or typeof(result) ~= "Instance" then
			warn("[SpawnService] could not build the bot rig: " .. tostring(result))
			return nil
		end
		local rig = result :: Model
		local hum = rig:FindFirstChildOfClass("Humanoid")
		if hum and not hum:FindFirstChildOfClass("Animator") then
			local a = Instance.new("Animator")
			a.Parent = hum
		end
		botTemplate = rig
	end
	local model = (botTemplate :: Model):Clone()
	model.Name = s.name
	return model
end

-- Spawn (or respawn) a soldier at a CFrame. Works for players and bots.
function SpawnService.spawnSoldier(s: SoldierRegistry.Soldier, cf: CFrame): boolean
	if s.player then
		local player = s.player
		player.Team = teamObject(s.team)
		local ok, err = pcall(function()
			player:LoadCharacter()
		end)
		if not ok then
			warn("[Spawn] LoadCharacter failed: " .. tostring(err))
			return false
		end
		local character = player.Character
		if not character then
			return false
		end
		setupCharacter(s, character)
		character:PivotTo(cf)
	else
		if s.model and s.model.Parent then
			s.model:Destroy()
		end
		local model = botModel(s)
		if not model then
			return false
		end
		model:PivotTo(cf)
		model.Parent = soldiersFolder
		setupCharacter(s, model)
		local root = model:FindFirstChild("HumanoidRootPart") :: BasePart
		pcall(function()
			root:SetNetworkOwner(nil)
		end)
	end
	return true
end

-- Deploy request (validated).
-- Human players may not stack one army: joining a team is refused while it
-- already has two or more players more than the other one.
function SpawnService.teamOpen(team: number, s: SoldierRegistry.Soldier?): boolean
	local count = { [TEAM.BLUE] = 0, [TEAM.RED] = 0 }
	for _, p in Players:GetPlayers() do
		local ps = SoldierRegistry.forPlayer(p)
		if ps and ps ~= s and count[ps.team] then
			count[ps.team] += 1
		end
	end
	return AntiCheat.teamOpen(count[team], count[Constants.enemyOf(team)])
end

function SpawnService.deploy(s: SoldierRegistry.Soldier, team: number, role: string, spawnId: string, vehicleKind: string?): (boolean, string?)
	if team ~= TEAM.BLUE and team ~= TEAM.RED then
		return false, "Invalid faction"
	end
	if not Defs.Roles[role] then
		return false, "Invalid class"
	end
	if s.alive then
		return false, "Already deployed"
	end
	if s.player and team ~= s.team and not SpawnService.teamOpen(team, s) then
		return false, "Teams are unbalanced - join the other army"
	end
	if os.clock() < s.respawnAt then
		return false, string.format("Redeploy in %d s", math.ceil(s.respawnAt - os.clock()))
	end
	if MatchService.mode() and MatchService.mode().state ~= "live" then
		return false, "Match is over"
	end
	s.team = team
	s.role = role
	-- vehicle deployment: spawn straight into the driver's seat
	if vehicleKind and vehicleKind ~= "" and SpawnService.vehicles then
		local v = SpawnService.vehicles.claimForDeploy(team, vehicleKind)
		if not v then
			return false, "Vehicle not available"
		end
		local seatCF = SpawnService.vehicles.seatCFrame(v, 1)
		if not SpawnService.spawnSoldier(s, seatCF + Vector3.new(0, 3, 0)) then
			return false, "Spawn failed"
		end
		SpawnService.vehicles.enter(s, v, 1)
		return true, nil
	end
	local vid = string.match(spawnId, "^V(%d+)$")
	if vid and SpawnService.vehicles then
		local v = SpawnService.vehicles.get(tonumber(vid))
		if not v or v.team ~= team or not v.alive or not v.def.mobileSpawn then
			return false, "Vehicle spawn unavailable"
		end
		local seat = SpawnService.vehicles.freeSeat(v, 2)
		if not seat then
			return false, "Vehicle full"
		end
		if not SpawnService.spawnSoldier(s, SpawnService.vehicles.seatCFrame(v, seat) + Vector3.new(0, 3, 0)) then
			return false, "Spawn failed"
		end
		SpawnService.vehicles.enter(s, v, seat)
		return true, nil
	end
	local cf = spawnCFrame(team, spawnId)
	if not cf then
		return false, "Spawn point unavailable"
	end
	if not SpawnService.spawnSoldier(s, cf) then
		return false, "Spawn failed"
	end
	return true, nil
end

-- ---------------------------------------------------------------------------
-- Init
-- ---------------------------------------------------------------------------
function SpawnService.init()
	soldiersFolder = Instance.new("Folder")
	soldiersFolder.Name = "Soldiers"
	soldiersFolder.Parent = workspace

	local deployLimiter = Net.rateLimiter(3)
	local optionsLimiter = Net.rateLimiter(4)
	Net.func("GetDeployOptions").OnServerInvoke = function(player: Player, team: any): any
		if not optionsLimiter(player) then
			return nil
		end
		local s = SoldierRegistry.forPlayer(player)
		local t = if team == TEAM.BLUE or team == TEAM.RED then team else (if s and s.team ~= 0 then s.team else TEAM.BLUE)
		local vehicles = if SpawnService.vehicles then SpawnService.vehicles.deployVehicles(t) else {}
		return { spawns = SpawnService.options(t), vehicles = vehicles, respawnIn = if s then math.max(0, s.respawnAt - os.clock()) else 0 }
	end
	Net.event("Deploy").OnServerEvent:Connect(function(player: Player, req: any)
		if not deployLimiter(player) or type(req) ~= "table" then
			return
		end
		local s = SoldierRegistry.forPlayer(player)
		if not s then
			return
		end
		local team = tonumber(req.team) or 0
		local role = if type(req.role) == "string" then req.role else "rifleman"
		local spawnId = if type(req.spawn) == "string" then req.spawn else "HQ"
		local vehicle = if type(req.vehicle) == "string" then req.vehicle else nil
		local ok, reason = SpawnService.deploy(s, team, role, spawnId, vehicle)
		Net.event("MatchEvent"):FireClient(player, { kind = "deployResult", ok = ok, reason = reason })
	end)

	Players.PlayerAdded:Connect(function(player)
		local s = SoldierRegistry.create(player.DisplayName, 0, "rifleman", player)
		s.respawnAt = 0
		SoldierRegistry.publish(s)
		player.Team = Teams:FindFirstChild("Deploying") :: Team?
	end)
	Players.PlayerRemoving:Connect(function(player)
		local s = SoldierRegistry.forPlayer(player)
		if s then
			if SpawnService.vehicles and s.vehicleId then
				SpawnService.vehicles.ejectSoldier(s, false)
			end
			SoldierRegistry.remove(s)
		end
	end)
	for _, player in Players:GetPlayers() do
		if not SoldierRegistry.forPlayer(player) then
			local s = SoldierRegistry.create(player.DisplayName, 0, "rifleman", player)
			SoldierRegistry.publish(s)
		end
	end

	-- out of bounds: warn, then take damage
	local acc = 0
	RunService.Heartbeat:Connect(function(dt)
		acc += dt
		if acc < 0.5 then
			return
		end
		acc = 0
		local now = os.clock()
		for _, s in SoldierRegistry.all() do
			local root = s.root
			if s.alive and root and root.Parent then
				local pos = root.Position
				if not MapInfo.isPlayable(pos.X, pos.Z) then
					s.outOfBoundsSince = s.outOfBoundsSince or now
					if s.model then
						s.model:SetAttribute("OutOfBounds", math.max(0, SOLDIER.OUT_OF_BOUNDS_GRACE - (now - (s.outOfBoundsSince :: number))))
					end
					if now - (s.outOfBoundsSince :: number) > SOLDIER.OUT_OF_BOUNDS_GRACE and s.humanoid then
						s.humanoid:TakeDamage(15)
					end
				elseif s.outOfBoundsSince then
					s.outOfBoundsSince = nil
					if s.model then
						s.model:SetAttribute("OutOfBounds", nil)
					end
				end
			end
		end
	end)
end

function SpawnService.killAll()
	for _, s in SoldierRegistry.all() do
		if s.alive and s.humanoid then
			s.alive = false
			s.respawnAt = 0
			if s.model then
				s.model:Destroy()
			end
			s.model = nil
			s.root = nil
			s.humanoid = nil
			s.vehicleId = nil
			s.seatIndex = nil
		end
		s.respawnAt = 0
	end
	for _, p in Players:GetPlayers() do
		p.Team = Teams:FindFirstChild("Deploying") :: Team?
	end
end

return SpawnService
