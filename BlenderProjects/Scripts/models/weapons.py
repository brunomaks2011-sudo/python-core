"""Infantry weapons and tools. Origin = right-hand grip, muzzle toward +Y.
Attachments: Grip, Muzzle, Sight (aim-down-sights eye point), LeftHand, Eject.
Group "Mag" is the detachable magazine (animated on reload).
"""
from rbxlib import Model
from models.palette import GLASS_DARK, GUNMETAL, MED_GREEN, RUBBER, WHITE, rgb

ALONG_Y = (0, 0, 90)
VERT = (0, -90, 0)
POLY = rgb(36, 37, 38)
TAN = rgb(152, 136, 104)
WOOD = rgb(122, 72, 40)
OD = rgb(76, 84, 64)


def _common(m, muzzle_y, sight, left_y, z_axis=0.05):
    m.attach("Grip", (0, 0, 0))
    m.attach("Muzzle", (0, muzzle_y, z_axis))
    m.attach("Sight", sight)
    m.attach("LeftHand", (0, left_y, z_axis - 0.02))
    m.attach("Eject", (0.04, 0.08, z_axis + 0.02))


def rifle_blue(kind="rifle"):
    names = {"rifle": "Rifle_Blue", "carbine": "Carbine_Blue", "lmg": "LMG_Blue", "dmr": "DMR_Blue", "smg": "SMG_Blue"}
    m = Model(names[kind], "Weapons", kind, {"Team": 1})
    furn = TAN if kind in ("rifle", "dmr") else POLY
    hg = {"rifle": 0.3, "carbine": 0.22, "lmg": 0.34, "dmr": 0.38, "smg": 0.14}[kind]
    bl = {"rifle": 0.2, "carbine": 0.12, "lmg": 0.28, "dmr": 0.34, "smg": 0.06}[kind]
    rec = 0.28 if kind != "lmg" else 0.36
    m.block("Receiver", (0.05, rec, 0.085), (0, 0.06, 0.05), mat="Metal", color=POLY)
    m.block("Rail", (0.03, rec + hg, 0.018), (0, 0.06 + hg / 2, 0.1), mat="Metal", color=GUNMETAL)
    m.block("Handguard", (0.055, hg, 0.06), (0, 0.2 + hg / 2, 0.05), mat="SmoothPlastic", color=furn)
    m.cyl("Barrel", bl, 0.02, (0, 0.2 + hg + bl / 2, 0.05), ALONG_Y, "Metal", GUNMETAL, segments=8)
    m.cyl("MuzzleDevice", 0.06, 0.032, (0, 0.2 + hg + bl + 0.03, 0.05), ALONG_Y, "Metal", GUNMETAL, segments=8)
    m.block("Grip", (0.03, 0.04, 0.1), (0, -0.01, -0.03), (18, 0, 0), "SmoothPlastic", furn)
    m.block("Trigger", (0.01, 0.03, 0.03), (0, 0.03, 0.0), mat="Metal", color=GUNMETAL)
    if kind != "smg":
        m.block("Stock", (0.04, 0.2, 0.07), (0, -0.2, 0.045), mat="SmoothPlastic", color=furn)
        m.block("ButtPad", (0.045, 0.03, 0.12), (0, -0.31, 0.03), mat="Rubber", color=RUBBER)
        m.block("BufferTube", (0.025, 0.12, 0.025), (0, -0.1, 0.07), mat="Metal", color=GUNMETAL)
    else:
        m.block("StockWire", (0.012, 0.18, 0.012), (0, -0.14, 0.06), mat="Metal", color=GUNMETAL)
    m.group("Mag", (0, 0.11, 0.0))
    if kind == "lmg":
        m.block("BoxMag", (0.12, 0.12, 0.12), (0.03, 0.11, -0.05), mat="SmoothPlastic", color=OD, group="Mag")
        for s in (-1, 1):
            m.block(f"Bipod{s}", (0.012, 0.012, 0.2), (s * 0.03, 0.5, -0.04), (0, s * 12, 0), "Metal", GUNMETAL)
        m.block("CarryHandle", (0.02, 0.12, 0.03), (0, 0.08, 0.14), mat="Metal", color=GUNMETAL)
    else:
        mag_len = 0.16 if kind != "dmr" else 0.1
        m.block("Magazine", (0.025, 0.07, mag_len), (0, 0.12, -mag_len / 2), (-8, 0, 0), "Metal", POLY, group="Mag")
    if kind == "dmr":
        m.cyl("Scope", 0.3, 0.045, (0, 0.06, 0.135), ALONG_Y, "Metal", POLY)
        m.cyl("ScopeBellF", 0.06, 0.06, (0, 0.2, 0.135), ALONG_Y, "Metal", POLY)
        m.cyl("ScopeBellR", 0.05, 0.05, (0, -0.08, 0.135), ALONG_Y, "Metal", POLY)
        m.block("ScopeLens", (0.045, 0.005, 0.045), (0, 0.23, 0.135), mat="Glass", color=GLASS_DARK)
        _common(m, 0.2 + hg + bl + 0.06, (0, -0.1, 0.135), 0.3)
    else:
        m.cyl("Optic", 0.06, 0.035, (0, 0.06, 0.13), ALONG_Y, "Metal", POLY)
        m.block("OpticLens", (0.028, 0.004, 0.028), (0, 0.09, 0.13), mat="Glass", color=rgb(120, 40, 40))
        _common(m, 0.2 + hg + bl + 0.06, (0, -0.02, 0.13), 0.2 + hg * 0.6)
    return m


