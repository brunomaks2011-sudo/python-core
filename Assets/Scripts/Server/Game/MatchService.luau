--!strict
-- Authoritative THREE FLAGS - DOMINATION match.
-- Ticks DominationMode at a fixed 10 Hz, computes zone occupancy from live
-- soldiers, credits captures / defence time, and replicates the official
-- state to clients through attributes on ReplicatedStorage.MatchState
-- (clients can only read them - the timers live on the server).

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local DominationMode = require(ReplicatedStorage.Shared.DominationMode)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local Net = require(ReplicatedStorage.Shared.Net)
local Defs = require(ReplicatedStorage.Shared.Defs)
local SoldierRegistry = require(script.Parent.SoldierRegistry)

local MatchService = {}

local TEAM = Constants.TEAM
local mode: any = nil
local state: Folder
local matchEvent: RemoteEvent
local accumulator = 0
local tickDt = 1 / Constants.MATCH_TICK_RATE
local endedAt = 0
local restartVotes: { [Player]: boolean } = {}
local summaryCache: { [string]: any }? = nil

MatchService.vehicleLookup = nil :: ((number) -> any)?
MatchService.onRestart = {} :: { () -> () }
MatchService.onPointEvent = nil :: ((ev: { [string]: any }) -> ())?
MatchService.RESTART_DELAY = 45

function MatchService.mode()
	return mode
end

local function publish()
	local s = mode:serialize()
	state:SetAttribute("State", s.state)
	state:SetAttribute("Winner", s.winner)
	state:SetAttribute("SuddenDeath", s.suddenDeath)
	state:SetAttribute("Tick", s.tick)
	state:SetAttribute("TickRate", s.tickRate)
	state:SetAttribute("VictoryTicks", s.victoryTicks)
	state:SetAttribute("BlueTicks", s.blueTicks)
	state:SetAttribute("RedTicks", s.redTicks)
	local heldB, heldR = 0, 0
	for _, p in s.points do
		local prefix = "P_" .. p.id .. "_"
		state:SetAttribute(prefix .. "Owner", p.owner)
		state:SetAttribute(prefix .. "Progress", math.floor(p.progress * 1000 + 0.5) / 1000)
		state:SetAttribute(prefix .. "Contested", p.contested)
		state:SetAttribute(prefix .. "Capturing", p.capturing)
		state:SetAttribute(prefix .. "Blue", p.blue)
		state:SetAttribute(prefix .. "Red", p.red)
		if p.owner == TEAM.BLUE then
			heldB += 1
		elseif p.owner == TEAM.RED then
			heldR += 1
		end
	end
	state:SetAttribute("BlueHeld", heldB)
	state:SetAttribute("RedHeld", heldR)
	state:SetAttribute("RestartIn", if s.state == "ended" then math.max(0, math.ceil(endedAt + MatchService.RESTART_DELAY - os.clock())) else 0)
end

local function soldierCountsForPoint(s: SoldierRegistry.Soldier): boolean
	if s.vehicleId and MatchService.vehicleLookup then
		local v = MatchService.vehicleLookup(s.vehicleId)
		if v and v.def and v.def.canCapture == false then
			return false
		end
	end
	return true
end

local function occupancy(point: any)
	local occ = { [TEAM.BLUE] = {}, [TEAM.RED] = {} }
	local r2 = point.radius * point.radius
	for _, s in SoldierRegistry.all() do
		local root = s.root
		if s.alive and root and root.Parent then
			local pos = root.Position
			local dx, dz = pos.X - point.x, pos.Z - point.z
			if dx * dx + dz * dz <= r2 and pos.Y > point.y - Constants.DOMINATION.ZONE_DEPTH and pos.Y < point.y + Constants.DOMINATION.ZONE_HEIGHT then
				if soldierCountsForPoint(s) then
					table.insert(occ[s.team], s.id)
				end
			end
		end
	end
	return occ
end

local POINT_NAMES: { [string]: string } = {}

local function handleEvents()
	for _, ev in mode:drainEvents() do
		local kind = ev.type
		if kind == "captured" then
			for _, id in ev.soldiers do
				local s = SoldierRegistry.get(id)
				if s then
					SoldierRegistry.addScore(s, "captures", 1, 200)
				end
			end
			matchEvent:FireAllClients({ kind = "captured", point = ev.point, team = ev.team, name = POINT_NAMES[ev.point] })
		elseif kind == "neutralized" then
			for _, id in ev.soldiers do
				local s = SoldierRegistry.get(id)
				if s then
					SoldierRegistry.addScore(s, "score", 0, 100)
				end
			end
			matchEvent:FireAllClients({ kind = "neutralized", point = ev.point, by = ev.by, from = ev.from, name = POINT_NAMES[ev.point] })
		elseif kind == "contested" then
			matchEvent:FireAllClients({ kind = "contested", point = ev.point, owner = ev.owner, name = POINT_NAMES[ev.point] })
		elseif kind == "suddenDeath" then
			matchEvent:FireAllClients({ kind = "suddenDeath" })
		elseif kind == "victory" then
			endedAt = os.clock()
			summaryCache = MatchService.buildSummary()
			matchEvent:FireAllClients({ kind = "victory", team = ev.team, reason = ev.reason, summary = summaryCache })
		end
		if MatchService.onPointEvent then
			MatchService.onPointEvent(ev)
		end
	end
end

