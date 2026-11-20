"""Military equipment and installations: radars, command posts, tents, supply
depots, defences (sandbags, barriers, bunkers, tank traps, watchtowers),
launch platforms, fuel tanks, helipads and flagpoles (control points + HQs).
Parts named "Team*" are recoloured to the owning team at runtime.
"""
import math

from rbxlib import Model
from models.palette import AMBER, DARK_STEEL, GLASS_DARK, GUNMETAL, RUBBER, STEEL, WHITE, WOOD, rgb

VERT = (0, -90, 0)
ALONG_Y = (0, 0, 90)
OLIVE = rgb(92, 96, 70)
CANVAS = rgb(96, 98, 76)
SAND = rgb(176, 160, 120)
SAND_DARK = rgb(150, 134, 98)
CONCRETE = rgb(150, 150, 146)
TEAM = rgb(200, 200, 200)  # placeholder, recoloured at runtime


def sandbag_course(m, name, x0, x1, y, z, rot_z=0, rows=3, bag=(0.6, 0.35, 0.18)):
    n = max(1, int((x1 - x0) / bag[0]))
    c, s = math.cos(math.radians(rot_z)), math.sin(math.radians(rot_z))
    for r in range(rows):
        off = (bag[0] / 2) if r % 2 else 0
        for i in range(n - (1 if r % 2 else 0)):
            lx = x0 + bag[0] * (i + 0.5) + off
            px, py = lx * c - y * s, lx * s + y * c
            col = SAND if (i + r) % 3 else SAND_DARK
            m.block(f"{name}_{r}_{i}", (bag[0] * 0.96, bag[1], bag[2]), (px, py, z + bag[2] * (r + 0.5)), (0, 0, rot_z + (3 if i % 2 else -3)), "Fabric", col)


def sandbag_wall():
    m = Model("SandbagWall", "MilitaryEquipment", "sandbag_wall", {"HP": 900, "Mat": "sand"})
    sandbag_course(m, "Bag", -3.0, 3.0, 0, 0, rows=4)
    return m


def sandbag_ring():
    m = Model("SandbagRing", "MilitaryEquipment", "sandbag_ring", {"HP": 900, "Mat": "sand"})
    for k, (rz, y) in enumerate(((0, 2.0), (180, 2.0), (90, 2.0), (270, 2.0))):
        sandbag_course(m, f"Side{k}", -1.8, 1.8 if k < 2 else 1.2, y, 0, rot_z=rz, rows=3)
    return m


def concrete_barrier():
    m = Model("ConcreteBarrier", "MilitaryEquipment", "concrete_barrier", {"HP": 700, "Mat": "concrete"})
    m.block("Base", (3.2, 0.7, 0.35), (0, 0, 0.175), mat="Concrete", color=CONCRETE)
    m.block("Mid", (3.2, 0.36, 0.45), (0, 0, 0.55), mat="Concrete", color=CONCRETE)
    m.block("Top", (3.2, 0.24, 0.25), (0, 0, 0.9), mat="Concrete", color=CONCRETE)
    for s in (-1, 1):
        m.wedge(f"Flare{'F' if s > 0 else 'B'}", (3.2, 0.17, 0.25), (0, s * 0.265, 0.475), (0, 0, 0 if s > 0 else 180), "Concrete", CONCRETE)
    m.block("Stripe", (0.8, 0.37, 0.12), (0.8, 0, 0.6), mat="SmoothPlastic", color=AMBER)
    return m


def tank_trap():
    m = Model("TankTrap", "MilitaryEquipment", "tank_trap", {"HP": 900, "Mat": "steel"})
    for k, rot in enumerate(((45, 0, 0), (0, 45, 0), (0, 0, 45))):
        m.block(f"Beam{k}", (0.2, 0.2, 1.9) if k < 2 else (1.9, 0.2, 0.2), (0, 0, 0.75), rot, "CorrodedMetal", rgb(86, 70, 56))
    return m


