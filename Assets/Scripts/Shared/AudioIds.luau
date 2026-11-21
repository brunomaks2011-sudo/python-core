--!strict
-- Sound asset IDs. The game ships its own original sounds in Assets/Audio
-- (synthesised weapons, engines, explosions, ambience, music, and radio voice
-- lines). Roblox only plays uploaded audio, so upload that folder once
-- (Studio > Asset Manager > Bulk Import, or Tools/upload_audio.py with an
-- Open Cloud key) and paste the IDs here - Tools/upload_audio.py writes this
-- file automatically. Empty entries fall back to Roblox's built-in sounds where
-- one exists, otherwise they are silent.

local AudioIds = {
	-- weapons
	rifle = "", smg = "", lmg = "", sniper = "", pistol = "", mg = "", hmg = "", autocannon = "",
	tank_gun = "", howitzer = "", rocket = "", rpg = "", mlrs_launch = "", grenade = "",
	-- explosions / destruction
	explosion = "", explosion_big = "", debris = "", glass = "", impact = "",
	-- vehicles
	engine_tank = "", engine_truck = "", engine_car = "", engine_heli = "",
	-- ambience / weather
	wind = "", rain = "", thunder = "", battle_ambience = "",
	-- ui / radio / music
	radio_click = "", ui_click = "", capture = "", music_menu = "", music_victory = "", music_defeat = "",
	-- radio voice lines: voice_<team>_<line>, e.g. voice_1_captured_A
	voice = {} :: { [string]: string },
}

-- Built-in Roblox client sounds used when nothing has been uploaded yet.
AudioIds.fallback = {
	explosion = "rbxasset://sounds/collide.wav",
	explosion_big = "rbxasset://sounds/collide.wav",
	rocket = "rbxasset://sounds/Rocket shot.wav",
	rpg = "rbxasset://sounds/Rocket shot.wav",
	mlrs_launch = "rbxasset://sounds/Rocket shot.wav",
	tank_gun = "rbxasset://sounds/collide.wav",
	grenade = "rbxasset://sounds/swoosh.wav",
	ui_click = "rbxasset://sounds/electronicpingshort.wav",
	capture = "rbxasset://sounds/electronicpingshort.wav",
	radio_click = "rbxasset://sounds/electronicpingshort.wav",
}

function AudioIds.get(name: string): string?
	local id = (AudioIds :: any)[name]
	if type(id) == "string" and id ~= "" then
		return id
	end
	local fb = AudioIds.fallback[name]
	return fb
end

return AudioIds
