"""Tracked excavator: crawler undercarriage, turntable, house with cab, Technic boom, arm and bucket.

Side view: the boom foot is pinned between two Technic bricks at the front of
the house; a double-bent liftarm rises forward, a pair of straight beams forms
the arm and a Technic bucket hangs between them. All three pivots are pinned.
"""
from __future__ import annotations

import math

from . import register
from .common import BRICK, PLATE, Plan, apply, colour, rot_x

DEFAULTS = {"body": "Yellow", "tracks": "Black"}  # the cab follows the body unless asked otherwise

# Y of the top of each layer (negative is up); the crawler loops stand on Y=0.
CHASSIS_BRICKS = -41.5  # level with the Technic frames inside the crawlers
CHASSIS_PLATE = CHASSIS_BRICKS - PLATE
TURNTABLE = CHASSIS_PLATE - BRICK
FLOOR = TURNTABLE - PLATE
L1 = FLOOR - BRICK
L2 = L1 - BRICK
L3 = L2 - BRICK
ROOF = L3 - PLATE

BOOM_X = 30  # the boom plane; the arm beams sit either side at 10 and 50
FOOT = (BOOM_X, L2 + 10, -60)  # through the holes of the Technic bricks at L2
BOOM_RISE = 55  # degrees above horizontal for the boom's long leg
ARM_DROP = 62  # degrees below horizontal for the arm
BUCKET_TILT = 190  # curled towards the cab, clear of the ground


def boom_matrix(rise: float):
    """Liftarm 32009 lies in its local XZ plane: local +Z is the rising leg, +X points 90° below it."""
    a = math.radians(rise)
    return [[0, 1, 0], [math.cos(a), 0, -math.sin(a)], [-math.sin(a), 0, -math.cos(a)]]


def beam_matrix(drop: float):
    """Straight beams lie along local Z with holes on local Y: point Z down-forward, holes along X."""
    dy, dz = math.sin(math.radians(drop)), -math.cos(math.radians(drop))
    return [[0, 1, 0], [-dz, 0, dy], [dy, 0, dz]], (0.0, dy, dz)


@register("excavator")
def build(colours: dict[str, str]) -> dict:
    c = {role: colour(colours.get(role, default)) for role, default in DEFAULTS.items()}
    c["cab"] = colour(colours.get("cab", colours.get("body", DEFAULTS["body"])))
    grey, black = colour("Dark_Bluish_Grey"), colour("Black")
    glass, beacon = colour("Trans_Black"), colour("Trans_Orange")
    plan = Plan("BrickGen excavator generator")
    m = plan.section("excavator.ldr", "Tracked excavator; front -Z, ground Y=0")

    # Undercarriage: rubber crawlers around Technic side frames, a brick chassis between them.
    for x in (-50, 50):
        m.add("498", c["tracks"], (x, -31.5, 0), yaw=90, purpose="crawler loop")
        m.add("3894", grey, (x, CHASSIS_BRICKS, 0), yaw=90, purpose="track frame inside the crawler")
    m.add("3001", grey, (-20, CHASSIS_BRICKS, -20), yaw=90)
    m.add("3003", grey, (-20, CHASSIS_BRICKS, 40))
    m.add("3003", grey, (20, CHASSIS_BRICKS, -40))
    m.add("3001", grey, (20, CHASSIS_BRICKS, 20), yaw=90)
    m.add("3032", grey, (0, CHASSIS_PLATE, 0), yaw=90)
    m.step()
    m.add("3403c01", grey, (0, TURNTABLE, 0), purpose="slewing ring")
    m.step()

    # House floor, 6 x 8 studs; columns at X -50..50, rows at Z -70 (front)..70.
    m.add("3036", c["body"], (0, FLOOR, 0), yaw=90)
    m.step()

    # First course: cab base, boom foot bearings, engine block, counterweight.
    m.add("3002", c["cab"], (-40, L1, -50), yaw=90, purpose="cab base")
    m.add("3004", c["body"], (-10, L1, -60), yaw=90)
    for x in (10, 30, 50):
        m.add("3004", c["body"], (x, L1, -60), yaw=90)
    m.add("3001", c["body"], (0, L1, 0), yaw=90)
    m.add("3001", c["body"], (40, L1, 0), yaw=90)
    m.add("3001", c["body"], (-40, L1, 20), yaw=90)
    m.add("3010", c["body"], (20, L1, 50))
    m.add("3009", grey, (0, L1, 70), purpose="counterweight")
    m.step()

    # Second course: cab glass, Technic bearings with the boom gap between them, engine rows.
    m.add("3002", glass, (-40, L2, -50), yaw=90, purpose="cab glass")
    m.add("3004", c["body"], (-10, L2, -60), yaw=90)
    for x in (10, 50):
        m.add("3700", c["body"], (x, L2, -60), yaw=90, purpose="boom foot bearing")
    m.add("3010", c["body"], (20, L2, -30))
    for z in (-10, 10, 30, 50):
        m.add("3009", c["body"], (0, L2, z))
    m.add("3009", grey, (0, L2, 70), purpose="counterweight")
    m.step()

    # Engine cover and counterweight cap.
    m.add("3032", c["body"], (0, L2 - PLATE, 20), purpose="engine cover")
    m.add("3710", c["body"], (20, L2 - PLATE, -30))
    m.add("3666", grey, (0, L2 - PLATE, 70))
    m.add("3069b", c["body"], (-10, L2 - PLATE, -60), yaw=90)
    m.step()
    for x in (-40, 0):
        m.add("2412b", black, (x, L2 - 2 * PLATE, 30), purpose="engine grille")
    m.add("6636", grey, (0, L2 - 2 * PLATE, 70))
    m.step()

    # Cab: a second glass course, roof plate, tiles and a beacon.
    m.add("3002", glass, (-40, L3, -50), yaw=90, purpose="cab glass")
    m.add("3021", c["cab"], (-40, ROOF, -50), yaw=90, purpose="cab roof")
    m.add("63864", c["cab"], (-50, ROOF - PLATE, -50), yaw=90)
    m.add("3069b", c["cab"], (-30, ROOF - PLATE, -40), yaw=90)
    m.add("6141", beacon, (-30, ROOF - PLATE, -70), purpose="beacon")
    m.step()

    # Boom: one double-bent liftarm pinned between the bearings.
    boom = boom_matrix(BOOM_RISE)
    foot_local = (0, 0, -160)
    shift = apply(boom, foot_local)
    m.add("32009", c["body"], (FOOT[0] - shift[0], FOOT[1] - shift[1], FOOT[2] - shift[2]), matrix=boom, id="boom")
    m.add("6558", grey, FOOT, purpose="boom foot pin")
    reach = apply(boom, (80 - foot_local[0], 0, 0 - foot_local[2]))  # foot hole to tip hole
    tip = (BOOM_X, FOOT[1] + reach[1], FOOT[2] + reach[2])
    m.step()

    # Arm: two straight 7-hole beams either side of the boom tip.
    arm, d = beam_matrix(ARM_DROP)
    for x in (10, 50):
        m.add("32524", c["body"], (x, tip[1] + 60 * d[1], tip[2] + 60 * d[2]), matrix=arm)
    m.add("6558", grey, tip, purpose="arm pivot pin")
    pivot = (BOOM_X, tip[1] + 120 * d[1], tip[2] + 120 * d[2])
    m.step()

    # Bucket between the arm beams.
    m.add("24120", grey, pivot, matrix=rot_x(BUCKET_TILT), id="bucket")
    m.add("6558", grey, pivot, purpose="bucket pin")
    return plan.to_dict()
