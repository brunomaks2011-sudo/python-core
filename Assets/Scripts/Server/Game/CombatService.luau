--!strict
-- Server-authoritative combat.
--  * Hitscan: clients raycast locally for instant feedback and report shots;
--    the server validates fire rate, ammo, muzzle position, range and line of
--    sight (re-raycast) before applying damage.
--  * Projectiles (tank shells, rockets, RPGs, grenades, C4, artillery) are
--    simulated on the server with gravity and raycast stepping.
--  * Explosions damage soldiers (with cover), vehicles and destructible structures.
--  * Kill / assist credit, kill feed, hit markers, class tools.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local AntiCheat = require(ReplicatedStorage.Shared.AntiCheat)
local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local Hits = require(ReplicatedStorage.Shared.Hits)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)
local SoldierRegistry = require(script.Parent.SoldierRegistry)
local SpawnService = require(script.Parent.SpawnService)
local DestructionService = require(script.Parent.DestructionService)
local EffectsBus = require(script.Parent.EffectsBus)
local CharacterStyle = require(script.Parent.CharacterStyle)

type Soldier = SoldierRegistry.Soldier

local CombatService = {}

-- hooks wired by Main
CombatService.vehicleDamage = nil :: ((vehicleId: number, amount: number, attacker: Soldier?, kind: string, weaponName: string) -> ())?
CombatService.vehicleAt = nil :: ((part: BasePart) -> any)?
CombatService.vehiclesNear = nil :: ((pos: Vector3, radius: number) -> { any })?
CombatService.vehicleRepair = nil :: ((s: Soldier, part: BasePart?, dt: number) -> boolean)?

local matchEvent: RemoteEvent
local hitmarker: RemoteEvent
local damageTaken: RemoteEvent
local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude
-- head -> muzzle line of sight (a shot may not start on the far side of a wall)
local losParams = RaycastParams.new()
losParams.FilterType = Enum.RaycastFilterType.Exclude

-- Fire validation: shots refill like a token bucket at the weapon's rate of
-- fire and at most BURST_TOKENS can be banked, so neither a stream nor a burst
-- after idling beats the real rate of fire; a packet is read up to
-- MAX_SHOTS_PER_PACKET entries.
local BURST_TOKENS = 3
local MAX_SHOTS_PER_PACKET = 16
local MUZZLE_REACH = 10 -- studs between the server's head position and the shot origin
local fireTokens: { [number]: { [string]: number } } = {}
rayParams.IgnoreWater = true

local GRAV = function(): number
	return workspace.Gravity
end

-- ---------------------------------------------------------------------------
-- Damage & kills
-- ---------------------------------------------------------------------------
local function headPosition(s: Soldier): Vector3?
	local m = s.model
	if not m then
		return nil
	end
	local head = m:FindFirstChild("Head") :: BasePart?
	return if head then head.Position elseif s.root then s.root.Position + Vector3.new(0, 1.5, 0) else nil
end
CombatService.headPosition = headPosition

function CombatService.creditKill(victim: Soldier, killer: Soldier?, weaponName: string, headshot: boolean)
	victim.stats.deaths += 1
	SoldierRegistry.publish(victim)
	local now = os.clock()
	if killer and killer ~= victim and killer.team ~= victim.team then
		SoldierRegistry.addScore(killer, "kills", 1, if headshot then 125 else 100)
	end
	for id, rec in victim.damagers do
		if killer and id == killer.id then
			continue
		end
		local a = SoldierRegistry.get(id)
		if a and a.team ~= victim.team and now - rec.t < 15 and rec.dmg >= 25 then
			SoldierRegistry.addScore(a, "assists", 1, 50)
		end
	end
	matchEvent:FireAllClients({
		kind = "kill", killer = killer and killer.name, killerTeam = killer and killer.team, killerId = killer and killer.id,
		victim = victim.name, victimTeam = victim.team, victimId = victim.id, weapon = weaponName, headshot = headshot,
	})
end

