--!strict
-- THREE FLAGS - DOMINATION (authoritative rules; runs only on the server)
--
--  * Three control points A, B, C. A point moves toward a team while only that
--    team has soldiers inside its zone. Both teams inside = CONTESTED: frozen,
--    and it earns nobody time.
--  * Neutral -> captured takes CAPTURE_SECONDS (30 s) for one soldier. An enemy
--    point is first neutralised (30 s), then captured (30 s). Extra soldiers
--    speed this up slightly (capped at 1.8x).
--  * Every second a team holds at least one uncontested point its timer grows
--    by exactly one second - holding 1, 2 or 3 points gives the same rate.
--  * The first team to reach exactly VICTORY_SECONDS wins. If both teams would
--    reach it on the same tick, the team holding more points wins; on a full
--    tie neither advances (sudden death) until the tie is broken.
--
-- Pure Luau (no Roblox APIs) so it is unit-tested outside Roblox with Lune.

local DominationMode = {}
DominationMode.__index = DominationMode

local BLUE, RED, NONE = 1, 2, 0

local DEFAULTS = {
	VICTORY_SECONDS = 1000,
	CAPTURE_SECONDS = 30,
	CAPTURE_BONUS_PER_SOLDIER = 0.2,
	CAPTURE_MAX_MULTIPLIER = 1.8,
	REGEN_SECONDS = 60,
	TICK_RATE = 10,
}

local function enemyOf(team: number): number
	return if team == BLUE then RED elseif team == RED then BLUE else NONE
end

local function sign(x: number): number
	return if x > 0 then 1 elseif x < 0 then -1 else 0
end

export type PointDef = { id: string, name: string?, x: number, y: number?, z: number, radius: number }
export type Occupancy = { [number]: { any } }

export type Point = {
	id: string,
	name: string,
	x: number,
	y: number,
	z: number,
	radius: number,
	owner: number,
	progress: number,
	contested: boolean,
	capturingTeam: number,
	counts: { [number]: number },
	occupants: { [number]: { any } },
	lastChangeTick: number,
}

export type Event = { [string]: any }

local function newPoint(def: PointDef): Point
	return {
		id = def.id,
		name = def.name or def.id,
		x = def.x,
		y = def.y or 0,
		z = def.z,
		radius = def.radius,
		owner = NONE,
		progress = 0,
		contested = false,
		capturingTeam = NONE,
		counts = { [BLUE] = 0, [RED] = 0 },
		occupants = { [BLUE] = {}, [RED] = {} },
		lastChangeTick = 0,
	}
end

function DominationMode.new(pointDefs: { PointDef }, options: { [string]: number }?)
	local cfg = table.clone(DEFAULTS)
	if options then
		for k, v in options do
			cfg[k] = v
		end
	end
	local self = setmetatable({}, DominationMode)
	self.cfg = cfg
	self.tickRate = cfg.TICK_RATE
	self.victoryTicks = math.floor(cfg.VICTORY_SECONDS * cfg.TICK_RATE + 0.5)
	-- progress units: one soldier advances 100 units per tick
	self.progressMax = math.floor(cfg.CAPTURE_SECONDS * cfg.TICK_RATE * 100 + 0.5)
	self.regenPerTick = math.max(1, math.floor(self.progressMax / (cfg.REGEN_SECONDS * cfg.TICK_RATE) + 0.5))
	self.points = {} :: { Point }
	for _, def in pointDefs do
		table.insert(self.points, newPoint(def))
	end
	self.events = {} :: { Event }
	self:reset()
	return self
end

