"""Aircraft: attack and transport helicopters for both armies (player-flown).
Groups: "Rotor" (spins about up), "TailRotor" (spins about the right axis),
"ChinTurret"/"ChinTurret/Gun", door guns.
"""
import math

from rbxlib import Model
from models.palette import DARK_STEEL, FACTIONS, GLASS, GLASS_DARK, GUNMETAL, RUBBER, TAIL, WHITE

VERT = (0, -90, 0)
ALONG_Y = (0, 0, 90)


def rotor(m, pal, hub, blades, length, chord=0.38, group="Rotor", tilt=0.0, color=None):
    m.group(group, hub)
    x, y, z = hub
    m.cyl(f"{group}Hub", 0.35, 0.55, (x, y, z), VERT, "Metal", GUNMETAL, group=group)
    m.cyl(f"{group}Cap", 0.2, 0.3, (x, y, z + 0.25), VERT, "Metal", DARK_STEEL, group=group)
    for k in range(blades):
        a = k * 360 / blades
        r = length / 2 + 0.2
        bx, by = math.sin(math.radians(a)) * r, math.cos(math.radians(a)) * r
        m.block(f"{group}Blade{k}", (chord, length, 0.06), (x + bx, y + by, z + 0.05), (tilt, 0, -a), "Metal", color or GUNMETAL, group=group)
        m.block(f"{group}Tip{k}", (chord + 0.02, 0.35, 0.065), (x + math.sin(math.radians(a)) * (length + 0.05), y + math.cos(math.radians(a)) * (length + 0.05), z + 0.05), (tilt, 0, -a), "SmoothPlastic", (0.85, 0.75, 0.15), group=group)
    disc = m.cyl(f"{group}Disc", 0.03, length * 2 + 0.6, (x, y, z + 0.05), VERT, "Glass", (0.25, 0.25, 0.25), group=group, segments=32, transparency=1.0)
    disc["extra"]["rotorDisc"] = True


def tail_rotor(m, at, blades, length, side=1):
    x, y, z = at
    m.group("TailRotor", at)
    m.cyl("TailHub", 0.25, 0.25, at, (0, 0, 0), "Metal", GUNMETAL, group="TailRotor")
    for k in range(blades):
        a = k * 360 / blades
        dy, dz = math.sin(math.radians(a)) * length / 2, math.cos(math.radians(a)) * length / 2
        m.block(f"TailBlade{k}", (0.04, 0.2, length), (x + side * 0.08, y + dy, z + dz), (a, 0, 0), "Metal", GUNMETAL, group="TailRotor")


def skids(m, pal, y0, y1, half_track, z=0.1):
    for s, tag in ((1, "R"), (-1, "L")):
        m.cyl(f"Skid{tag}", y1 - y0, 0.1, (s * half_track, (y0 + y1) / 2, z), ALONG_Y, "Metal", GUNMETAL)
        for k, y in enumerate((y0 + 0.6, y1 - 0.8)):
            m.block(f"SkidStrut{tag}{k}", (0.08, 0.08, 0.75), (s * (half_track - 0.15), y, z + 0.38), (0, s * 20, 0), "Metal", GUNMETAL)


def gear_wheel(m, name, at, d=0.5, w=0.22):
    x, y, z = at
    m.cyl(name, w, d, at, (0, 0, 0), "Rubber", RUBBER)
    m.block(name + "Strut", (0.08, 0.08, 0.7), (x, y, z + 0.4), mat="Metal", color=GUNMETAL)


