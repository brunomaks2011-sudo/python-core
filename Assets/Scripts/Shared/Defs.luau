--!strict
-- Gameplay definitions for two fictional armies. Values are authored in metres
-- and metres/second for readability and converted to studs (x3) on load.

local Defs = {}

local S = 3 -- studs per metre
local function m(v: number): number
	return v * S
end

-- ---------------------------------------------------------------------------
-- Infantry weapons
-- kind: hitscan | projectile | throw | tool
-- falloff = {start(m), end(m), minMultiplier}
-- ---------------------------------------------------------------------------
local W: { [string]: any } = {}

local function gun(t: { [string]: any }): any
	t.range = m(t.range)
	t.falloff = { m(t.falloff[1]), m(t.falloff[2]), t.falloff[3] }
	t.kind = "hitscan"
	t.headMul = t.headMul or 2.0
	return t
end

-- Blue Army
W.b_rifle = gun({ name = "VK-5 Assault Rifle", side = 1, slot = 1, damage = 26, headMul = 2.2, rpm = 720, mag = 30, reserve = 180, reload = 2.3, spread = 0.0045, adsSpread = 0.0012, recoil = 0.011, range = 450, falloff = { 60, 220, 0.6 }, model = "Rifle_Blue", sound = "rifle", structDmg = 2, auto = true })
W.b_carbine = gun({ name = "VK-5C Carbine", side = 1, slot = 1, damage = 24, rpm = 780, mag = 30, reserve = 180, reload = 2.1, spread = 0.0055, adsSpread = 0.0016, recoil = 0.010, range = 350, falloff = { 45, 180, 0.6 }, model = "Carbine_Blue", sound = "rifle", structDmg = 2, auto = true })
W.b_lmg = gun({ name = "VM-60 Light Machine Gun", side = 1, slot = 1, damage = 24, rpm = 820, mag = 100, reserve = 300, reload = 5.2, spread = 0.008, adsSpread = 0.0028, recoil = 0.009, range = 450, falloff = { 60, 250, 0.65 }, model = "LMG_Blue", sound = "lmg", structDmg = 3, auto = true })
W.b_dmr = gun({ name = "VS-11 Marksman Rifle", side = 1, slot = 1, damage = 62, headMul = 2.5, rpm = 160, mag = 10, reserve = 50, reload = 2.8, spread = 0.002, adsSpread = 0.0002, recoil = 0.03, range = 900, falloff = { 200, 700, 0.75 }, scope = 4, model = "DMR_Blue", sound = "sniper", structDmg = 4 })
W.b_smg = gun({ name = "VP-9 Submachine Gun", side = 1, slot = 1, damage = 20, headMul = 1.8, rpm = 900, mag = 32, reserve = 192, reload = 1.9, spread = 0.007, adsSpread = 0.0025, recoil = 0.007, range = 200, falloff = { 25, 90, 0.5 }, model = "SMG_Blue", sound = "smg", structDmg = 1, auto = true })
-- Red Army
W.r_rifle = gun({ name = "SR-7 Assault Rifle", side = 2, slot = 1, damage = 28, headMul = 2.2, rpm = 650, mag = 30, reserve = 180, reload = 2.4, spread = 0.005, adsSpread = 0.0014, recoil = 0.013, range = 450, falloff = { 60, 220, 0.6 }, model = "Rifle_Red", sound = "rifle", structDmg = 2, auto = true })
W.r_carbine = gun({ name = "SR-7U Carbine", side = 2, slot = 1, damage = 25, rpm = 700, mag = 30, reserve = 180, reload = 2.2, spread = 0.006, adsSpread = 0.0018, recoil = 0.012, range = 350, falloff = { 45, 180, 0.6 }, model = "Carbine_Red", sound = "rifle", structDmg = 2, auto = true })
W.r_lmg = gun({ name = "SP-12 Light Machine Gun", side = 2, slot = 1, damage = 26, rpm = 700, mag = 100, reserve = 300, reload = 5.6, spread = 0.0085, adsSpread = 0.003, recoil = 0.011, range = 450, falloff = { 60, 250, 0.65 }, model = "LMG_Red", sound = "lmg", structDmg = 3, auto = true })
W.r_dmr = gun({ name = "SD-3 Marksman Rifle", side = 2, slot = 1, damage = 66, headMul = 2.5, rpm = 140, mag = 10, reserve = 50, reload = 3.0, spread = 0.002, adsSpread = 0.0002, recoil = 0.034, range = 900, falloff = { 200, 700, 0.75 }, scope = 4, model = "DMR_Red", sound = "sniper", structDmg = 4 })
W.r_smg = gun({ name = "SK-9 Submachine Gun", side = 2, slot = 1, damage = 21, headMul = 1.8, rpm = 850, mag = 30, reserve = 180, reload = 2.0, spread = 0.0075, adsSpread = 0.0026, recoil = 0.008, range = 200, falloff = { 25, 90, 0.5 }, model = "SMG_Red", sound = "smg", structDmg = 1, auto = true })
-- Shared
W.pistol = gun({ name = "M-17 Sidearm", side = 0, slot = 2, damage = 30, rpm = 380, mag = 15, reserve = 60, reload = 1.6, spread = 0.006, adsSpread = 0.003, recoil = 0.02, range = 120, falloff = { 20, 70, 0.55 }, model = "Pistol", sound = "pistol", structDmg = 1 })