function DominationMode.reset(self: any)
	for _, p in self.points do
		p.owner = NONE
		p.progress = 0
		p.contested = false
		p.capturingTeam = NONE
		p.counts = { [BLUE] = 0, [RED] = 0 }
		p.occupants = { [BLUE] = {}, [RED] = {} }
		p.lastChangeTick = 0
	end
	self.timers = { [BLUE] = 0, [RED] = 0 }
	self.state = "live"
	self.winner = NONE
	self.suddenDeath = false
	self.tickCount = 0
	self.endTick = 0
	table.clear(self.events)
	local pointStats = {}
	for _, p in self.points do
		pointStats[p.id] = {
			heldTicks = { [BLUE] = 0, [RED] = 0 },
			contestedTicks = 0,
			captures = { [BLUE] = 0, [RED] = 0 },
			neutralizations = { [BLUE] = 0, [RED] = 0 },
		}
	end
	self.stats = {
		points = pointStats,
		maxHeld = { [BLUE] = 0, [RED] = 0 },
		allThreeTicks = { [BLUE] = 0, [RED] = 0 },
		noPointTicks = { [BLUE] = 0, [RED] = 0 },
		leadChanges = 0,
	}
	self._leader = NONE
end

function DominationMode.secondsOf(self: any, team: number): number
	return self.timers[team] / self.tickRate
end

function DominationMode.pointById(self: any, id: string): Point?
	for _, p in self.points do
		if p.id == id then
			return p
		end
	end
	return nil
end

function DominationMode.ownedCount(self: any, team: number, uncontestedOnly: boolean?): number
	local n = 0
	for _, p in self.points do
		if p.owner == team and (not uncontestedOnly or not p.contested) then
			n += 1
		end
	end
	return n
end

function DominationMode._emit(self: any, kind: string, data: { [string]: any })
	data.type = kind
	data.tick = self.tickCount
	table.insert(self.events, data)
end

function DominationMode._captureRate(self: any, n: number): number
	local mult = math.min(1 + self.cfg.CAPTURE_BONUS_PER_SOLDIER * (n - 1), self.cfg.CAPTURE_MAX_MULTIPLIER)
	return math.floor(100 * mult + 0.5)
end

-- occupancy(point) -> { [1] = {soldiers...}, [2] = {soldiers...} }
function DominationMode.tick(self: any, occupancy: (Point) -> Occupancy)
	if self.state ~= "live" then
		return
	end
	self.tickCount += 1

	for _, p in self.points do
		self:_updatePoint(p, occupancy(p))
	end

	local held = { [BLUE] = self:ownedCount(BLUE, true), [RED] = self:ownedCount(RED, true) }
	for _, team in { BLUE, RED } do
		local owned = self:ownedCount(team)
		if owned > self.stats.maxHeld[team] then
			self.stats.maxHeld[team] = owned
		end
		if owned == #self.points then
			self.stats.allThreeTicks[team] += 1
		end
		if owned == 0 then
			self.stats.noPointTicks[team] += 1
		end
	end
	for _, p in self.points do
		local st = self.stats.points[p.id]
		if p.contested then
			st.contestedTicks += 1
		elseif p.owner ~= NONE then
			st.heldTicks[p.owner] += 1
		end
	end

	local wants = { [BLUE] = held[BLUE] > 0, [RED] = held[RED] > 0 }
	local function reaches(t: number): boolean
		return wants[t] and self.timers[t] + 1 >= self.victoryTicks
	end

	if reaches(BLUE) and reaches(RED) then
		-- Both would hit the target on this very tick: never let both win.
		if held[BLUE] ~= held[RED] then
			local w = if held[BLUE] > held[RED] then BLUE else RED
			self.timers[w] = self.victoryTicks
			self.suddenDeath = false
			self:_finish(w, "more points held at the deciding moment")
		elseif not self.suddenDeath then
			self.suddenDeath = true
			self:_emit("suddenDeath", {})
		end
		return
	end

	for _, t in { BLUE, RED } do
		if wants[t] then
			self.timers[t] = math.min(self.victoryTicks, self.timers[t] + 1)
		end
	end

	local lead = if self.timers[BLUE] == self.timers[RED]
		then NONE
		elseif self.timers[BLUE] > self.timers[RED] then BLUE
		else RED
	if lead ~= NONE and lead ~= self._leader then
		if self._leader ~= NONE then
			self.stats.leadChanges += 1
		end
		self._leader = lead
	end

	for _, t in { BLUE, RED } do
		if self.timers[t] >= self.victoryTicks then
			self:_finish(t, if self.suddenDeath then "sudden death" else "reached 1000 seconds")
			return
		end
	end
