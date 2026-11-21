# Assets/Effects

Mapped to `ReplicatedStorage.Assets.Effects` by `default.project.json`.

The game's visual effects (muzzle flashes, tracers, explosions, smoke, fire,
sparks, dust, debris, rain, lightning) are generated at runtime by
`Assets/Scripts/Client/Effects/*.luau` from Roblox's built-in particle textures
(`rbxasset://textures/particles/*`), so nothing needs to be uploaded.

Drop custom `.rbxm` / `.model.json` effect templates here if you want to
override them; they replicate to every client.