-- Apply damage to a soldier. Returns true if this killed them.
function CombatService.damageSoldier(victim: Soldier, amount: number, attacker: Soldier?, weaponName: string, hitPart: string?, fromPos: Vector3?): boolean
	if not victim.alive or not victim.humanoid then
		return false
	end
	if SpawnService.isProtected(victim) then
		return false
	end
	if attacker and attacker ~= victim and attacker.team == victim.team then
		return false -- no friendly fire
	end
	local hum = victim.humanoid :: Humanoid
	if hum.Health <= 0 then
		return false
	end
	-- prone/crouched soldiers behind cover take slightly less from explosions
	local before = hum.Health
	hum:TakeDamage(amount)
	local dealt = before - math.max(0, hum.Health)
	victim.lastHurt = os.clock()
	if attacker and attacker ~= victim then
		local rec = victim.damagers[attacker.id]
		if not rec then
			rec = { dmg = 0, t = 0 }
			victim.damagers[attacker.id] = rec
		end
		rec.dmg += dealt
		rec.t = os.clock()
		attacker.stats.damage += dealt
		if attacker.player then
			hitmarker:FireClient(attacker.player, { kill = hum.Health <= 0, head = hitPart == "Head" })
		end
	end
	if victim.player then
		damageTaken:FireClient(victim.player, { amount = dealt, from = fromPos })
	end
	if hum.Health <= 0 then
		CombatService.creditKill(victim, attacker, weaponName, hitPart == "Head")
		return true
	end
	return false
end

-- ---------------------------------------------------------------------------
-- Explosions
-- ---------------------------------------------------------------------------
function CombatService.explode(pos: Vector3, radius: number, damage: number, attacker: Soldier?, weaponName: string, opts: { [string]: any }?)
	local o: { [string]: any } = opts or {}
	EffectsBus.push({ k = "explosion", p = pos, r = radius, big = radius > 18 })
	-- soldiers (cover reduces damage)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.IgnoreWater = true
	for _, s in SoldierRegistry.all() do
		local root = s.root
		if s.alive and root and root.Parent then
			local d = (root.Position - pos).Magnitude
			if d < radius then
				local falloff = (1 - d / radius) ^ 1.2
				local dir = root.Position - pos
				params.FilterDescendantsInstances = { s.model :: Instance }
				local hit = workspace:Raycast(pos, dir, params)
				local cover = if hit and (hit.Position - pos).Magnitude < d - 1.5 then 0.3 else 1
				if s.vehicleId then
					cover *= 0.15 -- crews are protected by their vehicle's armour
				end
				CombatService.damageSoldier(s, damage * falloff * cover, attacker, weaponName, nil, pos)
				-- knock back
				if s.humanoid and s.humanoid.Health > 0 and d < radius * 0.5 and not s.vehicleId then
					root.AssemblyLinearVelocity += (dir.Unit + Vector3.new(0, 0.6, 0)) * (40 * (1 - d / radius))
				end
			end
		end
	end
	-- vehicles
	if CombatService.vehiclesNear and CombatService.vehicleDamage then
		for _, v in CombatService.vehiclesNear(pos, radius + 12) do
			local d = math.max(0, (v.root.Position - pos).Magnitude - v.def.size.Magnitude * 0.3)
			if d < radius then
				local vdmg = (o.vehicleDamage or damage * 0.6) * (1 - d / radius) ^ 1.1
				CombatService.vehicleDamage(v.id, vdmg, attacker, "blast", weaponName)
			end
		end
	end
	-- structures
	DestructionService.blast(pos, o.structRadius or radius * 0.7, o.structDmg or damage * 3)
end

DestructionService.onExplode = function(pos, radius, damage, source)
	CombatService.explode(pos, radius, damage, nil, source, { structDmg = damage * 2, structRadius = radius * 0.5 })
end

-- ---------------------------------------------------------------------------
-- Projectiles
-- ---------------------------------------------------------------------------
export type Projectile = {
	pos: Vector3,
	vel: Vector3,
	gravity: number,
	owner: Soldier?,
	weapon: { [string]: any },
	life: number,
	kind: string,
	ignore: { Instance },
	fuse: number?,
	stuck: boolean?,
	id: number,
	vehicleId: number?,
}
local projectiles: { Projectile } = {}
local nextProjectile = 0
local charges: { [number]: { Projectile } } = {} -- C4 per soldier