end

function DominationMode._finish(self: any, team: number, reason: string)
	self.state = "ended"
	self.winner = team
	self.endTick = self.tickCount
	self:_emit("victory", { team = team, reason = reason, timers = table.clone(self.timers) })
end

function DominationMode._updatePoint(self: any, p: Point, occ: Occupancy)
	local blue = occ[BLUE] or {}
	local red = occ[RED] or {}
	p.occupants = { [BLUE] = blue, [RED] = red }
	p.counts = { [BLUE] = #blue, [RED] = #red }
	local nb, nr = #blue, #red
	local wasContested = p.contested
	p.contested = nb > 0 and nr > 0
	if p.contested then
		p.capturingTeam = NONE
		if not wasContested then
			self:_emit("contested", { point = p.id, owner = p.owner })
		end
		return
	end
	if wasContested then
		self:_emit("uncontested", { point = p.id, owner = p.owner })
	end

	if nb == 0 and nr == 0 then
		p.capturingTeam = NONE
		local target = if p.owner == BLUE then self.progressMax elseif p.owner == RED then -self.progressMax else 0
		if p.progress < target then
			p.progress = math.min(target, p.progress + self.regenPerTick)
		elseif p.progress > target then
			p.progress = math.max(target, p.progress - self.regenPerTick)
		end
		return
	end

	local team = if nb > 0 then BLUE else RED
	local occupants = if team == BLUE then blue else red
	local dir = if team == BLUE then 1 else -1
	local full = dir * self.progressMax
	if p.progress == full then
		p.capturingTeam = NONE -- fully held, defending
		return
	end
	p.capturingTeam = team
	local before = p.progress
	p.progress += dir * self:_captureRate(#occupants)
	if p.progress > self.progressMax then
		p.progress = self.progressMax
	elseif p.progress < -self.progressMax then
		p.progress = -self.progressMax
	end

	local enemy = enemyOf(team)
	local crossed = sign(p.progress) ~= sign(before) or p.progress == 0
	if p.owner == enemy and crossed then
		p.owner = NONE
		p.lastChangeTick = self.tickCount
		self.stats.points[p.id].neutralizations[team] += 1
		self:_emit("neutralized", { point = p.id, by = team, from = enemy, soldiers = table.clone(occupants) })
	end
	if p.owner == NONE and p.progress == full then
		p.owner = team
		p.lastChangeTick = self.tickCount
		self.stats.points[p.id].captures[team] += 1
		self:_emit("captured", { point = p.id, team = team, soldiers = table.clone(occupants) })
	end
end

function DominationMode.drainEvents(self: any): { Event }
	local e = table.clone(self.events)
	table.clear(self.events)
	return e
end

-- Read-only view for clients / HUD.
function DominationMode.serialize(self: any)
	local pts = {}
	for _, p in self.points do
		table.insert(pts, {
			id = p.id,
			owner = p.owner,
			progress = p.progress / self.progressMax,
			contested = p.contested,
			capturing = p.capturingTeam,
			blue = p.counts[BLUE],
			red = p.counts[RED],
		})
	end
	return {
		state = self.state,
		winner = self.winner,
		suddenDeath = self.suddenDeath,
		tick = self.tickCount,
		tickRate = self.tickRate,
		victoryTicks = self.victoryTicks,
		blueTicks = self.timers[BLUE],
		redTicks = self.timers[RED],
		points = pts,
	}
end

function DominationMode.summary(self: any)
	local owners = {}
	for _, p in self.points do
		owners[p.id] = p.owner
	end
	return {
		winner = self.winner,
		durationSeconds = self.tickCount / self.tickRate,
		blueSeconds = self.timers[BLUE] / self.tickRate,
		redSeconds = self.timers[RED] / self.tickRate,
		finalPointsHeld = { [BLUE] = self:ownedCount(BLUE), [RED] = self:ownedCount(RED) },
		finalOwners = owners,
		stats = self.stats,
	}
end

return DominationMode