def rifle_red(kind="rifle"):
    names = {"rifle": "Rifle_Red", "carbine": "Carbine_Red", "lmg": "LMG_Red", "dmr": "DMR_Red", "smg": "SMG_Red"}
    m = Model(names[kind], "Weapons", kind, {"Team": 2})
    furn = WOOD if kind in ("rifle", "lmg", "dmr") else POLY
    hg = {"rifle": 0.22, "carbine": 0.14, "lmg": 0.24, "dmr": 0.3, "smg": 0.1}[kind]
    bl = {"rifle": 0.26, "carbine": 0.12, "lmg": 0.36, "dmr": 0.4, "smg": 0.08}[kind]
    m.block("Receiver", (0.05, 0.3, 0.075), (0, 0.06, 0.045), mat="Metal", color=rgb(50, 50, 52))
    m.block("DustCover", (0.045, 0.26, 0.02), (0, 0.04, 0.09), mat="Metal", color=rgb(56, 56, 58))
    m.block("Handguard", (0.056, hg, 0.055), (0, 0.21 + hg / 2, 0.04), mat="Wood" if furn == WOOD else "SmoothPlastic", color=furn)
    m.cyl("GasTube", hg + 0.04, 0.022, (0, 0.21 + hg / 2, 0.085), ALONG_Y, "Wood" if furn == WOOD else "SmoothPlastic", furn, segments=8)
    m.cyl("Barrel", bl, 0.02, (0, 0.21 + hg + bl / 2, 0.045), ALONG_Y, "Metal", GUNMETAL, segments=8)
    m.block("FrontSight", (0.012, 0.02, 0.05), (0, 0.21 + hg + bl - 0.02, 0.075), mat="Metal", color=GUNMETAL)
    m.cyl("MuzzleBrake", 0.06, 0.03, (0, 0.21 + hg + bl + 0.03, 0.045), ALONG_Y, "Metal", GUNMETAL, segments=8)
    m.block("Grip", (0.03, 0.04, 0.1), (0, -0.01, -0.03), (18, 0, 0), "SmoothPlastic", POLY)
    if kind != "smg":
        m.block("Stock", (0.04, 0.24, 0.06), (0, -0.21, 0.03), (-6, 0, 0), "Wood" if furn == WOOD else "SmoothPlastic", furn)
        m.block("ButtPlate", (0.042, 0.02, 0.12), (0, -0.33, 0.0), mat="Metal", color=GUNMETAL)
    else:
        m.block("FoldedStock", (0.012, 0.2, 0.03), (0.03, -0.0, 0.03), mat="Metal", color=GUNMETAL)
    m.group("Mag", (0, 0.12, 0.0))
    if kind == "lmg":
        m.cyl("DrumMag", 0.06, 0.15, (0, 0.12, -0.08), (0, 0, 0), "Metal", rgb(50, 50, 52), group="Mag")
        for s in (-1, 1):
            m.block(f"Bipod{s}", (0.012, 0.012, 0.2), (s * 0.03, 0.55, -0.04), (0, s * 12, 0), "Metal", GUNMETAL)
    else:
        m.block("MagUpper", (0.026, 0.07, 0.1), (0, 0.13, -0.05), (-12, 0, 0), "Metal", rgb(150, 70, 40) if kind == "rifle" else POLY, group="Mag")
        m.block("MagLower", (0.026, 0.07, 0.09), (0, 0.16, -0.13), (-28, 0, 0), "Metal", rgb(150, 70, 40) if kind == "rifle" else POLY, group="Mag")
    if kind == "dmr":
        m.cyl("Scope", 0.26, 0.045, (0, 0.04, 0.13), ALONG_Y, "Metal", POLY)
        m.block("ScopeLens", (0.045, 0.005, 0.045), (0, 0.18, 0.13), mat="Glass", color=GLASS_DARK)
        _common(m, 0.21 + hg + bl + 0.06, (0, -0.1, 0.13), 0.3, 0.045)
    else:
        m.block("RearSight", (0.02, 0.03, 0.025), (0, 0.15, 0.1), mat="Metal", color=GUNMETAL)
        _common(m, 0.21 + hg + bl + 0.06, (0, -0.05, 0.105), 0.21 + hg * 0.5, 0.045)
    return m


