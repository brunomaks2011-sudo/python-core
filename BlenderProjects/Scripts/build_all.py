#!/usr/bin/env python3
"""Builds every Blender model for BLUE vs RED and exports it for Roblox.

    /opt/blender-venv/bin/python BlenderProjects/Scripts/build_all.py [--preview] [filter ...]

Filters match registry keys (e.g. "mbt", "truck:2", "kit_"). Without filters
everything is rebuilt. Each model writes:
    BlenderProjects/<Category>/<Name>.blend          editable source
    Assets/Models/<Category>/<Name>.model.json       native Roblox parts (Rojo)
    Assets/Meshes/<Category>/<Name>.fbx              mesh version (optional import)
    BlenderProjects/<Category>/previews/<Name>.png   with --preview
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib  # noqa: E402

MODULES = ["models.tracked", "models.wheeled", "models.aircraft", "models.equipment", "models.environment", "models.buildings", "models.soldiers", "models.weapons"]


def registry():
    out = []
    for modname in MODULES:
        try:
            mod = importlib.import_module(modname)
        except ModuleNotFoundError as e:
            if e.name == modname:
                continue
            raise
        for entry in mod.ENTRIES() if hasattr(mod, "ENTRIES") else []:
            out.append(entry)
        if hasattr(mod, "BUILDERS"):
            for kind, fn in mod.BUILDERS.items():
                for team in (1, 2):
                    out.append((f"{kind}:{team}", lambda fn=fn, team=team: fn(team)))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    preview = "--preview" in sys.argv
    t0 = time.time()
    built = 0
    total_parts = 0
    for key, fn in registry():
        if args and not any(a.lower() in key.lower() for a in args):
            continue
        model = fn()
        n = model.save(preview=preview)
        total_parts += n
        built += 1
        print(f"  {model.category}/{model.name}: {n} parts")
    print(f"built {built} models, {total_parts} parts, {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
