"""Environment models: trees and bushes, street furniture, civilian cars, wrecks,
industrial props, rail rolling stock, rubble, rocks, landmarks and fence kits.
"""
import math

from rbxlib import Model
from models.palette import AMBER, CHROME, DARK_STEEL, GLASS, GLASS_DARK, GUNMETAL, LENS, RUBBER, STEEL, TAIL, WHITE, WOOD, rgb

VERT = (0, -90, 0)
ALONG_Y = (0, 0, 90)
BARK = rgb(88, 72, 56)
PINE_BARK = rgb(120, 82, 58)
BIRCH_BARK = rgb(214, 210, 198)
CONCRETE = rgb(150, 150, 146)
RUST = rgb(110, 70, 48)


# ---------------------------------------------------------------------------
# Vegetation (kept to a few parts each: there are thousands of trees)
# ---------------------------------------------------------------------------
def tree(kind):
    m = Model(f"Tree_{kind}", "Environment/Trees", kind, {"Mat": "wood", "HP": 300})
    if kind == "pine":
        m.cyl("Trunk", 12.0, 0.42, (0, 0, 6.0), VERT, "Wood", PINE_BARK, segments=10)
        m.ball("Crown1", 4.2, (0.4, 0.2, 12.4), "LeafyGrass", rgb(44, 66, 38))
        m.ball("Crown2", 3.6, (-0.8, -0.5, 13.6), "LeafyGrass", rgb(50, 74, 42))
        m.ball("Crown3", 3.0, (0.6, -0.4, 14.6), "LeafyGrass", rgb(40, 62, 36))
    elif kind == "spruce":
        m.cyl("Trunk", 3.0, 0.4, (0, 0, 1.5), VERT, "Wood", BARK, segments=8)
        for k, (d, h) in enumerate(((5.6, 2.2), (4.6, 2.0), (3.6, 1.9), (2.6, 1.8), (1.6, 1.8))):
            z = 2.4 + sum(x[1] * 0.85 for x in ((5.6, 2.2), (4.6, 2.0), (3.6, 1.9), (2.6, 1.8), (1.6, 1.8))[:k]) + h / 2
            m.cyl(f"Tier{k}", h, d, (0, 0, z), VERT, "LeafyGrass", rgb(34 + k * 3, 58 + k * 3, 36), segments=12)
    elif kind == "birch":
        m.cyl("Trunk", 9.0, 0.3, (0, 0, 4.5), VERT, "Wood", BIRCH_BARK, segments=8)
        m.block("BarkMark", (0.32, 0.31, 0.15), (0, 0, 3.0), mat="Wood", color=rgb(40, 40, 38))
        m.ball("Crown1", 3.6, (0.3, 0.2, 9.0), "LeafyGrass", rgb(98, 132, 60))
        m.ball("Crown2", 2.8, (-0.7, -0.3, 10.4), "LeafyGrass", rgb(110, 142, 66))
    elif kind == "oak":
        m.cyl("Trunk", 5.0, 0.75, (0, 0, 2.5), VERT, "Wood", BARK, segments=10)
        m.ball("Crown1", 6.4, (0, 0, 7.0), "Grass", rgb(62, 92, 44))
        m.ball("Crown2", 4.6, (2.0, 1.0, 6.2), "Grass", rgb(70, 100, 48))
        m.ball("Crown3", 4.4, (-1.8, -0.8, 6.4), "Grass", rgb(58, 86, 42))
    elif kind == "poplar":
        m.cyl("Trunk", 4.0, 0.42, (0, 0, 2.0), VERT, "Wood", BARK, segments=8)
        m.cyl("Column", 11.0, 2.6, (0, 0, 9.0), VERT, "LeafyGrass", rgb(72, 102, 50), segments=12)
        m.ball("Top", 2.6, (0, 0, 14.5), "LeafyGrass", rgb(76, 108, 52))
        m.ball("Bottom", 2.6, (0, 0, 3.6), "LeafyGrass", rgb(68, 96, 48))
    elif kind == "willow":
        m.cyl("Trunk", 4.5, 0.7, (0, 0, 2.25), (8, -90, 0), "Wood", BARK, segments=10)
        m.ball("Crown1", 6.0, (0, 0.3, 6.2), "LeafyGrass", rgb(110, 138, 72))
        m.cyl("Drape", 3.4, 6.6, (0, 0.3, 4.4), VERT, "LeafyGrass", rgb(104, 132, 68), segments=14)
    elif kind == "fruit":
        m.cyl("Trunk", 2.4, 0.3, (0, 0, 1.2), VERT, "Wood", BARK, segments=8)
        m.ball("Crown1", 3.4, (0, 0, 3.4), "Grass", rgb(84, 116, 52))
        m.ball("Crown2", 2.4, (0.8, 0.5, 3.0), "Grass", rgb(90, 122, 56))
    return m


