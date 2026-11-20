#!/usr/bin/env bash
# Downloads the Roblox API definitions used by the static checks.
set -euo pipefail
cd "$(dirname "$0")"
curl -fsSL -o globalTypes.d.luau https://raw.githubusercontent.com/JohnnyMorganz/luau-lsp/main/scripts/globalTypes.d.luau
curl -fsSL -o API-Dump.json https://raw.githubusercontent.com/MaximumADHD/Roblox-Client-Tracker/roblox/API-Dump.json
python3 patch_defs.py