def attack_heli(team):
    pal = FACTIONS[team]
    red = team == 2
    m = Model(f"AttackHeli_{pal['key']}", "Aircraft", "attack_heli", {"Team": team})
    body = pal["base"]
    zc = 1.7
    w = 1.05 if not red else 1.35
    # fuselage
    m.block("Fuselage", (w, 5.0, 1.35), (0, 0.6, zc), mat="Metal", color=body)
    m.wedge("NoseTop", (w, 1.2, 0.5), (0, 3.7, zc + 0.43), mat="Metal", color=body)
    m.block("Nose", (w * 0.9, 1.1, 0.85), (0, 3.65, zc - 0.25), mat="Metal", color=body)
    m.wedge("NoseTip", (w * 0.9, 0.5, 0.85), (0, 4.45, zc - 0.25), mat="Metal", color=pal["dark"])
    m.wedge("Belly", (w, 1.4, 0.4), (0, -2.4, zc - 0.48), (0, 180, 180), "Metal", body)
    # stepped tandem canopies
    m.block("CanopyFront", (w * 0.85, 1.25, 0.6), (0, 2.75, zc + 0.95), mat="Glass", color=GLASS, transparency=0.3)
    m.wedge("CanopyFrontSlope", (w * 0.85, 0.6, 0.6), (0, 3.65, zc + 0.95), mat="Glass", color=GLASS, transparency=0.3)
    m.block("CanopyRear", (w * 0.85, 1.25, 0.8), (0, 1.45, zc + 1.12), mat="Glass", color=GLASS, transparency=0.3)
    m.block("CanopyFrame", (w * 0.88, 0.08, 0.85), (0, 2.1, zc + 1.12), mat="Metal", color=pal["dark"])
    m.block("Spine", (w * 0.7, 3.0, 0.55), (0, -0.6, zc + 0.95), mat="Metal", color=body)
    # engines
    for s, tag in ((1, "R"), (-1, "L")):
        m.cyl(f"Engine{tag}", 1.9, 0.6, (s * (w / 2 + 0.22), -0.4, zc + 0.9), ALONG_Y, "Metal", pal["dark"] if not red else body)
        m.cyl(f"Intake{tag}", 0.2, 0.5, (s * (w / 2 + 0.22), 0.6, zc + 0.9), ALONG_Y, "Metal", DARK_STEEL)
        m.cyl(f"Exhaust{tag}", 0.5, 0.42, (s * (w / 2 + 0.3), -1.5, zc + 0.95), (0, 0, 70 * s), "Metal", GUNMETAL)
        # stub wing + stores
        span = 1.45 if not red else 1.7
        m.block(f"Wing{tag}", (span, 0.9, 0.12), (s * (w / 2 + span / 2), 0.3, zc + 0.15), (0, s * -6, 0), "Metal", body)
        m.block(f"WingTip{tag}", (0.12, 0.9, 0.35), (s * (w / 2 + span), 0.3, zc + 0.05), mat="Metal", color=pal["dark"])
        m.cyl(f"RocketPod{tag}", 1.6, 0.45, (s * (w / 2 + span * 0.45), 0.4, zc - 0.25), ALONG_Y, "Metal", pal["dark"])
        m.cyl(f"RocketPodFace{tag}", 0.05, 0.38, (s * (w / 2 + span * 0.45), 1.22, zc - 0.25), ALONG_Y, "Metal", GUNMETAL)
        m.attach(f"Pod{tag}", (s * (w / 2 + span * 0.45), 1.35, zc - 0.25))
        for k in range(4 if not red else 2):
            m.cyl(f"Missile{tag}{k}", 1.4, 0.16, (s * (w / 2 + span * 0.85 + (k % 2) * 0.2), 0.45, zc - 0.15 - (k // 2) * 0.22), ALONG_Y, "Metal", WHITE if not red else pal["light"])
        m.block(f"BoomStripe{tag}", (0.02, 1.2, 0.18), (s * (0.24 if not red else 0.3), -4.4, zc + 0.6), mat="SmoothPlastic", color=pal["mark"])
    m.attach("Pod", (0, 1.35, zc - 0.25))
    # tail
    bw = 0.46 if not red else 0.6
    m.block("TailBoom", (bw, 4.6, 0.55), (0, -4.4, zc + 0.6), mat="Metal", color=body)
    m.wedge("TailBoomTaper", (bw, 0.8, 0.55), (0, -1.75, zc + 0.6), (0, 0, 180), "Metal", body)
    m.block("Fin", (0.1, 1.0, 1.7), (0, -6.9, zc + 1.4), (-15, 0, 0), "Metal", body)
    m.block("Stabilizer", (2.2, 0.6, 0.08), (0, -6.0, zc + 0.6), mat="Metal", color=body)
    tail_rotor(m, (0.18 if not red else -0.18, -7.15, zc + 1.9), 4 if not red else 3, 1.5, side=1 if not red else -1)
    # chin gun
    m.group("ChinTurret", (0, 3.6, zc - 0.75))
    m.ball("ChinBall", 0.55, (0, 3.6, zc - 0.85), "Metal", GUNMETAL, group="ChinTurret")
    m.group("ChinTurret/Gun", (0, 3.75, zc - 0.88))
    m.cyl("ChinBarrel", 1.3, 0.09, (0, 4.45, zc - 0.88), ALONG_Y, "Metal", GUNMETAL, group="ChinTurret/Gun")
    m.attach("ChinGun", (0, 5.15, zc - 0.88), group="ChinTurret/Gun")
    m.attach("CamGunner", (0, 2.9, zc + 1.1), group="ChinTurret/Gun")
    m.block("NoseSensor", (0.45, 0.3, 0.4), (0, 4.35, zc - 0.55), mat="Glass", color=GLASS_DARK)
    # rotors
    m.cyl("Mast", 0.75, 0.22, (0, 0.5, zc + 1.6), VERT, "Metal", GUNMETAL)
    rotor(m, pal, (0, 0.5, zc + 2.0), 4 if not red else 5, 6.4 if not red else 7.0)
    # landing gear
    if not red:
        for s, tag in ((1, "R"), (-1, "L")):
            gear_wheel(m, f"MainGear{tag}", (s * 1.0, 2.2, 0.27))
        gear_wheel(m, "TailGear", (0, -5.8, 0.27), d=0.35, w=0.15)
    else:
        for s, tag in ((1, "R"), (-1, "L")):
            gear_wheel(m, f"MainGear{tag}", (s * 1.2, 0.2, 0.3))
        gear_wheel(m, "NoseGear", (0, 3.4, 0.3), d=0.45)
    m.hitbox("Hitbox", (w + 0.6, 7.0, 1.9), (0, 0.3, zc + 0.15))
    m.hitbox("HitboxTail", (0.6, 5.0, 1.0), (0, -4.7, zc + 0.7))
    m.seat("Seat1", (0, 1.45, zc + 0.55))
    m.seat("Seat2", (0, 2.75, zc + 0.4))
    m.attach("CamDriver", (0, 1.45, zc + 1.3))
    m.attach("EngineSmoke", (0, -0.4, zc + 1.2))
    m.attach("Exit1", (-2.4, 1.5, 0.2))
    m.attach("Exit2", (2.4, 2.7, 0.2))
    m.light("Headlight1", (0, 4.2, zc - 0.6), (-25, 0, 0), brightness=3, range_=90)
    m.block("NavLightR", (0.08, 0.1, 0.06), (w / 2 + 1.5, 0.3, zc + 0.15), mat="Neon", color=(0.1, 0.9, 0.2))
    m.block("NavLightL", (0.08, 0.1, 0.06), (-w / 2 - 1.5, 0.3, zc + 0.15), mat="Neon", color=TAIL)
    return m


def transport_heli(team):
    pal = FACTIONS[team]
    red = team == 2
    m = Model(f"TransportHeli_{pal['key']}", "Aircraft", "transport_heli", {"Team": team})
    body = pal["base"]
    zc = 1.75
    W = 2.0 if not red else 2.3
    cab_len = 4.4 if not red else 6.0
    m.block("Cabin", (W, cab_len, 1.9), (0, 0, zc + 0.15), mat="Metal", color=body)
    m.block("CabinRoof", (W * 0.85, cab_len, 0.35), (0, 0, zc + 1.27), mat="Metal", color=body)
    m.block("Floor", (W, cab_len, 0.1), (0, 0, zc - 0.8), mat="DiamondPlate", color=pal["dark"])
    if not red:
        m.block("Cockpit", (W, 1.6, 1.4), (0, cab_len / 2 + 0.8, zc - 0.05), mat="Metal", color=body)
        m.wedge("Windscreen", (W * 0.95, 0.9, 0.9), (0, cab_len / 2 + 1.75, zc + 0.6), mat="Glass", color=GLASS, transparency=0.3)
        m.wedge("ChinWindows", (W * 0.95, 0.6, 0.5), (0, cab_len / 2 + 1.9, zc - 0.5), (0, 180, 0), "Glass", GLASS, transparency=0.3)
        m.block("NoseCone", (W * 0.9, 0.35, 0.7), (0, cab_len / 2 + 1.75, zc - 0.05), mat="Metal", color=pal["dark"])
        skids(m, pal, -cab_len / 2, cab_len / 2 + 1.0, W / 2 + 0.25)
    else:
        m.cyl("NoseDrum", 1.5, W * 0.95, (0, cab_len / 2 + 0.7, zc + 0.05), ALONG_Y, "Metal", body, segments=24)
        m.ball("NoseDome", W * 0.95, (0, cab_len / 2 + 1.45, zc + 0.05), "Glass", GLASS, transparency=0.35)
        m.block("NoseFrame", (W * 0.98, 0.08, 1.0), (0, cab_len / 2 + 1.42, zc + 0.05), mat="Metal", color=pal["dark"])
        for s, tag in ((1, "R"), (-1, "L")):
            m.cyl(f"ExtTank{tag}", 2.2, 0.75, (s * (W / 2 + 0.38), -0.3, zc - 0.25), ALONG_Y, "Metal", pal["dark"])
            for k in range(4):
                m.cyl(f"Porthole{tag}{k}", 0.04, 0.38, (s * (W / 2 + 0.01), 1.6 - k * 0.9, zc + 0.45), (0, 0, 0), "Glass", GLASS_DARK)
            gear_wheel(m, f"MainGear{tag}", (s * (W / 2 + 0.6), -1.0, 0.33), d=0.65, w=0.28)
        gear_wheel(m, "NoseGear", (0, cab_len / 2 + 0.6, 0.3), d=0.5)
        m.block("Clamshell", (W * 0.9, 0.12, 1.6), (0, -cab_len / 2 - 0.05, zc + 0.1), mat="Metal", color=pal["dark"])
    # engines + mast
    m.block("EngineDeck", (W * 0.7, 2.6, 0.6), (0, 0.6, zc + 1.7), mat="Metal", color=pal["dark"] if not red else body)
    for s, tag in ((1, "R"), (-1, "L")):
        m.cyl(f"Intake{tag}", 0.25, 0.42, (s * 0.38, 1.95, zc + 1.7), ALONG_Y, "Metal", DARK_STEEL)
        m.cyl(f"Exhaust{tag}", 0.5, 0.36, (s * 0.55, -0.8, zc + 1.75), (0, 0, 60 * s), "Metal", GUNMETAL)
        # side doors open + door guns
        dg = f"DoorGun{tag}"
        gx = s * (W / 2 + 0.1)
        m.block(f"DoorFrame{tag}", (0.05, 1.5, 1.4), (s * (W / 2 + 0.01), 0.7, zc + 0.15), mat="Metal", color=pal["dark"], transparency=0.0)
        m.group(dg, (gx, 0.9, zc + 0.35))
        m.block(f"{dg}Body", (0.12, 0.8, 0.15), (gx, 1.2, zc + 0.35), mat="Metal", color=GUNMETAL, group=dg)
        m.cyl(f"{dg}Barrel", 0.7, 0.06, (gx, 1.95, zc + 0.35), ALONG_Y, "Metal", GUNMETAL, group=dg)
        m.attach(dg, (gx, 2.35, zc + 0.35), group=dg)
        m.block(f"BoomStripe{tag}", (0.02, 1.1, 0.16), (s * 0.29, -cab_len / 2 - 2.3, zc + 0.75), mat="SmoothPlastic", color=pal["mark"])
    m.cyl("Mast", 0.6, 0.24, (0, 0.6, zc + 2.2), VERT, "Metal", GUNMETAL)
    rotor(m, pal, (0, 0.6, zc + 2.55), 4 if not red else 5, 6.6 if not red else 8.4, chord=0.45)
    # tail boom
    m.block("TailBoom", (0.55, 5.0, 0.6), (0, -cab_len / 2 - 2.5, zc + 0.75), mat="Metal", color=body)
    m.wedge("BoomTaper", (W * 0.8, 1.0, 1.0), (0, -cab_len / 2 - 0.45, zc + 0.6), (0, 0, 180), "Metal", body)
    m.block("Fin", (0.1, 1.0, 1.6), (0, -cab_len / 2 - 5.0, zc + 1.6), (-15, 0, 0), "Metal", body)
    m.block("Stabilizer", (2.0, 0.55, 0.08), (0, -cab_len / 2 - 4.2, zc + 0.75), mat="Metal", color=body)
    tail_rotor(m, (0.2 if not red else -0.2, -cab_len / 2 - 5.25, zc + 2.1), 2 if not red else 3, 1.6, side=1 if not red else -1)
    m.hitbox("Hitbox", (W + 0.4, cab_len + 2.4, 2.4), (0, 0.6, zc + 0.3))
    m.hitbox("HitboxTail", (0.7, 5.0, 1.0), (0, -cab_len / 2 - 2.7, zc + 0.9))
    m.seat("Seat1", (-0.45, cab_len / 2 + 0.7, zc - 0.25))
    m.seat("Seat2", (-W / 2 + 0.45, 0.6, zc - 0.4))
    m.seat("Seat3", (W / 2 - 0.45, 0.6, zc - 0.4))
    for k in range(4):
        m.seat(f"Seat{k + 4}", ((k % 2 - 0.5) * 1.0, -0.8 - (k // 2) * 0.9, zc - 0.4))
    m.attach("CamDriver", (-0.45, cab_len / 2 + 0.9, zc + 0.6))
    m.attach("EngineSmoke", (0, 0.6, zc + 2.0))
    for k in range(7):
        m.attach(f"Exit{k + 1}", ((-1 if k % 2 == 0 else 1) * (W / 2 + 1.5), 1.0 - (k // 2) * 0.8, 0.2))
    m.light("Headlight1", (0, cab_len / 2 + 1.6, zc - 0.7), (-25, 0, 0), brightness=3, range_=90)
    return m


BUILDERS = {"attack_heli": attack_heli, "transport_heli": transport_heli}
