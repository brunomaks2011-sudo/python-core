"""Wheeled vehicles: 8x8 APCs, utility jeeps, 6x6 trucks (cargo, supply, rocket
launcher, communications) and field ambulances for both armies.

Blender axes: +Y = front, +Z = up, +X = right. Units: metres.
Wheel groups: "WheelL1" (left, first axle from the front). Steerable axles
wrap the wheel in a "SteerL1" group (steer about up, spin about the axle).
"""
import math

from rbxlib import Model, box_grid
from models.palette import (
    AMBER, CHROME, DARK_STEEL, FACTIONS, GLASS, GLASS_DARK, GUNMETAL, LENS, MED_GREEN, RUBBER, STEEL, TAIL, WHITE, WOOD,
)

VERT = (0, -90, 0)
ALONG_Y = (0, 0, 90)


def wheel(m, pal, tag, x, y, z, d, w, steer=False, military=True):
    if steer:
        sg = f"Steer{tag}"
        m.group(sg, (x, y, z))
        g = f"{sg}/Wheel{tag}"
    else:
        g = f"Wheel{tag}"
    m.group(g, (x, y, z))
    m.cyl(f"Tyre{tag}", w, d, (x, y, z), group=g, mat="Rubber", color=RUBBER, segments=24)
    m.cyl(f"TreadBand{tag}", w * 0.6, d * 1.012, (x, y, z), group=g, mat="Rubber", color=RUBBER, segments=24)
    m.cyl(f"Rim{tag}", w * 1.02, d * 0.58, (x, y, z), group=g, mat="Metal", color=pal["dark"] if military else CHROME, segments=16)
    m.cyl(f"Hub{tag}", w * 1.1, d * 0.24, (x, y, z), group=g, mat="Metal", color=DARK_STEEL, segments=10)
    for k in range(2):
        m.block(f"RimBar{tag}{k}", (w * 1.06, 0.06, d * 0.5), (x, y, z), (k * 90, 0, 0), "Metal", GUNMETAL, group=g)


def axles(m, pal, ys, track, d, w, steer_axles=1, military=True):
    z = d / 2
    for i, y in enumerate(ys):
        for side, s in (("R", 1), ("L", -1)):
            wheel(m, pal, f"{side}{i + 1}", s * track / 2, y, z, d, w, steer=i < steer_axles, military=military)
        m.block(f"Axle{i + 1}", (track - w, 0.14, 0.14), (0, y, z), mat="Metal", color=GUNMETAL)


def lights_front(m, x, y, z, glass=LENS):
    for side, s in (("R", 1), ("L", -1)):
        m.block(f"Headlamp{side}", (0.24, 0.06, 0.16), (s * x, y, z), mat="Glass", color=glass)
    m.light("Headlight1", (x, y + 0.05, z))
    m.light("Headlight2", (-x, y + 0.05, z))


def lights_rear(m, x, y, z):
    for side, s in (("R", 1), ("L", -1)):
        m.block(f"Taillamp{side}", (0.16, 0.05, 0.1), (s * x, y, z), mat="Neon", color=TAIL)


def flag(m, pal, at, group="", h=1.3):
    x, y, z = at
    m.cyl("FlagPole", h, 0.035, (x, y, z + h / 2), VERT, "Metal", GUNMETAL, group)
    m.block("TeamFlag", (0.02, 0.48, 0.3), (x, y - 0.26, z + h - 0.17), mat="Fabric", color=pal["mark"], group=group)


def mg_turret(m, pal, at, shield=True, name="Turret"):
    """Small ring-mounted machine gun station: 'Turret' (yaw) + 'Turret/Gun' (pitch)."""
    x, y, z = at
    m.group(name, (x, y, z))
    m.cyl("RingMount", 0.12, 0.95, (x, y, z + 0.06), VERT, "Metal", pal["dark"], group=name)
    if shield:
        m.block("ShieldFront", (0.8, 0.05, 0.5), (x, y + 0.42, z + 0.4), (-8, 0, 0), "Metal", pal["base"], group=name)
        for s in (-1, 1):
            m.block(f"ShieldSide{'R' if s > 0 else 'L'}", (0.05, 0.4, 0.42), (x + s * 0.42, y + 0.25, z + 0.36), (0, 0, s * 20), "Metal", pal["base"], group=name)
    m.group(f"{name}/Gun", (x, y + 0.15, z + 0.5))
    m.block("GunBody", (0.13, 0.85, 0.16), (x, y + 0.4, z + 0.5), mat="Metal", color=GUNMETAL, group=f"{name}/Gun")
    m.cyl("GunBarrel", 0.8, 0.06, (x, y + 1.2, z + 0.5), ALONG_Y, "Metal", GUNMETAL, group=f"{name}/Gun")
    m.block("GunAmmo", (0.18, 0.22, 0.18), (x + 0.16, y + 0.35, z + 0.42), mat="Metal", color=pal["dark"], group=f"{name}/Gun")
    m.block("GunGrips", (0.2, 0.08, 0.14), (x, y + 0.0, z + 0.48), mat="Metal", color=GUNMETAL, group=f"{name}/Gun")
    m.attach("Muzzle", (x, y + 1.62, z + 0.5), group=f"{name}/Gun")
    m.attach("CamGunner", (x, y - 0.5, z + 0.95), group=f"{name}/Gun")


