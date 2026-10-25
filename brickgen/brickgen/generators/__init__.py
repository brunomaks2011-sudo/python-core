"""Parametric plan generators for subjects LDraw Nova has no recipe for.

Each generator returns an ordinary LDraw Nova plan (a JSON-ready dict); the
pipeline then builds and checks it exactly like the shipped examples.
"""
from __future__ import annotations

from typing import Callable

GENERATORS: dict[str, Callable[[dict[str, str]], dict]] = {}


def register(name: str):
    def wrap(func):
        GENERATORS[name] = func
        return func
    return wrap


def build(name: str, colours: dict[str, str]) -> dict:
    from . import excavator, robot  # noqa: F401  (registration)

    return GENERATORS[name](colours)
