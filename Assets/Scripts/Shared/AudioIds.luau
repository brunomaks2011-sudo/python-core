--!strict
-- Uploaded sound sheet IDs.
--
-- All game audio is original (Tools/audio/build_audio.py synthesises it; the
-- radio voice lines come from Tools/audio/gen_voice.py) and is packed into five
-- sheets. Roblox only plays uploaded audio, so upload these five files once
-- (Creator Dashboard > Development Items > Audio, or Studio > Asset Manager >
-- Bulk Import) and paste each asset ID below - either "1234567890" or
-- "rbxassetid://1234567890":
--
--   sfx        = Assets/Audio/SFX/sfx.ogg
--   loops      = Assets/Audio/SFX/loops.ogg
--   music      = Assets/Audio/Music/music.ogg
--   voice_blue = Assets/Audio/Voice/voice_blue.ogg
--   voice_red  = Assets/Audio/Voice/voice_red.ogg
--
-- Until then, the few clips that have a built-in Roblox equivalent use it and
-- the rest are silent.

local AudioSprites = require(script.Parent.AudioSprites)

local AudioIds = {}

AudioIds.sheets = {
	sfx = "",
	loops = "",
	music = "",
	voice_blue = "",
	voice_red = "",
} :: { [string]: string }

-- Built-in Roblox client sounds used while a sheet has no ID yet.
AudioIds.fallback = {
	explosion = "rbxasset://sounds/collide.wav",
	explosion_big = "rbxasset://sounds/collide.wav",
	tank_gun = "rbxasset://sounds/collide.wav",
	howitzer = "rbxasset://sounds/collide.wav",
	rocket = "rbxasset://sounds/Rocket shot.wav",
	rpg = "rbxasset://sounds/Rocket shot.wav",
	mlrs_launch = "rbxasset://sounds/Rocket shot.wav",
	grenade = "rbxasset://sounds/swoosh.wav",
	ui_click = "rbxasset://sounds/electronicpingshort.wav",
	capture = "rbxasset://sounds/electronicpingshort.wav",
	radio_click = "rbxasset://sounds/electronicpingshort.wav",
} :: { [string]: string }

-- A playable clip: `length` 0 means "the whole file".
export type Clip = { id: string, start: number, length: number, loop: boolean }

local function assetUri(id: string): string
	return if string.find(id, "://", 1, true) then id else "rbxassetid://" .. id
end

function AudioIds.clip(name: string): Clip?
	local region = AudioSprites.clips[name]
	if region then
		local id = AudioIds.sheets[region.sheet]
		if id and id ~= "" then
			return { id = assetUri(id), start = region.start, length = region.length, loop = region.loop }
		end
	end
	local fb = AudioIds.fallback[name]
	if fb then
		return { id = fb, start = 0, length = 0, loop = false }
	end
	return nil
end

return AudioIds