function CombatService.launch(origin: Vector3, velocity: Vector3, weapon: { [string]: any }, owner: Soldier?, ignore: { Instance }?, vehicleId: number?)
	nextProjectile += 1
	local p: Projectile = {
		pos = origin, vel = velocity, gravity = GRAV() * (weapon.gravityScale or 1), owner = owner, weapon = weapon,
		life = weapon.fuse or 14, kind = weapon.projectile or weapon.kind or "shell", ignore = ignore or {}, fuse = weapon.fuse,
		stuck = false, id = nextProjectile, vehicleId = vehicleId,
	}
	table.insert(projectiles, p)
	EffectsBus.push({ k = "proj", id = p.id, o = origin, v = velocity, g = p.gravity, t = p.kind, w = weapon.name })
	if weapon.remote and owner then
		local list = charges[owner.id]
		if not list then
			list = {}
			charges[owner.id] = list
		end
		table.insert(list, p)
		p.life = 300
	end
	return p
end

local function detonate(p: Projectile, at: Vector3)
	local w = p.weapon
	CombatService.explode(at, w.radius or 12, w.damage or 100, p.owner, w.name or "Explosion", {
		vehicleDamage = w.vehicleDamage, structDmg = w.structDmg, structRadius = w.structRadius,
	})
	EffectsBus.push({ k = "projEnd", id = p.id })
end

local function stepProjectiles(dt: number)
	if #projectiles == 0 then
		return
	end
	local keep = {}
	for _, p in projectiles do
		p.life -= dt
		if p.stuck then
			if p.fuse and p.life <= 0 then
				detonate(p, p.pos)
			elseif p.life > 0 then
				table.insert(keep, p)
			end
			continue
		end
		local newVel = p.vel - Vector3.new(0, p.gravity * dt, 0)
		local step = (p.vel + newVel) * 0.5 * dt
		rayParams.FilterDescendantsInstances = p.ignore
		local hit = workspace:Raycast(p.pos, step, rayParams)
		if hit then
			if p.weapon.kind == "throw" then
				-- grenades bounce / C4 sticks
				if p.weapon.remote then
					p.pos = hit.Position + hit.Normal * 0.3
					p.stuck = true
					EffectsBus.push({ k = "projStick", id = p.id, p = p.pos })
					table.insert(keep, p)
				else
					local n = hit.Normal
					local reflected = newVel - 2 * newVel:Dot(n) * n
					p.vel = reflected * 0.35
					p.pos = hit.Position + n * 0.3
					if p.vel.Magnitude < 3 then
						p.stuck = true
						EffectsBus.push({ k = "projStick", id = p.id, p = p.pos })
					end
					if p.life <= 0 then
						detonate(p, p.pos)
					else
						table.insert(keep, p)
					end
				end
				continue
			end
			-- direct hits on soldiers / vehicles do extra damage
			local info = Hits.classify(hit.Instance)
			if info.kind == "vehicle" and CombatService.vehicleDamage and info.vehicleId and info.vehicleId ~= p.vehicleId then
				CombatService.vehicleDamage(info.vehicleId, (p.weapon.vehicleDamage or 200) * 0.6, p.owner, "direct", p.weapon.name or "Shell")
			elseif info.kind == "soldier" and info.soldierId then
				local victim = SoldierRegistry.get(info.soldierId)
				if victim then
					CombatService.damageSoldier(victim, (p.weapon.damage or 100) * 1.5, p.owner, p.weapon.name or "Shell", info.bodyPart, p.pos)
				end
			elseif info.kind == "piece" and info.pieceId then
				DestructionService.damagePiece(info.pieceId, (p.weapon.structDmg or 500) * 0.6, "blast", p.pos)
			end
			detonate(p, hit.Position + hit.Normal * 0.5)
			continue
		end
		p.pos += step
		p.vel = newVel
		if p.life <= 0 then
			if p.weapon.kind == "throw" then
				detonate(p, p.pos)
			else
				EffectsBus.push({ k = "projEnd", id = p.id })
			end
		elseif p.pos.Y > -100 then
			table.insert(keep, p)
		end
	end
	projectiles = keep