W.grenade = { name = "Frag Grenade", kind = "throw", slot = 4, count = 2, fuse = 3.2, speed = m(17), damage = 140, radius = m(7), structDmg = 260, structRadius = m(4), model = "Grenade", sound = "grenade" }
W.c4 = { name = "Demolition Charge", kind = "throw", slot = 4, count = 2, speed = m(8), damage = 300, vehicleDamage = 900, radius = m(6), structDmg = 2400, structRadius = m(4.5), remote = true, model = "C4", sound = "explosion_big" }
W.rpg = { name = "PG-9 Rocket Launcher", kind = "projectile", slot = 2, count = 4, mag = 1, reserve = 3, speed = m(140), gravityScale = 0.15, damage = 120, vehicleDamage = 520, radius = m(4), structDmg = 650, structRadius = m(3.2), reload = 3.0, model = "RPG", sound = "rpg", projectile = "rocket" }
W.medkit = { name = "Field Medkit", kind = "tool", slot = 3, heal = 45, cooldown = 1.0, uses = 6, range = m(4), model = "Medkit" }
W.ammobox = { name = "Ammo Pouch", kind = "tool", slot = 3, uses = 6, cooldown = 1.0, range = m(4), model = "AmmoBox" }
W.repair = { name = "Repair Torch", kind = "tool", slot = 3, repairPerSec = 55, range = m(5), model = "Wrench" }
W.binoculars = { name = "Laser Binoculars", kind = "tool", slot = 3, zoom = 6, spotRange = m(600), artilleryCooldown = 90, model = "Binoculars" }

Defs.Weapons = W


