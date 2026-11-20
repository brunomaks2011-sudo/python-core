"""Colour palettes for the two fictional armies and common materials."""
from rbxlib import rgb

FACTIONS = {
    1: dict(  # Blue Army: grey-green with blue identification panels
        key="Blue", base=rgb(86, 96, 82), dark=rgb(58, 66, 57), light=rgb(112, 121, 104), camo=rgb(64, 72, 60),
        mark=rgb(38, 94, 210), mark2=rgb(238, 240, 244), canvas=rgb(84, 92, 76), interior=rgb(170, 175, 168),
    ),
    2: dict(  # Red Army: olive-khaki with brown camouflage and red identification panels
        key="Red", base=rgb(104, 99, 64), dark=rgb(74, 69, 46), light=rgb(128, 120, 84), camo=rgb(88, 70, 48),
        mark=rgb(180, 32, 26), mark2=rgb(242, 236, 226), canvas=rgb(96, 90, 60), interior=rgb(160, 168, 150),
    ),
}

RUBBER = rgb(31, 31, 33)
TRACK = rgb(44, 43, 42)
STEEL = rgb(76, 78, 78)
DARK_STEEL = rgb(42, 43, 45)
GUNMETAL = rgb(36, 37, 39)
GLASS = rgb(110, 140, 155)
GLASS_DARK = rgb(30, 40, 46)
LENS = rgb(235, 235, 215)
TAIL = rgb(150, 20, 18)
AMBER = rgb(230, 140, 20)
WOOD = rgb(112, 84, 56)
CHROME = rgb(170, 172, 175)
WHITE = rgb(232, 232, 228)
MED_GREEN = rgb(40, 150, 70)