def bunker():
    m = Model("Bunker", "MilitaryEquipment", "bunker", {"HP": 3500, "Mat": "concrete"})
    m.block("WallFront", (6.4, 0.8, 1.8), (0, 2.2, 0.9), mat="Concrete", color=CONCRETE)
    m.block("WallBack", (6.4, 0.8, 2.4), (0, -2.2, 1.2), mat="Concrete", color=CONCRETE)
    for s in (-1, 1):
        m.block(f"WallSide{'R' if s > 0 else 'L'}", (0.8, 3.6, 2.4), (s * 2.8, 0, 1.2), mat="Concrete", color=CONCRETE)
    m.block("Roof", (6.8, 5.4, 0.5), (0, 0, 2.65), mat="Concrete", color=rgb(138, 138, 132))
    m.block("Slit", (4.0, 0.82, 0.25), (0, 2.2, 2.0), mat="Concrete", color=rgb(40, 40, 40))
    sandbag_course(m, "RoofBags", -3.0, 3.0, 1.8, 2.9, rows=2)
    m.block("Entrance", (1.2, 0.82, 1.9), (-1.6, -2.2, 0.95), mat="SmoothPlastic", color=rgb(20, 20, 20))
    return m


def watchtower():
    m = Model("Watchtower", "MilitaryEquipment", "watchtower", {"HP": 900, "Mat": "wood", "Climb": True, "Deck": 7.45})
    for i, (x, y) in enumerate(((1.6, 1.6), (-1.6, 1.6), (1.6, -1.6), (-1.6, -1.6))):
        m.block(f"Leg{i}", (0.25, 0.25, 7.4), (x * 0.92, y * 0.92, 3.7), (y * -2, x * 2, 0), "Wood", WOOD)
    for h in (2.2, 4.6):
        for s in (-1, 1):
            m.block(f"BraceX{h}{s}", (3.2, 0.12, 0.12), (0, s * 1.5, h), (0, 25, 0), "Wood", WOOD)
            m.block(f"BraceY{h}{s}", (0.12, 3.2, 0.12), (s * 1.5, 0, h), (25, 0, 0), "Wood", WOOD)
    m.block("Deck", (4.0, 4.0, 0.25), (0, 0, 7.4), mat="WoodPlanks", color=rgb(120, 96, 66), collide=True)
    for k, (x, y, w, d) in enumerate(((0, 1.95, 4.0, 0.1), (0, -1.95, 4.0, 0.1), (1.95, 0, 0.1, 4.0), (-1.95, 0, 0.1, 4.0))):
        m.block(f"Rail{k}", (w, d, 1.0), (x, y, 8.0), mat="WoodPlanks", color=rgb(112, 88, 60), collide=True)
    m.block("Roof", (4.4, 4.4, 0.15), (0, 0, 10.0), (4, 0, 0), "CorrodedMetal", rgb(96, 92, 84))
    for i, (x, y) in enumerate(((1.9, 1.9), (-1.9, 1.9), (1.9, -1.9), (-1.9, -1.9))):
        m.block(f"RoofPost{i}", (0.12, 0.12, 2.4), (x, y, 8.7), mat="Wood", color=WOOD)
    # ladder
    m.block("LadderRailL", (0.06, 0.06, 7.6), (-0.35, -2.15, 3.8), (-8, 0, 0), "Wood", WOOD)
    m.block("LadderRailR", (0.06, 0.06, 7.6), (0.35, -2.15, 3.8), (-8, 0, 0), "Wood", WOOD)
    for k in range(18):
        m.block(f"Rung{k}", (0.7, 0.05, 0.05), (0, -2.15 - k * 0.022 + 0.2, 0.3 + k * 0.4), mat="Wood", color=WOOD)
    m.attach("LadderBottom", (0, -2.6, 0.2))
    m.attach("LadderTop", (0, -1.4, 7.6))
    m.block("Searchlight", (0.4, 0.5, 0.4), (1.5, 1.5, 8.7), mat="Metal", color=GUNMETAL)
    m.light("Lamp", (1.5, 1.8, 8.7), (-15, 0, 0), brightness=4, range_=60, angle=35)
    return m