def bush(v):
    m = Model(f"Bush_{v}", "Environment/Trees", "bush", {"Mat": "wood", "HP": 60})
    cols = [rgb(62, 88, 44), rgb(78, 102, 50), rgb(56, 80, 46)]
    for k in range(2 + (v % 2)):
        m.ball(f"Leaf{k}", 1.6 - k * 0.3, ((k - 1) * 0.6, (k % 2) * 0.4, 0.6), "LeafyGrass", cols[(v + k) % 3])
    return m


# ---------------------------------------------------------------------------
# Street furniture
# ---------------------------------------------------------------------------
def streetlight():
    m = Model("Streetlight", "Environment/Street", "streetlight", {"HP": 160, "Mat": "metal", "Fall": True})
    m.cyl("Pole", 7.8, 0.18, (0, 0, 3.9), VERT, "Metal", rgb(110, 112, 110), segments=10)
    m.cyl("Arm", 1.6, 0.1, (0, 0.75, 7.7), ALONG_Y, "Metal", rgb(110, 112, 110))
    m.block("Lamp", (0.4, 0.7, 0.18), (0, 1.5, 7.62), mat="Metal", color=GUNMETAL)
    m.block("LampGlass", (0.32, 0.6, 0.04), (0, 1.5, 7.52), mat="Neon", color=rgb(255, 214, 160), transparency=0.0, lamp=True)
    m.light("Light", (0, 1.5, 7.4), (-90, 0, 0), brightness=2.5, range_=40, angle=110, color=(1.0, 0.82, 0.6))
    m.cyl("Base", 0.6, 0.35, (0, 0, 0.3), VERT, "Concrete", CONCRETE)
    return m


def power_pole():
    m = Model("PowerPole", "Environment/Street", "power_pole", {"HP": 220, "Mat": "wood", "Fall": True})
    m.cyl("Pole", 9.0, 0.26, (0, 0, 4.5), VERT, "Wood", rgb(96, 80, 62), segments=10)
    m.block("CrossArm", (2.4, 0.12, 0.12), (0, 0, 8.4), mat="Wood", color=rgb(90, 74, 58))
    for k, x in enumerate((-1.0, 0.0, 1.0)):
        m.cyl(f"Insulator{k}", 0.25, 0.12, (x, 0, 8.6), VERT, "Glass", rgb(130, 160, 170))
        m.attach(f"Wire{k}", (x, 0, 8.7))
    return m


def road_sign():
    m = Model("RoadSign", "Environment/Street", "road_sign", {"HP": 60, "Mat": "metal", "Fall": True})
    m.cyl("Post", 2.4, 0.08, (0, 0, 1.2), VERT, "Metal", STEEL)
    m.block("Board", (1.6, 0.04, 0.55), (0, 0.04, 2.2), mat="SmoothPlastic", color=rgb(18, 64, 140), sign=True)
    m.block("Border", (1.66, 0.03, 0.61), (0, 0.02, 2.2), mat="SmoothPlastic", color=WHITE)
    return m


def bus_stop():
    m = Model("BusStop", "Environment/Street", "bus_stop", {"HP": 260, "Mat": "metal"})
    m.block("Back", (4.8, 0.08, 2.2), (0, -0.8, 1.2), mat="Glass", color=GLASS, transparency=0.4)
    for s in (-1, 1):
        m.block(f"Side{s}", (0.08, 1.6, 2.2), (s * 2.4, 0, 1.2), mat="Glass", color=GLASS, transparency=0.4)
        m.block(f"Post{s}", (0.1, 0.1, 2.5), (s * 2.4, -0.8, 1.25), mat="Metal", color=STEEL)
    m.block("Roof", (5.2, 1.9, 0.12), (0, -0.05, 2.5), mat="Metal", color=rgb(70, 90, 110))
    m.block("Bench", (3.0, 0.45, 0.1), (0, -0.5, 0.5), mat="WoodPlanks", color=WOOD)
    return m