end

-- ---------------------------------------------------------------------------
-- Hitscan (soldier rifles and vehicle machine guns)
-- ---------------------------------------------------------------------------
-- Resolves one bullet: what does it hit along origin->dir? Returns end point.
function CombatService.bullet(shooter: Soldier?, weapon: { [string]: any }, origin: Vector3, dir: Vector3, ignore: { Instance }, claimedHit: BasePart?, claimedPos: Vector3?): Vector3
	local range = weapon.range or 1200
	rayParams.FilterDescendantsInstances = ignore
	local result = workspace:Raycast(origin, dir.Unit * range, rayParams)
	local endPos = origin + dir.Unit * range
	local hitPart: BasePart? = nil
	local hitPos: Vector3? = nil
	if result then
		hitPart = result.Instance
		hitPos = result.Position
		endPos = result.Position
	end
	-- Trust the client's claimed target (lag compensation) only if the claim is
	-- consistent: the point lies on the ray that was fired, the claimed part is
	-- still near that point on the server, and the server ray reaches about
	-- that far.
	if claimedHit and claimedPos and claimedHit.Parent then
		local serverDist = if hitPos then (hitPos - origin).Magnitude else math.huge
		local claimInfo = Hits.classify(claimedHit)
		local consistent = AntiCheat.claimConsistent(origin, dir, claimedPos, claimedHit.Position, claimedHit.Size.Magnitude,
			claimedHit.AssemblyLinearVelocity.Magnitude, range, serverDist)
		if consistent and (claimInfo.kind == "soldier" or claimInfo.kind == "vehicle") then
			-- check nothing solid lies between the muzzle and the claimed point
			local d = claimedPos - origin
			local block = workspace:Raycast(origin, d * 0.97, rayParams)
			if not block or Hits.classify(block.Instance).kind == claimInfo.kind or (block.Position - claimedPos).Magnitude < 4 then
				hitPart = claimedHit
				hitPos = claimedPos
				endPos = claimedPos
			end
		end
	end
	if hitPart and hitPos then
		local info = Hits.classify(hitPart)
		local dist = (hitPos - origin).Magnitude
		if info.kind == "soldier" and info.soldierId then
			local victim = SoldierRegistry.get(info.soldierId)
			if victim then
				local dmg = (weapon.damage or 20) * Hits.zoneMultiplier(info.bodyPart, weapon.headMul) * Hits.falloff(dist, weapon.falloff)
				CombatService.damageSoldier(victim, dmg, shooter, weapon.name or "Gun", info.bodyPart, origin)
			end
		elseif info.kind == "vehicle" and info.vehicleId and CombatService.vehicleDamage then
			CombatService.vehicleDamage(info.vehicleId, weapon.vehicleDamage or (weapon.damage or 20) * 0.12, shooter, "bullet", weapon.name or "Gun")
		elseif info.kind == "piece" and info.pieceId then
			DestructionService.damagePiece(info.pieceId, weapon.structDmg or 2, "bullet", origin)
		elseif info.kind == "prop" then
			-- props are registered as pieces too; nothing else to do
		end
		EffectsBus.push({ k = "impact", p = hitPos, n = if result then result.Normal else -dir.Unit, m = hitPart.Material.Name, s = info.kind == "soldier" })
	end
	return endPos
end

local function spreadDir(dir: Vector3, spread: number): Vector3
	if spread <= 0 then
		return dir.Unit
	end
	local cf = CFrame.lookAt(Vector3.zero, dir)
	local a = math.random() * math.pi * 2
	local r = math.sqrt(math.random()) * spread
	return (cf * CFrame.Angles(math.cos(a) * r, math.sin(a) * r, 0)).LookVector
end
CombatService.spreadDir = spreadDir

-- ---------------------------------------------------------------------------
-- Player remotes
-- ---------------------------------------------------------------------------
local function equippedWeapon(s: Soldier): (string?, { [string]: any }?)
	local id = s.loadout[s.equipped]
	if not id or id == "" then
		return nil, nil
	end
	return id, Defs.Weapons[id]