-- ---------------------------------------------------------------------------
-- Infantry roles
-- ---------------------------------------------------------------------------
Defs.Roles = {
	rifleman = { name = "Rifleman", icon = "R", desc = "Assault rifle and frag grenades. Takes and holds the flags.", loadout = { [1] = { "b_rifle", "pistol", "", "grenade" }, [2] = { "r_rifle", "pistol", "", "grenade" } }, speed = 1.0 },
	medic = { name = "Medic", icon = "M", desc = "Carbine and a field medkit. Heals wounded teammates.", loadout = { [1] = { "b_carbine", "pistol", "medkit", "grenade" }, [2] = { "r_carbine", "pistol", "medkit", "grenade" } }, speed = 1.0 },
	engineer = { name = "Engineer", icon = "E", desc = "SMG, rocket launcher, repair torch and demolition charges. Kills armour, fixes vehicles.", loadout = { [1] = { "b_smg", "rpg", "repair", "c4" }, [2] = { "r_smg", "rpg", "repair", "c4" } }, speed = 0.97 },
	support = { name = "Support", icon = "S", desc = "Light machine gun and an ammo pouch. Suppresses and resupplies.", loadout = { [1] = { "b_lmg", "pistol", "ammobox", "grenade" }, [2] = { "r_lmg", "pistol", "ammobox", "grenade" } }, speed = 0.92 },
	recon = { name = "Reconnaissance", icon = "K", desc = "Marksman rifle and laser binoculars. Spots enemies and calls rocket artillery.", loadout = { [1] = { "b_dmr", "pistol", "binoculars", "grenade" }, [2] = { "r_dmr", "pistol", "binoculars", "grenade" } }, speed = 1.03 },
	crew = { name = "Vehicle Crew", icon = "V", desc = "Carbine and repair torch. Deploys straight into a vehicle and keeps it running.", loadout = { [1] = { "b_carbine", "pistol", "repair" }, [2] = { "r_carbine", "pistol", "repair" } }, speed = 1.0 },
}
Defs.RoleOrder = { "rifleman", "medic", "engineer", "support", "recon", "crew" }

-- ---------------------------------------------------------------------------
-- Vehicles. drive: tracked | wheeled | heli. Seats in order; seat 1 = driver.
-- Model names refer to ReplicatedStorage.Assets.Models.Vehicles.*
-- ---------------------------------------------------------------------------
local function shell(t: { [string]: any }): any
	t.kind = t.kind or "shell"
	t.speed = m(t.speed)
	t.radius = m(t.radius or 0)
	t.structRadius = m(t.structRadius or 0)
	return t
end
local function mg(t: { [string]: any }): any
	t.kind = "hitscan"
	t.range = m(t.range)
	t.falloff = { m(80), m(t.range / S * 0.8), 0.7 }
	t.headMul = 1.5
	return t
end

local V: { [string]: any } = {}
local function S(t: { [string]: any }): any
	return t