def bench():
    m = Model("Bench", "Environment/Street", "bench", {"HP": 80, "Mat": "wood"})
    m.block("Seat", (1.8, 0.45, 0.08), (0, 0, 0.45), mat="WoodPlanks", color=WOOD)
    m.block("Back", (1.8, 0.06, 0.4), (0, -0.22, 0.75), (-10, 0, 0), "WoodPlanks", WOOD)
    for s in (-1, 1):
        m.block(f"Leg{s}", (0.06, 0.45, 0.45), (s * 0.8, 0, 0.22), mat="Metal", color=GUNMETAL)
    return m


def car(v, wreck=False):
    cols = [rgb(150, 30, 28), rgb(220, 220, 214), rgb(40, 70, 120), rgb(96, 110, 70)]
    c = RUST if wreck else cols[v % 4]
    m = Model("CarWreck" if wreck else f"Car{v}", "Environment/Street", "car_wreck" if wreck else "car_civilian", {"HP": 600 if wreck else 300, "Mat": "metal", "Explode": not wreck})
    for s in (-1, 1):
        for k, y in enumerate((1.25, -1.25)):
            if wreck and k == 1 and s == 1:
                continue
            m.cyl(f"Wheel{s}{k}", 0.2, 0.62, (s * 0.78, y, 0.31 - (0.15 if wreck else 0)), (0, 0, 0), "Rubber", RUBBER)
    m.block("Body", (1.72, 4.1, 0.6), (0, 0, 0.62), (0, 3 if wreck else 0, 0), "CorrodedMetal" if wreck else "Metal", c)
    m.block("Cabin", (1.55, 2.0, 0.55), (0, -0.25, 1.17), (0, 3 if wreck else 0, 0), "CorrodedMetal" if wreck else "Metal", c)
    m.wedge("Windscreen", (1.5, 0.6, 0.53), (0, 1.05, 1.17), mat="Glass", color=GLASS_DARK if wreck else GLASS, transparency=0.0 if wreck else 0.3)
    m.wedge("RearScreen", (1.5, 0.5, 0.53), (0, -1.5, 1.17), (0, 0, 180), "Glass", GLASS_DARK if wreck else GLASS, transparency=0.0 if wreck else 0.3)
    if not wreck:
        for s in (-1, 1):
            m.block(f"Headlamp{s}", (0.3, 0.04, 0.14), (s * 0.6, 2.06, 0.72), mat="Glass", color=LENS)
            m.block(f"Taillamp{s}", (0.28, 0.04, 0.12), (s * 0.6, -2.06, 0.75), mat="Neon", color=TAIL)
        m.block("Bumpers", (1.76, 4.24, 0.12), (0, 0, 0.42), mat="Metal", color=CHROME)
    else:
        m.block("Soot", (1.6, 2.0, 0.02), (0, 0.5, 0.93), mat="SmoothPlastic", color=rgb(30, 28, 26))
    return m


def tank_wreck():
    m = Model("TankWreck", "Environment/Street", "tank_wreck", {"HP": 5000, "Mat": "steel"})
    m.block("Hull", (3.2, 6.8, 1.1), (0, 0, 0.75), (0, 4, 2), "CorrodedMetal", rgb(70, 62, 52))
    m.wedge("Glacis", (3.2, 1.2, 0.5), (0, 3.9, 1.1), mat="CorrodedMetal", color=rgb(66, 58, 50))
    for s in (-1, 1):
        m.block(f"Track{s}", (0.6, 6.6, 0.8), (s * 1.75, 0, 0.4), mat="Rubber", color=rgb(40, 36, 34))
    m.cyl("TurretTilted", 0.6, 2.5, (0.8, -1.8, 1.0), (30, -70, 0), "CorrodedMetal", rgb(60, 52, 44))
    m.cyl("BarrelBent", 4.0, 0.2, (1.8, 0.8, 1.5), (0, 20, 75), "CorrodedMetal", rgb(54, 48, 42))
    m.block("Soot", (2.6, 3.0, 0.03), (0, 0.4, 1.32), mat="SmoothPlastic", color=rgb(28, 26, 24))
    return m