def pistol():
    m = Model("Pistol", "Weapons", "pistol", {})
    m.block("Slide", (0.03, 0.19, 0.035), (0, 0.06, 0.05), mat="Metal", color=POLY)
    m.block("Frame", (0.028, 0.16, 0.025), (0, 0.05, 0.022), mat="SmoothPlastic", color=POLY)
    m.block("Grip", (0.03, 0.045, 0.11), (0, -0.01, -0.03), (14, 0, 0), "SmoothPlastic", POLY)
    m.group("Mag", (0, -0.01, -0.06))
    m.block("Magazine", (0.022, 0.035, 0.03), (0, -0.015, -0.09), mat="Metal", color=GUNMETAL, group="Mag")
    _common(m, 0.16, (0, -0.02, 0.075), 0.0, 0.05)
    return m


def rpg():
    m = Model("RPG", "Weapons", "rpg", {})
    m.cyl("Tube", 1.0, 0.075, (0, 0.15, 0.06), ALONG_Y, "Metal", OD)
    m.cyl("Warhead", 0.22, 0.11, (0, 0.74, 0.06), ALONG_Y, "Metal", rgb(70, 80, 60))
    m.wedge("Nose", (0.09, 0.12, 0.09), (0, 0.9, 0.06), (0, 90, 0), "Metal", rgb(60, 70, 52))
    m.block("Grip", (0.03, 0.04, 0.1), (0, 0.0, -0.03), mat="SmoothPlastic", color=POLY)
    m.block("ForeGrip", (0.03, 0.04, 0.09), (0, 0.25, -0.02), mat="SmoothPlastic", color=POLY)
    m.block("Sight", (0.03, 0.06, 0.06), (-0.05, 0.12, 0.12), mat="Metal", color=POLY)
    m.cyl("Shield", 0.04, 0.12, (0, -0.33, 0.06), ALONG_Y, "Metal", OD)
    m.group("Mag", (0, 0.74, 0.06))
    _common(m, 0.95, (-0.05, 0.0, 0.13), 0.25, 0.06)
    return m


