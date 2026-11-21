--!strict
-- Path following for AI soldiers on top of Roblox PathfindingService.
-- * Path requests are queued and computed a few per frame (ComputeAsync yields).
-- * Long trips are broken into ~450 stud legs toward the goal.
-- * Stuck detection: jump, then side-step, then re-path; direct steering fallback.

local PathfindingService = game:GetService("PathfindingService")
local RunService = game:GetService("RunService")

local Navigator = {}
Navigator.__index = Navigator

export type Navigator = {
	humanoid: Humanoid,
	root: BasePart,
	goal: Vector3?,
	waypoints: { PathWaypoint },
	index: number,
	pending: boolean,
	lastProgress: number,
	lastPos: Vector3,
	stuckStage: number,
	arriveRadius: number,
	failed: number,
	direct: boolean,
}

local AGENT = {
	AgentRadius = 2.2,
	AgentHeight = 5.5,
	AgentCanJump = true,
	AgentCanClimb = false,
	WaypointSpacing = 14,
	Costs = { Water = 25, Mud = 1.6, Rock = 1.3 },
}

local queue: { { nav: any, from: Vector3, to: Vector3 } } = {}
local MAX_PER_FRAME = 3
local LEG = 450

RunService.Heartbeat:Connect(function()
	local n = 0
	while #queue > 0 and n < MAX_PER_FRAME do
		local job = table.remove(queue, 1)
		n += 1
		task.spawn(function()
			local nav = job.nav
			local path = PathfindingService:CreatePath(AGENT)
			local ok = pcall(function()
				path:ComputeAsync(job.from, job.to)
			end)
			nav.pending = false
			if ok and path.Status == Enum.PathStatus.Success then
				nav.waypoints = path:GetWaypoints()
				nav.index = math.min(2, #nav.waypoints)
				nav.direct = false
				nav.failed = 0
			else
				nav.waypoints = {}
				nav.index = 1
				nav.direct = true
				nav.failed += 1
			end
		end)
	end
end)

function Navigator.new(humanoid: Humanoid, root: BasePart)
	local self = setmetatable({
		humanoid = humanoid,
		root = root,
		goal = nil,
		waypoints = {},
		index = 1,
		pending = false,
		lastProgress = os.clock(),
		lastPos = root.Position,
		stuckStage = 0,
		arriveRadius = 6,
		failed = 0,
		direct = false,
	}, Navigator)
	return self
end

local function legTarget(from: Vector3, goal: Vector3): Vector3
	local d = goal - from
	local flat = Vector3.new(d.X, 0, d.Z)
	if flat.Magnitude <= LEG then
		return goal
	end
	return from + flat.Unit * LEG
end

function Navigator.moveTo(self: any, goal: Vector3, arriveRadius: number?)
	self.arriveRadius = arriveRadius or 6
	if self.goal and (self.goal - goal).Magnitude < 8 and (#self.waypoints > 0 or self.pending or self.direct) then
		return
	end
	self.goal = goal
	self:_request()
end

function Navigator._request(self: any)
	if self.pending or not self.goal then
		return
	end
	self.pending = true
	self.direct = false
	self.waypoints = {}
	table.insert(queue, { nav = self, from = self.root.Position, to = legTarget(self.root.Position, self.goal) })
end

function Navigator.stop(self: any)
	self.goal = nil
	self.waypoints = {}
	self.direct = false
	if self.humanoid.Parent then
		self.humanoid:Move(Vector3.zero)
		self.humanoid:MoveTo(self.root.Position)
	end
end

function Navigator.arrived(self: any): boolean
	if not self.goal then
		return true
	end
	local d = self.goal - self.root.Position
	return Vector3.new(d.X, 0, d.Z).Magnitude <= self.arriveRadius
end

-- Call every AI tick (~5 Hz).
function Navigator.update(self: any)
	local goal = self.goal
	if not goal or not self.root.Parent then
		return
	end
	local pos = self.root.Position
	if self:arrived() then
		self:stop()
		return
	end
	-- stuck detection
	local now = os.clock()
	if (pos - self.lastPos).Magnitude > 2.5 then
		self.lastPos = pos
		self.lastProgress = now
		self.stuckStage = 0
	elseif now - self.lastProgress > 2.5 then
		self.stuckStage += 1
		self.lastProgress = now
		if self.stuckStage == 1 then
			self.humanoid.Jump = true
		elseif self.stuckStage == 2 then
			local side = self.root.CFrame.RightVector * (if math.random() < 0.5 then -8 else 8)
			self.humanoid:MoveTo(pos + side)
			return
		else
			self.stuckStage = 0
			self:_request()
			return
		end
	end
	if self.pending then
		return
	end
	if self.direct then
		-- fallback: steer straight at the goal, dodging obstacles with feelers
		local dir = Vector3.new(goal.X - pos.X, 0, goal.Z - pos.Z)
		if dir.Magnitude > 0.1 then
			dir = dir.Unit
			local params = RaycastParams.new()
			params.FilterType = Enum.RaycastFilterType.Exclude
			params.FilterDescendantsInstances = { self.humanoid.Parent :: Instance }
			for _, a in { 0, 0.6, -0.6, 1.2, -1.2 } do
				local d = (CFrame.Angles(0, a, 0) * CFrame.new(dir)).Position
				if not workspace:Raycast(pos, d * 10, params) then
					dir = d
					break
				end
			end
			self.humanoid:MoveTo(pos + dir * 20)
		end
		if self.failed < 3 and math.random() < 0.05 then
			self:_request()
		end
		return
	end
	local wp = self.waypoints[self.index]
	if not wp then
		-- leg finished: request the next leg (long trips)
		self:_request()
		return
	end
	local flat = Vector3.new(wp.Position.X - pos.X, 0, wp.Position.Z - pos.Z)
	if flat.Magnitude < 5 then
		self.index += 1
		wp = self.waypoints[self.index]
		if not wp then
			self:_request()
			return
		end
	end
	if wp.Action == Enum.PathWaypointAction.Jump then
		self.humanoid.Jump = true
	end
	self.humanoid:MoveTo(wp.Position)
end

return Navigator
