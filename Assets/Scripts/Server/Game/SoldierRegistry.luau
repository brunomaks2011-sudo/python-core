--!strict
-- Every player in the battle is a Soldier record here (PvP only: there are no
-- AI combatants). The record outlives deaths and respawns, so stats persist for
-- the whole match; it is removed when the player leaves.

local Players = game:GetService("Players")

local SoldierRegistry = {}

export type Stats = {
	kills: number,
	deaths: number,
	assists: number,
	captures: number,
	defendTime: number,
	score: number,
	vehicleKills: number,
	revives: number,
	heals: number,
	resupplies: number,
	repairs: number,
	damage: number,
}

export type Soldier = {
	id: number,
	name: string,
	team: number,
	role: string,
	player: Player,
	model: Model?,
	humanoid: Humanoid?,
	root: BasePart?,
	alive: boolean,
	deployed: boolean,
	vehicleId: number?,
	seatIndex: number?,
	stats: Stats,
	damagers: { [number]: { dmg: number, t: number } },
	spawnProtUntil: number,
	ammo: { [string]: { mag: number, reserve: number } },
	loadout: { string },
	equipped: number,
	lastShot: { [string]: number },
	toolCooldown: number,
	respawnAt: number,
	stance: number,
	spottedUntil: number,
	outOfBoundsSince: number?,
	lastHurt: number,
}

local soldiers: { [number]: Soldier } = {}
local byPlayer: { [Player]: Soldier } = {}
local nextId = 0

local function newStats(): Stats
	return { kills = 0, deaths = 0, assists = 0, captures = 0, defendTime = 0, score = 0, vehicleKills = 0, revives = 0, heals = 0, resupplies = 0, repairs = 0, damage = 0 }
end

function SoldierRegistry.create(player: Player, team: number, role: string): Soldier
	nextId += 1
	local s: Soldier = {
		id = nextId, name = player.DisplayName, team = team, role = role, player = player,
		model = nil, humanoid = nil, root = nil, alive = false, deployed = false, vehicleId = nil, seatIndex = nil,
		stats = newStats(), damagers = {}, spawnProtUntil = 0, ammo = {}, loadout = {}, equipped = 1, lastShot = {},
		toolCooldown = 0, respawnAt = 0, stance = 0, spottedUntil = 0, outOfBoundsSince = nil, lastHurt = 0,
	}
	soldiers[nextId] = s
	byPlayer[player] = s
	return s
end

function SoldierRegistry.get(id: number?): Soldier?
	if not id then
		return nil
	end
	return soldiers[id]
end

function SoldierRegistry.forPlayer(player: Player): Soldier?
	return byPlayer[player]
end

function SoldierRegistry.remove(s: Soldier)
	soldiers[s.id] = nil
	byPlayer[s.player] = nil
end

function SoldierRegistry.all(): { [number]: Soldier }
	return soldiers
end

function SoldierRegistry.alive(team: number?): { Soldier }
	local out = {}
	for _, s in soldiers do
		if s.alive and s.root and (team == nil or s.team == team) then
			table.insert(out, s)
		end
	end
	return out
end

function SoldierRegistry.count(team: number): number
	local n = 0
	for _, s in soldiers do
		if s.team == team then
			n += 1
		end
	end
	return n
end

function SoldierRegistry.resetStats()
	for _, s in soldiers do
		s.stats = newStats()
		s.damagers = {}
	end
	for _, p in Players:GetPlayers() do
		local s = byPlayer[p]
		if s then
			SoldierRegistry.publish(s)
		end
	end
end

-- Mirror the scoreboard-relevant stats onto the Player object (read-only for clients).
function SoldierRegistry.publish(s: Soldier)
	local p = s.player
	p:SetAttribute("Kills", s.stats.kills)
	p:SetAttribute("Deaths", s.stats.deaths)
	p:SetAttribute("Assists", s.stats.assists)
	p:SetAttribute("Captures", s.stats.captures)
	p:SetAttribute("Score", s.stats.score)
	p:SetAttribute("Role", s.role)
	p:SetAttribute("SoldierId", s.id)
end

function SoldierRegistry.addScore(s: Soldier, key: string, amount: number, points: number)
	local st = s.stats :: any
	st[key] = (st[key] or 0) + amount
	s.stats.score += points
	SoldierRegistry.publish(s)
end

function SoldierRegistry.scoreboard(): { { [string]: any } }
	local out = {}
	for _, s in soldiers do
		table.insert(out, {
			id = s.id, name = s.name, team = s.team, role = s.role, alive = s.alive,
			kills = s.stats.kills, deaths = s.stats.deaths, assists = s.stats.assists, captures = s.stats.captures,
			defend = math.floor(s.stats.defendTime), score = s.stats.score, vkills = s.stats.vehicleKills,
		})
	end
	table.sort(out, function(a, b)
		return a.score > b.score
	end)
	return out
end

return SoldierRegistry
