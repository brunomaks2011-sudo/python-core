--!strict
-- Vehicle movement shared by the client (when a player drives and owns the
-- physics) and the server (AI drivers / empty vehicles).
--
-- Constraint-driven so it is stable at Roblox's 240 Hz solver rate:
--   * a VectorForce spring holds the hull at ride height above the ground
--     (average of 4 suspension raycasts),
--   * an AlignOrientation tilts the hull to the ground normal and applies the
--     steering yaw (tracks pivot on the spot, wheels need speed),
--   * a LinearVelocity (planar, force limited by traction) drives the hull.
-- Helicopters use the same movers in 3D with an arcade flight model.

local VehiclePhysics = {}

export type Input = {
	throttle: number, -- -1..1 (W/S)
	steer: number, -- -1..1 (A/D)
	brake: boolean,
	lift: number, -- helicopters: -1..1 (Space / Ctrl)
	yaw: number, -- helicopters: -1..1 (Q/E)
}

export type State = {
	def: { [string]: any },
	hull: BasePart,
	att: Attachment,
	force: VectorForce,
	align: AlignOrientation,
	linear: LinearVelocity,
	yaw: number,
	speed: number,
	grounded: boolean,
	rotorSpin: number, -- 0..1 helicopter rotor spool
	params: RaycastParams,
	lastGroundY: number,
	engineOn: boolean,
}

