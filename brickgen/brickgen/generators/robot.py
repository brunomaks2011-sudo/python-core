"""Standing robot: feet, legs with round knees, a 6 x 4 torso with a lit panel,
shoulders with hanging arms, and a printed face under a helmet with ears and an antenna.

Everything hangs off ordinary studs: the legs stand on the feet, the torso on
a hip plate, and the arms and ears hang under the shoulder and brow plates.
"""
from __future__ import annotations

from . import register
from .common import BRICK, PLATE, Plan, colour

DEFAULTS = {"body": "White", "limbs": "Light_Bluish_Grey", "accent": "Medium_Azure"}

# Y of the top of each layer (negative is up); the feet stand on Y=0.
FEET = -PLATE
SHIN = FEET - BRICK
KNEE = SHIN - BRICK
THIGH = KNEE - BRICK
HIPS = THIGH - PLATE
CHEST = [HIPS - BRICK, HIPS - 2 * BRICK, HIPS - 3 * BRICK]
CAP = CHEST[-1] - PLATE
SHOULDERS = CAP - PLATE
NECK = SHOULDERS - PLATE
FACE = NECK - BRICK
BROW = FACE - PLATE
FOREHEAD = BROW - BRICK
CROWN = FOREHEAD - PLATE

LEG_X = 40  # legs under the outer studs of the 6-wide torso
ARM_X = 80  # arms hang under the ends of the 2 x 10 shoulder plate


@register("robot")
def build(colours: dict[str, str]) -> dict:
    c = {role: colour(colours.get(role, default)) for role, default in DEFAULTS.items()}
    joint, black = colour("Dark_Bluish_Grey"), colour("Black")
    plan = Plan("BrickGen robot generator")
    m = plan.section("robot.ldr", "Standing robot; front -Z, ground Y=0")

    # Legs: feet poking forward, two-brick legs with round knee joints.
    for x in (-LEG_X, LEG_X):
        m.add("3020", joint, (x, FEET, -20), yaw=90, purpose="foot")
        m.add("3003", c["limbs"], (x, SHIN, 0))
        m.add("3941", c["accent"], (x, KNEE, 0), purpose="knee")
        m.add("3003", c["limbs"], (x, THIGH, 0))
    m.step()
    m.add("3032", joint, (0, HIPS, 0), purpose="hips")
    m.step()

    # Torso, 6 x 4: three courses, the middle one with a row of lights at the front.
    m.add("2456", c["body"], (0, CHEST[0], -20))
    m.add("2456", c["body"], (0, CHEST[0], 20))
    m.step()
    m.add("3004", c["body"], (-40, CHEST[1], -30))
    m.add("3062b", colour("Trans_Red"), (-10, CHEST[1], -30), purpose="panel light")
    m.add("3062b", colour("Trans_Bright_Green"), (10, CHEST[1], -30), purpose="panel light")
    m.add("3004", c["body"], (40, CHEST[1], -30))
    m.add("2456", c["body"], (0, CHEST[1], 0))
    m.add("3009", c["body"], (0, CHEST[1], 30))
    m.step()
    m.add("3009", c["accent"], (0, CHEST[2], -30), purpose="chest stripe")
    m.add("2456", c["body"], (0, CHEST[2], 0))
    m.add("3009", c["body"], (0, CHEST[2], 30))
    m.step()
    m.add("3032", c["body"], (0, CAP, 0))
    m.add("3832", c["accent"], (0, SHOULDERS, 0), purpose="shoulders")
    m.step()

    # Arms hang under the shoulder plate: round shoulder joint, two-brick arm, round fist.
    for x in (-ARM_X, ARM_X):
        m.add("3941", joint, (x, CAP, 0), purpose="shoulder joint")
        m.add("3003", c["limbs"], (x, CAP + BRICK, 0))
        m.add("3003", c["limbs"], (x, CAP + 2 * BRICK, 0))
        m.add("3941", joint, (x, CAP + 3 * BRICK, 0), purpose="fist")
    m.step()

    # Head: neck, printed face, ears hanging under a brow plate, a helmet with lights and an antenna.
    m.add("4032a", joint, (0, NECK, 0), purpose="neck")
    m.add("3001p0e", c["body"], (0, FACE, 0), purpose="face")
    m.step()
    m.add("3795", c["accent"], (0, BROW, 0), purpose="brow")
    for x in (-50, 50):
        m.add("2877", joint, (x, FACE, 0), yaw=90, purpose="ear")
    m.step()
    m.add("2456", c["body"], (0, FOREHEAD, 0), purpose="helmet")
    m.step()
    m.add("87079", c["accent"], (0, CROWN, 0))
    m.add("6141", colour("Trans_Red"), (-50, CROWN, -10), purpose="ear light")
    m.add("6141", colour("Trans_Red"), (50, CROWN, -10), purpose="ear light")
    m.add("6141", joint, (-50, CROWN, 10))
    m.add("3957a", black, (50, CROWN, 10), purpose="antenna")
    return plan.to_dict()