def radar():
    m = Model("Radar", "MilitaryEquipment", "radar", {"HP": 1300, "Mat": "metal"})
    m.block("Shelter", (3.0, 4.0, 2.4), (0, 0, 1.2), mat="Metal", color=OLIVE)
    m.block("ShelterRoof", (3.1, 4.1, 0.1), (0, 0, 2.45), mat="DiamondPlate", color=rgb(80, 82, 70))
    m.cyl("Pedestal", 1.6, 0.6, (0, 0, 3.3), VERT, "Metal", STEEL)
    m.group("Dish", (0, 0, 4.1))
    m.block("Array", (5.5, 0.25, 2.2), (0, 0.3, 4.6), (-12, 0, 0), "Metal", rgb(205, 208, 205), group="Dish")
    m.block("ArrayFrame", (5.6, 0.15, 0.15), (0, 0.15, 3.5), mat="Metal", color=GUNMETAL, group="Dish")
    for s in (-1, 1):
        m.block(f"Strut{s}", (0.1, 0.8, 0.1), (s * 1.5, -0.2, 4.1), (40, 0, 0), "Metal", GUNMETAL, group="Dish")
    m.block("Door", (0.9, 0.05, 1.9), (0.8, 2.02, 0.95), mat="Metal", color=rgb(70, 74, 60))
    m.block("Generator", (1.4, 1.0, 1.0), (2.4, -1.2, 0.5), mat="Metal", color=OLIVE)
    return m


def radar_mobile():
    m = Model("RadarMobile", "MilitaryEquipment", "radar_mobile", {"HP": 900, "Mat": "metal"})
    for s in (-1, 1):
        for k, y in enumerate((-1.5, 1.6)):
            m.cyl(f"Wheel{s}{k}", 0.35, 0.95, (s * 1.0, y, 0.48), (0, 0, 0), "Rubber", RUBBER)
    m.block("Trailer", (2.4, 6.4, 0.3), (0, 0, 0.95), mat="Metal", color=OLIVE)
    m.block("Cabin", (2.2, 2.4, 1.6), (0, -1.6, 1.9), mat="Metal", color=OLIVE)
    m.block("TeamPanel", (0.02, 1.0, 0.3), (1.11, -1.6, 2.3), mat="SmoothPlastic", color=TEAM)
    m.cyl("Mast", 1.5, 0.3, (0, 1.4, 1.9), VERT, "Metal", STEEL)
    m.group("Dish", (0, 1.4, 2.7))
    m.block("Array", (3.6, 0.2, 1.6), (0, 1.55, 3.2), (-15, 0, 0), "Metal", rgb(205, 208, 205), group="Dish")
    m.block("Drawbar", (0.2, 1.6, 0.15), (0, 3.9, 0.9), mat="Metal", color=GUNMETAL)
    return m


def comms_tower():
    m = Model("CommsTower", "MilitaryEquipment", "comms_tower", {"HP": 1400, "Mat": "steel", "Fall": True})
    h = 24
    for i, (x, y) in enumerate(((0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7))):
        m.block(f"Leg{i}", (0.12, 0.12, h), (x * 0.6, y * 0.6, h / 2), (y * -1.5, x * 1.5, 0), "Metal", rgb(200, 60, 40) if i % 2 else WHITE)
    for k in range(12):
        z = 1.5 + k * 1.9
        m.block(f"Ring{k}", (1.0, 1.0, 0.08), (0, 0, z), mat="Metal", color=STEEL, transparency=0.0)
        m.block(f"Diag{k}", (0.06, 1.3, 0.06), (0.45, 0, z + 0.9), (45 if k % 2 else -45, 0, 0), "Metal", STEEL)
    for k, a in enumerate((0, 120, 240)):
        m.cyl(f"Dish{k}", 0.2, 1.0, (math.sin(math.radians(a)) * 0.6, math.cos(math.radians(a)) * 0.6, h - 3), (0, 0, 90 - a), "Metal", WHITE)
    m.cyl("Whip", 4.0, 0.06, (0, 0, h + 2), VERT, "Metal", GUNMETAL)
    m.block("Beacon", (0.25, 0.25, 0.25), (0, 0, h + 0.2), mat="Neon", color=rgb(255, 40, 30))
    return m


