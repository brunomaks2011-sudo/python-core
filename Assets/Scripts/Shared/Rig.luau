--!strict
-- Assembles models exported by the Blender pipeline (BlenderProjects/Scripts/rbxlib.py).
--
-- Exported structure: every group is a Model containing a "Pivot" part at the
-- group origin. Rig.assemble() welds each group's parts to its Pivot and joins
-- child groups to their parent group with a Motor6D named after the group
-- ("Turret", "Gun", "WheelL1", "Rotor", "DoorL1", ...). Clients animate those
-- joints through Motor6D.Transform (local, smooth); the server never needs to.

local Rig = {}

export type Rigged = {
	model: Model,
	root: BasePart,
	pivot: BasePart,
	joints: { [string]: Motor6D },
	groups: { [string]: Model },
	attachments: { [string]: Attachment },
	seats: { Seat },
}

local function setPhysical(part: BasePart, anchored: boolean)
	part.Anchored = anchored
end

function Rig.assemble(model: Model, anchored: boolean?): Rigged
	local rootPivot = model:FindFirstChild("Pivot") :: BasePart
	assert(rootPivot and rootPivot:IsA("BasePart"), "model " .. model.Name .. " has no Pivot")
	local hitbox = model:FindFirstChild("Hitbox")
	local root: BasePart = if hitbox and hitbox:IsA("BasePart") then hitbox else rootPivot
	local joints: { [string]: Motor6D } = {}
	local groups: { [string]: Model } = {}
	local attachments: { [string]: Attachment } = {}
	local seats: { Seat } = {}

	local function visit(group: Instance, pivot: BasePart)
		for _, child in group:GetChildren() do
			if child:IsA("BasePart") then
				if child ~= pivot then
					local w = Instance.new("WeldConstraint")
					w.Part0 = pivot
					w.Part1 = child
					w.Parent = pivot
				end
				setPhysical(child, false)
				if child:IsA("Seat") then
					table.insert(seats, child)
				end
			elseif child:IsA("Model") then
				local cp = child:FindFirstChild("Pivot")
				if cp and cp:IsA("BasePart") then
					local m6 = Instance.new("Motor6D")
					m6.Name = child.Name
					m6.Part0 = pivot
					m6.Part1 = cp
					m6.C0 = pivot.CFrame:ToObjectSpace(cp.CFrame)
					m6.C1 = CFrame.identity
					m6.Parent = pivot
					joints[child.Name] = m6
					groups[child.Name] = child
					visit(child, cp)
				end
			end
		end
		for _, a in pivot:GetChildren() do
			if a:IsA("Attachment") then
				attachments[a.Name] = a
			end
		end
	end
	visit(model, rootPivot)
	if root ~= rootPivot then
		root.RootPriority = 127
	end
	-- order seats by name (Seat1, Seat2, ...)
	table.sort(seats, function(a, b)
		local na = tonumber(string.match(a.Name, "%d+")) or 0
		local nb = tonumber(string.match(b.Name, "%d+")) or 0
		return na < nb
	end)
	model.PrimaryPart = rootPivot
	if anchored then
		root.Anchored = true
		rootPivot.Anchored = true
	end
	return { model = model, root = root, pivot = rootPivot, joints = joints, groups = groups, attachments = attachments, seats = seats }
end

-- For static props / buildings: anchor every part, no joints (cheap).
function Rig.anchorAll(model: Model, collide: boolean?)
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") then
			d.Anchored = true
			if d.Name == "Pivot" then
				d.CanCollide = false
				d.CanQuery = false
			elseif collide ~= nil then
				d.CanCollide = collide and d.Transparency < 0.95
			end
			d.Massless = false
		end
	end
	local p = model:FindFirstChild("Pivot")
	if p and p:IsA("BasePart") then
		model.PrimaryPart = p
	end
end

-- Recolour parts named Team* (gear, tents, flags) to a colour.
function Rig.tint(model: Instance, prefix: string, color: Color3)
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") and string.sub(d.Name, 1, #prefix) == prefix then
			d.Color = color
		end
	end
end

-- World CFrame of an attachment by name anywhere in a rigged model.
function Rig.findAttachment(model: Instance, name: string): Attachment?
	for _, d in model:GetDescendants() do
		if d:IsA("Attachment") and d.Name == name then
			return d
		end
	end
	return nil
end

function Rig.findGroup(model: Instance, name: string): Model?
	for _, d in model:GetDescendants() do
		if d:IsA("Model") and d.Name == name and d:FindFirstChild("Pivot") then
			return d
		end
	end
	return nil
end

-- Scale a gear model so that it fits a body part (uniform scale).
function Rig.fitScale(model: Model, factor: number)
	if math.abs(factor - 1) > 0.01 then
		model:ScaleTo(factor)
	end
end

return Rig