local function defendCredit(dt: number)
	for _, p in mode.points do
		if p.owner ~= TEAM.NONE then
			for _, id in p.occupants[p.owner] or {} do
				local s = SoldierRegistry.get(id)
				if s then
					s.stats.defendTime += dt
					if math.floor(s.stats.defendTime) % 10 == 0 and math.floor(s.stats.defendTime - dt) % 10 ~= 0 then
						SoldierRegistry.addScore(s, "score", 0, 10)
					end
				end
			end
		end
	end
end

function MatchService.buildSummary(): { [string]: any }
	local sum = mode:summary()
	local board = SoldierRegistry.scoreboard()
	local teamStats = { [1] = { kills = 0, deaths = 0, captures = 0, vehicleKills = 0 }, [2] = { kills = 0, deaths = 0, captures = 0, vehicleKills = 0 } }
	local mvp = nil
	for _, row in board do
		local t = teamStats[row.team]
		if t then
			t.kills += row.kills
			t.deaths += row.deaths
			t.captures += row.captures
			t.vehicleKills += row.vkills
		end
		if not mvp or row.score > mvp.score then
			mvp = row
		end
	end
	local pointStats = {}
	for id, st in sum.stats.points do
		pointStats[id] = {
			blueHeld = math.floor(st.heldTicks[TEAM.BLUE] / mode.tickRate),
			redHeld = math.floor(st.heldTicks[TEAM.RED] / mode.tickRate),
			contested = math.floor(st.contestedTicks / mode.tickRate),
			blueCaptures = st.captures[TEAM.BLUE],
			redCaptures = st.captures[TEAM.RED],
		}
	end
	return {
		winner = sum.winner,
		duration = sum.durationSeconds,
		blueSeconds = sum.blueSeconds,
		redSeconds = sum.redSeconds,
		blueHeld = sum.finalPointsHeld[TEAM.BLUE],
		redHeld = sum.finalPointsHeld[TEAM.RED],
		maxHeldBlue = sum.stats.maxHeld[TEAM.BLUE],
		maxHeldRed = sum.stats.maxHeld[TEAM.RED],
		leadChanges = sum.stats.leadChanges,
		points = pointStats,
		teams = teamStats,
		mvp = mvp,
		board = board,
	}
end

function MatchService.restart()
	if mode.state ~= "ended" and not RunService:IsStudio() then
		return
	end
	matchEvent:FireAllClients({ kind = "restarting" })
	state:SetAttribute("Restarting", true)
	for _, fn in MatchService.onRestart do
		local ok, err = pcall(fn :: any)
		if not ok then
			warn("[Match] restart hook failed: " .. tostring(err))
		end
	end
	mode:reset()
	SoldierRegistry.resetStats()
	restartVotes = {}
	summaryCache = nil
	accumulator = 0
	state:SetAttribute("Restarting", false)
	publish()
	matchEvent:FireAllClients({ kind = "restarted" })
end

function MatchService.isLive(): boolean
	return mode ~= nil and mode.state == "live"
end

function MatchService.init()
	local info = MapInfo.get()
	local defs = {}
	for _, p in info.points do
		table.insert(defs, { id = p.id, name = p.name, x = p.x, y = p.y, z = p.z, radius = p.radius })
		POINT_NAMES[p.id] = p.name
	end
	mode = DominationMode.new(defs, { TICK_RATE = Constants.MATCH_TICK_RATE })
	state = Net.matchState()
	state:SetAttribute("MapName", info.name)
	for _, p in info.points do
		state:SetAttribute("P_" .. p.id .. "_Name", p.name)
		state:SetAttribute("P_" .. p.id .. "_X", p.x)
		state:SetAttribute("P_" .. p.id .. "_Z", p.z)
		state:SetAttribute("P_" .. p.id .. "_Radius", p.radius)
	end
	matchEvent = Net.event("MatchEvent")
	local queryLimiter = Net.rateLimiter(4)
	Net.func("GetScoreboard").OnServerInvoke = function(player: Player): any
		if not queryLimiter(player) then
			return nil
		end
		return SoldierRegistry.scoreboard()
	end
	Net.func("GetMatchSummary").OnServerInvoke = function(player: Player): any
		if not queryLimiter(player) then
			return nil
		end
		if mode.state == "ended" then
			return summaryCache or MatchService.buildSummary()
		end
		return MatchService.buildSummary()
	end
	local limiter = Net.rateLimiter(2)
	Net.event("RequestRestart").OnServerEvent:Connect(function(player)
		if not limiter(player) or mode.state ~= "ended" then
			return
		end
		restartVotes[player] = true
		local votes, total = 0, 0
		for _, p in game:GetService("Players"):GetPlayers() do
			total += 1
			if restartVotes[p] then
				votes += 1
			end
		end
		state:SetAttribute("RestartVotes", votes)
		-- single player / majority restarts immediately
		if votes * 2 > total or total <= 1 then
			MatchService.restart()
		end
	end)
	publish()
	local publishAcc = 0
	RunService.Heartbeat:Connect(function(dt)
		if mode.state == "ended" then
			publishAcc += dt
			if publishAcc > 0.5 then
				publishAcc = 0
				publish()
			end
			if os.clock() - endedAt > MatchService.RESTART_DELAY then
				MatchService.restart()
			end
			return
		end
		accumulator += math.min(dt, 0.5)
		local stepped = false
		while accumulator >= tickDt do
			accumulator -= tickDt
			mode:tick(occupancy)
			defendCredit(tickDt)
			stepped = true
			if mode.state ~= "live" then
				break
			end
		end
		if stepped then
			handleEvents()
			publish()
		end
	end)
	local _ = Defs
end

return MatchService