end

local function muzzleClear(s: Soldier, head: Vector3, origin: Vector3): boolean
	local d = origin - head
	if d.Magnitude < 0.05 then
		return true
	end
	losParams.FilterDescendantsInstances = { s.model :: Instance }
	local hit = workspace:Raycast(head, d, losParams)
	if not hit then
		return true
	end
	local kind = Hits.classify(hit.Instance).kind
	return kind == "soldier" or kind == "vehicle"
end

local function onFire(player: Player, req: any)
	local s = SoldierRegistry.forPlayer(player)
	if not s or not s.alive or s.vehicleId or type(req) ~= "table" or type(req.shots) ~= "table" then
		return
	end
	local id, w = equippedWeapon(s)
	if not id or not w or w.kind ~= "hitscan" then
		return
	end
	local ammo = s.ammo[id]
	if not ammo then
		return
	end
	local headPos = headPosition(s)
	if not headPos then
		return
	end
	local now = os.clock()
	local interval = 60 / (w.rpm or 600)
	local bucket = fireTokens[s.id]
	if not bucket then
		bucket = {}
		fireTokens[s.id] = bucket
	end
	local tokens = AntiCheat.refillTokens(bucket[id], s.lastShot[id] or 0, now, interval, BURST_TOKENS)
	local fired, examined = 0, 0
	for _, shot in req.shots do
		examined += 1
		if examined > MAX_SHOTS_PER_PACKET or tokens < 1 or ammo.mag <= 0 then
			break
		end
		if type(shot) ~= "table" then
			continue
		end
		local origin = Util.finiteVector(shot.o)
		local dir = Util.finiteVector(shot.d)
		if not origin or not dir or dir.Magnitude < 0.5 or (origin - headPos).Magnitude > MUZZLE_REACH then
			continue -- malformed, or the muzzle is not where the server sees the soldier
		end
		if not muzzleClear(s, headPos, origin) then
			continue -- muzzle on the far side of a wall
		end
		tokens -= 1
		fired += 1
		ammo.mag -= 1
		local claimed = if typeof(shot.h) == "Instance" and (shot.h :: Instance):IsA("BasePart") then shot.h :: BasePart else nil
		local claimedPos = Util.finiteVector(shot.p)
		local endPos = CombatService.bullet(s, w, origin, dir, { s.model :: Instance }, claimed, claimedPos)
		EffectsBus.push({ k = "tracer", a = origin, b = endPos, w = w.sound, sid = s.id })
	end
	bucket[id] = tokens
	s.lastShot[id] = now
	if fired > 0 then
		SpawnService.dropProtection(s)
	end
end

local function onReload(player: Player)
	local s = SoldierRegistry.forPlayer(player)
	if not s or not s.alive then
		return
	end
	local id, w = equippedWeapon(s)
	if not id or not w or not w.mag then
		return
	end
	local ammo = s.ammo[id]
	if not ammo or ammo.reserve <= 0 or ammo.mag >= w.mag then
		return
	end
	local reloadTime = w.reload or 2
	task.delay(reloadTime * 0.9, function()
		if not s.alive or s.loadout[s.equipped] ~= id then
			return
		end
		local need = w.mag - ammo.mag
		local take = math.min(need, ammo.reserve)
		ammo.mag += take
		ammo.reserve -= take
		if s.player then
			Net.event("MatchEvent"):FireClient(s.player, { kind = "ammo", weapon = id, mag = ammo.mag, reserve = ammo.reserve })
		end
	end)
end

local function onSwitch(player: Player, slot: any)
	local s = SoldierRegistry.forPlayer(player)
	local n = Util.finiteNumber(slot)
	if not s or not s.alive or not n then
		return
	end
	slot = math.clamp(math.floor(n), 1, 4)
	local id = s.loadout[slot]
	if not id or id == "" then
		return
	end
	s.equipped = slot
	local w = Defs.Weapons[id]
	if s.model then
		s.model:SetAttribute("Equipped", slot)
		CharacterStyle.holdWeapon(s.model, w and w.model)
	end