# ---------------------------------------------------------------------------
# 8x8 armoured personnel carriers
# ---------------------------------------------------------------------------
def apc(team):
    pal = FACTIONS[team]
    red = team == 2
    m = Model(f"APC_{pal['key']}", "Vehicles/Armored", "apc", {"Team": team})
    L, W = 7.6, 2.9
    d, w, track = 1.22, 0.42, 2.45
    ys = [2.55, 1.15, -0.85, -2.3] if not red else [2.6, 1.3, -0.6, -2.0]
    axles(m, pal, ys, track, d, w, steer_axles=2)
    zb, zt = 0.6, 1.65
    inner = track - w - 0.05
    if not red:
        m.block("LowerHull", (inner, L - 1.6, zt - zb), (0, -0.5, (zb + zt) / 2), mat="Metal", color=pal["dark"])
        m.wedge("NoseLow", (inner, 1.1, zt - zb), (0, L / 2 - 0.55 - 0.3, (zb + zt) / 2), (0, 180, 0), "Metal", pal["base"])
        m.block("UpperHull", (W, L - 1.8, 0.62), (0, -0.55, zt + 0.31), mat="Metal", color=pal["base"])
        m.wedge("Glacis", (W, 1.3, 0.62), (0, L / 2 - 0.95, zt + 0.31), mat="Metal", color=pal["base"])
        for s, tag in ((1, "R"), (-1, "L")):
            m.wedge(f"SideSlope{tag}", (L - 2.2, 0.38, 0.5), (s * (W / 2 - 0.19), -0.6, zt + 0.87), (0, 0, -90 * s), "Metal", pal["base"])
            m.block(f"Stripe{tag}", (0.02, 1.4, 0.16), (s * (W / 2 + 0.005), -1.6, zt + 0.35), mat="SmoothPlastic", color=pal["mark"])
            m.block(f"SideDoorPanel{tag}", (0.03, 0.9, 0.55), (s * (W / 2 + 0.01), 0.2, zt + 0.25), mat="Metal", color=pal["camo"])
            for k, y in enumerate(ys):
                m.block(f"Mudguard{tag}{k}", (0.5, 1.35, 0.06), (s * (track / 2), y, d + 0.08), mat="Metal", color=pal["dark"])
        m.block("Roof", (W - 0.8, L - 2.3, 0.08), (0, -0.6, zt + 1.16), mat="DiamondPlate", color=pal["dark"])
        m.block("RearDoor", (1.3, 0.08, 1.0), (0, -L / 2 + 0.38, zt + 0.0), mat="Metal", color=pal["dark"])
        m.block("TrimVane", (inner, 0.08, 0.5), (0, L / 2 - 0.35, zt - 0.05), (25, 0, 0), "Metal", pal["camo"])
        box_grid(m, "Grille", (-0.9, 1.6, zt + 1.13), (0.5, 0.12, 0.03), 4, 4, 0.06, "Metal", GUNMETAL)
        roof = zt + 1.2
        mg_turret(m, pal, (0, 0.2, roof), shield=False)
        m.block("RWSBox", (0.55, 0.5, 0.38), (0.0, 0.25, roof + 0.3), mat="Metal", color=pal["base"], group="Turret")
        m.block("RWSOptic", (0.28, 0.12, 0.2), (0.32, 0.55, roof + 0.62), mat="Glass", color=GLASS_DARK, group="Turret")
        for k in range(3):
            m.cyl(f"Smoke{k}", 0.25, 0.08, (-0.38, 0.3 + k * 0.11, roof + 0.4), (0, -50, -90), "Metal", GUNMETAL, group="Turret")
    else:
        # boat-shaped hull
        m.block("LowerHull", (inner, L - 2.4, zt - zb), (0, -0.4, (zb + zt) / 2), mat="Metal", color=pal["dark"])
        m.wedge("NoseLow", (inner, 1.4, zt - zb), (0, L / 2 - 0.7 - 0.1, (zb + zt) / 2), (0, 180, 0), "Metal", pal["base"])
        m.wedge("SternLow", (inner, 0.9, zt - zb), (0, -L / 2 + 0.6, (zb + zt) / 2), (0, 180, 180), "Metal", pal["base"])
        m.block("UpperHull", (W, L - 2.6, 0.55), (0, -0.3, zt + 0.27), mat="Metal", color=pal["base"])
        m.wedge("Glacis", (W, 1.9, 0.55), (0, L / 2 - 1.15, zt + 0.27), mat="Metal", color=pal["base"])
        m.wedge("Stern", (W, 0.7, 0.55), (0, -L / 2 + 0.75, zt + 0.27), (0, 0, 180), "Metal", pal["base"])
        for s, tag in ((1, "R"), (-1, "L")):
            m.wedge(f"SideSlope{tag}", (L - 3.0, 0.42, 0.42), (s * (W / 2 - 0.21), -0.3, zt + 0.76), (0, 0, -90 * s), "Metal", pal["base"])
            m.block(f"SideDoor{tag}", (0.04, 0.75, 0.8), (s * (W / 2 + 0.01), (ys[1] + ys[2]) / 2, zt + 0.1), mat="Metal", color=pal["camo"])
            m.block(f"Stripe{tag}", (0.02, 1.0, 0.15), (s * (W / 2 + 0.005), -1.9, zt + 0.35), mat="SmoothPlastic", color=pal["mark"])
            for k in range(3):
                m.block(f"Vision{tag}{k}", (0.03, 0.18, 0.12), (s * (W / 2 + 0.015), 0.9 - k * 1.1, zt + 0.42), mat="Glass", color=GLASS_DARK)
        m.block("Roof", (W - 0.9, L - 3.0, 0.06), (0, -0.4, zt + 0.98), mat="DiamondPlate", color=pal["dark"])
        m.block("TrimVane", (inner, 0.08, 0.45), (0, L / 2 - 0.2, zt - 0.2), (30, 0, 0), "Metal", pal["camo"])
        for k in range(2):
            m.cyl(f"Hatch{k}", 0.05, 0.55, ((k - 0.5) * 0.9, -1.4, zt + 1.02), VERT, "Metal", pal["dark"])
        roof = zt + 1.0
        m.group("Turret", (0, 1.0, roof))
        m.cyl("TurretBase", 0.4, 1.25, (0, 1.0, roof + 0.2), VERT, "Metal", pal["base"], group="Turret", segments=20)
        m.cyl("TurretCone", 0.22, 0.95, (0, 0.95, roof + 0.5), VERT, "Metal", pal["base"], group="Turret", segments=20)
        m.group("Turret/Gun", (0, 1.4, roof + 0.3))
        m.cyl("GunBarrel", 2.0, 0.09, (0, 2.4, roof + 0.3), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun")
        m.cyl("GunSleeve", 0.5, 0.16, (0, 1.65, roof + 0.3), ALONG_Y, "Metal", pal["dark"], group="Turret/Gun")
        m.attach("Muzzle", (0, 3.45, roof + 0.3), group="Turret/Gun")
        m.attach("CamGunner", (0.2, 0.6, roof + 0.85), group="Turret/Gun")
    m.hitbox("Hitbox", (W, L, roof - 0.5), (0, 0, 0.5 + (roof - 0.5) / 2))
    lights_front(m, W / 2 - 0.35, L / 2 - (1.2 if not red else 1.55), zt + 0.3)
    lights_rear(m, W / 2 - 0.25, -L / 2 + 0.05 + (0.5 if red else 0), zt + 0.2)
    flag(m, pal, (-W / 2 + 0.35, -L / 2 + 0.7, roof - 0.05))
    m.cyl("Antenna", 2.0, 0.03, (W / 2 - 0.35, -L / 2 + 0.7, roof + 1.0), VERT, "Metal", GUNMETAL)
    m.seat("Seat1", (-0.6, L / 2 - 1.8, zt - 0.3))
    m.seat("Seat2", (0, 0.2 if not red else 1.0, roof - 0.9))
    for k in range(4):
        m.seat(f"Seat{k + 3}", ((k % 2 - 0.5) * 0.9, -1.0 - (k // 2) * 1.0, zt - 0.4))
    m.attach("CamDriver", (-0.6, L / 2 - 1.5, zt + 0.55))
    m.attach("Exhaust", (W / 2 + 0.05, 1.5, zt + 0.3), (0, 0, -90))
    m.attach("EngineSmoke", (0.6, 1.6, roof))
    m.attach("Exit1", (-2.0, 1.5, 0.2))
    m.attach("Exit2", (2.0, 1.0, 0.2))
    for k in range(4):
        m.attach(f"Exit{k + 3}", ((k % 2 - 0.5) * 1.2, -L / 2 - 1.0 - (k // 2) * 0.8, 0.2))
    return m


# ---------------------------------------------------------------------------
# Light utility vehicles
# ---------------------------------------------------------------------------
def jeep(team):
    pal = FACTIONS[team]
    red = team == 2
    m = Model(f"Jeep_{pal['key']}", "Vehicles/Light", "jeep", {"Team": team})
    if not red:
        L, W, d, w, track = 4.7, 2.18, 0.92, 0.36, 1.85
        ys = [1.55, -1.45]
        axles(m, pal, ys, track, d, w, steer_axles=1)
        zb = 0.5
        m.block("Frame", (1.2, L - 0.4, 0.22), (0, 0, zb + 0.1), mat="Metal", color=GUNMETAL)
        m.block("Body", (W, L - 0.3, 0.6), (0, -0.1, zb + 0.55), mat="Metal", color=pal["base"])
        m.wedge("Hood", (W - 0.1, 1.5, 0.22), (0, 1.45, zb + 0.96), mat="Metal", color=pal["base"])
        m.block("HoodTop", (W - 0.1, 1.3, 0.08), (0, 1.4, zb + 0.89), mat="Metal", color=pal["base"])
        m.block("Grille", (1.3, 0.06, 0.5), (0, L / 2 - 0.12, zb + 0.55), mat="Metal", color=GUNMETAL)
        box_grid(m, "GrilleSlot", (-0.5, L / 2 - 0.09, zb + 0.4), (0.06, 0.03, 0.34), 9, 1, 0.065, "Metal", DARK_STEEL)
        m.block("Bumper", (W + 0.05, 0.18, 0.2), (0, L / 2 + 0.02, zb + 0.15), mat="Metal", color=GUNMETAL)
        for s, tag in ((1, "R"), (-1, "L")):
            for k, (y, door) in enumerate(((0.35, f"Door{tag}1"), (-0.65, f"Door{tag}2"))):
                hinge_y = y + 0.48
                m.group(door, (s * W / 2, hinge_y, zb + 0.9))
                m.block(f"{door}Panel", (0.06, 0.95, 0.75), (s * (W / 2 + 0.02), y, zb + 0.88), mat="Metal", color=pal["base"], group=door)
                m.block(f"{door}Window", (0.04, 0.6, 0.4), (s * (W / 2 + 0.03), y, zb + 1.45), mat="Glass", color=GLASS, group=door, transparency=0.35)
                m.block(f"{door}Handle", (0.03, 0.16, 0.04), (s * (W / 2 + 0.06), y - 0.25, zb + 1.05), mat="Metal", color=GUNMETAL, group=door)
            m.block(f"Stripe{tag}", (0.02, 0.9, 0.12), (s * (W / 2 + 0.035), -1.6, zb + 0.75), mat="SmoothPlastic", color=pal["mark"])
            m.block(f"Fender{tag}", (0.5, 1.3, 0.08), (s * track / 2, 1.55, zb + 0.88), mat="Metal", color=pal["dark"])
        m.block("Windshield", (W - 0.2, 0.06, 0.55), (0, 0.85, zb + 1.32), (-12, 0, 0), "Glass", GLASS, transparency=0.35)
        m.block("Pillars", (W - 0.15, 0.08, 0.06), (0, 0.85, zb + 1.62), mat="Metal", color=pal["base"])
        m.block("Roof", (W - 0.05, 2.0, 0.1), (0, -0.15, zb + 1.72), mat="Metal", color=pal["base"])
        m.block("CargoBed", (W - 0.1, 1.2, 0.5), (0, -L / 2 + 0.75, zb + 0.95), mat="Metal", color=pal["dark"])
        m.block("Seats", (W - 0.5, 1.6, 0.35), (0, -0.2, zb + 0.95), mat="Fabric", color=pal["canvas"])
        mg_turret(m, pal, (0, -0.2, zb + 1.77), shield=True)
        lights_front(m, W / 2 - 0.3, L / 2 - 0.1, zb + 0.7)
        lights_rear(m, W / 2 - 0.15, -L / 2 + 0.12, zb + 0.75)
        roof = zb + 1.75
    else:
        L, W, d, w, track = 4.1, 1.9, 0.86, 0.3, 1.6
        ys = [1.25, -1.15]
        axles(m, pal, ys, track, d, w, steer_axles=1)
        zb = 0.48
        m.block("Frame", (1.0, L - 0.3, 0.2), (0, 0, zb + 0.1), mat="Metal", color=GUNMETAL)
        m.block("Body", (W - 0.2, L - 0.4, 0.6), (0, -0.1, zb + 0.55), mat="Metal", color=pal["base"])
        m.block("Hood", (W - 0.35, 1.2, 0.35), (0, 1.25, zb + 1.0), mat="Metal", color=pal["base"])
        m.wedge("HoodNose", (W - 0.35, 0.3, 0.35), (0, 1.95, zb + 1.0), mat="Metal", color=pal["base"])
        m.block("Grille", (0.9, 0.05, 0.55), (0, L / 2 - 0.06, zb + 0.6), mat="Metal", color=pal["dark"])
        box_grid(m, "GrilleSlot", (-0.36, L / 2 - 0.03, zb + 0.45), (0.05, 0.03, 0.36), 9, 1, 0.04, "Metal", DARK_STEEL)
        m.block("Bumper", (W, 0.12, 0.14), (0, L / 2 + 0.02, zb + 0.2), mat="Metal", color=GUNMETAL)
        for s, tag in ((1, "R"), (-1, "L")):
            for k, y in enumerate(ys):
                m.block(f"Fender{tag}{k}", (0.4, 1.0, 0.06), (s * track / 2, y, d + 0.1), mat="Metal", color=pal["dark"])
                m.wedge(f"FenderLipF{tag}{k}", (0.4, 0.2, 0.18), (s * track / 2, y + 0.55, d + 0.0), (0, 180, 0), "Metal", pal["dark"])
            door = f"Door{tag}1"
            m.group(door, (s * (W / 2 - 0.1), 0.85, zb + 0.9))
            m.block(f"{door}Panel", (0.05, 0.85, 0.65), (s * (W / 2 - 0.08), 0.4, zb + 0.82), mat="Metal", color=pal["base"], group=door)
            m.block(f"{door}Window", (0.03, 0.55, 0.38), (s * (W / 2 - 0.08), 0.4, zb + 1.38), mat="Glass", color=GLASS, group=door, transparency=0.35)
            m.block(f"Stripe{tag}", (0.02, 0.6, 0.12), (s * (W / 2 - 0.085), -1.1, zb + 0.75), mat="SmoothPlastic", color=pal["mark"])
            m.block(f"Headlamp{tag}Ring", (0.24, 0.05, 0.24), (s * 0.62, L / 2 - 0.02, zb + 0.82), mat="Metal", color=GUNMETAL)
        m.block("Windshield", (W - 0.3, 0.05, 0.5), (0, 0.72, zb + 1.38), (-8, 0, 0), "Glass", GLASS, transparency=0.35)
        m.block("CanvasTop", (W - 0.15, 2.4, 0.95), (0, -0.55, zb + 1.38), mat="Fabric", color=pal["canvas"])
        m.wedge("CanvasTopEdge", (W - 0.15, 0.25, 0.25), (0, 0.6, zb + 1.73), (0, 0, 180), "Fabric", pal["canvas"])
        m.cyl("SpareWheel", 0.28, d, (0, -L / 2 - 0.12, zb + 0.95), ALONG_Y, "Rubber", RUBBER)
        m.group("Turret", (0, -1.2, zb + 1.9))
        m.cyl("Pintle", 0.6, 0.08, (0, -1.2, zb + 1.6), VERT, "Metal", GUNMETAL, group="Turret")
        m.group("Turret/Gun", (0, -1.05, zb + 1.95))
        m.block("GunBody", (0.12, 0.8, 0.15), (0, -0.8, zb + 1.95), mat="Metal", color=GUNMETAL, group="Turret/Gun")
        m.cyl("GunBarrel", 0.75, 0.06, (0, -0.05, zb + 1.95), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun")
        m.attach("Muzzle", (0, 0.35, zb + 1.95), group="Turret/Gun")
        m.attach("CamGunner", (0, -1.7, zb + 2.35), group="Turret/Gun")
        lights_front(m, 0.62, L / 2 - 0.02, zb + 0.82)
        lights_rear(m, W / 2 - 0.2, -L / 2 + 0.1, zb + 0.7)
        roof = zb + 1.85
    m.hitbox("Hitbox", (W, L, roof - 0.45), (0, 0, 0.45 + (roof - 0.45) / 2))
    flag(m, pal, (-W / 2 + 0.2, -L / 2 + 0.3, roof - 0.6), h=1.1)
    m.cyl("Antenna", 2.2, 0.025, (W / 2 - 0.2, -L / 2 + 0.3, roof + 0.4), VERT, "Metal", GUNMETAL)
    seat_z = zb + 0.65
    m.seat("Seat1", (-0.45, 0.0 if not red else -0.1, seat_z))
    m.seat("Seat2", (0, -0.6 if not red else -1.3, seat_z + 0.3))
    m.seat("Seat3", (0.45, 0.0 if not red else -0.1, seat_z))
    m.seat("Seat4", (-0.45, -1.0, seat_z))
    m.attach("CamDriver", (-0.45, 0.2, seat_z + 1.0))
    m.attach("Exhaust", (0.6, -L / 2 - 0.05, zb + 0.15), (0, 0, 180))
    m.attach("EngineSmoke", (0, 1.4, roof - 0.7))
    m.attach("Exit1", (-1.7, 0.1, 0.2))
    m.attach("Exit2", (1.6, -0.9, 0.2))
    m.attach("Exit3", (1.7, 0.1, 0.2))
    m.attach("Exit4", (-1.7, -1.0, 0.2))
    return m


# ---------------------------------------------------------------------------
# 6x6 truck family
# ---------------------------------------------------------------------------
def truck_chassis(m, pal, red, L=8.0, W=2.5, d=1.12, w=0.4, track=2.05):
    ys = [L / 2 - 1.6, -L / 2 + 2.3, -L / 2 + 1.0]
    axles(m, pal, ys, track, d, w, steer_axles=1)
    zf = d * 0.62
    m.block("FrameRailR", (0.14, L - 0.6, 0.3), (0.5, -0.1, zf), mat="Metal", color=GUNMETAL)
    m.block("FrameRailL", (0.14, L - 0.6, 0.3), (-0.5, -0.1, zf), mat="Metal", color=GUNMETAL)
    m.block("Bumper", (W, 0.2, 0.26), (0, L / 2 - 0.1, zf), mat="Metal", color=GUNMETAL)
    for s, tag in ((1, "R"), (-1, "L")):
        m.cyl(f"FuelTank{tag}", 1.0, 0.5, (s * 0.85, 0.7, zf + 0.05), ALONG_Y, "Metal", pal["dark"])
        m.block(f"Step{tag}", (0.3, 0.4, 0.06), (s * (W / 2 - 0.15), L / 2 - 1.6, zf - 0.2), mat="DiamondPlate", color=STEEL)
        for k, y in enumerate(ys[1:]):
            m.block(f"Mudflap{tag}{k}", (0.45, 0.04, 0.4), (s * track / 2, y - 0.75, d * 0.55), mat="Rubber", color=RUBBER)
    # cab
    if not red:
        # cab-over-engine, flat front
        cy = L / 2 - 0.85
        m.block("Cab", (W, 1.7, 1.55), (0, cy, zf + 1.05), mat="Metal", color=pal["base"])
        m.block("CabRoof", (W - 0.1, 1.6, 0.08), (0, cy - 0.05, zf + 1.86), mat="Metal", color=pal["dark"])
        m.block("Windshield", (W - 0.25, 0.05, 0.6), (0, cy + 0.86, zf + 1.4), mat="Glass", color=GLASS, transparency=0.35)
        m.block("GrilleFront", (W - 0.6, 0.05, 0.45), (0, cy + 0.86, zf + 0.62), mat="Metal", color=GUNMETAL)
        box_grid(m, "Grille", (-0.7, cy + 0.88, zf + 0.5), (0.08, 0.03, 0.3), 11, 1, 0.06, "Metal", DARK_STEEL)
        for s, tag in ((1, "R"), (-1, "L")):
            door = f"Door{tag}1"
            m.group(door, (s * W / 2, cy + 0.75, zf + 1.0))
            m.block(f"{door}Panel", (0.05, 1.2, 1.1), (s * (W / 2 + 0.02), cy + 0.1, zf + 0.95), mat="Metal", color=pal["base"], group=door)
            m.block(f"{door}Window", (0.04, 0.8, 0.45), (s * (W / 2 + 0.03), cy + 0.15, zf + 1.4), mat="Glass", color=GLASS, group=door, transparency=0.35)
            m.block(f"Mirror{tag}", (0.06, 0.12, 0.3), (s * (W / 2 + 0.25), cy + 0.6, zf + 1.45), mat="Metal", color=GUNMETAL)
            m.block(f"CabStripe{tag}", (0.02, 0.6, 0.12), (s * (W / 2 + 0.035), cy - 0.45, zf + 0.6), mat="SmoothPlastic", color=pal["mark"])
        lights_front(m, W / 2 - 0.3, L / 2 - 0.02, zf + 0.25)
        cab_back = cy - 0.85
    else:
        # bonneted cab
        hy = L / 2 - 0.75
        m.block("Bonnet", (1.5, 1.4, 0.75), (0, hy, zf + 0.75), mat="Metal", color=pal["base"])
        m.wedge("BonnetFront", (1.5, 0.25, 0.3), (0, hy + 0.82, zf + 1.0), mat="Metal", color=pal["base"])
        m.block("Grille", (1.1, 0.05, 0.6), (0, hy + 0.71, zf + 0.6), mat="Metal", color=pal["dark"])
        box_grid(m, "GrilleSlot", (-0.45, hy + 0.73, zf + 0.4), (0.05, 0.03, 0.45), 10, 1, 0.05, "Metal", DARK_STEEL)
        for s, tag in ((1, "R"), (-1, "L")):
            m.block(f"Fender{tag}", (0.5, 1.3, 0.06), (s * 2.05 / 2, hy - 0.05, d + 0.12), mat="Metal", color=pal["dark"])
            m.wedge(f"FenderLip{tag}", (0.5, 0.25, 0.25), (s * 2.05 / 2, hy + 0.7, d - 0.05), (0, 180, 0), "Metal", pal["dark"])
        cy = hy - 1.45
        m.block("Cab", (W - 0.1, 1.5, 1.3), (0, cy, zf + 1.15), mat="Metal", color=pal["base"])
        m.block("CabRoof", (W - 0.2, 1.4, 0.08), (0, cy, zf + 1.84), mat="Metal", color=pal["dark"])
        m.block("Windshield", (W - 0.35, 0.05, 0.55), (0, cy + 0.76, zf + 1.45), (-6, 0, 0), "Glass", GLASS, transparency=0.35)
        for s, tag in ((1, "R"), (-1, "L")):
            door = f"Door{tag}1"
            m.group(door, (s * (W / 2 - 0.05), cy + 0.7, zf + 1.0))
            m.block(f"{door}Panel", (0.05, 1.1, 1.0), (s * (W / 2 - 0.03), cy + 0.1, zf + 1.0), mat="Metal", color=pal["base"], group=door)
            m.block(f"{door}Window", (0.04, 0.7, 0.42), (s * (W / 2 - 0.02), cy + 0.15, zf + 1.48), mat="Glass", color=GLASS, group=door, transparency=0.35)
            m.block(f"CabStripe{tag}", (0.02, 0.6, 0.12), (s * (W / 2 - 0.015), cy - 0.3, zf + 0.75), mat="SmoothPlastic", color=pal["mark"])
            m.block(f"Headlamp{tag}Ring", (0.24, 0.05, 0.24), (s * 0.95, hy + 0.66, zf + 0.92), mat="Metal", color=GUNMETAL)
        lights_front(m, 0.95, hy + 0.7, zf + 0.92)
        cab_back = cy - 0.75
    lights_rear(m, W / 2 - 0.2, -L / 2 + 0.1, zf + 0.15)
    m.seat("Seat1", (-0.5, cy, zf + 0.75))
    m.seat("Seat2", (0.5, cy, zf + 0.75))
    m.attach("CamDriver", (-0.5, cy + 0.3, zf + 1.65))
    m.attach("Exhaust", (W / 2 - 0.1, cy - 0.6, zf + 1.9), (90, 0, 0))
    m.attach("EngineSmoke", (0, cy + (0.4 if not red else 1.4), zf + 1.2))
    m.attach("Exit1", (-1.8, cy, 0.2))
    m.attach("Exit2", (1.8, cy, 0.2))
    m.cyl("Antenna", 2.0, 0.025, (-W / 2 + 0.2, cab_back + 0.1, zf + 2.6), VERT, "Metal", GUNMETAL)
    flag(m, pal, (W / 2 - 0.15, cab_back + 0.1, zf + 1.6), h=1.0)
    return zf, cab_back


def truck_variant(team, kind):
    pal = FACTIONS[team]
    red = team == 2
    names = {"truck": "Truck", "supply_truck": "Supply", "mlrs": "MLRS", "comms": "Comms"}
    cats = {"truck": "Vehicles/Trucks", "supply_truck": "Vehicles/Trucks", "mlrs": "Vehicles/RocketLaunchers", "comms": "Vehicles/Trucks"}
    m = Model(f"{names[kind]}_{pal['key']}", cats[kind], kind, {"Team": team})
    L, W = 8.0, 2.5
    zf, cab_back = truck_chassis(m, pal, red, L, W)
    bed_len = cab_back + L / 2 - 0.2
    bed_y = -L / 2 + 0.1 + bed_len / 2
    bz = zf + 0.3
    top = bz + 1.0
    if kind in ("truck", "supply_truck"):
        m.block("BedFloor", (W, bed_len, 0.12), (0, bed_y, bz), mat="WoodPlanks", color=pal["dark"])
        for s, tag in ((1, "R"), (-1, "L")):
            m.block(f"BedSide{tag}", (0.06, bed_len, 0.55), (s * (W / 2 - 0.03), bed_y, bz + 0.33), mat="Metal", color=pal["base"])
            m.block(f"BedStripe{tag}", (0.02, 1.2, 0.14), (s * (W / 2 + 0.005), bed_y - 1.0, bz + 0.33), mat="SmoothPlastic", color=pal["mark"])
        m.block("Tailgate", (W, 0.06, 0.55), (0, bed_y - bed_len / 2, bz + 0.33), mat="Metal", color=pal["base"])
        m.block("Headboard", (W, 0.06, 0.8), (0, bed_y + bed_len / 2, bz + 0.46), mat="Metal", color=pal["dark"])
        if kind == "truck":
            m.block("Canvas", (W + 0.04, bed_len, 1.35), (0, bed_y, bz + 1.2), mat="Fabric", color=pal["canvas"])
            for s in (-1, 1):
                m.wedge(f"CanvasEave{'R' if s > 0 else 'L'}", (bed_len, 0.25, 0.25), (s * (W / 2 - 0.1), bed_y, bz + 2.0), (0, 0, -90 * s), "Fabric", pal["canvas"])
            m.block("CanvasRoof", (W - 0.45, bed_len, 0.1), (0, bed_y, bz + 1.93), mat="Fabric", color=pal["canvas"])
            for k in range(4):
                m.block(f"CanvasRib{k}", (W + 0.06, 0.05, 1.32), (0, bed_y - bed_len / 2 + 0.5 + k * (bed_len - 1) / 3, bz + 1.2), mat="Fabric", color=pal["dark"])
            top = bz + 1.95
            for k in range(6):
                m.seat(f"Seat{k + 3}", ((k % 2 - 0.5) * 1.3, bed_y + 1.2 - (k // 2) * 1.1, bz + 0.45))
                m.attach(f"Exit{k + 3}", ((k % 2 - 0.5) * 1.2, -L / 2 - 1.0 - (k // 2) * 0.7, 0.2))
        else:
            for i in range(3):
                for j in range(2):
                    m.block(f"AmmoCrate{i}_{j}", (0.9, 0.6, 0.45), ((j - 0.5) * 1.05, bed_y + 1.4 - i * 0.75, bz + 0.3), mat="WoodPlanks", color=WOOD)
                    m.block(f"CrateBand{i}_{j}", (0.92, 0.08, 0.47), ((j - 0.5) * 1.05, bed_y + 1.4 - i * 0.75, bz + 0.3), mat="Metal", color=GUNMETAL)
            for k in range(4):
                m.cyl(f"FuelBarrel{k}", 0.85, 0.55, ((k % 2 - 0.5) * 1.0, bed_y - 1.2 - (k // 2) * 0.6, bz + 0.48), VERT, "Metal", pal["dark"])
            m.block("SupplyPanel", (0.6, 0.02, 0.6), (0, bed_y - bed_len / 2 - 0.03, bz + 0.33), mat="SmoothPlastic", color=AMBER)
            top = bz + 0.9
    elif kind == "mlrs":
        m.block("Platform", (W, bed_len, 0.25), (0, bed_y, bz), mat="Metal", color=pal["dark"])
        for s, tag in ((1, "R"), (-1, "L")):
            m.block(f"Outrigger{tag}", (0.15, 0.15, 0.8), (s * (W / 2 - 0.1), bed_y - bed_len / 2 + 0.3, bz - 0.35), mat="Metal", color=GUNMETAL)
            m.block(f"PlatformStripe{tag}", (0.02, 1.0, 0.12), (s * (W / 2 + 0.005), bed_y, bz), mat="SmoothPlastic", color=pal["mark"])
        ring = (0, bed_y - 0.4, bz + 0.12)
        m.group("Turret", ring)
        m.cyl("LauncherBase", 0.35, 1.5, (ring[0], ring[1], bz + 0.3), VERT, "Metal", pal["base"], group="Turret")
        m.block("LauncherCradle", (1.9, 0.6, 0.4), (ring[0], ring[1], bz + 0.6), mat="Metal", color=pal["dark"], group="Turret")
        piv = (0, ring[1] - 0.2, bz + 0.85)
        m.group("Turret/Gun", piv)
        tubes = []
        if not red:
            # two boxy pods with 6 tubes each
            for p, px in enumerate((-0.5, 0.5)):
                m.block(f"Pod{p}", (0.9, 3.6, 0.75), (px, piv[1] + 1.4, piv[2] + 0.45), mat="Metal", color=pal["base"], group="Turret/Gun")
                for i in range(3):
                    for j in range(2):
                        tx, tz = px - 0.28 + i * 0.28, piv[2] + 0.25 + j * 0.38
                        m.cyl(f"Tube{p}_{i}_{j}", 0.04, 0.22, (tx, piv[1] + 3.22, tz), ALONG_Y, "Metal", GUNMETAL, group="Turret/Gun", segments=10)
                        tubes.append((tx, piv[1] + 3.3, tz))
        else:
            # Grad-style bundle of 20 tubes
            m.block("TubeFrame", (1.9, 0.2, 1.1), (0, piv[1] + 0.2, piv[2] + 0.45), mat="Metal", color=pal["dark"], group="Turret/Gun")
            m.block("TubeFrameFront", (1.9, 0.2, 1.1), (0, piv[1] + 2.6, piv[2] + 0.45), mat="Metal", color=pal["dark"], group="Turret/Gun")
            for i in range(5):
                for j in range(4):
                    tx, tz = -0.76 + i * 0.38, piv[2] + 0.06 + j * 0.27
                    m.cyl(f"Tube{i}_{j}", 3.2, 0.2, (tx, piv[1] + 1.5, tz), ALONG_Y, "Metal", pal["base"] if (i + j) % 2 == 0 else pal["light"], group="Turret/Gun", segments=10)
                    tubes.append((tx, piv[1] + 3.15, tz))
        for k, t in enumerate(tubes[:12]):
            m.attach(f"Tube{k + 1}", t, group="Turret/Gun")
        m.attach("Pod", tubes[0], group="Turret/Gun")
        m.attach("CamGunner", (0, ring[1] - 4.0, bz + 3.0), group="Turret")
        top = bz + 1.8
    elif kind == "comms":
        m.block("Shelter", (W, bed_len - 0.2, 1.9), (0, bed_y, bz + 0.95), mat="Metal", color=pal["base"])
        m.block("ShelterDoor", (0.8, 0.05, 1.5), (0.4, bed_y - bed_len / 2 + 0.08, bz + 0.85), mat="Metal", color=pal["dark"])
        m.block("ShelterRoof", (W - 0.1, bed_len - 0.3, 0.06), (0, bed_y, bz + 1.93), mat="DiamondPlate", color=pal["dark"])
        for s, tag in ((1, "R"), (-1, "L")):
            m.block(f"ShelterStripe{tag}", (0.02, 1.5, 0.15), (s * (W / 2 + 0.005), bed_y, bz + 1.6), mat="SmoothPlastic", color=pal["mark"])
            m.block(f"AC{tag}", (0.12, 0.5, 0.4), (s * (W / 2 + 0.06), bed_y - 1.0, bz + 1.2), mat="Metal", color=GUNMETAL)
        m.group("Turret", (0.6, bed_y + 0.8, bz + 1.95))
        m.cyl("Mast", 6.5, 0.16, (0.6, bed_y + 0.8, bz + 1.95 + 3.25), VERT, "Metal", STEEL, group="Turret")
        m.cyl("Dish", 0.15, 1.2, (0.6, bed_y + 0.95, bz + 7.4), ALONG_Y, "Metal", WHITE, group="Turret")
        for k in range(3):
            m.block(f"MastAntenna{k}", (0.05, 0.05, 1.2), (0.6 + (k - 1) * 0.3, bed_y + 0.8, bz + 8.4), mat="Metal", color=GUNMETAL, group="Turret")
        m.cyl("WhipA", 3.0, 0.03, (-0.9, bed_y - 1.5, bz + 3.4), VERT, "Metal", GUNMETAL)
        m.cyl("WhipB", 3.0, 0.03, (-0.9, bed_y + 1.0, bz + 3.4), VERT, "Metal", GUNMETAL)
        m.group("Turret/Gun", (0.6, bed_y + 0.95, bz + 7.4))
        top = bz + 1.95
    m.hitbox("Hitbox", (W, L, top - 0.6), (0, 0, 0.6 + (top - 0.6) / 2))
    return m


def ambulance(team):
    pal = FACTIONS[team]
    red = team == 2
    m = Model(f"Ambulance_{pal['key']}", "Vehicles/Trucks", "ambulance", {"Team": team})
    L, W, d, w, track = 6.0, 2.3, 0.96, 0.34, 1.9
    ys = [L / 2 - 1.15, -L / 2 + 1.2]
    axles(m, pal, ys, track, d, w, steer_axles=1)
    zf = d * 0.6
    m.block("Frame", (1.0, L - 0.4, 0.22), (0, 0, zf), mat="Metal", color=GUNMETAL)
    m.block("Bumper", (W, 0.16, 0.22), (0, L / 2 - 0.05, zf), mat="Metal", color=GUNMETAL)
    cy = L / 2 - 0.9
    m.block("Cab", (W, 1.4, 1.3), (0, cy, zf + 0.85), mat="Metal", color=pal["base"])
    m.wedge("CabNose", (W, 0.35, 0.5), (0, cy + 0.85, zf + 0.45), (0, 180, 0), "Metal", pal["base"])
    m.block("Windshield", (W - 0.3, 0.05, 0.55), (0, cy + 0.72, zf + 1.2), (-10, 0, 0), "Glass", GLASS, transparency=0.35)
    for s, tag in ((1, "R"), (-1, "L")):
        door = f"Door{tag}1"
        m.group(door, (s * W / 2, cy + 0.65, zf + 0.9))
        m.block(f"{door}Panel", (0.05, 1.0, 0.95), (s * (W / 2 + 0.02), cy + 0.1, zf + 0.8), mat="Metal", color=pal["base"], group=door)
        m.block(f"{door}Window", (0.04, 0.65, 0.4), (s * (W / 2 + 0.03), cy + 0.1, zf + 1.25), mat="Glass", color=GLASS, group=door, transparency=0.35)
    by = cy - 0.7 - 1.75
    m.block("MedBox", (W + 0.1, 3.5, 2.0), (0, by, zf + 1.1), mat="Metal", color=pal["light"])
    m.block("MedBoxRoof", (W, 3.4, 0.06), (0, by, zf + 2.12), mat="Metal", color=pal["dark"])
    for s, tag in ((1, "R"), (-1, "L")):
        m.block(f"CrossPanel{tag}", (0.02, 1.0, 1.0), (s * (W / 2 + 0.06), by, zf + 1.3), mat="SmoothPlastic", color=WHITE)
        m.block(f"CrossV{tag}", (0.03, 0.22, 0.7), (s * (W / 2 + 0.07), by, zf + 1.3), mat="SmoothPlastic", color=MED_GREEN)
        m.block(f"CrossH{tag}", (0.03, 0.7, 0.22), (s * (W / 2 + 0.07), by, zf + 1.3), mat="SmoothPlastic", color=MED_GREEN)
        m.block(f"BoxStripe{tag}", (0.02, 0.8, 0.12), (s * (W / 2 + 0.06), by - 1.2, zf + 0.5), mat="SmoothPlastic", color=pal["mark"])
    m.block("RoofCrossPanel", (1.0, 1.0, 0.02), (0, by, zf + 2.16), mat="SmoothPlastic", color=WHITE)
    m.block("RoofCrossV", (0.22, 0.7, 0.03), (0, by, zf + 2.17), mat="SmoothPlastic", color=MED_GREEN)
    m.block("RoofCrossH", (0.7, 0.22, 0.03), (0, by, zf + 2.17), mat="SmoothPlastic", color=MED_GREEN)
    m.group("DoorRear", (0, by - 1.76, zf + 1.1))
    m.block("RearDoors", (W - 0.2, 0.06, 1.7), (0, by - 1.78, zf + 1.0), mat="Metal", color=pal["light"], group="DoorRear")
    m.block("LightBar", (1.0, 0.25, 0.12), (0, cy + 0.2, zf + 1.56), mat="Neon", color=(0.2, 0.45, 1.0) if not red else (0.2, 0.45, 1.0))
    lights_front(m, W / 2 - 0.3, L / 2 - 0.05, zf + 0.5)
    lights_rear(m, W / 2 - 0.15, -L / 2 + 0.1, zf + 0.4)
    m.hitbox("Hitbox", (W, L, zf + 2.15 - 0.5), (0, 0, 0.5 + (zf + 2.15 - 0.5) / 2))
    m.seat("Seat1", (-0.5, cy, zf + 0.6))
    m.seat("Seat2", (0.5, cy, zf + 0.6))
    m.seat("Seat3", (0, by - 0.5, zf + 0.6))
    m.attach("CamDriver", (-0.5, cy + 0.3, zf + 1.45))
    m.attach("Exhaust", (0.7, -L / 2 - 0.05, zf - 0.1), (0, 0, 180))
    m.attach("EngineSmoke", (0, cy + 0.5, zf + 1.0))
    m.attach("Exit1", (-1.7, cy, 0.2))
    m.attach("Exit2", (1.7, cy, 0.2))
    m.attach("Exit3", (0, -L / 2 - 1.2, 0.2))
    flag(m, pal, (W / 2 - 0.1, by - 1.5, zf + 2.15), h=1.0)
    return m


BUILDERS = {
    "apc": apc,
    "jeep": jeep,
    "truck": lambda t: truck_variant(t, "truck"),
    "supply_truck": lambda t: truck_variant(t, "supply_truck"),
    "mlrs": lambda t: truck_variant(t, "mlrs"),
    "comms": lambda t: truck_variant(t, "comms"),
    "ambulance": ambulance,
}