def tent(large=False, command=False):
    name = "CommandTent" if command else ("TentLarge" if large else "Tent")
    m = Model(name, "MilitaryEquipment", "command_tent" if command else ("tent_large" if large else "tent"), {"HP": 200 if large else 120, "Mat": "canvas"})
    W, L, H = (5.0, 9.0, 3.4) if command else ((7.0, 13.0, 4.0) if large else (4.6, 5.6, 2.8))
    wall = H * 0.45
    m.block("Floor", (W, L, 0.05), (0, 0, 0.025), mat="Fabric", color=rgb(70, 72, 60))
    for s in (-1, 1):
        m.block(f"Wall{'R' if s > 0 else 'L'}", (0.05, L, wall), (s * W / 2, 0, wall / 2), mat="Fabric", color=CANVAS)
        m.wedge(f"Roof{'R' if s > 0 else 'L'}", (L, W / 2, H - wall), (s * W / 4, 0, wall + (H - wall) / 2), (0, 0, -90 * s), "Fabric", CANVAS)
    for s in (-1, 1):
        m.block(f"End{'F' if s > 0 else 'B'}", (W, 0.05, wall), (0, s * L / 2, wall / 2), mat="Fabric", color=CANVAS)
    for s in (-1, 1):
        for k in range(2):
            m.wedge(f"Gable{'F' if s > 0 else 'B'}{k}", (0.05, W / 2, H - wall), ((k - 0.5) * W / 2, s * L / 2, wall + (H - wall) / 2), (0, 0, 90 if k else -90), "Fabric", CANVAS)
    m.block("Door", (1.2, 0.06, 1.9), (0, L / 2 + 0.01, 0.95), mat="Fabric", color=rgb(60, 62, 50))
    m.block("TeamFlag", (0.02, 0.5, 0.35), (W / 2 + 0.2, L / 2, H + 0.4), mat="Fabric", color=TEAM)
    m.cyl("FlagPole", H + 0.8, 0.04, (W / 2 + 0.2, L / 2 + 0.25, (H + 0.8) / 2), VERT, "Metal", GUNMETAL)
    if command:
        m.block("MapTable", (1.6, 1.0, 0.8), (0, 0, 0.4), mat="WoodPlanks", color=WOOD)
        m.block("RadioBox", (0.6, 0.4, 0.5), (1.6, -2.5, 0.25), mat="Metal", color=OLIVE)
        m.cyl("RadioMast", 6.0, 0.06, (W / 2 + 0.6, -L / 2, 3.0), VERT, "Metal", GUNMETAL)
        m.block("Generator", (1.2, 0.9, 0.9), (-W / 2 - 1.0, -L / 2 + 1.0, 0.45), mat="Metal", color=OLIVE)
    return m