def haystack():
    m = Model("Haystack", "Environment/Farm", "haystack", {"HP": 150, "Mat": "hay"})
    m.cyl("Bale", 1.6, 1.8, (0, 0, 0.9), (0, 0, 0), "Fabric", rgb(196, 168, 92))
    m.cyl("Bale2", 1.6, 1.8, (0.2, 1.7, 0.9), (0, 0, 8), "Fabric", rgb(186, 158, 86))
    m.cyl("Bale3", 1.6, 1.7, (0.1, 0.85, 2.3), (0, 0, -4), "Fabric", rgb(200, 172, 96))
    return m


def crate_stack():
    m = Model("CrateStack", "Environment/Industrial", "crate_stack", {"HP": 220, "Mat": "wood"})
    for i in range(3):
        for k in range(2 - (i == 2)):
            m.block(f"Crate{i}{k}", (1.1, 1.1, 0.9), ((i - 1) * 1.15, 0, 0.45 + k * 0.92), (0, 0, (i * 9) % 10 - 5), "WoodPlanks", rgb(140, 110, 72))
    return m


def fuel_barrels():
    m = Model("FuelBarrels", "Environment/Industrial", "fuel_barrels", {"HP": 60, "Mat": "metal", "Explode": True})
    for k in range(5):
        m.cyl(f"Barrel{k}", 0.9, 0.58, ((k % 3 - 1) * 0.62, (k // 3) * 0.62 - 0.3, 0.45), VERT, "Metal", rgb(150, 40, 30) if k % 2 else rgb(60, 80, 110))
    return m


def transformer():
    m = Model("Transformer", "Environment/Industrial", "transformer", {"HP": 400, "Mat": "metal", "Explode": True})
    m.block("Tank", (2.0, 1.6, 2.0), (0, 0, 1.0), mat="Metal", color=rgb(110, 116, 106))
    for k in range(6):
        m.block(f"Fin{k}", (0.06, 1.4, 1.6), (-1.05 - (k % 2) * 0.0, -0.6 + k * 0.24, 1.0), mat="Metal", color=rgb(100, 106, 96))
    for k in range(3):
        m.cyl(f"Bushing{k}", 0.6, 0.18, ((k - 1) * 0.6, 0, 2.3), VERT, "Glass", rgb(140, 90, 70))
    m.block("Warning", (0.5, 0.02, 0.4), (0, 0.81, 1.3), mat="SmoothPlastic", color=AMBER)
    return m


def chem_tank():
    m = Model("ChemTank", "Environment/Industrial", "chem_tank", {"HP": 1200, "Mat": "metal"})
    m.cyl("Tank", 6.0, 4.8, (0, 0, 3.6), VERT, "Metal", rgb(200, 200, 196), segments=28)
    m.ball("Dome", 4.8, (0, 0, 6.4), "Metal", rgb(196, 196, 192))
    for k in range(4):
        a = math.radians(k * 90 + 45)
        m.block(f"Leg{k}", (0.25, 0.25, 1.2), (math.sin(a) * 2.0, math.cos(a) * 2.0, 0.6), mat="Metal", color=STEEL)
    m.block("Band", (4.9, 4.9, 0.3), (0, 0, 4.0), mat="Metal", color=rgb(40, 100, 160), transparency=0.0)
    return m


def pipe_rack():
    m = Model("PipeRack", "Environment/Industrial", "pipe_rack", {"HP": 900, "Mat": "steel"})
    for k in range(4):
        y = -9 + k * 6
        for s in (-1, 1):
            m.block(f"Post{k}{s}", (0.25, 0.25, 3.4), (s * 0.7, y, 1.7), mat="Metal", color=STEEL)
        m.block(f"Beam{k}", (1.7, 0.25, 0.2), (0, y, 3.3), mat="Metal", color=STEEL)
    for k, (x, d, c) in enumerate(((-0.45, 0.4, rgb(180, 160, 60)), (0.0, 0.5, rgb(200, 200, 196)), (0.45, 0.3, rgb(140, 60, 40)))):
        m.cyl(f"Pipe{k}", 18.4, d, (x, -0.0, 3.62), ALONG_Y, "Metal", c)
    return m


def gas_pump():
    m = Model("GasPump", "Environment/Street", "gas_pump", {"HP": 120, "Mat": "metal", "Explode": True})
    m.block("Body", (0.8, 0.55, 1.7), (0, 0, 0.85), mat="Metal", color=rgb(200, 40, 34))
    m.block("Screen", (0.5, 0.03, 0.35), (0, 0.29, 1.35), mat="Glass", color=GLASS_DARK)
    m.block("Base", (1.1, 0.8, 0.2), (0, 0, 0.1), mat="Concrete", color=CONCRETE)
    m.cyl("Hose", 0.6, 0.06, (0.45, 0.1, 0.9), VERT, "Rubber", RUBBER)
    return m


def fuel_canopy():
    m = Model("FuelCanopy", "Environment/Street", "fuel_canopy", {"HP": 900, "Mat": "metal"})
    m.block("Roof", (18.0, 10.0, 0.6), (0, 0, 5.2), mat="Metal", color=WHITE)
    m.block("Fascia", (18.2, 10.2, 0.25), (0, 0, 5.0), mat="SmoothPlastic", color=rgb(30, 120, 60))
    for s in (-1, 1):
        m.block(f"Column{s}", (0.6, 0.6, 5.0), (s * 5.0, 0, 2.5), mat="Metal", color=rgb(200, 200, 196))
    m.light("CanopyLight", (0, 0, 4.85), (-90, 0, 0), kind="PointLight", brightness=1.5, range_=26)
    return m


def water_tower():
    m = Model("WaterTower", "Environment/Industrial", "water_tower", {"HP": 6000, "Mat": "concrete", "Climb": True, "Deck": 22.2})
    m.cyl("Shaft", 22.0, 4.2, (0, 0, 11.0), VERT, "Concrete", rgb(170, 168, 160), segments=24)
    m.cyl("Tank", 6.0, 9.0, (0, 0, 25.0), VERT, "Concrete", rgb(180, 178, 170), segments=28)
    m.cyl("Gallery", 0.2, 10.4, (0, 0, 22.1), VERT, "Metal", STEEL, segments=28, collide=True)
    for k in range(16):
        a = math.radians(k * 22.5)
        m.block(f"Railing{k}", (0.06, 2.0, 1.0), (math.sin(a) * 5.15, math.cos(a) * 5.15, 22.7), (0, 0, -k * 22.5 + 90), "Metal", STEEL)
    m.cyl("Roof", 1.0, 9.2, (0, 0, 28.5), VERT, "Concrete", rgb(150, 148, 140), segments=28)
    m.block("Door", (1.2, 0.1, 2.2), (0, 2.08, 1.1), mat="Metal", color=rgb(90, 110, 90))
    for k in range(20):
        m.block(f"LadderRung{k}", (0.6, 0.05, 0.05), (0, -2.18, 0.5 + k * 1.08), mat="Metal", color=STEEL)
    m.block("LadderRailL", (0.05, 0.05, 21.8), (-0.3, -2.18, 10.9), mat="Metal", color=STEEL)
    m.block("LadderRailR", (0.05, 0.05, 21.8), (0.3, -2.18, 10.9), mat="Metal", color=STEEL)
    m.attach("LadderBottom", (0, -2.7, 0.2))
    m.attach("LadderTop", (0, -3.0, 22.3))
    return m


def chimney():
    m = Model("Chimney", "Environment/Industrial", "chimney", {"HP": 4500, "Mat": "brick", "Fall": True})
    for k in range(8):
        d = 4.4 - k * 0.32
        m.cyl(f"Section{k}", 5.0, d, (0, 0, 2.5 + k * 5.0), VERT, "Brick", rgb(146, 76, 58) if k % 2 else rgb(136, 70, 54), segments=20)
    m.cyl("Crown", 0.6, 2.4, (0, 0, 40.3), VERT, "Concrete", rgb(60, 56, 52))
    for k in range(3):
        m.cyl(f"Band{k}", 0.4, 4.2 - k * 0.9, (0, 0, 8 + k * 11), VERT, "Metal", rgb(200, 200, 196))
    return m


def rail_car(loco=False):
    m = Model("Locomotive" if loco else "RailCar", "Environment/Rail", "locomotive" if loco else "rail_car", {"HP": 4000 if loco else 3000, "Mat": "steel"})
    L = 17.0 if loco else 15.0
    for s in (-1, 1):
        for b in (-1, 1):
            for w in (-1, 1):
                m.cyl(f"Wheel{s}{b}{w}", 0.15, 0.9, (s * 0.72, b * (L / 2 - 2.5) + w * 0.9, 0.45), (0, 0, 0), "Metal", DARK_STEEL)
            m.block(f"Bogie{s}{b}", (0.2, 2.6, 0.5), (s * 0.85, b * (L / 2 - 2.5), 0.55), mat="Metal", color=GUNMETAL)
    m.block("Frame", (2.8, L, 0.4), (0, 0, 1.1), mat="Metal", color=GUNMETAL)
    if loco:
        m.block("Hood", (2.6, L - 5.0, 2.6), (0, -1.5, 2.6), mat="Metal", color=rgb(40, 90, 70))
        m.block("Cab", (3.0, 4.0, 3.2), (0, L / 2 - 2.5, 2.9), mat="Metal", color=rgb(40, 90, 70))
        m.block("CabWindows", (3.02, 2.0, 0.8), (0, L / 2 - 2.0, 3.6), mat="Glass", color=GLASS_DARK)
        m.block("Stripe", (2.62, L - 5.0, 0.3), (0, -1.5, 1.6), mat="SmoothPlastic", color=AMBER)
        m.light("Headlight1", (0, L / 2 - 0.4, 4.0), brightness=3, range_=80)
    else:
        m.block("Box", (3.0, L - 0.6, 3.0), (0, 0, 2.8), mat="CorrodedMetal", color=rgb(116, 60, 42))
        m.block("Door", (0.05, 2.6, 2.4), (1.52, 0, 2.6), mat="CorrodedMetal", color=rgb(100, 52, 36))
        m.block("Roof", (3.1, L - 0.5, 0.15), (0, 0, 4.35), mat="Metal", color=rgb(90, 88, 84))
    return m


def rail_platform():
    m = Model("RailPlatform", "Environment/Rail", "rail_platform", {})
    m.block("Platform", (6.0, 60.0, 0.8), (0, 0, 0.4), mat="Concrete", color=CONCRETE, collide=True)
    m.block("Edge", (0.4, 60.0, 0.82), (2.9, 0, 0.41), mat="SmoothPlastic", color=rgb(230, 200, 40))
    for k in range(4):
        m.block(f"ShelterPost{k}", (0.15, 0.15, 3.0), (-1.5, -9 + k * 6, 2.3), mat="Metal", color=STEEL)
    m.block("ShelterRoof", (3.6, 20.0, 0.15), (-1.2, 0, 3.85), (0, 4, 0), "Metal", rgb(70, 80, 90))
    return m


def monument():
    m = Model("Monument", "Environment/Street", "monument", {"HP": 1500, "Mat": "concrete"})
    m.block("Base", (3.6, 3.6, 0.6), (0, 0, 0.3), mat="Granite", color=rgb(110, 110, 112))
    m.block("Plinth", (2.2, 2.2, 1.6), (0, 0, 1.4), mat="Granite", color=rgb(120, 120, 122))
    m.block("Obelisk", (1.0, 1.0, 5.0), (0, 0, 4.7), mat="Granite", color=rgb(126, 126, 128))
    m.wedge("TipA", (1.0, 0.5, 0.6), (0, 0.25, 7.5), mat="Granite", color=rgb(126, 126, 128))
    m.wedge("TipB", (1.0, 0.5, 0.6), (0, -0.25, 7.5), (0, 0, 180), "Granite", rgb(126, 126, 128))
    m.block("Plaque", (0.8, 0.05, 0.5), (0, 1.13, 1.6), mat="Metal", color=rgb(150, 120, 60))
    return m


def shed():
    m = Model("Shed", "Environment/Farm", "shed", {"HP": 300, "Mat": "wood"})
    m.block("Walls", (3.0, 2.4, 2.2), (0, 0, 1.1), mat="WoodPlanks", color=rgb(110, 86, 60))
    m.wedge("RoofA", (3.4, 1.4, 0.6), (0, 0.6, 2.5), mat="CorrodedMetal", color=rgb(100, 96, 88))
    m.wedge("RoofB", (3.4, 1.4, 0.6), (0, -0.6, 2.5), (0, 0, 180), "CorrodedMetal", rgb(100, 96, 88))
    m.block("Door", (0.9, 0.05, 1.8), (0.6, 1.22, 0.9), mat="WoodPlanks", color=rgb(90, 70, 50))
    return m


def well():
    m = Model("Well", "Environment/Farm", "well", {"HP": 600, "Mat": "concrete"})
    m.cyl("Ring", 0.9, 1.5, (0, 0, 0.45), VERT, "Cobblestone", rgb(130, 126, 120))
    for s in (-1, 1):
        m.block(f"Post{s}", (0.12, 0.12, 1.6), (s * 0.7, 0, 1.4), mat="Wood", color=WOOD)
    m.wedge("RoofA", (1.8, 0.6, 0.4), (0, 0.3, 2.3), mat="WoodPlanks", color=rgb(100, 76, 52))
    m.wedge("RoofB", (1.8, 0.6, 0.4), (0, -0.3, 2.3), (0, 0, 180), "WoodPlanks", rgb(100, 76, 52))
    return m


def woodpile():
    m = Model("Woodpile", "Environment/Farm", "woodpile", {"HP": 200, "Mat": "wood"})
    for r in range(3):
        for i in range(6 - r):
            m.cyl(f"Log{r}{i}", 1.0, 0.24, ((i - (5 - r) / 2) * 0.25, 0, 0.12 + r * 0.21), ALONG_Y, "Wood", rgb(150 - i * 4, 110, 70))
    return m


def rubble_pile(v):
    m = Model(f"Rubble{v}", "Environment/Rubble", "rubble_pile", {"Mat": "concrete"})
    import random
    rnd = random.Random(v * 977)
    cols = [rgb(150, 146, 140), rgb(130, 120, 110), rgb(160, 110, 88), rgb(110, 106, 100)]
    m.block("Core", (4.6, 4.6, 0.9), (0, 0, 0.3), (0, 0, rnd.uniform(0, 30)), "Concrete", cols[0], collide=True)
    for k in range(12):
        x, y = rnd.uniform(-2.4, 2.4), rnd.uniform(-2.4, 2.4)
        s = rnd.uniform(0.4, 1.2)
        fn = m.wedge if k % 3 == 0 else m.block
        fn(f"Chunk{k}", (s, s * rnd.uniform(0.6, 1.4), s * 0.7), (x, y, 0.7 + rnd.uniform(0, 0.6)),
           (rnd.uniform(-30, 30), rnd.uniform(-30, 30), rnd.uniform(0, 360)), rnd.choice(["Concrete", "Brick", "Concrete"]), rnd.choice(cols))
    for k in range(2):
        m.cyl(f"Rebar{k}", rnd.uniform(1.5, 2.5), 0.04, (rnd.uniform(-1, 1), rnd.uniform(-1, 1), 1.3), (rnd.uniform(-40, 40), rnd.uniform(-60, 60), rnd.uniform(0, 180)), "CorrodedMetal", RUST)
    return m


def rock(large=False):
    m = Model("RockLarge" if large else "Rock", "Environment/Rocks", "rock_large" if large else "rock", {"Mat": "rock"})
    s = 2.2 if large else 1.0
    m.block("A", (2.0 * s, 1.6 * s, 1.1 * s), (0, 0, 0.45 * s), (8, -6, 20), "Rock", rgb(118, 114, 108), collide=True)
    m.wedge("B", (1.4 * s, 1.2 * s, 0.9 * s), (0.6 * s, -0.3 * s, 1.0 * s), (0, 10, 60), "Rock", rgb(108, 104, 98))
    m.block("C", (1.0 * s, 1.0 * s, 0.7 * s), (-0.7 * s, 0.5 * s, 0.35 * s), (14, 4, -30), "Rock", rgb(124, 120, 112))
    return m


# ---------------------------------------------------------------------------
# Fence kits: one 3 m segment each, cloned along fence polylines at runtime
# ---------------------------------------------------------------------------
def fence(kind):
    m = Model(f"Fence_{kind}", "Environment/Fences", f"fence_{kind}", {"HP": {"wood": 90, "picket": 70, "metal": 160, "concrete": 600, "military": 220}[kind],
                                                                       "Mat": {"wood": "wood", "picket": "wood", "metal": "metal", "concrete": "concrete", "military": "metal"}[kind]})
    if kind == "wood":
        m.block("Post", (0.14, 0.14, 1.4), (-1.5, 0, 0.7), mat="Wood", color=WOOD)
        for k, z in enumerate((0.45, 1.05)):
            m.block(f"Rail{k}", (3.0, 0.06, 0.12), (0, 0, z), mat="WoodPlanks", color=rgb(120, 94, 64))
    elif kind == "picket":
        m.block("Post", (0.12, 0.12, 1.2), (-1.5, 0, 0.6), mat="Wood", color=rgb(220, 220, 210))
        m.block("Rail", (3.0, 0.05, 0.1), (0, -0.04, 0.7), mat="Wood", color=rgb(220, 220, 210))
        for k in range(10):
            m.block(f"Picket{k}", (0.1, 0.03, 1.0), (-1.35 + k * 0.3, 0, 0.55), mat="Wood", color=rgb(225, 225, 214))
    elif kind == "metal":
        m.block("Post", (0.08, 0.08, 1.6), (-1.5, 0, 0.8), mat="Metal", color=STEEL)
        m.block("Mesh", (3.0, 0.03, 1.4), (0, 0, 0.8), mat="Metal", color=rgb(120, 124, 122), transparency=0.55)
        m.block("TopRail", (3.0, 0.05, 0.05), (0, 0, 1.52), mat="Metal", color=STEEL)
    elif kind == "concrete":
        m.block("Panel", (3.0, 0.18, 2.4), (0, 0, 1.2), mat="Concrete", color=rgb(170, 168, 160))
        for k in range(3):
            m.block(f"Relief{k}", (0.9, 0.2, 0.6), (-1.0 + k * 1.0, 0, 1.6), mat="Concrete", color=rgb(160, 158, 150))
        m.block("Post", (0.3, 0.3, 2.6), (-1.5, 0, 1.3), mat="Concrete", color=rgb(150, 148, 140))
    elif kind == "military":
        m.block("Post", (0.1, 0.1, 2.6), (-1.5, 0, 1.3), mat="Metal", color=STEEL)
        m.block("Mesh", (3.0, 0.03, 2.2), (0, 0, 1.15), mat="Metal", color=rgb(120, 124, 122), transparency=0.6)
        m.block("Outrigger", (0.06, 0.5, 0.06), (-1.5, -0.2, 2.6), (40, 0, 0), "Metal", STEEL)
        for k in range(3):
            m.cyl(f"Wire{k}", 3.0, 0.03, (0, -0.1 - k * 0.12, 2.45 + k * 0.1), (0, 0, 0), "Metal", rgb(150, 150, 150))
        m.cyl("Concertina", 3.0, 0.5, (0, 0, 2.85), (0, 0, 0), "Metal", rgb(150, 150, 150), transparency=0.5)
    return m


def ENTRIES():
    out = [(f"tree_{k}", (lambda k=k: lambda: tree(k))()) for k in ("pine", "spruce", "birch", "oak", "poplar", "willow", "fruit")]
    out += [(f"bush_{v}", (lambda v=v: lambda: bush(v))()) for v in range(3)]
    out += [("streetlight", streetlight), ("power_pole", power_pole), ("road_sign", road_sign), ("bus_stop", bus_stop), ("bench", bench)]
    out += [(f"car_{v}", (lambda v=v: lambda: car(v))()) for v in range(4)]
    out += [("car_wreck", lambda: car(0, wreck=True)), ("tank_wreck", tank_wreck), ("haystack", haystack), ("crate_stack", crate_stack),
            ("fuel_barrels", fuel_barrels), ("transformer", transformer), ("chem_tank", chem_tank), ("pipe_rack", pipe_rack),
            ("gas_pump", gas_pump), ("fuel_canopy", fuel_canopy), ("water_tower", water_tower), ("chimney", chimney),
            ("rail_car", lambda: rail_car(False)), ("locomotive", lambda: rail_car(True)), ("rail_platform", rail_platform),
            ("monument", monument), ("shed", shed), ("well", well), ("woodpile", woodpile), ("rock", lambda: rock(False)),
            ("rock_large", lambda: rock(True))]
    out += [(f"rubble_{v}", (lambda v=v: lambda: rubble_pile(v))()) for v in range(3)]
    out += [(f"fence_{k}", (lambda k=k: lambda: fence(k))()) for k in ("wood", "picket", "metal", "concrete", "military")]
    return out