end
V.mbt = {
	category = "Main Battle Tank", names = { [1] = "BV-90 Warden", [2] = "RT-88 Vulkan" }, model = { [1] = "MBT_Blue", [2] = "MBT_Red" },
	drive = "tracked", mass = 52000, hp = 1600, armor = 0.35, maxSpeed = m(17), reverseSpeed = m(6), accel = m(3.4), turnRate = 0.75,
	size = Vector3.new(m(3.6), m(2.4), m(9.6)), clearance = m(0.45), suspension = m(0.45),
	turret = { yawSpeed = 0.7, pitchMin = -0.12, pitchMax = 0.35 },
	weapons = {
		shell({ name = "125mm Main Gun", damage = 260, vehicleDamage = 780, radius = 5.5, structDmg = 1400, structRadius = 4.2, speed = 900, gravityScale = 0.2, reload = 4.2, muzzle = "Muzzle", sound = "tank_gun", recoil = 1 }),
		mg({ name = "Coaxial MG", damage = 22, rpm = 700, spread = 0.004, range = 500, muzzle = "MuzzleCoax", sound = "mg", structDmg = 3 }),
	},
	seats = {
		S({ role = "driver", weapons = { 1, 2 }, camera = "gunner", hidden = true }),
		S({ role = "gunner", name = "Commander MG", weapons = { mg({ name = "Heavy MG", damage = 34, rpm = 520, spread = 0.005, range = 600, muzzle = "MuzzleCupola", sound = "hmg", structDmg = 6 }) }, aimNode = "Cupola", camera = "mg" }),
	},
	respawn = 90, canCapture = true, crush = true, engineSound = "engine_tank",
}
V.ifv = {
	category = "Infantry Fighting Vehicle", names = { [1] = "BX-40 Lancer", [2] = "RK-3 Kurgan" }, model = { [1] = "IFV_Blue", [2] = "IFV_Red" },
	drive = "tracked", mass = 26000, hp = 1050, armor = 0.5, maxSpeed = m(19), reverseSpeed = m(7), accel = m(4.2), turnRate = 0.95,
	size = Vector3.new(m(3.3), m(2.3), m(7.4)), clearance = m(0.42), suspension = m(0.45),
	turret = { yawSpeed = 1.1, pitchMin = -0.15, pitchMax = 0.9 },
	weapons = {
		shell({ name = "30mm Autocannon", damage = 55, vehicleDamage = 70, radius = 2.0, structDmg = 160, structRadius = 1.6, speed = 1000, gravityScale = 0.2, reload = 0.22, mag = 50, magReload = 5, muzzle = "Muzzle", sound = "autocannon" }),
		shell({ name = "ATGM", kind = "missile", damage = 150, vehicleDamage = 700, radius = 3.5, structDmg = 900, structRadius = 3, speed = 160, gravityScale = 0, reload = 12, muzzle = "MuzzleATGM", sound = "rocket" }),
	},
	seats = { S({ role = "driver", weapons = { 1, 2 }, camera = "gunner", hidden = true }), S({ role = "passenger", hidden = true }), S({ role = "passenger", hidden = true }), S({ role = "passenger", hidden = true }), S({ role = "passenger", hidden = true }) },
	respawn = 70, canCapture = true, crush = true, engineSound = "engine_tank",
}
V.apc = {
	category = "Armoured Personnel Carrier", names = { [1] = "BW-8 Badger", [2] = "RB-80 Tur" }, model = { [1] = "APC_Blue", [2] = "APC_Red" },
	drive = "wheeled", axles = 4, mass = 18000, hp = 820, armor = 0.6, maxSpeed = m(25), reverseSpeed = m(8), accel = m(4.4), turnRate = 0.6, maxSteer = 0.5,
	size = Vector3.new(m(2.9), m(2.3), m(7.8)), clearance = m(0.5), suspension = m(0.5), wheelRadius = m(0.62),
	turret = { yawSpeed = 1.6, pitchMin = -0.15, pitchMax = 1.0 },
	weapons = { mg({ name = "14.5mm Heavy MG", damage = 40, vehicleDamage = 14, rpm = 560, spread = 0.004, range = 700, muzzle = "Muzzle", sound = "hmg", structDmg = 8 }) },
	seats = { S({ role = "driver", camera = "driver", hidden = true }), S({ role = "gunner", weapons = { 1 }, camera = "gunner", hidden = true }), S({ role = "passenger", hidden = true }), S({ role = "passenger", hidden = true }), S({ role = "passenger", hidden = true }), S({ role = "passenger", hidden = true }) },
	respawn = 60, canCapture = true, engineSound = "engine_truck", lights = true,
}
V.jeep = {
	category = "Light Utility Vehicle", names = { [1] = "BL-4 Hound", [2] = "RL-31 Kozak" }, model = { [1] = "Jeep_Blue", [2] = "Jeep_Red" },
	drive = "wheeled", axles = 2, mass = 2600, hp = 300, armor = 1.0, maxSpeed = m(31), reverseSpeed = m(10), accel = m(7.5), turnRate = 1.0, maxSteer = 0.6,
	size = Vector3.new(m(2.1), m(1.9), m(4.7)), clearance = m(0.4), suspension = m(0.32), wheelRadius = m(0.42),
	turret = { yawSpeed = 3, pitchMin = -0.2, pitchMax = 0.6 },
	weapons = { mg({ name = "12.7mm MG", damage = 34, rpm = 560, spread = 0.006, range = 600, muzzle = "Muzzle", sound = "hmg", structDmg = 6 }) },
	seats = { S({ role = "driver", camera = "driver" }), S({ role = "gunner", weapons = { 1 }, camera = "mg" }), S({ role = "passenger" }), S({ role = "passenger" }) },
	respawn = 30, canCapture = true, engineSound = "engine_car", lights = true,
}
V.truck = {
	category = "Military Truck", names = { [1] = "BT-6 Mule", [2] = "RT-43 Zubr" }, model = { [1] = "Truck_Blue", [2] = "Truck_Red" },
	drive = "wheeled", axles = 3, mass = 11000, hp = 450, armor = 0.95, maxSpeed = m(24), reverseSpeed = m(8), accel = m(4.0), turnRate = 0.6, maxSteer = 0.55,
	size = Vector3.new(m(2.5), m(3.2), m(8.2)), clearance = m(0.45), suspension = m(0.4), wheelRadius = m(0.55),
	weapons = {},
	seats = { S({ role = "driver", camera = "driver" }), S({ role = "passenger" }), S({ role = "passenger" }), S({ role = "passenger" }), S({ role = "passenger" }), S({ role = "passenger" }), S({ role = "passenger" }), S({ role = "passenger" }) },
	respawn = 45, canCapture = true, engineSound = "engine_truck", lights = true, mobileSpawn = true,
}
V.supply_truck = {
	category = "Supply Truck", names = { [1] = "BT-6S Packhorse", [2] = "RT-43S Oboz" }, model = { [1] = "Supply_Blue", [2] = "Supply_Red" },
	drive = "wheeled", axles = 3, mass = 12000, hp = 420, armor = 0.95, maxSpeed = m(22), reverseSpeed = m(8), accel = m(3.6), turnRate = 0.6, maxSteer = 0.55,
	size = Vector3.new(m(2.5), m(3.2), m(8.2)), clearance = m(0.45), suspension = m(0.4), wheelRadius = m(0.55),
	weapons = {}, aura = { kind = "resupply", radius = m(16) },
	seats = { S({ role = "driver", camera = "driver" }), S({ role = "passenger" }) },
	respawn = 60, canCapture = true, engineSound = "engine_truck", lights = true,
}
V.ambulance = {
	category = "Field Ambulance", names = { [1] = "BA-2 Lifeline", [2] = "RA-9 Sanitar" }, model = { [1] = "Ambulance_Blue", [2] = "Ambulance_Red" },
	drive = "wheeled", axles = 2, mass = 5200, hp = 360, armor = 0.95, maxSpeed = m(27), reverseSpeed = m(9), accel = m(5.0), turnRate = 0.75, maxSteer = 0.58,
	size = Vector3.new(m(2.3), m(2.8), m(6.0)), clearance = m(0.4), suspension = m(0.35), wheelRadius = m(0.48),
	weapons = {}, aura = { kind = "heal", radius = m(14) },
	seats = { S({ role = "driver", camera = "driver" }), S({ role = "passenger" }), S({ role = "passenger" }) },
	respawn = 60, canCapture = true, engineSound = "engine_car", lights = true, mobileSpawn = true,
}
V.mlrs = {
	category = "Rocket Launcher Vehicle", names = { [1] = "BR-12 Thunder", [2] = "RG-122 Grad-K" }, model = { [1] = "MLRS_Blue", [2] = "MLRS_Red" },
	drive = "wheeled", axles = 3, mass = 14000, hp = 520, armor = 0.9, maxSpeed = m(22), reverseSpeed = m(7), accel = m(3.4), turnRate = 0.55, maxSteer = 0.52,
	size = Vector3.new(m(2.6), m(3.1), m(8.6)), clearance = m(0.45), suspension = m(0.4), wheelRadius = m(0.58),
	turret = { yawSpeed = 0.5, pitchMin = 0.1, pitchMax = 0.95, indirect = true },
	weapons = { shell({ name = "122mm Rocket Salvo", kind = "rocket_salvo", count = 12, interval = 0.28, damage = 180, vehicleDamage = 420, radius = 8, structDmg = 1500, structRadius = 6.5, speed = 220, gravityScale = 1, reload = 30, dispersion = m(22), muzzle = "Pod", sound = "mlrs_launch" }) },
	seats = { S({ role = "driver", weapons = { 1 }, camera = "artillery" }), S({ role = "passenger" }) },
	respawn = 120, canCapture = true, engineSound = "engine_truck", lights = true,
}
V.artillery = {
	category = "Self-Propelled Howitzer", names = { [1] = "BH-155 Bastion", [2] = "RS-152 Akatsiya-K" }, model = { [1] = "Artillery_Blue", [2] = "Artillery_Red" },
	drive = "tracked", mass = 38000, hp = 1100, armor = 0.55, maxSpeed = m(15), reverseSpeed = m(5), accel = m(2.8), turnRate = 0.6,
	size = Vector3.new(m(3.4), m(3.0), m(8.4)), clearance = m(0.45), suspension = m(0.45),
	turret = { yawSpeed = 0.4, pitchMin = 0.0, pitchMax = 1.05, indirect = true },
	weapons = { shell({ name = "155mm Howitzer", damage = 300, vehicleDamage = 650, radius = 9, structDmg = 1800, structRadius = 7, speed = 420, gravityScale = 1, reload = 9, muzzle = "Muzzle", sound = "howitzer" }) },
	seats = { S({ role = "driver", weapons = { 1 }, camera = "artillery", hidden = true }) },
	respawn = 120, canCapture = true, crush = true, engineSound = "engine_tank",
}
V.recovery = {
	category = "Armoured Recovery Vehicle", names = { [1] = "BV-90R Tow", [2] = "RT-88R Tyagach" }, model = { [1] = "Recovery_Blue", [2] = "Recovery_Red" },
	drive = "tracked", mass = 46000, hp = 1300, armor = 0.45, maxSpeed = m(15), reverseSpeed = m(6), accel = m(3.0), turnRate = 0.7,
	size = Vector3.new(m(3.5), m(2.6), m(8.8)), clearance = m(0.45), suspension = m(0.45),
	turret = { yawSpeed = 2, pitchMin = -0.2, pitchMax = 0.5 },
	weapons = { mg({ name = "7.62mm MG", damage = 22, rpm = 650, spread = 0.006, range = 500, muzzle = "Muzzle", sound = "mg", structDmg = 3 }) },
	aura = { kind = "repair", radius = m(14), rate = 45 },
	seats = { S({ role = "driver", weapons = { 1 }, camera = "driver", hidden = true }), S({ role = "passenger", hidden = true }) },
	respawn = 75, canCapture = true, crush = true, engineSound = "engine_tank",
}
V.comms = {
	category = "Communications Vehicle", names = { [1] = "BC-7 Relay", [2] = "RC-14 Svyaz" }, model = { [1] = "Comms_Blue", [2] = "Comms_Red" },
	drive = "wheeled", axles = 3, mass = 12000, hp = 400, armor = 0.95, maxSpeed = m(23), reverseSpeed = m(8), accel = m(3.8), turnRate = 0.6, maxSteer = 0.55,
	size = Vector3.new(m(2.5), m(3.3), m(8.0)), clearance = m(0.45), suspension = m(0.4), wheelRadius = m(0.55),
	weapons = {}, aura = { kind = "radar", radius = m(220) },
	seats = { S({ role = "driver", camera = "driver" }), S({ role = "passenger" }) },
	respawn = 60, canCapture = true, engineSound = "engine_truck", lights = true,
}
V.attack_heli = {
	category = "Attack Helicopter", names = { [1] = "AH-9 Kestrel", [2] = "RH-24 Berkut" }, model = { [1] = "AttackHeli_Blue", [2] = "AttackHeli_Red" },
	drive = "heli", mass = 8000, hp = 950, armor = 0.75, maxSpeed = m(72), accel = m(14), climb = m(11), turnRate = 1.3,
	size = Vector3.new(m(3.2), m(4.2), m(16)), clearance = m(0.2),
	weapons = { shell({ name = "70mm Rocket Pods", kind = "rocket", damage = 95, vehicleDamage = 280, radius = 4.5, structDmg = 700, structRadius = 3.5, speed = 300, gravityScale = 0.1, reload = 0.25, mag = 14, magReload = 10, muzzle = "Pod", sound = "rocket" }) },
	seats = {
		S({ role = "driver", weapons = { 1 }, camera = "chase" }),
		S({ role = "gunner", weapons = { shell({ name = "30mm Chain Gun", damage = 60, vehicleDamage = 55, radius = 2, structDmg = 120, structRadius = 1.5, speed = 900, gravityScale = 0.2, reload = 0.12, muzzle = "ChinGun", sound = "autocannon" }) }, aimNode = "ChinTurret", camera = "gunner" }),
	},
	respawn = 150, canCapture = false, engineSound = "engine_heli",
}
V.transport_heli = {
	category = "Transport Helicopter", names = { [1] = "UH-12 Ferry", [2] = "RT-8 Zhuravl" }, model = { [1] = "TransportHeli_Blue", [2] = "TransportHeli_Red" },
	drive = "heli", mass = 11000, hp = 900, armor = 0.85, maxSpeed = m(62), accel = m(11), climb = m(9), turnRate = 1.0,
	size = Vector3.new(m(3.6), m(4.6), m(18)), clearance = m(0.2),
	weapons = {},
	seats = {
		S({ role = "driver", camera = "chase" }),
		S({ role = "gunner", weapons = { mg({ name = "Door Gun", damage = 26, rpm = 750, spread = 0.008, range = 500, muzzle = "DoorGunL", sound = "mg", structDmg = 3 }) }, aimNode = "DoorGunL", camera = "door" }),
		S({ role = "gunner", weapons = { mg({ name = "Door Gun", damage = 26, rpm = 750, spread = 0.008, range = 500, muzzle = "DoorGunR", sound = "mg", structDmg = 3 }) }, aimNode = "DoorGunR", camera = "door" }),
		S({ role = "passenger" }), S({ role = "passenger" }), S({ role = "passenger" }), S({ role = "passenger" }),
	},
	respawn = 120, canCapture = false, engineSound = "engine_heli", mobileSpawn = true,
}
Defs.Vehicles = V
Defs.VehicleOrder = { "mbt", "ifv", "apc", "jeep", "truck", "supply_truck", "ambulance", "mlrs", "artillery", "recovery", "comms", "attack_heli", "transport_heli" }