def small_items():
    out = []

    def grenade():
        m = Model("Grenade", "Weapons", "grenade", {})
        m.ball("Body", 0.075, (0, 0, 0.04), "Metal", OD)
        m.block("Lever", (0.012, 0.02, 0.06), (0.03, 0, 0.06), mat="Metal", color=GUNMETAL)
        m.cyl("Ring", 0.005, 0.03, (0, 0.02, 0.085), (0, 0, 0), "Metal", GUNMETAL)
        m.attach("Grip", (0, 0, 0))
        return m

    def c4():
        m = Model("C4", "Weapons", "c4", {})
        m.block("Block", (0.12, 0.2, 0.06), (0, 0, 0.03), mat="SmoothPlastic", color=rgb(200, 196, 170))
        m.block("Detonator", (0.04, 0.05, 0.03), (0, 0.06, 0.07), mat="Metal", color=GUNMETAL)
        m.block("Light", (0.01, 0.01, 0.01), (0.015, 0.07, 0.09), mat="Neon", color=rgb(255, 40, 30))
        m.attach("Grip", (0, 0, 0))
        return m

    def medkit():
        m = Model("Medkit", "Weapons", "medkit", {})
        m.block("Bag", (0.24, 0.12, 0.16), (0, 0.04, 0.0), mat="Fabric", color=rgb(70, 84, 62))
        m.block("CrossPanel", (0.1, 0.005, 0.1), (0, 0.102, 0.0), mat="SmoothPlastic", color=WHITE)
        m.block("CrossV", (0.025, 0.006, 0.07), (0, 0.104, 0.0), mat="SmoothPlastic", color=MED_GREEN)
        m.block("CrossH", (0.07, 0.006, 0.025), (0, 0.104, 0.0), mat="SmoothPlastic", color=MED_GREEN)
        m.attach("Grip", (0, 0, 0))
        return m

    def ammobox():
        m = Model("AmmoBox", "Weapons", "ammobox", {})
        m.block("Box", (0.26, 0.12, 0.16), (0, 0.04, 0.0), mat="Metal", color=OD)
        m.block("Handle", (0.08, 0.02, 0.02), (0, 0.04, 0.09), mat="Metal", color=GUNMETAL)
        m.block("Label", (0.12, 0.005, 0.04), (0, 0.102, 0.03), mat="SmoothPlastic", color=rgb(230, 190, 60))
        m.attach("Grip", (0, 0, 0))
        return m

    def wrench():
        m = Model("Wrench", "Weapons", "wrench", {})
        m.cyl("Body", 0.24, 0.05, (0, 0.06, 0.03), ALONG_Y, "Metal", rgb(200, 120, 30))
        m.cyl("Nozzle", 0.1, 0.02, (0, 0.23, 0.03), ALONG_Y, "Metal", GUNMETAL)
        m.block("Grip", (0.03, 0.04, 0.09), (0, 0.0, -0.02), mat="Rubber", color=RUBBER)
        m.attach("Grip", (0, 0, 0))
        m.attach("Muzzle", (0, 0.29, 0.03))
        return m

    def binoculars():
        m = Model("Binoculars", "Weapons", "binoculars", {})
        for s in (-1, 1):
            m.cyl(f"Tube{s}", 0.14, 0.05, (s * 0.035, 0.05, 0.05), ALONG_Y, "Rubber", rgb(48, 52, 44))
            m.block(f"Lens{s}", (0.04, 0.004, 0.04), (s * 0.035, 0.122, 0.05), mat="Glass", color=GLASS_DARK)
        m.block("Bridge", (0.05, 0.04, 0.02), (0, 0.04, 0.05), mat="Metal", color=GUNMETAL)
        m.attach("Grip", (0, 0, 0))
        m.attach("Sight", (0, -0.02, 0.05))
        return m

    for name, fn in (("grenade", grenade), ("c4", c4), ("medkit", medkit), ("ammobox", ammobox), ("wrench", wrench), ("binoculars", binoculars)):
        out.append((f"weapon_{name}", fn))
    return out


def ENTRIES():
    out = []
    for kind in ("rifle", "carbine", "lmg", "dmr", "smg"):
        out.append((f"weapon_{kind}:1", (lambda k=kind: lambda: rifle_blue(k))()))
        out.append((f"weapon_{kind}:2", (lambda k=kind: lambda: rifle_red(k))()))
    out += [("weapon_pistol", pistol), ("weapon_rpg", rpg)]
    out += small_items()
    return out
