--!strict
-- General helpers shared by server and client (and Lune tests where possible).

local Util = {}

-- ---------------------------------------------------------------------------
-- Math
-- ---------------------------------------------------------------------------
function Util.clamp(v: number, a: number, b: number): number
	return if v < a then a elseif v > b then b else v
end

function Util.lerp(a: number, b: number, t: number): number
	return a + (b - a) * t
end

function Util.smoothstep(a: number, b: number, v: number): number
	local t = Util.clamp((v - a) / (b - a), 0, 1)
	return t * t * (3 - 2 * t)
end

function Util.wrapAngle(a: number): number
	a = (a + math.pi) % (2 * math.pi)
	if a < 0 then
		a += 2 * math.pi
	end
	return a - math.pi
end

function Util.approach(current: number, target: number, step: number): number
	if current < target then
		return math.min(current + step, target)
	end
	return math.max(current - step, target)
end

function Util.approachAngle(current: number, target: number, step: number): number
	local d = Util.wrapAngle(target - current)
	if math.abs(d) <= step then
		return target
	end
	return Util.wrapAngle(current + (if d > 0 then step else -step))
end

function Util.dist2D(ax: number, az: number, bx: number, bz: number): number
	local dx, dz = ax - bx, az - bz
	return math.sqrt(dx * dx + dz * dz)
end

-- Yaw (radians) such that CFrame.Angles(0, yaw, 0).LookVector points along (dx, dz).
function Util.yawFromDir(dx: number, dz: number): number
	return math.atan2(-dx, -dz)
end

function Util.formatTime(seconds: number): string
	seconds = math.max(0, math.floor(seconds))
	return string.format("%02d:%02d", seconds // 60, seconds % 60)
end

function Util.pointInPolygon(x: number, z: number, poly: { { number } }): boolean
	local inside = false
	local j = #poly
	for i = 1, #poly do
		local xi, zi = poly[i][1], poly[i][2]
		local xj, zj = poly[j][1], poly[j][2]
		if ((zi > z) ~= (zj > z)) and (x < (xj - xi) * (z - zi) / (zj - zi) + xi) then
			inside = not inside
		end
		j = i
	end
	return inside
end

-- ---------------------------------------------------------------------------
-- Base64 -> buffer (bulk map data)
-- ---------------------------------------------------------------------------
local ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local LOOKUP = table.create(256, 0)
for i = 1, 64 do
	LOOKUP[string.byte(ALPHABET, i) + 1] = i - 1
end

function Util.base64ToBuffer(s: string): buffer
	local len = #s
	local pad = 0
	if string.sub(s, -2) == "==" then
		pad = 2
	elseif string.sub(s, -1) == "=" then
		pad = 1
	end
	local outLen = (len // 4) * 3 - pad
	local out = buffer.create(outLen)
	local o = 0
	local lk = LOOKUP
	for i = 1, len - 3, 4 do
		local a, b, c, d = string.byte(s, i, i + 3)
		local n = bit32.bor(
			bit32.lshift(lk[a + 1], 18),
			bit32.lshift(lk[b + 1], 12),
			bit32.lshift(lk[c + 1], 6),
			lk[d + 1]
		)
		if o + 2 < outLen then
			buffer.writeu8(out, o, bit32.rshift(n, 16))
			buffer.writeu8(out, o + 1, bit32.band(bit32.rshift(n, 8), 255))
			buffer.writeu8(out, o + 2, bit32.band(n, 255))
		else
			if o < outLen then
				buffer.writeu8(out, o, bit32.rshift(n, 16))
			end
			if o + 1 < outLen then
				buffer.writeu8(out, o + 1, bit32.band(bit32.rshift(n, 8), 255))
			end
			if o + 2 < outLen then
				buffer.writeu8(out, o + 2, bit32.band(n, 255))
			end
		end
		o += 3
	end
	return out
end

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
function Util.shallowCopy<T>(t: T): T
	return table.clone(t :: any) :: any
end

function Util.keys(t: { [any]: any }): { any }
	local out = {}
	for k in t do
		table.insert(out, k)
	end
	return out
end

function Util.shuffle<T>(arr: { T }, rng: Random): { T }
	for i = #arr, 2, -1 do
		local j = rng:NextInteger(1, i)
		arr[i], arr[j] = arr[j], arr[i]
	end
	return arr
end

-- ---------------------------------------------------------------------------
-- Tiny signal
-- ---------------------------------------------------------------------------
export type Signal = {
	Connect: (self: Signal, fn: (...any) -> ()) -> { Disconnect: () -> () },
	Fire: (self: Signal, ...any) -> (),
	DisconnectAll: (self: Signal) -> (),
}

function Util.signal(): Signal
	local handlers: { [number]: ((...any) -> ())? } = {}
	local nextId = 0
	local sig = {}
	function sig.Connect(_self: any, fn: (...any) -> ())
		nextId += 1
		local id = nextId
		handlers[id] = fn
		return {
			Disconnect = function()
				handlers[id] = nil
			end,
		}
	end
	function sig.Fire(_self: any, ...: any)
		for _, fn in handlers do
			if fn then
				task.spawn(fn, ...)
			end
		end
	end
	function sig.DisconnectAll(_self: any)
		table.clear(handlers)
	end
	return (sig :: any) :: Signal
end

-- ---------------------------------------------------------------------------
-- Fictional soldier names (callsigns) for AI soldiers
-- ---------------------------------------------------------------------------
local FIRST = {
	"Anton", "Bogdan", "Dima", "Emil", "Fedir", "Gleb", "Igor", "Jakub", "Kiril", "Lev", "Marek", "Nikola",
	"Oleg", "Pavel", "Radek", "Stas", "Taras", "Vadim", "Yuri", "Zoran", "Artem", "Borys", "Danylo", "Ivo",
	"Luka", "Milan", "Ostap", "Petro", "Roman", "Sasha", "Tomas", "Viktor",
}
local LAST = {
	"Kral", "Novak", "Petrenko", "Horak", "Sokol", "Vlasov", "Zelenko", "Bilyk", "Duda", "Hrytsenko", "Koval",
	"Lysenko", "Marchuk", "Orlov", "Pavlik", "Rudenko", "Savchuk", "Tkach", "Voronin", "Yakov", "Zuev", "Bondar",
	"Chernyak", "Fedorov", "Gavrilov", "Ivanek", "Klymenko", "Moroz", "Polak", "Shevchuk",
}

function Util.soldierName(rng: Random): string
	return FIRST[rng:NextInteger(1, #FIRST)] .. " " .. LAST[rng:NextInteger(1, #LAST)]
end

return Util