end

local function onThrow(player: Player, req: any)
	local s = SoldierRegistry.forPlayer(player)
	if not s or not s.alive or s.vehicleId or type(req) ~= "table" then
		return
	end
	local throwDir = Util.finiteVector(req.d)
	if not throwDir or throwDir.Magnitude < 0.5 then
		return
	end
	local slot = Util.finiteNumber(req.slot) or 4
	local id = s.loadout[slot]
	local w = Defs.Weapons[id or ""]
	if not w then
		return
	end
	local ammo = s.ammo[id :: string]
	if not ammo then
		return
	end
	local head = headPosition(s)
	if not head then
		return
	end
	local dir = throwDir.Unit
	if w.kind == "throw" then
		if ammo.mag <= 0 then
			return
		end
		ammo.mag -= 1
		local power = math.clamp(Util.finiteNumber(req.power) or 1, 0.3, 1)
		CombatService.launch(head + dir * 1.5, dir * w.speed * power + Vector3.new(0, w.speed * 0.18, 0), w, s, { s.model :: Instance })
	elseif w.kind == "projectile" then
		-- RPG
		if ammo.mag <= 0 then
			return
		end
		local now = os.clock()
		if now - (s.lastShot[id :: string] or 0) < 1 then
			return
		end
		s.lastShot[id :: string] = now
		ammo.mag -= 1
		CombatService.launch(head + dir * 2.5, dir * w.speed, w, s, { s.model :: Instance })
		task.delay(w.reload or 3, function()
			if ammo.reserve > 0 and ammo.mag == 0 then
				ammo.reserve -= 1
				ammo.mag = 1
			end
		end)
	end
	SpawnService.dropProtection(s)
end

local function onDetonate(player: Player)
	local s = SoldierRegistry.forPlayer(player)
	if not s then
		return
	end
	local list = charges[s.id]
	if not list then
		return
	end
	for _, p in list do
		if table.find(projectiles, p) then
			p.life = 0
			p.fuse = 0
			p.stuck = true
		end
	end
	charges[s.id] = nil
end

-- ---------------------------------------------------------------------------
-- Class tools: medkit, ammo pouch, repair torch, binoculars (spot / artillery)
-- ---------------------------------------------------------------------------
local artilleryCooldown: { [number]: number } = {}

function CombatService.artilleryStrike(caller: Soldier, target: Vector3)
	local w = Defs.Vehicles.mlrs.weapons[1]
	matchEvent:FireAllClients({ kind = "artillery", team = caller.team, x = target.X, z = target.Z, by = caller.name })
	task.delay(4, function()
		for k = 1, 8 do
			local off = Vector3.new((math.random() - 0.5) * 60, 0, (math.random() - 0.5) * 60)
			local origin = target + off + Vector3.new(30, 420, 60)
			local vel = (target + off - origin).Unit * 260
			CombatService.launch(origin, vel, w, caller)
			task.wait(0.35)
		end
	end)
end

