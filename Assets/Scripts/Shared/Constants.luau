--!strict
-- Shared constants for BLUE vs RED: Three Flags Domination.
-- Scale: 3 studs = 1 metre (character ~5.5 studs, tank ~29 studs long).

local Constants = {}

Constants.STUDS_PER_METER = 3

Constants.TEAM = table.freeze({ NONE = 0, BLUE = 1, RED = 2 })
Constants.TEAMS = table.freeze({ 1, 2 })
Constants.TEAM_NAME = table.freeze({ [0] = "NEUTRAL", [1] = "BLUE", [2] = "RED" })
Constants.TEAM_ARMY = table.freeze({ [0] = "Neutral", [1] = "Blue Army", [2] = "Red Army" })
Constants.TEAM_OBJECT_NAME = table.freeze({ [1] = "Blue Army", [2] = "Red Army" })
Constants.TEAM_COLOR = table.freeze({
	[0] = Color3.fromRGB(205, 208, 214),
	[1] = Color3.fromRGB(47, 123, 255),
	[2] = Color3.fromRGB(255, 59, 48),
})
Constants.TEAM_COLOR_DARK = table.freeze({
	[0] = Color3.fromRGB(70, 72, 78),
	[1] = Color3.fromRGB(16, 44, 104),
	[2] = Color3.fromRGB(104, 18, 14),
})

function Constants.enemyOf(team: number): number
	if team == 1 then
		return 2
	elseif team == 2 then
		return 1
	end
	return 0
end

-- Fixed simulation tick for match logic. Timers are integer ticks so the
-- 1000-second victory is exact.
Constants.MATCH_TICK_RATE = 10

Constants.DOMINATION = table.freeze({
	VICTORY_SECONDS = 1000,
	-- one soldier: neutral -> captured in 30 s (enemy point: neutralise 30 s, then capture 30 s)
	CAPTURE_SECONDS = 30,
	CAPTURE_BONUS_PER_SOLDIER = 0.2,
	CAPTURE_MAX_MULTIPLIER = 1.8,
	REGEN_SECONDS = 60,
	ZONE_HEIGHT = 54, -- studs above the flag base that still count (no aircraft)
	ZONE_DEPTH = 18,
})

Constants.MATCH_STATE = table.freeze({
	WARMUP = "warmup",
	LIVE = "live",
	ENDED = "ended",
})

Constants.STANCE = table.freeze({ STAND = 0, CROUCH = 1, PRONE = 2 })

Constants.SOLDIER = table.freeze({
	MAX_HEALTH = 100,
	WALK_SPEED = 12,
	RUN_SPEED = 16,
	SPRINT_SPEED = 23,
	CROUCH_SPEED = 8,
	PRONE_SPEED = 3,
	STAMINA = 8, -- seconds of sprint
	STAMINA_REGEN = 0.6, -- per second, fraction of max
	SPAWN_PROTECTION = 4,
	RESPAWN_DELAY = 6,
	OUT_OF_BOUNDS_GRACE = 10,
	HIP_HEIGHT = { [0] = 2.0, [1] = 1.15, [2] = 0.25 },
})

return table.freeze(Constants)
