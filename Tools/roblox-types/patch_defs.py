#!/usr/bin/env python3
"""Adds string-literal overloads to luau-lsp's Roblox definitions so the plain
Luau Analysis engine (without luau-lsp's C++ "magic functions") can type
Instance.new("Part") as Part and game:GetService("Players") as Players.

    python3 Tools/roblox-types/patch_defs.py
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).parent
src = (HERE / "globalTypes.d.luau").read_text()
first, rest = src.split("\n", 1)
meta = json.loads(first[len("--#METADATA#"):])
declared = set(re.findall(r"^declare extern type (\w+)", src, re.M))

services = [s for s in meta["SERVICES"] if s in declared]
creatable = [c for c in meta["CREATABLE_INSTANCES"] if c in declared]

# game:GetService / FindService overloads
gs_old = "\tfunction GetService(self, className: string): Instance\n"
assert gs_old in rest, "GetService declaration not found"
gs_new = "".join(f'\tfunction GetService(self, className: "{s}"): {s}\n' for s in services) + gs_old
rest = rest.replace(gs_old, gs_new, 1)

# Instance.new overloads
new_old = "\tnew: ((className: string, parent: Instance?) -> Instance),\n"
assert new_old in rest, "Instance.new declaration not found"
parts = [f'((className: "{c}", parent: Instance?) -> {c})' for c in creatable]
parts.append("((className: string, parent: Instance?) -> Instance)")
rest = rest.replace(new_old, "\tnew: " + " & ".join(parts) + ",\n", 1)

out = HERE / "globalTypes.patched.d.luau"
out.write_text(first + "\n" + rest)
print(f"wrote {out.name}: {len(services)} service overloads, {len(creatable)} Instance.new overloads")