local function horizontal(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

local function yawOf(cf: CFrame): number
	local look = cf.LookVector
	return math.atan2(-look.X, -look.Z)
end

-- Create the movers on a vehicle hull (server, once when spawned).
function VehiclePhysics.setup(hull: BasePart, def: { [string]: any }): State
	local att = hull:FindFirstChild("VPAttachment") :: Attachment?
	if not att then
		local a = Instance.new("Attachment")
		a.Name = "VPAttachment"
		a.Parent = hull
		att = a
	end
	local force = hull:FindFirstChild("VPForce") :: VectorForce?
	if not force then
		local f = Instance.new("VectorForce")
		f.Name = "VPForce"
		f.Attachment0 = att
		f.RelativeTo = Enum.ActuatorRelativeTo.World
		f.ApplyAtCenterOfMass = true
		f.Force = Vector3.zero
		f.Parent = hull
		force = f
	end
	local align = hull:FindFirstChild("VPAlign") :: AlignOrientation?
	if not align then
		local a = Instance.new("AlignOrientation")
		a.Name = "VPAlign"
		a.Mode = Enum.OrientationAlignmentMode.OneAttachment
		a.Attachment0 = att
		a.RigidityEnabled = false
		a.Responsiveness = if def.drive == "heli" then 8 else 14
		a.MaxTorque = 0
		a.CFrame = hull.CFrame.Rotation
		a.Parent = hull
		align = a
	end
	local linear = hull:FindFirstChild("VPLinear") :: LinearVelocity?
	if not linear then
		local l = Instance.new("LinearVelocity")
		l.Name = "VPLinear"
		l.Attachment0 = att
		l.RelativeTo = Enum.ActuatorRelativeTo.World
		l.VelocityConstraintMode = Enum.VelocityConstraintMode.Vector
		l.ForceLimitMode = Enum.ForceLimitMode.PerAxis
		l.MaxAxesForce = Vector3.zero
		l.VectorVelocity = Vector3.zero
		l.Parent = hull
		linear = l
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { hull.Parent :: Instance }
	params.IgnoreWater = def.drive ~= "heli"
	return {
		def = def,
		hull = hull,
		att = att :: Attachment,
		force = force :: VectorForce,
		align = align :: AlignOrientation,
		linear = linear :: LinearVelocity,
		yaw = yawOf(hull.CFrame),
		speed = 0,
		grounded = false,
		rotorSpin = 0,
		params = params,
		lastGroundY = hull.Position.Y,
		engineOn = false,
	}
end

-- Re-bind an existing State to the movers (e.g. on the client after it gains ownership).
function VehiclePhysics.bind(hull: BasePart, def: { [string]: any }): State
	return VehiclePhysics.setup(hull, def)
end

local NEUTRAL: Input = { throttle = 0, steer = 0, brake = true, lift = 0, yaw = 0 }
VehiclePhysics.NEUTRAL = NEUTRAL

-- Suspension rays: returns grounded, average normal, average ground distance below the hull centre.
local function probe(state: State)
	local hull = state.hull
	local cf = hull.CFrame
	local size = state.def.size :: Vector3
	local hx, hz = size.X * 0.4, size.Z * 0.42
	local reach = state.def.clearance + (state.def.suspension or 1.2) + size.Y * 0.5 + 2.5
	local hits = 0
	local nsum = Vector3.zero
	local dsum = 0
	for _, off in { Vector3.new(hx, 0, hz), Vector3.new(-hx, 0, hz), Vector3.new(hx, 0, -hz), Vector3.new(-hx, 0, -hz) } do
		local origin = cf:PointToWorldSpace(off)
		local result = workspace:Raycast(origin, Vector3.new(0, -reach, 0), state.params)
		if result then
			hits += 1
			nsum += result.Normal
			dsum += origin.Y - result.Position.Y
		end
	end
	if hits == 0 then
		return false, Vector3.yAxis, math.huge
	end
	return hits >= 2, (nsum / hits).Unit, dsum / hits
end

function VehiclePhysics.step(state: State, input: Input?, dt: number)
	local def = state.def
	local hull = state.hull
	if not hull.Parent then
		return
	end
	local inp = input or NEUTRAL
	local mass = hull.AssemblyMass
	local g = workspace.Gravity
	local vel = hull.AssemblyLinearVelocity
	local cf = hull.CFrame

	if def.drive == "heli" then
		local spool = if state.engineOn then 1 else 0
		state.rotorSpin += (spool - state.rotorSpin) * math.min(1, dt * 0.35)
		local power = state.rotorSpin
		state.yaw += (inp.yaw ~= 0 and -inp.yaw or -inp.steer * 0.6) * def.turnRate * dt * power
		local fwd = Vector3.new(-math.sin(state.yaw), 0, -math.cos(state.yaw))
		local right = Vector3.new(math.cos(state.yaw), 0, -math.sin(state.yaw))
		local grounded, _, groundDist = probe(state)
		state.grounded = grounded and groundDist < def.size.Y * 0.5 + 3
		local target = fwd * (inp.throttle * def.maxSpeed) + right * (inp.steer * def.maxSpeed * 0.25)
		local climb = inp.lift * def.climb
		if state.grounded and inp.lift <= 0 and math.abs(inp.throttle) < 0.1 then
			climb = math.min(climb, 0)
		end
		local desired = Vector3.new(target.X, climb, target.Z)
		state.linear.VectorVelocity = desired * power
		local fmax = mass * (def.accel + g) * power
		state.linear.MaxAxesForce = Vector3.new(fmax, fmax * 1.4, fmax)
		state.force.Force = Vector3.zero
		local pitch = -inp.throttle * 0.28 * power
		local roll = -inp.steer * 0.25 * power
		state.align.MaxTorque = mass * 900
		state.align.CFrame = CFrame.Angles(0, state.yaw, 0) * CFrame.Angles(pitch, 0, roll)
		state.speed = horizontal(vel).Magnitude
		return
	end

	-- ground vehicles ------------------------------------------------------------
	local grounded, normal, groundDist = probe(state)
	state.grounded = grounded
	local rideHeight = def.size.Y * 0.5 + def.clearance
	local fwdFlat = horizontal(cf.LookVector)
	if fwdFlat.Magnitude < 1e-3 then
		fwdFlat = Vector3.new(-math.sin(state.yaw), 0, -math.cos(state.yaw))
	end
	fwdFlat = fwdFlat.Unit
	local fwdSpeed = vel:Dot(fwdFlat)
	state.speed = fwdSpeed

	if grounded then
		-- spring-damper toward ride height
		local compression = rideHeight - groundDist
		local k = mass * g * 6 / math.max(0.5, def.suspension or 1.2)
		local c = 2 * math.sqrt(k * mass) * 0.9
		local up = math.clamp(mass * g + k * compression - c * vel.Y, 0, mass * g * 4)
		state.force.Force = Vector3.new(0, up, 0)

		-- steering
		local tracked = def.drive == "tracked"
		local steerInput = inp.steer
		local yawRate
		if tracked then
			yawRate = -steerInput * def.turnRate * (if fwdSpeed < -0.5 then -1 else 1)
		else
			local speedFactor = math.clamp(math.abs(fwdSpeed) / (def.maxSpeed * 0.25), 0, 1)
			yawRate = -steerInput * def.turnRate * speedFactor * (if fwdSpeed < 0 then -1 else 1)
		end
		state.yaw += yawRate * dt
		-- orientation: yaw + ground normal
		local yawCF = CFrame.Angles(0, state.yaw, 0)
		local look = yawCF.LookVector
		local rightV = look:Cross(normal)
		if rightV.Magnitude > 1e-3 then
			rightV = rightV.Unit
			local fwdOnGround = normal:Cross(rightV).Unit
			state.align.CFrame = CFrame.fromMatrix(Vector3.zero, rightV, normal, -fwdOnGround)
		else
			state.align.CFrame = yawCF
		end
		state.align.MaxTorque = mass * 2500

		-- drive
		local target
		if state.engineOn and inp.throttle > 0.05 then
			target = def.maxSpeed * inp.throttle
		elseif state.engineOn and inp.throttle < -0.05 then
			target = -def.reverseSpeed * -inp.throttle
		else
			target = 0
		end
		if inp.brake and math.abs(inp.throttle) < 0.05 then
			target = 0
		end
		local newFwd = fwdSpeed + math.clamp(target - fwdSpeed, -def.accel * 2.2 * dt, def.accel * dt)
		if target == 0 then
			newFwd = fwdSpeed + math.clamp(-fwdSpeed, -def.accel * 1.6 * dt, def.accel * 1.6 * dt)
		end
		local dir = Vector3.new(-math.sin(state.yaw), 0, -math.cos(state.yaw))
		local desired = dir * newFwd
		state.linear.VectorVelocity = Vector3.new(desired.X, 0, desired.Z)
		-- traction: limits how hard the tracks/tyres can push (slopes, collisions)
		local traction = mass * (def.accel * 2.5 + 30)
		state.linear.MaxAxesForce = Vector3.new(traction, 0, traction)
		state.lastGroundY = hull.Position.Y - groundDist
	else
		-- airborne: let gravity act, keep a gentle upright bias
		state.force.Force = Vector3.zero
		state.linear.MaxAxesForce = Vector3.zero
		state.align.MaxTorque = mass * 150
		state.align.CFrame = CFrame.Angles(0, state.yaw, 0)
	end
end

-- Neutral state for an unattended vehicle (handbrake, engine off).
function VehiclePhysics.park(state: State)
	state.engineOn = false
	VehiclePhysics.step(state, NEUTRAL, 1 / 30)
end

return VehiclePhysics
