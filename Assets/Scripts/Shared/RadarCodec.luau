--!strict
-- Compact binary form of the 2 Hz minimap radar packet.
--
-- The radar travels over an UnreliableRemoteEvent, and Roblox drops
-- unreliable payloads larger than about 1000 bytes. As a table of numbers a
-- full battle is roughly twice that, so it is packed into a buffer: positions
-- are whole studs as int16, a friendly soldier costs 7 bytes and every other
-- marker 4. encode() never produces more than MAX_BYTES; if a battle ever has
-- more markers than fit, the least important ones (enemy vehicles, then
-- spotted enemies, then friendly vehicles) are left out for that update.

export type Packet = {
	s: { { number } }, -- friendly soldiers: x, z, soldier id, in a vehicle (0 / 1)
	v: { { number } }, -- friendly vehicles: x, z
	e: { { number } }, -- spotted enemy soldiers: x, z
	ev: { { number } }, -- visible enemy vehicles: x, z
}

local RadarCodec = {}

RadarCodec.MAX_BYTES = 900
local HEADER = 8 -- four uint16 counts
local SOLDIER = 7
local MARKER = 4

local function i16(v: number): number
	return math.clamp(math.floor(v + 0.5), -32768, 32767)
end

function RadarCodec.encode(p: Packet): buffer
	local budget = RadarCodec.MAX_BYTES - HEADER
	local ns = math.min(#p.s, budget // SOLDIER)
	budget -= ns * SOLDIER
	local nv = math.min(#p.v, budget // MARKER)
	budget -= nv * MARKER
	local ne = math.min(#p.e, budget // MARKER)
	budget -= ne * MARKER
	local nev = math.min(#p.ev, budget // MARKER)
	local b = buffer.create(HEADER + ns * SOLDIER + (nv + ne + nev) * MARKER)
	local o = 0
	local function u16(v: number)
		buffer.writeu16(b, o, v)
		o += 2
	end
	local function xz(e: { number })
		buffer.writei16(b, o, i16(e[1]))
		buffer.writei16(b, o + 2, i16(e[2]))
		o += 4
	end
	u16(ns)
	for i = 1, ns do
		local e = p.s[i]
		xz(e)
		buffer.writeu16(b, o, math.clamp(math.floor(e[3]), 0, 65535))
		buffer.writeu8(b, o + 2, if e[4] == 1 then 1 else 0)
		o += 3
	end
	for _, section in { { list = p.v, n = nv }, { list = p.e, n = ne }, { list = p.ev, n = nev } } do
		u16(section.n)
		for i = 1, section.n do
			xz(section.list[i])
		end
	end
	return b
end

-- Returns nil for anything that is not a well-formed radar buffer.
function RadarCodec.decode(b: any): Packet?
	if typeof(b) ~= "buffer" then
		return nil
	end
	local len = buffer.len(b)
	local o = 0
	local function u16(): number?
		if o + 2 > len then
			return nil
		end
		local v = buffer.readu16(b, o)
		o += 2
		return v
	end
	local out: Packet = { s = {}, v = {}, e = {}, ev = {} }
	local ns = u16()
	if not ns or o + ns * SOLDIER > len then
		return nil
	end
	for _ = 1, ns do
		local x, z = buffer.readi16(b, o), buffer.readi16(b, o + 2)
		local id, flag = buffer.readu16(b, o + 4), buffer.readu8(b, o + 6)
		table.insert(out.s, { x, z, id, flag })
		o += SOLDIER
	end
	for _, list in { out.v, out.e, out.ev } do
		local n = u16()
		if not n or o + n * MARKER > len then
			return nil
		end
		for _ = 1, n do
			table.insert(list, { buffer.readi16(b, o), buffer.readi16(b, o + 2) })
			o += MARKER
		end
	end
	return out
end

return RadarCodec
