"""Soldier gear for the R15 character rig (sized in studs / 3 so that 1 Blender
metre = 3 studs). Each model's origin is the centre of the body part it is
welded to at runtime (Head, UpperTorso, UpperArm...). Parts named "Team*" are
recoloured to the team colour, "Camo*" parts to the army's uniform colour.
"""
from rbxlib import Model
from models.palette import GLASS_DARK, GUNMETAL, MED_GREEN, RUBBER, WHITE, rgb

VERT = (0, -90, 0)
TEAM = rgb(200, 200, 200)
BLUE_UNIFORM = rgb(86, 96, 82)
RED_UNIFORM = rgb(108, 102, 68)
WEB_BLUE = rgb(70, 78, 66)
WEB_RED = rgb(88, 82, 56)


def helmet(team):
    red = team == 2
    m = Model(f"Helmet_{'Red' if red else 'Blue'}", "Soldiers/Gear", "helmet", {"Team": team, "Mount": "Head"})
    shell = rgb(78, 88, 74) if not red else rgb(92, 98, 66)
    if not red:
        m.ball("Shell", 0.47, (0, -0.01, 0.075), "Fabric", shell)
        m.cyl("Rim", 0.035, 0.475, (0, -0.01, 0.025), VERT, "Fabric", shell)
        m.cyl("TeamBand", 0.03, 0.482, (0, -0.01, 0.1), VERT, "Fabric", TEAM)
        m.block("NVGMount", (0.06, 0.03, 0.05), (0, 0.225, 0.13), mat="Metal", color=GUNMETAL)
        m.block("Goggles", (0.2, 0.05, 0.06), (0, 0.2, 0.22), (20, 0, 0), "Glass", GLASS_DARK)
        m.block("GoggleStrap", (0.24, 0.24, 0.025), (0, 0.0, 0.2), mat="Fabric", color=rgb(40, 40, 40))
        for s in (-1, 1):
            m.block(f"Rail{s}", (0.02, 0.14, 0.03), (s * 0.225, 0.0, 0.07), mat="Metal", color=GUNMETAL)
    else:
        m.ball("Shell", 0.48, (0, 0.0, 0.11), "Metal", shell)
        m.cyl("Brim", 0.025, 0.535, (0, 0.0, 0.0), VERT, "Metal", shell)
        m.cyl("TeamBand", 0.03, 0.49, (0, 0.0, 0.07), VERT, "Fabric", TEAM)
        m.block("Scrim", (0.34, 0.34, 0.02), (0, 0, 0.33), mat="Fabric", color=rgb(84, 90, 58))
    m.block("ChinStrapL", (0.015, 0.02, 0.2), (-0.21, 0.05, -0.08), mat="Fabric", color=rgb(40, 40, 36))
    m.block("ChinStrapR", (0.015, 0.02, 0.2), (0.21, 0.05, -0.08), mat="Fabric", color=rgb(40, 40, 36))
    return m


def vest(team):
    red = team == 2
    m = Model(f"Vest_{'Red' if red else 'Blue'}", "Soldiers/Gear", "vest", {"Team": team, "Mount": "UpperTorso"})
    web = WEB_BLUE if not red else WEB_RED
    if not red:
        m.block("FrontPlate", (0.6, 0.07, 0.42), (0, 0.2, 0.02), mat="Fabric", color=web)
        m.block("BackPlate", (0.6, 0.07, 0.44), (0, -0.2, 0.02), mat="Fabric", color=web)
        for s in (-1, 1):
            m.block(f"Cummerbund{s}", (0.07, 0.34, 0.2), (s * 0.33, 0, -0.08), mat="Fabric", color=web)
            m.block(f"Shoulder{s}", (0.12, 0.42, 0.03), (s * 0.2, 0, 0.255), mat="Fabric", color=web)
        for k in range(3):
            m.block(f"MagPouch{k}", (0.11, 0.07, 0.14), (-0.18 + k * 0.12, 0.27, -0.07), mat="Fabric", color=rgb(76, 84, 70))
        m.block("Radio", (0.08, 0.06, 0.16), (0.27, 0.24, 0.08), mat="Metal", color=rgb(40, 42, 40))
        m.cyl("RadioAntenna", 0.3, 0.012, (0.27, 0.24, 0.3), VERT, "Rubber", RUBBER)
        m.block("TeamPatch", (0.1, 0.01, 0.06), (-0.17, 0.24, 0.16), mat="Fabric", color=TEAM)
    else:
        m.block("ChestRig", (0.56, 0.08, 0.3), (0, 0.2, -0.06), mat="Fabric", color=web)
        for k in range(4):
            m.block(f"Pouch{k}", (0.12, 0.08, 0.16), (-0.195 + k * 0.13, 0.26, -0.06), mat="Fabric", color=rgb(96, 90, 62))
        for s in (-1, 1):
            m.block(f"Strap{s}", (0.08, 0.44, 0.03), (s * 0.18, 0, 0.25), mat="Fabric", color=web)
            m.block(f"Belt{s}", (0.06, 0.34, 0.08), (s * 0.31, 0, -0.2), mat="Fabric", color=web)
        m.block("BackStrap", (0.5, 0.04, 0.08), (0, -0.19, -0.05), mat="Fabric", color=web)
        m.block("TeamPatch", (0.1, 0.01, 0.06), (-0.15, 0.25, 0.14), mat="Fabric", color=TEAM)
    return m


