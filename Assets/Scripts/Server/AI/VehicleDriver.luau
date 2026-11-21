--!strict
-- AI control of a vehicle: route following (PathfindingService with a
-- vehicle-sized agent, bridges preferred over water), stuck recovery, and
-- turret gunnery for any seat occupied by a bot.

local PathfindingService = game:GetService("PathfindingService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Constants = require(ReplicatedStorage.Shared.Constants)
local Util = require(ReplicatedStorage.Shared.Util)
local SoldierRegistry = require(script.Parent.Parent.Game.SoldierRegistry)
local VehicleService = require(script.Parent.Parent.Game.VehicleService)

local VehicleDriver = {}
VehicleDriver.__index = VehicleDriver

local function yawOf(v: Vector3): number
	return math.atan2(-v.X, -v.Z)
end

function VehicleDriver.new(vehicle: any)
	return setmetatable({
		v = vehicle,
		goal = nil :: Vector3?,
		stopRadius = 30,
		waypoints = {} :: { Vector3 },
		index = 1,
		pending = false,
		lastProgress = os.clock(),
		lastPos = vehicle.root.Position,
		reverseUntil = 0,
		reverseSteer = 0,
		gunTimer = 0,
		targets = {} :: { [number]: any },
	}, VehicleDriver)
end

function VehicleDriver.setGoal(self: any, goal: Vector3?, stopRadius: number?)
	self.stopRadius = stopRadius or 30
	if goal == nil then
		self.goal = nil
		self.waypoints = {}
		return
	end
	if self.goal and (self.goal - goal).Magnitude < 20 then
		return
	end
	self.goal = goal
	self.waypoints = {}
	self.index = 1
	if self.pending then
		return
	end
	self.pending = true
	local from = self.v.root.Position
	local def = self.v.def
	task.spawn(function()
		local path = PathfindingService:CreatePath({
			AgentRadius = math.max(4, def.size.X * 0.6),
			AgentHeight = def.size.Y + 2,
			AgentCanJump = false,
			WaypointSpacing = 30,
			Costs = { Water = 200, Mud = 2 },
		})
		local ok = pcall(function()
			path:ComputeAsync(from, goal)
		end)
		self.pending = false
		if ok and path.Status == Enum.PathStatus.Success then
			local pts = {}
			for _, wp in path:GetWaypoints() do
				table.insert(pts, wp.Position)
			end
			self.waypoints = pts
			self.index = math.min(2, #pts)
		else
			self.waypoints = { goal }
			self.index = 1
		end
	end)
end

-- Driving input toward the current waypoint.
function VehicleDriver.drive(self: any, dt: number)
	local v = self.v
	if not v.alive then
		return
	end
	local root = v.root
	local pos = root.Position
	local now = os.clock()
	if not self.goal then
		VehicleService.setAIInput(v, { throttle = 0, steer = 0, brake = true, lift = 0, yaw = 0 })
		return
	end
	local flatGoal = Vector3.new(self.goal.X - pos.X, 0, self.goal.Z - pos.Z)
	if flatGoal.Magnitude < self.stopRadius then
		VehicleService.setAIInput(v, { throttle = 0, steer = 0, brake = true, lift = 0, yaw = 0 })
		return
	end
	local wp = self.waypoints[self.index] or self.goal
	local to = Vector3.new(wp.X - pos.X, 0, wp.Z - pos.Z)
	if to.Magnitude < 14 and self.index < #self.waypoints then
		self.index += 1
		wp = self.waypoints[self.index]
		to = Vector3.new(wp.X - pos.X, 0, wp.Z - pos.Z)
	end
	-- stuck recovery: reverse with opposite steering
	if (pos - self.lastPos).Magnitude > 4 then
		self.lastPos = pos
		self.lastProgress = now
	elseif now - self.lastProgress > 3 and self.reverseUntil < now then
		self.reverseUntil = now + 1.8
		self.reverseSteer = if math.random() < 0.5 then -1 else 1
		self.lastProgress = now
	end
	if self.reverseUntil > now then
		VehicleService.setAIInput(v, { throttle = -0.8, steer = self.reverseSteer, brake = false, lift = 0, yaw = 0 })
		return
	end
	local fwd = root.CFrame.LookVector
	local diff = Util.wrapAngle(yawOf(to) - yawOf(Vector3.new(fwd.X, 0, fwd.Z)))
	local steer = math.clamp(-diff * 2.2, -1, 1)
	local tracked = v.def.drive == "tracked"
	local throttle
	if math.abs(diff) > 1.1 then
		throttle = if tracked then 0 else 0.35
	else
		throttle = math.clamp(flatGoal.Magnitude / 80, 0.35, 1) * (1 - math.abs(diff) * 0.35)
	end
	VehicleService.setAIInput(v, { throttle = throttle, steer = steer, brake = false, lift = 0, yaw = 0 })
end

-- Turret gunnery for bot-occupied seats with weapons.
local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude
rayParams.IgnoreWater = true

function VehicleDriver.gunnery(self: any, dt: number)
	local v = self.v
	if not v.alive then
		return
	end
	self.gunTimer -= dt
	local retarget = self.gunTimer <= 0
	if retarget then
		self.gunTimer = 0.35
	end
	for seatIdx, sid in v.seats do
		local s = SoldierRegistry.get(sid)
		local seatDef = v.def.seats[seatIdx]
		if not s or s.player or not seatDef or not seatDef.weapons or #seatDef.weapons == 0 then
			continue
		end
		if retarget then
			-- choose a target: vehicles for cannons, infantry for machine guns
			local entry = seatDef.weapons[1]
			local w = if type(entry) == "number" then v.def.weapons[entry] else entry
			local range = if w.kind == "hitscan" then (w.range or 1500) else 2400
			local best, bd = nil, range
			for _, e in SoldierRegistry.alive(Constants.enemyOf(v.team)) do
				if e.root then
					local d = (e.root.Position - v.root.Position).Magnitude
					local prefer = if e.vehicleId and w.kind ~= "hitscan" then 0.6 else 1
					if d * prefer < bd then
						rayParams.FilterDescendantsInstances = { v.model }
						local from = v.root.Position + Vector3.new(0, v.def.size.Y, 0)
						local hit = workspace:Raycast(from, e.root.Position - from, rayParams)
						local ok = not hit or (e.model and hit.Instance:IsDescendantOf(e.model)) or (hit.Position - e.root.Position).Magnitude < 6
						if ok then
							best, bd = e, d * prefer
						end
					end
				end
			end
			self.targets[seatIdx] = best
		end
		local target = self.targets[seatIdx]
		if not target or not target.alive or not target.root then
			continue
		end
		local entry = seatDef.weapons[1]
		local w = if type(entry) == "number" then v.def.weapons[entry] else entry
		-- secondary coax / MG against infantry when the main gun is a cannon
		local weaponIndex = 1
		if not target.vehicleId and #seatDef.weapons > 1 then
			local e2 = seatDef.weapons[2]
			local w2 = if type(e2) == "number" then v.def.weapons[e2] else e2
			if w2 and w2.kind == "hitscan" then
				weaponIndex = 2
				w = w2
			end
		end
		local muzzle = VehicleService.muzzleCFrame(v, w.muzzle or "Muzzle")
		local tp = target.root.Position + Vector3.new(0, 1, 0)
		local dist = (tp - muzzle.Position).Magnitude
		local drop = if w.kind ~= "hitscan" and w.speed then 0.5 * workspace.Gravity * (w.gravityScale or 1) * (dist / w.speed) ^ 2 else 0
		local aimPoint = tp + Vector3.new(0, drop, 0)
		local localDir = v.root.CFrame:VectorToObjectSpace((aimPoint - muzzle.Position).Unit)
		local wantYaw = math.atan2(-localDir.X, -localDir.Z)
		local wantPitch = math.atan2(localDir.Y, math.sqrt(localDir.X ^ 2 + localDir.Z ^ 2))
		local aim = v.aim[seatIdx]
		if aim then
			local tdef = v.def.turret
			local yawSpeed = if tdef then tdef.yawSpeed else 2
			local newYaw = Util.approachAngle(aim.yaw, wantYaw, yawSpeed * dt)
			local newPitch = Util.approach(aim.pitch, math.clamp(wantPitch, if tdef then tdef.pitchMin else -0.3, if tdef then tdef.pitchMax else 0.8), 0.6 * dt)
			VehicleService.setAim(v, seatIdx, newYaw, newPitch)
			if math.abs(Util.wrapAngle(newYaw - wantYaw)) < 0.05 and math.abs(newPitch - wantPitch) < 0.06 then
				local dir = (aimPoint - muzzle.Position).Unit
				local spread = 0.012 * (1 + dist / 500)
				dir = (CFrame.lookAt(Vector3.zero, dir) * CFrame.Angles((math.random() - 0.5) * spread, (math.random() - 0.5) * spread, 0)).LookVector
				VehicleService.fire(s, v, weaponIndex, dir, tp)
			end
		end
	end
end

return VehicleDriver