local function onTool(player: Player, req: any)
	local s = SoldierRegistry.forPlayer(player)
	if not s or not s.alive or type(req) ~= "table" then
		return
	end
	local id = s.loadout[3]
	local w = Defs.Weapons[id or ""]
	if not w then
		return
	end
	local now = os.clock()
	local root = s.root
	if not root then
		return
	end
	if id == "medkit" or id == "ammobox" then
		if now < s.toolCooldown then
			return
		end
		local target = s
		if type(req.target) == "number" then
			local t = SoldierRegistry.get(req.target)
			if t and t.alive and t.team == s.team and t.root and (t.root.Position - root.Position).Magnitude <= (w.range or 12) + 4 then
				target = t
			end
		end
		s.toolCooldown = now + (w.cooldown or 1)
		if id == "medkit" and target.humanoid then
			local hum = target.humanoid
			if hum.Health < hum.MaxHealth then
				hum.Health = math.min(hum.MaxHealth, hum.Health + (w.heal or 40))
				if target ~= s then
					SoldierRegistry.addScore(s, "heals", 1, 20)
				end
			end
		elseif id == "ammobox" then
			if SpawnService.refill(target, 1) and target ~= s then
				SoldierRegistry.addScore(s, "resupplies", 1, 15)
			end
		end
	elseif id == "repair" then
		if CombatService.vehicleRepair then
			local part = if typeof(req.part) == "Instance" and (req.part :: Instance):IsA("BasePart") then req.part :: BasePart else nil
			if CombatService.vehicleRepair(s, part, 0.25) then
				s.stats.repairs += 1
			end
		end
	elseif id == "binoculars" then
		local target = Util.finiteVector(req.p)
		if not target then
			return
		end
		if (target - root.Position).Magnitude > (w.spotRange or 1800) then
			return
		end
		if req.artillery then
			if now < (artilleryCooldown[s.team] or 0) then
				if s.player then
					matchEvent:FireClient(s.player, { kind = "notice", text = string.format("Rocket artillery reloading (%d s)", math.ceil((artilleryCooldown[s.team] or 0) - now)) })
				end
				return
			end
			artilleryCooldown[s.team] = now + (w.artilleryCooldown or 90)
			CombatService.artilleryStrike(s, target)
		else
			-- spot: enemies near the aim point show on the team's minimap for 10 s
			local n = 0
			for _, e in SoldierRegistry.alive(Constants.enemyOf(s.team)) do
				if e.root and (e.root.Position - target).Magnitude < 45 then
					e.spottedUntil = now + 10
					n += 1
				end
			end
			if n > 0 then
				SoldierRegistry.addScore(s, "score", 0, 5 * n)
			end
		end
	end
end

local function onStance(player: Player, stance: any)
	local s = SoldierRegistry.forPlayer(player)
	local n = Util.finiteNumber(stance)
	if not s or not s.alive or not n then
		return
	end
	stance = math.clamp(math.floor(n), 0, 2)
	s.stance = stance
	if s.model then
		s.model:SetAttribute("Stance", stance)
	end
end

-- ---------------------------------------------------------------------------
-- Init
-- ---------------------------------------------------------------------------
function CombatService.init()
	matchEvent = Net.event("MatchEvent")
	hitmarker = Net.event("Hitmarker")
	damageTaken = Net.event("DamageTaken")
	local fireLimiter = Net.rateLimiter(40)
	Net.event("Fire").OnServerEvent:Connect(function(player, req)
		if fireLimiter(player) then
			onFire(player, req)
		end
	end)
	local misc = Net.rateLimiter(12)
	Net.event("Reload").OnServerEvent:Connect(function(player)
		if misc(player) then
			onReload(player)
		end
	end)
	Net.event("SwitchWeapon").OnServerEvent:Connect(function(player, slot)
		if misc(player) then
			onSwitch(player, slot)
		end
	end)
	Net.event("Throw").OnServerEvent:Connect(function(player, req)
		if misc(player) then
			onThrow(player, req)
		end
	end)
	Net.event("Detonate").OnServerEvent:Connect(function(player)
		if misc(player) then
			onDetonate(player)
		end
	end)
	Net.event("UseTool").OnServerEvent:Connect(function(player, req)
		if misc(player) then
			onTool(player, req)
		end
	end)
	Net.event("Stance").OnServerEvent:Connect(function(player, stance)
		if misc(player) then
			onStance(player, stance)
		end
	end)
	Net.event("Spot").OnServerEvent:Connect(function(player, pos)
		if misc(player) and Util.finiteVector(pos) then
			onTool(player, { p = pos })
		end
	end)
	Net.event("ArtilleryCall").OnServerEvent:Connect(function(player, pos)
		if misc(player) and Util.finiteVector(pos) then
			onTool(player, { p = pos, artillery = true })
		end
	end)
	RunService.Heartbeat:Connect(function(dt)
		stepProjectiles(math.min(dt, 0.1))
	end)
	local _ = Players
end

function CombatService.reset()
	table.clear(projectiles)
	table.clear(charges)
	table.clear(artilleryCooldown)
	table.clear(fireTokens)
end

return CombatService