def backpack(team):
    red = team == 2
    m = Model(f"Backpack_{'Red' if red else 'Blue'}", "Soldiers/Gear", "backpack", {"Team": team, "Mount": "UpperTorso"})
    c = rgb(74, 82, 68) if not red else rgb(98, 92, 62)
    m.block("Pack", (0.42, 0.18, 0.42), (0, -0.3, 0.0), mat="Fabric", color=c)
    m.block("Flap", (0.4, 0.2, 0.08), (0, -0.3, 0.2), (8, 0, 0), "Fabric", tuple(x * 0.9 for x in c))
    m.cyl("Bedroll", 0.44, 0.13, (0, -0.32, 0.27), (0, 0, 0), "Fabric", rgb(60, 66, 52))
    m.block("SidePocketL", (0.06, 0.12, 0.18), (-0.23, -0.3, -0.08), mat="Fabric", color=c)
    m.block("SidePocketR", (0.06, 0.12, 0.18), (0.23, -0.3, -0.08), mat="Fabric", color=c)
    return m


def armband(kind="team"):
    m = Model(f"Armband_{kind}", "Soldiers/Gear", "armband", {"Mount": "LeftUpperArm"})
    if kind == "medic":
        m.cyl("Band", 0.08, 0.37, (0, 0, 0.02), VERT, "Fabric", WHITE)
        m.block("CrossV", (0.012, 0.02, 0.06), (-0.185, 0, 0.02), mat="SmoothPlastic", color=MED_GREEN)
        m.block("CrossH", (0.012, 0.05, 0.02), (-0.185, 0, 0.02), mat="SmoothPlastic", color=MED_GREEN)
    else:
        m.cyl("TeamBand", 0.08, 0.37, (0, 0, 0.02), VERT, "Fabric", TEAM)
    return m


def boonie(team):
    red = team == 2
    m = Model(f"Boonie_{'Red' if red else 'Blue'}", "Soldiers/Gear", "boonie", {"Team": team, "Mount": "Head"})
    c = BLUE_UNIFORM if not red else RED_UNIFORM
    m.cyl("Crown", 0.14, 0.43, (0, 0, 0.17), VERT, "Fabric", c)
    m.cyl("Brim", 0.02, 0.62, (0, 0, 0.1), VERT, "Fabric", c)
    m.cyl("TeamBand", 0.03, 0.435, (0, 0, 0.13), VERT, "Fabric", TEAM)
    return m


def tanker(team):
    red = team == 2
    m = Model(f"TankerHelmet_{'Red' if red else 'Blue'}", "Soldiers/Gear", "tanker", {"Team": team, "Mount": "Head"})
    c = rgb(60, 60, 58) if red else rgb(72, 80, 68)
    m.ball("Shell", 0.46, (0, -0.01, 0.08), "Leather" if red else "Fabric", c)
    if red:
        for k in range(3):
            m.block(f"Pad{k}", (0.07, 0.4, 0.06), (-0.08 + k * 0.08, -0.01, 0.27), mat="Leather", color=rgb(50, 50, 48))
    for s in (-1, 1):
        m.cyl(f"EarCup{s}", 0.06, 0.16, (s * 0.22, 0.0, -0.02), (0, 0, 0), "Leather", rgb(40, 40, 38))
    m.cyl("TeamBand", 0.025, 0.47, (0, -0.01, 0.07), VERT, "Fabric", TEAM)
    return m


def ENTRIES():
    out = []
    for team in (1, 2):
        out += [(f"helmet:{team}", (lambda t=team: lambda: helmet(t))()), (f"vest:{team}", (lambda t=team: lambda: vest(t))()),
                (f"backpack:{team}", (lambda t=team: lambda: backpack(t))()), (f"boonie:{team}", (lambda t=team: lambda: boonie(t))()),
                (f"tanker:{team}", (lambda t=team: lambda: tanker(t))())]
    out += [("armband_team", lambda: armband("team")), ("armband_medic", lambda: armband("medic"))]
    return out
