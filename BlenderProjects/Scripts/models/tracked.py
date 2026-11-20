"""Tracked vehicles: main battle tanks, infantry fighting vehicles, self-propelled
howitzers and armoured recovery vehicles for both armies.

Blender axes: +Y = front, +Z = up, +X = right. Units: metres.
"""
import math

from rbxlib import Model, box_grid
from models.palette import (
    AMBER, DARK_STEEL, FACTIONS, GLASS_DARK, GUNMETAL, LENS, RUBBER, STEEL, TAIL, TRACK, WOOD,
)

VERT = (0, -90, 0)  # cylinder axis -> up
ALONG_Y = (0, 0, 90)  # cylinder axis -> front


def running_gear(m, pal, W, track_w, wheels, wheel_d, y_rear, y_front, skirt=True, red=False, rollers=3, wheel_z=None):
    """Road wheels (each its own group for animation), sprocket, idler, track
    belt, return rollers and side skirts on both sides."""
    wz = wheel_z if wheel_z is not None else wheel_d / 2 + 0.03
    span = y_front - y_rear
    pitch = (span - 1.3) / (wheels - 1)
    top_z = wz + wheel_d / 2 + 0.06
    for side, tag in ((1, "R"), (-1, "L")):
        x = side * (W / 2 - track_w / 2)
        for i in range(wheels):
            y = y_front - 0.65 - i * pitch
            g = f"Wheel{tag}{i + 1}"
            m.group(g, (x, y, wz))
            m.cyl(f"Road{tag}{i + 1}", track_w * 0.78, wheel_d, (x, y, wz), group=g, mat="Metal", color=pal["dark"] if not red else STEEL)
            m.cyl(f"Tyre{tag}{i + 1}", track_w * 0.82, wheel_d * 0.98, (x, y, wz), group=g, mat="Rubber", color=RUBBER, segments=24)
            m.cyl(f"Hub{tag}{i + 1}", track_w * 0.86, wheel_d * 0.38, (x, y, wz), group=g, mat="Metal", color=DARK_STEEL, segments=10)
            if red:  # spoked look: a few radial bars
                for k in range(3):
                    a = k * 60
                    m.block(f"Spoke{tag}{i + 1}_{k}", (track_w * 0.88, 0.06, wheel_d * 0.82), (x, y, wz), (a, 0, 0), "Metal", STEEL, group=g)
        # sprocket (rear) and idler (front)
        m.group(f"Sprocket{tag}", (x, y_rear + 0.35, wz + 0.18))
        m.cyl(f"SprocketDisc{tag}", track_w * 0.7, wheel_d * 0.86, (x, y_rear + 0.35, wz + 0.18), group=f"Sprocket{tag}", mat="Metal", color=DARK_STEEL)
        for k in range(4):
            m.block(f"SprocketTooth{tag}{k}", (track_w * 0.5, 0.1, wheel_d * 1.0), (x, y_rear + 0.35, wz + 0.18), (k * 45, 0, 0), "Metal", GUNMETAL, group=f"Sprocket{tag}")
        m.group(f"Idler{tag}", (x, y_front - 0.05, wz + 0.16))
        m.cyl(f"IdlerDisc{tag}", track_w * 0.72, wheel_d * 0.8, (x, y_front - 0.05, wz + 0.16), group=f"Idler{tag}", mat="Metal", color=DARK_STEEL)
        # track belt: bottom run, top run and the two wraps
        m.block(f"TrackBottom{tag}", (track_w, span - 1.0, 0.09), (x, (y_front + y_rear) / 2, 0.045), mat="Rubber", color=TRACK)
        m.block(f"TrackTop{tag}", (track_w, span - 0.5, 0.09), (x, (y_front + y_rear) / 2 + 0.1, top_z), mat="Rubber", color=TRACK)
        m.cyl(f"TrackWrapRear{tag}", track_w, wheel_d * 1.05, (x, y_rear + 0.35, wz + 0.18), mat="Rubber", color=TRACK, segments=24)
        m.cyl(f"TrackWrapFront{tag}", track_w, wheel_d * 0.98, (x, y_front - 0.05, wz + 0.16), mat="Rubber", color=TRACK, segments=24)
        m.block(f"TrackRiseF{tag}", (track_w, 0.75, 0.09), (x, y_front - 0.45, 0.24), (32, 0, 0), "Rubber", TRACK)
        m.block(f"TrackRiseR{tag}", (track_w, 0.6, 0.09), (x, y_rear + 0.6, 0.24), (-34, 0, 0), "Rubber", TRACK)
        # grousers (track links) on the visible top run
        for k in range(10):
            y = y_rear + 0.6 + k * (span - 1.2) / 9
            m.block(f"Grouser{tag}{k}", (track_w * 1.02, 0.07, 0.04), (x, y, top_z + 0.06), mat="Metal", color=GUNMETAL)
        if rollers:
            for k in range(rollers):
                y = y_rear + 1.0 + k * (span - 2.0) / max(1, rollers - 1)
                m.cyl(f"Roller{tag}{k}", track_w * 0.5, 0.2, (x, y, top_z - 0.12), mat="Metal", color=DARK_STEEL, segments=10)
        if skirt:
            n = 5
            seg = (span - 0.6) / n
            for k in range(n):
                y = y_front - 0.3 - seg * (k + 0.5)
                h = 0.62 if k > 0 else 0.7
                th = 0.07 if k > 0 else 0.12
                col = pal["base"] if k % 2 == 0 else pal["camo"]
                if red:
                    m.block(f"Skirt{tag}{k}", (0.03, seg - 0.04, 0.45), (side * (W / 2 + 0.02), y, top_z - 0.15), mat="Rubber", color=RUBBER)
                else:
                    m.block(f"Skirt{tag}{k}", (th, seg - 0.04, h), (side * (W / 2 + th / 2), y, top_z - h / 2 + 0.12), mat="Metal", color=col)
                    m.block(f"SkirtBolt{tag}{k}", (th + 0.02, 0.06, 0.06), (side * (W / 2 + th / 2), y + seg / 2 - 0.12, top_z + 0.05), mat="Metal", color=DARK_STEEL)