def supply_depot():
    m = Model("SupplyDepot", "MilitaryEquipment", "supply_depot", {"HP": 700, "Mat": "wood"})
    for i in range(3):
        for j in range(2):
            for k in range(2 - (i == 2)):
                m.block(f"Crate{i}{j}{k}", (1.1, 0.75, 0.6), (-2.5 + i * 1.25, -0.4 + j * 0.85, 0.3 + k * 0.62), (0, 0, (i * 7 + j * 3) % 8 - 4), "WoodPlanks", WOOD)
    for k in range(5):
        m.cyl(f"Drum{k}", 0.9, 0.58, (1.6 + (k % 3) * 0.62, -0.5 + (k // 3) * 0.62, 0.45), VERT, "Metal", rgb(70, 78, 58) if k % 2 else rgb(110, 50, 40))
    m.block("Pallet", (2.6, 1.2, 0.15), (0, 2.4, 0.075), mat="WoodPlanks", color=rgb(150, 120, 80))
    for k in range(3):
        m.block(f"AmmoBox{k}", (0.8, 0.4, 0.35), (-0.9 + k * 0.9, 2.4, 0.33), mat="Metal", color=OLIVE)
    m.block("Camo", (6.8, 4.4, 0.05), (0, 0.6, 2.6), mat="Fabric", color=rgb(78, 86, 60), transparency=0.25)
    for i, (x, y) in enumerate(((3.3, 2.7), (-3.3, 2.7), (3.3, -1.5), (-3.3, -1.5))):
        m.cyl(f"Pole{i}", 2.6, 0.08, (x, y, 1.3), VERT, "Wood", WOOD)
    m.block("TeamMarker", (0.6, 0.02, 0.4), (0, -1.0, 1.4), mat="SmoothPlastic", color=TEAM)
    return m


def fuel_tank():
    m = Model("FuelTank", "MilitaryEquipment", "fuel_tank", {"HP": 1600, "Mat": "metal", "Explode": True})
    m.cyl("Tank", 5.5, 7.6, (0, 0, 2.8), VERT, "Metal", rgb(190, 192, 186), segments=32)
    m.cyl("Roof", 0.3, 7.7, (0, 0, 5.65), VERT, "Metal", rgb(170, 172, 168), segments=32)
    m.cyl("Bund", 0.6, 9.0, (0, 0, 0.3), VERT, "Concrete", CONCRETE, segments=32)
    for k in range(10):
        m.block(f"Stair{k}", (0.8, 0.3, 0.06), (3.9, -2.0 + k * 0.42, 0.5 + k * 0.5), (0, 0, 0), "Metal", STEEL)
    m.block("WarningBand", (0.05, 2.0, 0.4), (3.81, 0, 3.0), mat="SmoothPlastic", color=AMBER)
    return m


def helipad():
    m = Model("Helipad", "MilitaryEquipment", "helipad", {})
    m.cyl("Pad", 0.15, 16, (0, 0, 0.075), VERT, "Concrete", rgb(120, 122, 118), segments=40)
    m.block("H1", (0.7, 5.0, 0.03), (-1.5, 0, 0.16), mat="SmoothPlastic", color=WHITE)
    m.block("H2", (0.7, 5.0, 0.03), (1.5, 0, 0.16), mat="SmoothPlastic", color=WHITE)
    m.block("H3", (3.0, 0.7, 0.03), (0, 0, 0.16), mat="SmoothPlastic", color=WHITE)
    for k in range(8):
        a = math.radians(k * 45)
        m.block(f"Lamp{k}", (0.2, 0.2, 0.15), (math.sin(a) * 7.6, math.cos(a) * 7.6, 0.2), mat="Neon", color=AMBER)
    return m


def launch_platform():
    """Stationary rocket launch platform (usable by the owner of point C)."""
    m = Model("LaunchPlatform", "MilitaryEquipment", "launch_platform", {"HP": 2200, "Mat": "steel"})
    m.block("Pad", (6.0, 10.0, 0.6), (0, 0, 0.3), mat="Concrete", color=CONCRETE)
    m.block("Base", (3.0, 4.0, 0.8), (0, 0, 1.0), mat="Metal", color=OLIVE)
    m.group("Turret", (0, 0, 1.4))
    m.cyl("Ring", 0.4, 2.6, (0, 0, 1.6), VERT, "Metal", STEEL, group="Turret")
    m.block("Cradle", (2.6, 1.0, 0.8), (0, 0, 2.2), mat="Metal", color=OLIVE, group="Turret")
    m.group("Turret/Gun", (0, -0.6, 2.6))
    tubes = []
    for i in range(4):
        for j in range(4):
            x, z = -0.75 + i * 0.5, 2.5 + j * 0.42
            m.cyl(f"Tube{i}{j}", 5.0, 0.36, (x, 1.2, z), ALONG_Y, "Metal", OLIVE if (i + j) % 2 else rgb(80, 86, 64), group="Turret/Gun", segments=12)
            tubes.append((x, 3.75, z))
    m.block("TubeBand", (2.2, 0.2, 1.8), (0, 0.0, 3.1), mat="Metal", color=GUNMETAL, group="Turret/Gun")
    for k, t in enumerate(tubes[:12]):
        m.attach(f"Tube{k + 1}", t, group="Turret/Gun")
    m.attach("Pod", tubes[0], group="Turret/Gun")
    m.attach("CamGunner", (0, -6.0, 6.0), group="Turret")
    m.block("ControlCabin", (2.0, 2.0, 2.0), (3.6, -3.2, 1.6), mat="Metal", color=OLIVE)
    m.seat("Seat1", (3.6, -3.2, 1.1))
    m.block("TeamPanel", (0.02, 1.2, 0.4), (4.61, -3.2, 2.0), mat="SmoothPlastic", color=TEAM)
    m.hitbox("Hitbox", (6.0, 10.0, 0.6), (0, 0, 0.3))
    return m


def flagpole_point():
    """Large control-point flagpole. The 'Flag' group is raised/lowered and the
    'Cloth*' parts are animated and recoloured by the client."""
    m = Model("ControlPointFlag", "MilitaryEquipment", "control_flag", {})
    m.cyl("Base", 0.5, 2.4, (0, 0, 0.25), VERT, "Concrete", CONCRETE, segments=24)
    m.cyl("Plinth", 0.35, 1.2, (0, 0, 0.67), VERT, "Concrete", rgb(130, 130, 126))
    m.cyl("Pole", 14.0, 0.18, (0, 0, 7.5), VERT, "Metal", rgb(200, 202, 204))
    m.ball("Finial", 0.32, (0, 0, 14.6), "Metal", rgb(220, 190, 80))
    m.group("Flag", (0, 0, 13.6))
    for k in range(8):
        m.block(f"Cloth{k}", (0.03, 0.4, 1.8), (0, -0.1 - 0.4 * (k + 0.5), 13.6 - 0.9), mat="Fabric", color=WHITE, group="Flag")
    m.block("Halyard", (0.02, 0.02, 13), (0.06, 0.05, 7.4), mat="Fabric", color=rgb(220, 220, 220))
    m.light("Floodlight", (0, 0, 0.9), (60, 0, 0), kind="PointLight", brightness=1.5, range_=20)
    return m


def flagpole_hq():
    m = Model("HQFlag", "MilitaryEquipment", "flagpole_hq", {})
    m.cyl("Pole", 9.0, 0.12, (0, 0, 4.5), VERT, "Metal", rgb(200, 202, 204))
    m.ball("Finial", 0.22, (0, 0, 9.1), "Metal", rgb(220, 190, 80))
    m.group("Flag", (0, 0, 8.5))
    for k in range(6):
        m.block(f"Cloth{k}", (0.03, 0.35, 1.3), (0, -0.1 - 0.35 * (k + 0.5), 8.5 - 0.65), mat="Fabric", color=TEAM, group="Flag")
    m.cyl("Base", 0.4, 1.0, (0, 0, 0.2), VERT, "Concrete", CONCRETE)
    return m


def gate_barrier():
    m = Model("GateBarrier", "MilitaryEquipment", "gate_barrier", {"HP": 40, "Mat": "metal"})
    m.block("Post", (0.4, 0.4, 1.1), (-3.2, 0, 0.55), mat="Metal", color=STEEL)
    m.group("Arm", (-3.2, 0, 1.0))
    for k in range(6):
        m.block(f"Arm{k}", (1.0, 0.1, 0.12), (-2.6 + k * 1.0, 0, 1.0), mat="SmoothPlastic", color=(rgb(220, 30, 30) if k % 2 else WHITE), group="Arm")
    m.block("Rest", (0.2, 0.2, 0.9), (3.2, 0, 0.45), mat="Metal", color=STEEL)
    return m


def guardhouse():
    m = Model("Guardhouse", "MilitaryEquipment", "guardhouse", {"HP": 900, "Mat": "concrete"})
    m.block("Walls", (3.0, 3.0, 2.6), (0, 0, 1.3), mat="Concrete", color=rgb(165, 165, 158))
    for s in (-1, 1):
        m.block(f"Window{'F' if s > 0 else 'B'}", (1.8, 0.05, 0.8), (0, s * 1.51, 1.7), mat="Glass", color=GLASS_DARK)
    m.block("Roof", (3.6, 3.6, 0.2), (0, 0, 2.7), mat="Concrete", color=rgb(120, 120, 116))
    m.block("Door", (0.9, 0.05, 1.9), (1.0, -1.52, 0.95), mat="Metal", color=rgb(70, 80, 70))
    return m


def containers(color_idx=0):
    cols = [rgb(46, 92, 140), rgb(150, 56, 38), rgb(88, 112, 70), rgb(160, 130, 60)]
    m = Model(f"Container{color_idx}", "MilitaryEquipment", "container", {"HP": 1500, "Mat": "metal"})
    c = cols[color_idx % 4]
    m.block("Box", (2.44, 12.0, 2.6), (0, 0, 1.3), mat="CorrodedMetal", color=c)
    for k in range(14):
        m.block(f"Rib{k}", (2.48, 0.08, 2.5), (0, -5.6 + k * 0.86, 1.3), mat="CorrodedMetal", color=c)
    m.block("Doors", (2.3, 0.06, 2.4), (0, 6.02, 1.3), mat="Metal", color=c)
    for s in (-1, 1):
        m.block(f"Lock{s}", (0.05, 0.08, 2.2), (s * 0.3, 6.07, 1.3), mat="Metal", color=GUNMETAL)
    return m


def container_stack():
    m = Model("ContainerStack", "MilitaryEquipment", "container_stack", {"HP": 2500, "Mat": "metal"})
    cols = [rgb(46, 92, 140), rgb(150, 56, 38), rgb(88, 112, 70)]
    for k in range(2):
        m.block(f"Box{k}", (2.44, 12.0, 2.6), (0, k * 0.4, 1.3 + k * 2.6), mat="CorrodedMetal", color=cols[k])
        for r in range(6):
            m.block(f"Rib{k}_{r}", (2.48, 0.1, 2.5), (0, -5.0 + r * 2.0 + k * 0.4, 1.3 + k * 2.6), mat="CorrodedMetal", color=cols[k])
    return m


def ENTRIES():
    return [
        ("sandbag_wall", sandbag_wall), ("sandbag_ring", sandbag_ring), ("concrete_barrier", concrete_barrier),
        ("tank_trap", tank_trap), ("bunker", bunker), ("watchtower", watchtower), ("radar", radar),
        ("radar_mobile", radar_mobile), ("comms_tower", comms_tower), ("tent", lambda: tent()),
        ("tent_large", lambda: tent(large=True)), ("command_tent", lambda: tent(command=True)),
        ("supply_depot", supply_depot), ("fuel_tank", fuel_tank), ("helipad", helipad),
        ("launch_platform", launch_platform), ("control_flag", flagpole_point), ("flagpole_hq", flagpole_hq),
        ("gate_barrier", gate_barrier), ("guardhouse", guardhouse), ("container0", lambda: containers(0)),
        ("container1", lambda: containers(1)), ("container2", lambda: containers(2)), ("container_stack", container_stack),
    ]
