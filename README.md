# BLUE vs RED — Three Flags Domination

A combined-arms military game for **Roblox**. Two fictional armies, Blue Army and
Red Army, fight over three flags in Dolyna Valley, a fictional Eastern European
river valley: **A** Ironvale Works (industrial complex), **B** Dolyna Village and
**C** Garrison 41 (military base).

The whole game is in this repository as a [Rojo](https://rojo.space) project, and
the ready-built place file is `Build/BlueVsRed.rbxl`.

## Play it

1. Open **`Build/BlueVsRed.rbxl`** in Roblox Studio (File → Open from File).
2. Press **Play** (F5). The server builds the valley (terrain, about 90 buildings,
   bridges, the railway and about 9,000 trees), which takes a moment behind
   the loading screen. Then pick a faction, class and spawn on the deployment screen.
3. For multiplayer in Studio, use Test → Clients and Servers. To play online, use
   File → Publish to Roblox.

AI soldiers fill both armies (16 a side by default, up to 32), so the battle is full
even when you play alone.

### Sound (one-time step)

Roblox only plays audio uploaded to Roblox, so the game ships five sound sheets.
Upload them once (Creator Dashboard → Development Items → Audio, or Studio's Asset
Manager → Bulk Import), then paste the five asset IDs into
`Assets/Scripts/Shared/AudioIds.luau`:

| Sheet        | File                                | Contents                                                  |
| ------------ | ----------------------------------- | --------------------------------------------------------- |
| `sfx`        | `Assets/Audio/SFX/sfx.ogg`          | 23 one-shots: every weapon, explosions, debris, glass, UI |
| `loops`      | `Assets/Audio/SFX/loops.ogg`        | tank, truck, car and helicopter engines, wind, rain, distant battle |
| `music`      | `Assets/Audio/Music/music.ogg`      | menu theme (loops), victory and defeat stings             |
| `voice_blue` | `Assets/Audio/Voice/voice_blue.ogg` | 17 Blue HQ radio calls                                    |
| `voice_red`  | `Assets/Audio/Voice/voice_red.ogg`  | 17 Red HQ radio calls                                     |

Each sound is a region of a sheet (`Sound.PlaybackRegion`), so 67 sounds need only 5
uploads. Until the IDs are filled in, a few sounds fall back to Roblox's built-in
ones and the rest are silent. After editing `AudioIds.luau`, rebuild the place (see
Development) or paste the same IDs into the `AudioIds` ModuleScript in Studio.

## The rules: Three Flags Domination

- Each flag has a capture zone. While only one army has soldiers in a zone, the flag
  moves towards that army: about **30 s** to capture a neutral flag, and an enemy
  flag must first be neutralised. Extra soldiers in the zone capture slightly faster.
- If both armies are in a zone it is **CONTESTED**: progress stops and nobody earns.
- Each army has a timer from **0 to 1000 seconds**. It gains **one second per second
  while the army holds at least one flag**. Holding two or three flags does not make
  it faster; holding none stops it.
- The **first army to reach exactly 1000 wins**, and the match ends with a victory
  screen showing the winner, final timers, flags held, match length and player stats.
  If both armies would reach 1000 on the same tick, the one holding more flags wins.
  On a full tie neither timer moves (**sudden death**) until one side holds more.
- Everything above runs on the server (`Shared/DominationMode.luau`, tested by
  `Tests/unit/Domination.spec.luau`). Clients only display it and cannot change it.

## Controls

| On foot                       |                                       |
| ----------------------------- | ------------------------------------- |
| W A S D, mouse                | move, look                            |
| Left Shift                    | sprint                                |
| C or Left Ctrl / Z            | crouch / prone (Space stands up)      |
| Space                         | jump                                  |
| Left mouse / right mouse      | fire / aim down sights                |
| R                             | reload                                |
| 1 2 3 or mouse wheel          | primary, sidearm, class tool          |
| G                             | throw grenade or demolition charge    |
| X                             | detonate demolition charges           |
| F (binoculars)                | call rocket artillery on the aim point |
| E                             | enter a vehicle, climb a ladder       |
| V                             | first / third person                  |
| Tab, M, P                     | scoreboard, full map, menu            |

| In a vehicle                  |                                       |
| ----------------------------- | ------------------------------------- |
| W S / A D                     | throttle / steer                      |
| Space                         | brake (helicopters: climb; Left Ctrl descends, Q / E yaw) |
| Left mouse, 1 2               | fire, select weapon                   |
| F                             | change seat                           |
| C                             | camera mode                           |
| L                             | headlights                            |
| E (helicopter pilot: G)       | get out                               |

## What is in the game

**Factions and classes.** Blue Army and Red Army, each with its own weapons,
vehicles and uniforms. Six classes: Rifleman, Medic (heals teammates),
Engineer (rocket launcher, repair torch, demolition charges), Support
(machine gun, ammo pouch), Reconnaissance (marksman rifle, binoculars that spot
enemies and call rocket artillery) and Vehicle Crew. You deploy at the HQ, at a
flag your army holds (unless it is contested), at a friendly mobile-spawn vehicle,
or straight into a vehicle. Spawn protection makes you invulnerable for 4 seconds,
or until you fire.

**Vehicles, all drivable, all Blender-built, in Blue and Red versions.**

| Type                       | Blue           | Red              |
| -------------------------- | -------------- | ---------------- |
| Main battle tank           | BV-90 Warden   | RT-88 Vulkan     |
| Infantry fighting vehicle  | BX-40 Lancer   | RK-3 Kurgan      |
| Armoured personnel carrier | BW-8 Badger    | RB-80 Tur        |
| Light utility vehicle      | BL-4 Hound     | RL-31 Kozak      |
| Military truck             | BT-6 Mule      | RT-43 Zubr       |
| Supply truck               | BT-6S Packhorse | RT-43S Oboz     |
| Field ambulance            | BA-2 Lifeline  | RA-9 Sanitar     |
| Rocket launcher vehicle    | BR-12 Thunder  | RG-122 Grad-K    |
| Self-propelled howitzer    | BH-155 Bastion | RS-152 Akatsiya-K |
| Armoured recovery vehicle  | BV-90R Tow     | RT-88R Tyagach   |
| Communications vehicle     | BC-7 Relay     | RC-14 Svyaz      |
| Attack helicopter          | AH-9 Kestrel   | RH-24 Berkut     |
| Transport helicopter       | UH-12 Ferry    | RT-8 Zhuravl     |

Vehicles have seats with their own weapons and cameras, turrets that follow the
gunner, rolling wheels and tracks, suspension, doors, headlights, engine sound and
damage smoke and fire. Recon drones and observation planes fly overhead as AI
support aircraft.

**Destruction.** Buildings are assembled from structural pieces with a support
graph. Damage goes through five stages (intact → damaged → broken → partly
collapsed → ruin), unsupported floors and walls fall, and debris, dust, smoke, fire
and sparks persist until the match restarts. Trees, fences and props break too.

**AI.** Bots have roles and squads, path-find across the map, use cover, crew and
drive vehicles, and retreat when hurt. A commander per army assigns squads to
attack or defend A, B and C.

**World.** Day and night cycle; clear, cloudy, rain, fog and storm weather with
wind, lightning and thunder; street and building lights at night. Original music,
3D positional sound (distant shots arrive late, at the speed of sound) and HQ radio
calls ("Bravo is ours.", "Incoming artillery!").

**Menus.** PLAY, MULTIPLAYER, SINGLEPLAYER (bots, difficulty, time, weather),
SETTINGS, VEHICLE GARAGE (3D preview of every vehicle), MAP SELECTION and EXIT,
plus the deployment screen, HUD, minimap, scoreboard and victory screen.

## Multiplayer and server authority

The server owns the match state, flags, timers, damage, ammunition and vehicles.
Clients send requests and the server checks them all:

- **Rate of fire.** A token bucket per weapon, so a modified client cannot fire
  faster than the weapon's real rate, even after idling.
- **Hit claims.** A client may claim a hit (lag compensation), but the server
  accepts it only if the point lies on the ray actually fired, the target is near
  that point on the server, and no wall is in the way.
- **Positions and movement.** NaN and infinite vectors are rejected everywhere.
  Shots must start at the shooter's head with a clear line of sight. Teleports and
  speed hacks are pulled back by `MovementGuard`, which also covers vehicles.
- **Teams and settings.** Teams cannot be stacked. Only Studio, a solo player, the
  private-server owner or the place creator can change battle settings.

The pure rules are in `Shared/AntiCheat.luau` and are unit-tested exploit by exploit.

## Project layout

```
default.project.json        Rojo project: maps the folders below into the place
Build/BlueVsRed.rbxl         the built place file
Assets/
  Scripts/Server/            Main, Game/ (match, spawn, combat, vehicles, destruction,
                             radar, environment, movement guard), World/ (terrain,
                             map, buildings), AI/ (navigator, bot brain, commander,
                             vehicle driver, support aircraft)
  Scripts/Client/            Main, UI/, Player/, Vehicles/, Effects/, Audio/
  Scripts/Shared/            rules and data used by both: DominationMode, Defs,
                             AntiCheat, RadarCodec, MapInfo, Rig, VehiclePhysics, ...
  Scripts/ReplicatedFirst/   loading screen
  Models/                    181 Blender-built models as Roblox parts (.model.json):
                             Vehicles, Aircraft, MilitaryEquipment, Buildings,
                             Environment, Soldiers, Weapons
  Meshes/                    the same models as FBX (optional import)
  Maps/DolynaValley/         generated height, material and vegetation data
  Audio/                     the five sound sheets + raw voice recordings
BlenderProjects/             a .blend for every model, render previews, and the
                             Python build scripts (Scripts/)
Tools/                       map generator, audio generators, static checkers
Tests/                       Lune unit tests
```

## Development

The tools used: [Rojo](https://rojo.space) 7, [Lune](https://lune-org.github.io/docs)
0.11, Node 18+, Python 3 with numpy and ffmpeg (audio), and the `bpy` 5.x Python
module (models; Python 3.13).

```bash
rojo build default.project.json -o Build/BlueVsRed.rbxl
```

```bash
lune run Tests/run
```

```bash
bash Tools/check.sh
```

`check.sh` type-checks all Luau against the Roblox API, validates class, service
and enum names against the API dump, checks every cross-module reference, and
builds the place. `npm run` gives the same commands, plus the generators:
`gen:map` (terrain, layout, vegetation), `gen:models` (all Blender models; append
names to rebuild some), `gen:voice` (radio lines through ElevenLabs; needs
`ELEVENLABS_API_KEY`) and `gen:audio` (synthesises the sounds and music and packs
the sheets).

## Verification status

Checked in this repository:

- 54 unit tests:
  - the domination rules
  - map data decoding and building structure
  - every vehicle definition against its Blender models
  - the anti-cheat rules
  - the radar packet size
  - the built place file itself: it opens, every script compiles, and scripts,
    models and service settings are where Roblox needs them
- The static checks above report zero errors.
- Every model was rendered and inspected (`BlenderProjects/*/previews`).
- Every audio clip was measured for levels, loop seams and alignment in the sheets.

**Not yet tested inside Roblox.** No Roblox client or server could run where this
was built, so playing it is the remaining test: vehicle handling, AI behaviour,
visual balance and performance on real devices may need tuning after the first
sessions in Studio.
