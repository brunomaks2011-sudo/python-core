--!strict
-- Unarmed support aircraft flown by the AI: each army has a reconnaissance
-- drone and an observation plane orbiting over the fighting. They spot enemy
-- soldiers and vehicles below them (shown on the team minimap).
-- The orbit is described by attributes; clients animate the Blender models
-- locally (smooth, no per-frame replication). The server evaluates the same
-- orbit maths for spotting.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Defs = require(ReplicatedStorage.Shared.Defs)
local MapInfo = require(ReplicatedStorage.Shared.MapInfo)
local SoldierRegistry = require(script.Parent.Parent.Game.SoldierRegistry)
local MatchService = require(script.Parent.Parent.Game.MatchService)

local SupportAir = {}

type Craft = { name: string, kind: string, team: number, center: Vector3, radius: number, speed: number, altitude: number, phase: number, cfg: Folder }
local crafts: { Craft } = {}

function SupportAir.position(c: Craft, t: number): Vector3
	local angle = c.phase + t * c.speed / c.radius
	local x = c.center.X + math.cos(angle) * c.radius
	local z = c.center.Z + math.sin(angle) * c.radius
	return Vector3.new(x, c.altitude, z)
end

local function retarget(c: Craft)
	-- orbit the point that matters most to this team: contested, else enemy-held, else ours
	local mode = MatchService.mode()
	local info = MapInfo.get()
	if not mode then
		return
	end
	local best, bestScore = nil, -1
	for _, p in info.points do
		local pt = mode:pointById(p.id)
		if pt then
			local score = (if pt.contested then 3 else 0) + (if pt.owner ~= c.team then 1.5 else 0.5) + math.random() * 0.5
			if score > bestScore then
				best, bestScore = p, score
			end
		end
	end
	if best then
		c.center = Vector3.new(best.x, 0, best.z)
		c.cfg:SetAttribute("Center", c.center)
		c.cfg:SetAttribute("Since", workspace:GetServerTimeNow())
		c.cfg:SetAttribute("Phase", c.phase)
	end
end

function SupportAir.init()
	local folder = Instance.new("Folder")
	folder.Name = "SupportAir"
	folder.Parent = ReplicatedStorage
	local info = MapInfo.get()
	local baseY = info.waterLevel
	for _, team in Constants.TEAMS do
		for kind, d in Defs.SupportAircraft do
			local cfg = Instance.new("Folder")
			cfg.Name = kind .. "_" .. team
			local c: Craft = {
				name = d.names[team], kind = kind, team = team, center = Vector3.new(0, 0, 0),
				radius = if kind == "drone" then 260 else 520, speed = d.speed, altitude = baseY + d.altitude,
				phase = math.random() * math.pi * 2, cfg = cfg,
			}
			cfg:SetAttribute("Model", d.model[team])
			cfg:SetAttribute("Team", team)
			cfg:SetAttribute("Radius", c.radius)
			cfg:SetAttribute("Speed", c.speed)
			cfg:SetAttribute("Altitude", c.altitude)
			cfg:SetAttribute("Phase", c.phase)
			cfg:SetAttribute("Center", c.center)
			cfg:SetAttribute("Since", workspace:GetServerTimeNow())
			cfg.Parent = folder
			table.insert(crafts, c)
		end
	end
	local acc, retargetAcc = 0, 0
	RunService.Heartbeat:Connect(function(dt)
		acc += dt
		retargetAcc += dt
		if retargetAcc > 60 then
			retargetAcc = 0
			for _, c in crafts do
				-- continue the orbit from where it is now
				local t = workspace:GetServerTimeNow() - (c.cfg:GetAttribute("Since") :: number)
				c.phase += t * c.speed / c.radius
				retarget(c)
			end
		end
		if acc < 1 then
			return
		end
		acc = 0
		local now = workspace:GetServerTimeNow()
		for _, c in crafts do
			local t = now - (c.cfg:GetAttribute("Since") :: number)
			local pos = SupportAir.position(c, t)
			local spot = Defs.SupportAircraft[c.kind].spotRadius
			for _, e in SoldierRegistry.alive(Constants.enemyOf(c.team)) do
				local r = e.root
				if r and Vector3.new(r.Position.X - pos.X, 0, r.Position.Z - pos.Z).Magnitude < spot then
					e.spottedUntil = math.max(e.spottedUntil, os.clock() + 2)
				end
			end
		end
	end)
	task.delay(5, function()
		for _, c in crafts do
			retarget(c)
		end
	end)
end

return SupportAir
