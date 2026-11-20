#!/usr/bin/env python3
"""Cross-checks Roblox API usage in Luau sources against the official API dump:
   - Instance.new("Class") class names (must exist and be creatable)
   - game:GetService("Service") names
   - Enum.<Enum>.<Item> references
   - property names in property tables passed to our create helpers is left to luau-check
Usage: python3 Tools/api_check.py file.luau ...
"""
import json
import pathlib
import re
import sys

dump = json.loads((pathlib.Path(__file__).parent / "roblox-types" / "API-Dump.json").read_text())
classes = {c["Name"]: c for c in dump["Classes"]}
not_creatable = {c["Name"] for c in dump["Classes"] if "NotCreatable" in (c.get("Tags") or [])}
services = {c["Name"] for c in dump["Classes"] if "Service" in (c.get("Tags") or [])} | {"Workspace", "Players", "Lighting", "ReplicatedStorage", "ServerStorage", "ServerScriptService", "StarterGui", "StarterPlayer", "Teams", "SoundService", "Chat"}
enums = {e["Name"]: {i["Name"] for i in e["Items"]} for e in dump["Enums"]}

bad = 0
for f in sys.argv[1:]:
    src = pathlib.Path(f).read_text()
    for ln, line in enumerate(src.splitlines(), 1):
        code = line.split("--", 1)[0]
        for cls in re.findall(r'Instance\.new\(\s*"(\w+)"', code):
            if cls not in classes:
                print(f"{f}:{ln}: unknown class '{cls}'")
                bad += 1
            elif cls in not_creatable:
                print(f"{f}:{ln}: class '{cls}' is not creatable")
                bad += 1
        for svc in re.findall(r'GetService\(\s*"(\w+)"', code):
            if svc not in classes:
                print(f"{f}:{ln}: unknown service '{svc}'")
                bad += 1
        for en, item in re.findall(r"\bEnum\.(\w+)\.(\w+)", code):
            if en not in enums:
                print(f"{f}:{ln}: unknown enum 'Enum.{en}'")
                bad += 1
            elif item not in enums[en] and item not in ("GetEnumItems", "FromName", "FromValue"):
                print(f"{f}:{ln}: unknown enum item 'Enum.{en}.{item}'")
                bad += 1
print(f"api_check: {bad} problem(s)")
sys.exit(1 if bad else 0)