def hull(m, pal, L, W, track_w, clear, low_h, deck_h, glacis_len, lower_len, red=False, era=False, rear_slope=0.6):
    """Lower hull between the tracks + upper hull / fenders + glacis plates."""
    yf, yr = L / 2, -L / 2
    inner = W - 2 * track_w - 0.06
    top = clear + low_h
    m.block("LowerHull", (inner, L - lower_len, low_h), (0, -lower_len / 2, clear + low_h / 2), mat="Metal", color=pal["dark"])
    m.wedge("LowerGlacis", (inner, lower_len, low_h), (0, yf - lower_len / 2, clear + low_h / 2), (0, 180, 0), "Metal", pal["base"])
    body_len = L - glacis_len - rear_slope
    m.block("UpperHull", (W, body_len, deck_h), (0, yr + rear_slope + body_len / 2, top + deck_h / 2), mat="Metal", color=pal["base"])
    m.wedge("Glacis", (W - 0.1, glacis_len, deck_h), (0, yf - glacis_len / 2, top + deck_h / 2), mat="Metal", color=pal["base"])
    m.wedge("RearSlope", (W, rear_slope, deck_h), (0, yr + rear_slope / 2, top + deck_h / 2), (0, 0, 180), "Metal", pal["base"])
    m.block("RearPlate", (inner, 0.08, low_h + deck_h * 0.4), (0, yr + 0.04, clear + (low_h + deck_h * 0.4) / 2), mat="Metal", color=pal["dark"])
    # fender lips
    for side, tag in ((1, "R"), (-1, "L")):
        m.block(f"FenderLip{tag}", (0.06, L - 0.4, 0.06), (side * (W / 2 - 0.03), -0.1, top + 0.03), mat="Metal", color=pal["dark"])
        # stowage boxes on fenders
        for k, y in enumerate((-1.9, -0.6)):
            m.block(f"FenderBox{tag}{k}", (track_w * 0.85, 1.1, 0.42), (side * (W / 2 - track_w / 2 - 0.02), y, top + deck_h + 0.21), mat="Metal", color=pal["camo"] if k else pal["base"])
            m.block(f"FenderBoxLid{tag}{k}", (track_w * 0.88, 1.14, 0.05), (side * (W / 2 - track_w / 2 - 0.02), y, top + deck_h + 0.44), mat="Metal", color=pal["dark"])
        # headlight + guard
        m.cyl(f"Headlight{tag}", 0.12, 0.2, (side * (W / 2 - 0.35), yf - glacis_len + 0.2, top + deck_h + 0.1), ALONG_Y, "Glass", LENS)
        m.block(f"HeadGuard{tag}", (0.28, 0.04, 0.26), (side * (W / 2 - 0.35), yf - glacis_len + 0.36, top + deck_h + 0.1), mat="Metal", color=pal["dark"])
        m.block(f"Taillight{tag}", (0.14, 0.05, 0.08), (side * (inner / 2 - 0.15), yr - 0.02, top - 0.05), mat="Neon", color=TAIL)
        # tow hooks
        m.block(f"TowFront{tag}", (0.14, 0.2, 0.14), (side * 0.75, yf + 0.05, clear + 0.25), mat="Metal", color=GUNMETAL)
        m.block(f"TowRear{tag}", (0.14, 0.2, 0.14), (side * 0.75, yr - 0.06, clear + 0.35), mat="Metal", color=GUNMETAL)
    # engine deck grilles
    box_grid(m, "Grille", (-W / 2 + 0.75, yr + rear_slope + 0.15, top + deck_h + 0.02), (0.55, 0.12, 0.03), 4, 6, 0.06, "Metal", GUNMETAL)
    # driver's hatch + periscopes
    m.cyl("DriverHatch", 0.06, 0.62, (-0.45 if not red else 0, yf - glacis_len - 0.35, top + deck_h + 0.03), VERT, "Metal", pal["dark"])
    for k in range(3):
        m.block(f"Periscope{k}", (0.18, 0.08, 0.1), ((-0.45 if not red else 0) + (k - 1) * 0.22, yf - glacis_len - 0.02, top + deck_h + 0.06), mat="Glass", color=GLASS_DARK)
    if era:
        # reactive armour blocks on the glacis (follow the slope)
        ang = math.degrees(math.atan2(deck_h, glacis_len))
        for i in range(6):
            for j in range(2):
                y = yf - glacis_len + 0.3 + j * 0.55
                z = top + deck_h - (y - (yf - glacis_len)) * deck_h / glacis_len + 0.06
                m.block(f"GlacisERA{i}_{j}", (0.44, 0.5, 0.1), (-W / 2 + 0.5 + i * 0.52, y, z), (-ang, 0, 0), "Metal", pal["light"])
    return top + deck_h


