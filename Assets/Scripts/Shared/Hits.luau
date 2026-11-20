--!strict
-- Classifies what a raycast hit: a soldier (player or bot), a vehicle, a
-- destructible structure piece, a prop, terrain or other world geometry.

local Hits = {}

export type HitInfo = {
	kind: "soldier" | "vehicle" | "piece" | "prop" | "terrain" | "world",
	soldierId: number?,
	vehicleId: number?,
	pieceId: number?,
	propId: number?,
	part: BasePart,
	bodyPart: string?,
	model: Model?,
}

local function findAttr(inst: Instance?, attr: string, maxDepth: number): (Instance?, any)
	local cur = inst
	local depth = 0
	while cur and depth < maxDepth do
		local v = cur:GetAttribute(attr)
		if v ~= nil then
			return cur, v
		end
		cur = cur.Parent
		depth += 1
	end
	return nil, nil
end

local function asModel(inst: Instance?): Model?
	if inst and inst:IsA("Model") then
		return (inst :: any) :: Model
	end
	return nil
end

function Hits.classify(part: BasePart): HitInfo
	if part:IsA("Terrain") then
		return { kind = "terrain", part = part }
	end
	local sInst, sid = findAttr(part, "SoldierId", 4)
	if sInst and sid then
		return { kind = "soldier", soldierId = sid, part = part, bodyPart = part.Name, model = asModel(sInst) }
	end
	local vInst, vid = findAttr(part, "VehicleId", 7)
	if vInst and vid then
		return { kind = "vehicle", vehicleId = vid, part = part, model = asModel(vInst) }
	end
	local pInst, pid = findAttr(part, "PieceId", 3)
	if pInst and pid then
		return { kind = "piece", pieceId = pid, part = part, model = asModel(pInst) }
	end
	local prInst, prid = findAttr(part, "PropId", 4)
	if prInst and prid then
		return { kind = "prop", propId = prid, part = part, model = asModel(prInst) }
	end
	return { kind = "world", part = part }
end

-- Damage multiplier by R15 body part.
local ZONES = {
	Head = 2.0,
	UpperTorso = 1.0,
	LowerTorso = 0.95,
	HumanoidRootPart = 1.0,
	LeftUpperArm = 0.75, RightUpperArm = 0.75, LeftLowerArm = 0.65, RightLowerArm = 0.65, LeftHand = 0.6, RightHand = 0.6,
	LeftUpperLeg = 0.8, RightUpperLeg = 0.8, LeftLowerLeg = 0.7, RightLowerLeg = 0.7, LeftFoot = 0.6, RightFoot = 0.6,
}

function Hits.zoneMultiplier(bodyPart: string?, headMul: number?): number
	if bodyPart == "Head" or bodyPart == "Handle" then
		return headMul or 2.0
	end
	return ZONES[bodyPart or ""] or 0.9
end

-- Distance falloff: full damage until f[1], linearly down to f[3] at f[2].
function Hits.falloff(distance: number, f: { number }?): number
	if not f then
		return 1
	end
	if distance <= f[1] then
		return 1
	end
	if distance >= f[2] then
		return f[3]
	end
	return 1 - (1 - f[3]) * (distance - f[1]) / (f[2] - f[1])
end

return Hits
