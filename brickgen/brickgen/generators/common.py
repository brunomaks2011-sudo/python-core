"""A small writer for LDraw Nova plans in LDraw units.

Coordinates are LDU: X is width, negative Y is up (ground at Y=0), -Z is the
front. A brick or plate origin is the top of its body; bodies are 24 and 8 LDU
high, and one stud is 20 LDU.
"""
from __future__ import annotations

import math
from collections import Counter

BRICK = 24
PLATE = 8
STUD = 20

Matrix = list[list[float]]

YAW90: Matrix = [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]


def colour(name: str) -> str:
    return f"@colours.{name}"


def rot_x(degrees: float) -> Matrix:
    """Proper rotation about +X; positive degrees tilt +Z towards -Y (upwards)."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def mul(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def apply(m: Matrix, v: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def clean(m: Matrix) -> Matrix:
    return [[0.0 if abs(x) < 1e-12 else round(x, 9) for x in row] for row in m]


class Section:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.steps: list[list[dict]] = [[]]
        self._ids: Counter = Counter()

    def _id(self, ref: str, wanted: str | None) -> str:
        base = wanted or ref.removesuffix(".dat").removesuffix(".ldr").replace(".", "-")
        self._ids[base] += 1
        return base if self._ids[base] == 1 and wanted else f"{base}-{self._ids[base]}"

    def add(self, ref: str, colour_: str | int, at: tuple[float, float, float] | None = None, *,
            yaw: float | None = None, matrix: Matrix | None = None, on: str | None = None,
            offset: tuple[float, float] | None = None, id: str | None = None, purpose: str | None = None) -> str:
        if "." not in ref:
            ref += ".dat"
        placement: dict = {"id": self._id(ref, id), "ref": ref, "colour": colour_}
        if purpose:
            placement["purpose"] = purpose
        if on is not None:
            placement["on"] = on
            if offset is not None:
                placement["offset_studs"] = list(offset)
        else:
            placement["at"] = [round(float(v), 6) + 0.0 for v in at]
        if matrix is not None:
            placement["matrix"] = clean(matrix)
        elif yaw:
            placement["yaw"] = yaw
        self.steps[-1].append(placement)
        return placement["id"]

    def step(self) -> None:
        if self.steps[-1]:
            self.steps.append([])

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "steps": [step for step in self.steps if step]}


class Plan:
    def __init__(self, author: str):
        self.author = author
        self.sections: list[Section] = []

    def section(self, name: str, description: str) -> Section:
        section = Section(name, description)
        self.sections.append(section)
        return section

    def to_dict(self) -> dict:
        return {"version": 1, "author": self.author, "sections": [s.to_dict() for s in self.sections]}
