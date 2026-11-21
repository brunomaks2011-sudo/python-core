--!strict
-- Network contract between client and server. The server creates every remote
-- in ReplicatedStorage.Remotes; clients wait for them. The server validates
-- everything it receives - clients can never write match state, timers or
-- objective ownership (those live on the server and replicate read-only via
-- attributes on ReplicatedStorage.MatchState).

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Net = {}

-- client -> server
Net.Events = {
	"Deploy", -- {team, role, spawnId, vehicleKind?}
	"Fire", -- weapon shots batch
	"Reload",
	"SwitchWeapon",
	"Throw", -- grenade / charge
	"Detonate",
	"UseTool", -- medkit / ammo / repair / binoculars
	"Stance",
	"Sprint",
	"Interact", -- enter/exit/switch seat
	"VehicleAim", -- gunner aim (yaw/pitch) for seats that are not the physics owner
	"VehicleFire",
	"VehicleToggle", -- lights / engine
	"Spot",
	"ArtilleryCall",
	"RequestRestart",
	"ChangeSettings", -- bot count / time of day / weather (host only)
	-- server -> client
	"MatchEvent", -- capture/neutralise/contested/victory/kill feed/notifications
	"Effect", -- tracers, impacts, explosions, debris bursts, muzzle flashes from others
	"Hitmarker",
	"DamageTaken",
	"Radio", -- radio voice line cue
}

Net.Functions = {
	"GetScoreboard",
	"GetDeployOptions",
	"GetMatchSummary",
}

-- high-frequency, loss-tolerant
Net.Unreliable = {
	"Radar", -- minimap: friendly + spotted units
	"VehicleState", -- turret angles of vehicles owned by others
}

local folder: Folder? = nil

local function getFolder(): Folder
	if folder then
		return folder
	end
	if RunService:IsServer() then
		local f = ReplicatedStorage:FindFirstChild("Remotes") :: Folder?
		if not f then
			local created = Instance.new("Folder")
			created.Name = "Remotes"
			created.Parent = ReplicatedStorage
			f = created
		end
		folder = f
	else
		folder = ReplicatedStorage:WaitForChild("Remotes") :: Folder
	end
	return folder :: Folder
end

function Net.setupServer()
	local f = getFolder()
	for _, name in Net.Events do
		if not f:FindFirstChild(name) then
			local r = Instance.new("RemoteEvent")
			r.Name = name
			r.Parent = f
		end
	end
	for _, name in Net.Functions do
		if not f:FindFirstChild(name) then
			local r = Instance.new("RemoteFunction")
			r.Name = name
			r.Parent = f
		end
	end
	for _, name in Net.Unreliable do
		if not f:FindFirstChild(name) then
			local r = Instance.new("UnreliableRemoteEvent")
			r.Name = name
			r.Parent = f
		end
	end
end

function Net.event(name: string): RemoteEvent
	return getFolder():WaitForChild(name) :: RemoteEvent
end

function Net.func(name: string): RemoteFunction
	return getFolder():WaitForChild(name) :: RemoteFunction
end

function Net.unreliable(name: string): UnreliableRemoteEvent
	return getFolder():WaitForChild(name) :: UnreliableRemoteEvent
end

-- The replicated, read-only match state container (attributes).
function Net.matchState(): Folder
	if RunService:IsServer() then
		local f = ReplicatedStorage:FindFirstChild("MatchState") :: Folder?
		if not f then
			local created = Instance.new("Folder")
			created.Name = "MatchState"
			created.Parent = ReplicatedStorage
			f = created
		end
		return f :: Folder
	end
	return ReplicatedStorage:WaitForChild("MatchState") :: Folder
end

-- Simple per-player rate limiter for remotes (weak keys: players who leave
-- are forgotten).
function Net.rateLimiter(maxPerSecond: number)
	local buckets: { [Player]: { t: number, n: number } } = setmetatable({}, { __mode = "k" }) :: any
	return function(player: Player): boolean
		local now = os.clock()
		local b = buckets[player]
		if not b or now - b.t >= 1 then
			buckets[player] = { t = now, n = 1 }
			return true
		end
		b.n += 1
		return b.n <= maxPerSecond
	end
end

return Net
