--!strict
-- Client-side shared state between controllers and UI (purely local).

local Util = require(game:GetService("ReplicatedStorage").Shared.Util)

local ClientState = {
	team = 0,
	role = "rifleman",
	deployed = false,
	inMenu = true,
	-- vehicle
	vehicleId = nil :: number?,
	seat = nil :: number?,
	vehicleKind = nil :: string?,
	vehicleModel = nil :: Model?,
	vehicleWeapon = 1,
	vehicleReload = 0, -- 0..1
	cameraMode = "first", -- first | third | chase | gunner | driver | artillery
	-- infantry weapon
	weaponName = "",
	ammoMag = 0,
	ammoReserve = 0,
	equipped = 1,
	reloading = false,
	aiming = false,
	spread = 0,
	stamina = 1,
	stance = 0,
	sprinting = false,
	localAim = {} :: { [number]: { yaw: number, pitch: number } }, -- seat -> local turret aim
	-- settings
	settings = {
		sensitivity = 0.35,
		adsSensitivity = 0.6,
		fov = 80,
		invertY = false,
		masterVolume = 0.8,
		musicVolume = 0.5,
		quality = "high", -- low | medium | high
		showMinimap = true,
	},
	-- signals
	changed = Util.signal(),
	notify = Util.signal(), -- (text, color, sound?)
	killfeed = Util.signal(),
	hit = Util.signal(), -- hitmarker
	damaged = Util.signal(), -- (amount, fromPos)
	cameraShake = Util.signal(), -- (intensity)
}

return ClientState