function Defs.vehicleName(kind: string, team: number): string
	local d = V[kind]
	if not d then
		return kind
	end
	return d.names[team] or d.names[1]
end

-- Support aircraft flown by the AI (spotting only, unarmed).
Defs.SupportAircraft = {
	drone = { names = { [1] = "RQ-5 Skylark", [2] = "RO-2 Orlan-S" }, model = { [1] = "Drone_Blue", [2] = "Drone_Red" }, speed = m(32), altitude = m(140), spotRadius = m(160), hp = 120 },
	observation = { names = { [1] = "O-3 Lookout", [2] = "RO-9 Yastreb" }, model = { [1] = "Observer_Blue", [2] = "Observer_Red" }, speed = m(48), altitude = m(320), spotRadius = m(230), hp = 300 },
}

-- ---------------------------------------------------------------------------
-- Material durability for destructible pieces and props.
-- ---------------------------------------------------------------------------
Defs.MaterialHP = {
	glass = 4, wood = 220, plaster = 450, brick = 520, concrete = 700, panel = 650, metal = 320, steel = 900, tile = 250, sand = 900, canvas = 120, hay = 120, rock = 5000,
}
-- How much of each damage type a material takes (bullets barely scratch concrete).
Defs.MaterialResist = {
	glass = { bullet = 1, blast = 1 },
	wood = { bullet = 0.5, blast = 1 },
	plaster = { bullet = 0.12, blast = 1 },
	brick = { bullet = 0.08, blast = 1 },
	concrete = { bullet = 0.05, blast = 0.9 },
	panel = { bullet = 0.05, blast = 0.95 },
	metal = { bullet = 0.15, blast = 1 },
	steel = { bullet = 0.02, blast = 0.7 },
	tile = { bullet = 0.3, blast = 1.1 },
	sand = { bullet = 0.02, blast = 0.6 },
	canvas = { bullet = 0.6, blast = 1.2 },
	hay = { bullet = 0.5, blast = 1.2 },
	rock = { bullet = 0, blast = 0.1 },
}

return Defs