def flag(m, pal, at, group="", h=1.4):
    x, y, z = at
    m.cyl("FlagPole", h, 0.035, (x, y, z + h / 2), VERT, "Metal", GUNMETAL, group)
    m.block("TeamFlag", (0.02, 0.5, 0.32), (x, y - 0.27, z + h - 0.18), mat="Fabric", color=pal["mark"], group=group)


# ---------------------------------------------------------------------------
# Main battle tanks
# ---------------------------------------------------------------------------
def mbt(team):
    pal = FACTIONS[team]
    red = team == 2
    name = f"MBT_{pal['key']}"
    m = Model(name, "Vehicles/Tanks", "mbt", {"Team": team})
    L, W, tw = 7.4, 3.6, 0.64
    running_gear(m, pal, W, tw, 6 if red else 7, 0.78 if not red else 0.82, -L / 2, L / 2 - 0.1, skirt=True, red=red, rollers=0 if not red else 3)
    deck = hull(m, pal, L, W, tw, 0.45, 0.55, 0.42, 1.5, 0.8, red=red, era=red)
    m.hitbox("Hitbox", (W, L, deck - 0.4), (0, 0, 0.4 + (deck - 0.4) / 2))

    ring = (0, 0.15 if not red else 0.35, deck)
    m.group("Turret", ring)
    if not red:
        # angular western-style turret
        m.block("TurretBody", (2.7, 2.6, 0.72), (0, 0.0, deck + 0.38), mat="Metal", color=pal["base"], group="Turret")
        m.block("TurretBustle", (2.45, 1.5, 0.62), (0, -1.95, deck + 0.42), mat="Metal", color=pal["base"], group="Turret")
        for side, tag in ((1, "R"), (-1, "L")):
            m.block(f"Cheek{tag}", (0.95, 1.15, 0.68), (side * 0.86, 1.48, deck + 0.38), (0, 0, -side * 16), "Metal", pal["base"], group="Turret")
            m.wedge(f"CheekTop{tag}", (0.95, 1.15, 0.12), (side * 0.86, 1.48, deck + 0.78), (0, 0, -side * 16), "Metal", pal["light"], group="Turret")
            m.block(f"BustleRail{tag}", (0.05, 1.6, 0.05), (side * 1.32, -2.0, deck + 0.82), mat="Metal", color=GUNMETAL, group="Turret")
            m.block(f"BustleStripe{tag}", (0.02, 1.0, 0.18), (side * 1.24, -1.95, deck + 0.5), mat="SmoothPlastic", color=pal["mark"], group="Turret")
            for k in range(4):
                m.cyl(f"Smoke{tag}{k}", 0.3, 0.09, (side * 1.42, 0.55 + k * 0.13, deck + 0.62), (0, -55, 90 * side), "Metal", GUNMETAL, group="Turret")
        m.block("TurretRoof", (2.55, 3.9, 0.04), (0, -0.55, deck + 0.75), mat="DiamondPlate", color=pal["dark"], group="Turret")
        m.block("BasketRear", (2.6, 0.04, 0.3), (0, -2.75, deck + 0.95), mat="Metal", color=GUNMETAL, group="Turret")
        m.block("StowageBag", (1.5, 0.5, 0.32), (0.3, -2.45, deck + 0.94), mat="Fabric", color=pal["canvas"], group="Turret")
        m.block("GunnerSight", (0.5, 0.55, 0.36), (0.78, 0.85, deck + 0.95), mat="Metal", color=pal["base"], group="Turret")
        m.block("GunnerSightGlass", (0.38, 0.03, 0.2), (0.78, 1.13, deck + 0.97), mat="Glass", color=GLASS_DARK, group="Turret")
        m.cyl("CIVSStem", 0.42, 0.22, (-0.62, 0.55, deck + 0.98), VERT, "Metal", pal["dark"], group="Turret")
        m.block("CIVSHead", (0.4, 0.35, 0.3), (-0.62, 0.55, deck + 1.3), mat="Metal", color=pal["base"], group="Turret")
        m.block("CIVSGlass", (0.3, 0.02, 0.16), (-0.62, 0.73, deck + 1.3), mat="Glass", color=GLASS_DARK, group="Turret")
        cup = (0.62, -0.55, deck + 0.78)
    else:
        # rounded eastern-style turret with reactive armour horseshoe
        m.cyl("TurretBase", 0.6, 3.05, (0, 0, deck + 0.3), VERT, "Metal", pal["base"], group="Turret", segments=28)
        m.cyl("TurretDome", 0.32, 2.55, (0, -0.05, deck + 0.75), VERT, "Metal", pal["base"], group="Turret", segments=28)
        m.cyl("TurretTop", 0.14, 1.95, (0, -0.1, deck + 0.98), VERT, "Metal", pal["camo"], group="Turret", segments=24)
        for k in range(9):
            a = math.radians(-70 + k * 17.5)
            r = 1.48
            m.block(f"ERA{k}", (0.52, 0.42, 0.42), (math.sin(a) * r, math.cos(a) * r, deck + 0.52), (0, 0, -math.degrees(a)), "Metal", pal["light"], group="Turret")
            m.wedge(f"ERATop{k}", (0.52, 0.42, 0.14), (math.sin(a) * r, math.cos(a) * r, deck + 0.8), (0, 0, -math.degrees(a)), "Metal", pal["light"], group="Turret")
        m.block("TurretStowage", (1.9, 0.55, 0.45), (0, -1.65, deck + 0.5), mat="Metal", color=pal["camo"], group="Turret")
        m.cyl("Snorkel", 2.2, 0.16, (0, -1.98, deck + 0.82), (0, 0, 0), "Metal", pal["dark"], group="Turret")
        m.cyl("Searchlight", 0.28, 0.42, (0.95, 0.95, deck + 0.95), ALONG_Y, "Metal", pal["dark"], group="Turret")
        m.cyl("SearchlightGlass", 0.04, 0.34, (0.95, 1.1, deck + 0.95), ALONG_Y, "Glass", LENS, group="Turret")
        m.block("GunnerSight", (0.42, 0.45, 0.32), (0.62, 0.7, deck + 1.05), mat="Metal", color=pal["dark"], group="Turret")
        m.block("GunnerSightGlass", (0.32, 0.03, 0.18), (0.62, 0.93, deck + 1.07), mat="Glass", color=GLASS_DARK, group="Turret")
        for side, tag in ((1, "R"), (-1, "L")):
            m.block(f"TurretStripe{tag}", (0.02, 0.9, 0.16), (side * 1.52, -0.4, deck + 0.35), mat="SmoothPlastic", color=pal["mark"], group="Turret")
            for k in range(4):
                m.cyl(f"Smoke{tag}{k}", 0.28, 0.09, (side * (0.85 + k * 0.12), -0.95 - k * 0.06, deck + 0.75), (0, -40, 0), "Metal", GUNMETAL, group="Turret")
        cup = (-0.62, -0.25, deck + 1.05)
        # external fuel drums + unditching log on the hull rear
        for side in (-1, 1):
            m.cyl(f"FuelDrum{'R' if side > 0 else 'L'}", 0.9, 0.58, (side * 0.85, -L / 2 - 0.25, deck - 0.1), (0, 0, 0), "Metal", pal["dark"])
        m.cyl("UnditchLog", 3.3, 0.3, (0, -L / 2 - 0.2, deck + 0.28), (0, 0, 0), "Wood", WOOD)
    # commander cupola + heavy MG (its own group so the 2nd seat can aim it)
    m.cyl("CupolaRing", 0.28, 0.82, cup, VERT, "Metal", pal["dark"], group="Turret")
    m.cyl("CupolaHatch", 0.05, 0.6, (cup[0], cup[1], cup[2] + 0.16), VERT, "Metal", pal["base"], group="Turret")
    for k in range(6):
        a = math.radians(k * 60)
        m.block(f"CupolaScope{k}", (0.12, 0.07, 0.09), (cup[0] + math.sin(a) * 0.37, cup[1] + math.cos(a) * 0.37, cup[2] + 0.1), (0, 0, -k * 60), "Glass", GLASS_DARK, group="Turret")
    m.group("Turret/Cupola", (cup[0], cup[1], cup[2] + 0.2))
    m.block("MGMount", (0.12, 0.3, 0.3), (cup[0], cup[1] + 0.25, cup[2] + 0.35), mat="Metal", color=GUNMETAL, group="Turret/Cupola")
    m.block("MGBody", (0.12, 0.8, 0.14), (cup[0], cup[1] + 0.5, cup[2] + 0.5), mat="Metal", color=GUNMETAL, group="Turret/Cupola")
    m.cyl("MGBarrel", 0.7, 0.05, (cup[0], cup[1] + 1.2, cup[2] + 0.5), ALONG_Y, "Metal", GUNMETAL, group="Turret/Cupola")
    m.block("MGAmmoBox", (0.18, 0.22, 0.16), (cup[0] + 0.15, cup[1] + 0.45, cup[2] + 0.42), mat="Metal", color=pal["dark"], group="Turret/Cupola")
    m.attach("MuzzleCupola", (cup[0], cup[1] + 1.58, cup[2] + 0.5), group="Turret/Cupola")
    # antennae + team flag
    m.cyl("AntennaL", 2.2, 0.03, (-1.0, -2.3 if not red else -1.2, deck + 1.9), VERT, "Metal", GUNMETAL, group="Turret")
    flag(m, pal, (1.0, -2.3 if not red else -1.2, deck + 0.8), group="Turret")

    # main gun
    trunnion = (0, 1.3 if not red else 1.25, deck + 0.42)
    m.group("Turret/Gun", trunnion)
    tx, ty, tz = trunnion
    m.block("Mantlet", (0.78 if not red else 0.62, 0.55, 0.52), (0, ty + 0.25, tz), mat="Metal", color=pal["base"] if not red else pal["dark"], group="Turret/Gun")
    barrel_len = 5.3 if not red else 5.6
    m.cyl("Barrel", barrel_len, 0.19, (0, ty + 0.5 + barrel_len / 2, tz), ALONG_Y, "Metal", pal["dark"], group="Turret/Gun")
    for k in range(3):
        m.cyl(f"Sleeve{k}", 1.05, 0.25, (0, ty + 0.95 + k * 1.3, tz), ALONG_Y, "Metal", pal["base"], group="Turret/Gun")
    fy = ty + 0.5 + (2.3 if not red else 3.6)
    m.cyl("FumeExtractor", 0.7, 0.32, (0, fy, tz), ALONG_Y, "Metal", pal["base"], group="Turret/Gun")
    m.cyl("MuzzleRing", 0.18, 0.24, (0, ty + 0.5 + barrel_len - 0.1, tz), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun")
    m.cyl("CoaxMG", 0.42, 0.06, (0.36, ty + 0.62, tz + 0.05), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun")
    m.attach("Muzzle", (0, ty + 0.55 + barrel_len, tz), group="Turret/Gun")
    m.attach("MuzzleCoax", (0.36, ty + 0.85, tz + 0.05), group="Turret/Gun")
    m.attach("CamGunner", (0.75 if not red else 0.62, ty - 0.4, tz + 0.6), group="Turret/Gun")

    # seats, cameras, lights, effects
    m.seat("Seat1", (-0.45 if not red else 0, L / 2 - 1.9, deck - 0.4))
    m.seat("Seat2", (cup[0], cup[1], cup[2] - 0.4), group="Turret")
    m.attach("CamDriver", (-0.45 if not red else 0, L / 2 - 1.6, deck + 0.25))
    m.attach("Exhaust", (0, -L / 2 - 0.1, deck - 0.2), (0, 0, 180))
    m.attach("EngineSmoke", (0, -L / 2 + 1.2, deck + 0.1))
    m.light("Headlight1", (W / 2 - 0.35, L / 2 - 1.2, deck + 0.1), group="")
    m.light("Headlight2", (-W / 2 + 0.35, L / 2 - 1.2, deck + 0.1), group="")
    for k, x in enumerate((-2.2, 2.2)):
        m.attach(f"Exit{k + 1}", (x, 0.5, 0.2))
    return m


# ---------------------------------------------------------------------------
# Infantry fighting vehicles
# ---------------------------------------------------------------------------
def ifv(team):
    pal = FACTIONS[team]
    red = team == 2
    name = f"IFV_{pal['key']}"
    m = Model(name, "Vehicles/Armored", "ifv", {"Team": team})
    L, W, tw = 6.9, 3.25, 0.5
    running_gear(m, pal, W, tw, 6, 0.68, -L / 2, L / 2 - 0.05, skirt=not red, red=red, rollers=3)
    if not red:
        deck = hull(m, pal, L, W, tw, 0.42, 0.75, 0.62, 1.2, 0.7, rear_slope=0.15)
        # tall boxy troop compartment
        m.block("TroopBox", (W - 0.25, 2.8, 0.45), (0, -1.75, deck + 0.22), mat="Metal", color=pal["base"])
        m.block("TroopRoof", (W - 0.4, 2.6, 0.05), (0, -1.75, deck + 0.47), mat="DiamondPlate", color=pal["dark"])
        m.block("RearRamp", (1.7, 0.1, 1.45), (0, -L / 2 - 0.04, 1.15), mat="Metal", color=pal["dark"])
        m.block("RampHinge", (1.8, 0.14, 0.12), (0, -L / 2 - 0.05, 0.45), mat="Metal", color=GUNMETAL)
    else:
        deck = hull(m, pal, L, W, tw, 0.4, 0.55, 0.42, 2.0, 0.6, red=True, rear_slope=0.4)
        for side in (-1, 1):
            m.block(f"RearDoor{'R' if side > 0 else 'L'}", (0.75, 0.1, 0.8), (side * 0.5, -L / 2 - 0.03, 0.95), mat="Metal", color=pal["dark"])
            m.cyl(f"DoorTank{'R' if side > 0 else 'L'}", 0.65, 0.32, (side * 0.5, -L / 2 - 0.2, 1.05), VERT, "Metal", pal["base"])
        for k in range(4):
            m.cyl(f"TroopHatch{k}", 0.05, 0.55, ((k % 2 - 0.5) * 1.0, -1.2 - (k // 2) * 1.0, deck + 0.03), VERT, "Metal", pal["dark"])
    m.hitbox("Hitbox", (W, L, deck - 0.35), (0, 0, 0.35 + (deck - 0.35) / 2))
    ring = (0.25 if not red else 0, 0.6 if not red else 0.2, deck + (0.45 if not red else 0))
    m.group("Turret", ring)
    rx, ry, rz = ring
    if not red:
        m.block("TurretBody", (1.7, 1.9, 0.62), (rx, ry - 0.1, rz + 0.31), mat="Metal", color=pal["base"], group="Turret")
        m.wedge("TurretFront", (1.7, 0.5, 0.62), (rx, ry + 1.1, rz + 0.31), mat="Metal", color=pal["base"], group="Turret")
        m.block("ATGMBox", (0.4, 1.3, 0.42), (rx - 1.07, ry - 0.05, rz + 0.5), mat="Metal", color=pal["dark"], group="Turret")
        m.attach("MuzzleATGM", (rx - 1.07, ry + 0.7, rz + 0.5), group="Turret")
        m.block("TurretStripe", (0.02, 1.0, 0.14), (rx + 0.86, ry - 0.3, rz + 0.4), mat="SmoothPlastic", color=pal["mark"], group="Turret")
        m.block("Sight", (0.36, 0.4, 0.3), (rx + 0.55, ry + 0.35, rz + 0.78), mat="Metal", color=pal["dark"], group="Turret")
        m.block("SightGlass", (0.28, 0.03, 0.16), (rx + 0.55, ry + 0.56, rz + 0.8), mat="Glass", color=GLASS_DARK, group="Turret")
        for k in range(3):
            m.cyl(f"Smoke{k}", 0.26, 0.08, (rx + 0.88, ry + 0.3 + k * 0.12, rz + 0.5), (0, -50, 90), "Metal", GUNMETAL, group="Turret")
    else:
        m.cyl("TurretBase", 0.45, 1.85, (rx, ry, rz + 0.22), VERT, "Metal", pal["base"], group="Turret", segments=24)
        m.cyl("TurretTop", 0.25, 1.45, (rx, ry - 0.05, rz + 0.55), VERT, "Metal", pal["base"], group="Turret", segments=24)
        m.block("ATGMRail", (0.18, 1.1, 0.18), (rx, ry - 0.1, rz + 0.8), mat="Metal", color=pal["dark"], group="Turret")
        m.cyl("ATGMTube", 1.0, 0.16, (rx, ry, rz + 0.95), ALONG_Y, "Metal", pal["camo"], group="Turret")
        m.attach("MuzzleATGM", (rx, ry + 0.55, rz + 0.95), group="Turret")
        m.block("TurretStripe", (0.02, 0.7, 0.14), (rx + 0.92, ry, rz + 0.25), mat="SmoothPlastic", color=pal["mark"], group="Turret")
        for k in range(3):
            m.cyl(f"Smoke{k}", 0.26, 0.08, (rx - 0.7 + k * 0.12, ry - 0.7, rz + 0.5), (0, -40, 0), "Metal", GUNMETAL, group="Turret")
    trunnion = (rx, ry + (1.0 if not red else 0.85), rz + 0.32)
    m.group("Turret/Gun", trunnion)
    m.block("Mantlet", (0.4, 0.35, 0.36), (trunnion[0], trunnion[1] + 0.15, trunnion[2]), mat="Metal", color=pal["dark"], group="Turret/Gun")
    m.cyl("Autocannon", 2.4, 0.1, (trunnion[0], trunnion[1] + 1.4, trunnion[2]), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun")
    m.cyl("CannonSleeve", 0.9, 0.16, (trunnion[0], trunnion[1] + 0.7, trunnion[2]), ALONG_Y, "Metal", pal["dark"], group="Turret/Gun")
    m.cyl("MuzzleBrake", 0.22, 0.15, (trunnion[0], trunnion[1] + 2.55, trunnion[2]), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun")
    m.attach("Muzzle", (trunnion[0], trunnion[1] + 2.7, trunnion[2]), group="Turret/Gun")
    m.attach("CamGunner", (trunnion[0] + 0.35, trunnion[1] - 0.6, trunnion[2] + 0.45), group="Turret/Gun")
    flag(m, pal, (-1.25 if not red else -1.1, -L / 2 + 0.4, deck + (0.47 if not red else 0)))
    m.cyl("Antenna", 1.8, 0.03, (1.25, -L / 2 + 0.4, deck + 1.0), VERT, "Metal", GUNMETAL)
    m.seat("Seat1", (-0.6, L / 2 - 1.5, deck - 0.45))
    for k in range(4):
        m.seat(f"Seat{k + 2}", ((k % 2 - 0.5) * 0.9, -1.4 - (k // 2) * 0.9, deck - 0.6))
    m.attach("CamDriver", (-0.6, L / 2 - 1.3, deck + 0.25))
    m.attach("Exhaust", (W / 2 - 0.3, L / 2 - 2.2, deck + 0.05), (0, 0, -90))
    m.attach("EngineSmoke", (0.6, L / 2 - 1.8, deck + 0.1))
    m.light("Headlight1", (W / 2 - 0.35, L / 2 - 1.0, deck + 0.1))
    m.light("Headlight2", (-W / 2 + 0.35, L / 2 - 1.0, deck + 0.1))
    m.attach("Exit1", (-2.1, 1.0, 0.2))
    for k in range(4):
        m.attach(f"Exit{k + 2}", ((k % 2 - 0.5) * 1.2, -L / 2 - 1.2 - (k // 2) * 0.8, 0.2))
    return m


# ---------------------------------------------------------------------------
# Self-propelled howitzer
# ---------------------------------------------------------------------------
def artillery(team):
    pal = FACTIONS[team]
    red = team == 2
    m = Model(f"Artillery_{pal['key']}", "Vehicles/Tanks", "artillery", {"Team": team})
    L, W, tw = 7.6, 3.4, 0.56
    running_gear(m, pal, W, tw, 7 if not red else 6, 0.72, -L / 2, L / 2 - 0.05, skirt=not red, red=red, rollers=3)
    deck = hull(m, pal, L, W, tw, 0.42, 0.58, 0.4, 1.3, 0.7, red=red, rear_slope=0.1)
    m.hitbox("Hitbox", (W, L, deck - 0.4), (0, 0, 0.4 + (deck - 0.4) / 2))
    ring = (0, -0.9, deck)
    m.group("Turret", ring)
    m.block("TurretBody", (W - 0.3, 3.6, 1.35), (0, -1.0, deck + 0.68), mat="Metal", color=pal["base"], group="Turret")
    m.wedge("TurretNose", (W - 0.3, 0.6, 1.35), (0, 1.1, deck + 0.68), mat="Metal", color=pal["base"], group="Turret")
    m.block("TurretRoof", (W - 0.5, 3.4, 0.05), (0, -1.0, deck + 1.38), mat="DiamondPlate", color=pal["dark"], group="Turret")
    for side, tag in ((1, "R"), (-1, "L")):
        m.block(f"TurretStripe{tag}", (0.02, 1.4, 0.2), (side * (W / 2 - 0.14), -1.6, deck + 0.9), mat="SmoothPlastic", color=pal["mark"], group="Turret")
        m.block(f"SideDoor{tag}", (0.03, 0.8, 1.0), (side * (W / 2 - 0.14), -0.4, deck + 0.6), mat="Metal", color=pal["dark"], group="Turret")
        m.block(f"AmmoRack{tag}", (0.4, 1.6, 0.5), (side * (W / 2 - 0.35), -2.4, deck + 1.65), mat="Metal", color=pal["camo"], group="Turret")
    m.cyl("CupolaRing", 0.25, 0.75, (-0.7, -1.4, deck + 1.5), VERT, "Metal", pal["dark"], group="Turret")
    m.cyl("Antenna", 2.0, 0.03, (1.2, -2.6, deck + 2.3), VERT, "Metal", GUNMETAL, group="Turret")
    trunnion = (0, 0.9, deck + 0.75)
    m.group("Turret/Gun", trunnion)
    m.block("Mantlet", (0.95, 0.5, 0.7), (0, 1.15, deck + 0.75), mat="Metal", color=pal["dark"], group="Turret/Gun")
    m.cyl("Barrel", 6.4, 0.22, (0, 1.4 + 3.2, deck + 0.75), ALONG_Y, "Metal", pal["base"], group="Turret/Gun")
    m.cyl("Recoil", 1.4, 0.36, (0, 1.9, deck + 0.75), ALONG_Y, "Metal", pal["dark"], group="Turret/Gun")
    m.cyl("Bore", 0.7, 0.3, (0, 4.4, deck + 0.75), ALONG_Y, "Metal", pal["base"], group="Turret/Gun")
    m.block("MuzzleBrake", (0.42, 0.55, 0.32), (0, 7.7, deck + 0.75), mat="Metal", color=GUNMETAL, group="Turret/Gun")
    m.attach("Muzzle", (0, 8.05, deck + 0.75), group="Turret/Gun")
    m.attach("CamGunner", (0.9, -0.6, deck + 1.9), group="Turret/Gun")
    # travel lock on the glacis
    m.block("TravelLock", (0.5, 0.15, 0.5), (0, L / 2 - 0.9, deck + 0.25), mat="Metal", color=GUNMETAL)
    flag(m, pal, (-1.3, -3.2, deck + 1.4), group="Turret")
    m.seat("Seat1", (-0.6, L / 2 - 1.6, deck - 0.4))
    m.attach("CamDriver", (-0.6, L / 2 - 1.2, deck + 0.25))
    m.attach("Exhaust", (W / 2 - 0.2, 1.4, deck + 0.05), (0, 0, -90))
    m.attach("EngineSmoke", (0.6, 1.6, deck + 0.1))
    m.light("Headlight1", (W / 2 - 0.35, L / 2 - 1.1, deck + 0.1))
    m.light("Headlight2", (-W / 2 + 0.35, L / 2 - 1.1, deck + 0.1))
    m.attach("Exit1", (-2.2, 0.5, 0.2))
    return m


# ---------------------------------------------------------------------------
# Armoured recovery vehicle (tank chassis, crane, dozer blade)
# ---------------------------------------------------------------------------
def recovery(team):
    pal = FACTIONS[team]
    red = team == 2
    m = Model(f"Recovery_{pal['key']}", "Vehicles/Armored", "recovery", {"Team": team})
    L, W, tw = 7.4, 3.5, 0.62
    running_gear(m, pal, W, tw, 7 if not red else 6, 0.78, -L / 2, L / 2 - 0.1, skirt=not red, red=red, rollers=0 if not red else 3)
    deck = hull(m, pal, L, W, tw, 0.45, 0.55, 0.42, 1.4, 0.8, red=red)
    m.hitbox("Hitbox", (W, L, deck - 0.4), (0, 0, 0.4 + (deck - 0.4) / 2))
    m.block("Superstructure", (W - 0.6, 3.0, 1.0), (0, 0.3, deck + 0.5), mat="Metal", color=pal["base"])
    m.wedge("SuperNose", (W - 0.6, 0.6, 1.0), (0, 2.1, deck + 0.5), mat="Metal", color=pal["base"])
    m.block("SuperRoof", (W - 0.8, 2.8, 0.05), (0, 0.3, deck + 1.02), mat="DiamondPlate", color=pal["dark"])
    for side, tag in ((1, "R"), (-1, "L")):
        m.block(f"Stripe{tag}", (0.02, 1.2, 0.18), (side * (W / 2 - 0.29), -0.2, deck + 0.7), mat="SmoothPlastic", color=pal["mark"])
        m.block(f"BladeArm{tag}", (0.15, 1.2, 0.15), (side * 1.2, L / 2 + 0.3, 0.75), (25, 0, 0), "Metal", GUNMETAL)
    m.block("DozerBlade", (W + 0.1, 0.25, 0.85), (0, L / 2 + 0.85, 0.5), (-10, 0, 0), "Metal", pal["dark"])
    m.block("BladeEdge", (W + 0.1, 0.3, 0.08), (0, L / 2 + 0.95, 0.1), mat="Metal", color=STEEL)
    # crane (rotates with the "Turret" group)
    m.group("Turret", (1.0, -1.6, deck))
    m.cyl("CraneBase", 0.4, 0.9, (1.0, -1.6, deck + 0.2), VERT, "Metal", pal["dark"], group="Turret")
    m.block("CraneBoom", (0.35, 4.2, 0.35), (1.0, -0.1, deck + 1.4), (28, 0, 0), "Metal", AMBER, group="Turret")
    m.block("CraneTip", (0.3, 0.4, 0.3), (1.0, 1.75, deck + 2.4), mat="Metal", color=AMBER, group="Turret")
    m.cyl("CraneCable", 1.6, 0.03, (1.0, 1.85, deck + 1.55), VERT, "Metal", GUNMETAL, group="Turret")
    m.block("CraneHook", (0.15, 0.2, 0.25), (1.0, 1.85, deck + 0.7), mat="Metal", color=GUNMETAL, group="Turret")
    m.group("Turret/Gun", (-0.8, 1.6, deck + 1.1))
    m.block("MGBody", (0.12, 0.7, 0.14), (-0.8, 1.9, deck + 1.2), mat="Metal", color=GUNMETAL, group="Turret/Gun")
    m.cyl("MGBarrel", 0.5, 0.05, (-0.8, 2.45, deck + 1.2), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun")
    m.attach("Muzzle", (-0.8, 2.75, deck + 1.2), group="Turret/Gun")
    m.block("Winch", (1.2, 0.6, 0.5), (0, -L / 2 + 0.5, deck + 0.25), mat="Metal", color=pal["dark"])
    m.block("SpareTrack", (0.7, 1.4, 0.12), (-1.0, -1.5, deck + 0.06), mat="Rubber", color=TRACK)
    flag(m, pal, (-1.2, -2.8, deck))
    m.seat("Seat1", (-0.6, 1.0, deck - 0.3))
    m.seat("Seat2", (0.6, 1.0, deck - 0.3))
    m.attach("CamDriver", (-0.6, 1.6, deck + 0.8))
    m.attach("Exhaust", (0, -L / 2 - 0.1, deck - 0.2), (0, 0, 180))
    m.attach("EngineSmoke", (0, -L / 2 + 1.0, deck + 0.1))
    m.light("Headlight1", (W / 2 - 0.35, L / 2 - 1.1, deck + 0.1))
    m.light("Headlight2", (-W / 2 + 0.35, L / 2 - 1.1, deck + 0.1))
    m.attach("Exit1", (-2.3, 0.5, 0.2))
    m.attach("Exit2", (2.3, 0.5, 0.2))
    return m


BUILDERS = {"mbt": mbt, "ifv": ifv, "artillery": artillery, "recovery": recovery}
