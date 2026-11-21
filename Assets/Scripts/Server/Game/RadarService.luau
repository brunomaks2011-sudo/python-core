--!strict
-- Minimap feed: twice a second each player receives their team's soldiers and
-- vehicles plus enemies that are currently spotted (recon binoculars, drones,
-- observation planes, communication vehicles, radars, or firing nearby).
-- Sent through an UnreliableRemoteEvent (positions only, loss tolerant).

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Net = require(ReplicatedStorage.Shared.Net)
local RadarCodec = require(ReplicatedStorage.Shared.RadarCodec)
local SoldierRegistry = require(script.Parent.SoldierRegistry)

local RadarService = {}
RadarService.vehicles = nil :: (() -> { [number]: any })?

local function q(v: number): number
	return math.floor(v + 0.5)
end

function RadarService.init()
	local remote = Net.unreliable("Radar")
	local acc = 0
	RunService.Heartbeat:Connect(function(dt)
		acc += dt
		if acc < 0.5 then
			return
		end
		acc = 0
		local now = os.clock()
		local packets = { [1] = { s = {}, v = {}, e = {}, ev = {} }, [2] = { s = {}, v = {}, e = {}, ev = {} } }
		for _, s in SoldierRegistry.all() do
			local r = s.root
			if s.alive and r and r.Parent and (s.team == 1 or s.team == 2) then
				local p = r.Position
				local entry = { q(p.X), q(p.Z), s.id, if s.vehicleId then 1 else 0 }
				table.insert(packets[s.team].s, entry)
				-- recently firing soldiers reveal themselves briefly
				local fired = false
				for _, t in s.lastShot do
					if now - t < 1.5 then
						fired = true
						break
					end
				end
				if s.spottedUntil > now or fired then
					table.insert(packets[Constants.enemyOf(s.team)].e, { q(p.X), q(p.Z) })
				end
			end
		end
		if RadarService.vehicles then
			for _, v in RadarService.vehicles() do
				if v.alive and v.root.Parent then
					local p = v.root.Position
					local entry = { q(p.X), q(p.Z) }
					if v.team == 1 or v.team == 2 then
						table.insert(packets[v.team].v, entry)
						-- crewed enemy vehicles are visible to the other side when spotted or moving fast
						local crewed = v.seats[1] ~= nil
						if crewed and (v.root.AssemblyLinearVelocity.Magnitude > 20 or v.def.drive == "heli") then
							table.insert(packets[Constants.enemyOf(v.team)].ev, entry)
						end
					end
				end
			end
		end
		-- binary-packed: unreliable remotes drop payloads over ~1000 bytes
		local encoded = { [1] = RadarCodec.encode(packets[1]), [2] = RadarCodec.encode(packets[2]) }
		for _, player in Players:GetPlayers() do
			local s = SoldierRegistry.forPlayer(player)
			if s and (s.team == 1 or s.team == 2) then
				remote:FireClient(player, encoded[s.team])
			end
		end
	end)
end

return RadarService
