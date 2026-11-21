--!strict
-- Pure server-authority rules (no Roblox services), unit-tested with Lune in
-- Tests/unit/AntiCheat.spec.luau and used by the server's remote handlers.

local AntiCheat = {}

-- Movement: may something move from `from` to `to` in `dt` seconds, given its
-- horizontal and upward speed limits (studs/s) and a fixed slack in studs?
-- Falling is unlimited; NaN positions are never legal.
function AntiCheat.movementLegal(from: Vector3, to: Vector3, dt: number, horizontal: number, rise: number, slack: number): boolean
	if to ~= to or from ~= from then
		return false
	end
	local d = to - from
	local h = math.sqrt(d.X * d.X + d.Z * d.Z)
	return h <= horizontal * dt + slack and d.Y <= rise * dt + slack
end

-- Rate of fire as a token bucket: tokens refill at one per `interval` seconds
-- since `last` and never exceed `cap`. A shot spends one token.
function AntiCheat.refillTokens(tokens: number?, last: number, now: number, interval: number, cap: number): number
	local elapsed = math.max(0, now - last)
	return math.min(cap, (tokens or cap) + elapsed / interval)
end

-- Lag-compensated hit claims: a client says its shot from `origin` along
-- `dir` hit a part at `claimedPos`. Accept only if that point lies on the ray
-- (within `rayTolerance`), in front of the muzzle and within range, no farther
-- than the server's own ray reached (+6 studs), and the part on the server is
-- still close to the point (its size, plus how far it could have moved).
function AntiCheat.claimConsistent(origin: Vector3, dir: Vector3, claimedPos: Vector3, partPos: Vector3, partSize: number, partSpeed: number, range: number, serverDist: number): boolean
	if dir.Magnitude < 1e-3 then
		return false
	end
	local unit = dir.Unit
	local rel = claimedPos - origin
	local along = rel:Dot(unit)
	if along <= 0 or rel.Magnitude > range or rel.Magnitude > serverDist + 6 then
		return false
	end
	local offRay = (rel - unit * along).Magnitude
	if offRay > 2.5 then
		return false
	end
	local drift = (partPos - claimedPos).Magnitude
	return drift <= partSize * 0.5 + 6 + partSpeed * 0.35
end

-- Team balance for human players: joining a team is refused while it already
-- has two or more players more than the other team.
function AntiCheat.teamOpen(sameTeam: number, otherTeam: number): boolean
	return sameTeam - otherTeam < 2
end

return AntiCheat
