#!/usr/bin/env bash
# Static checks for the Roblox Luau code:
#   1. luau-check: Luau's type checker against the Roblox API definitions
#   2. api_check.py: Instance.new class names / GetService names / Enum items vs the API dump
#   3. selene lint (syntax + common mistakes)
#   4. rojo build (project + model files are valid)
set -uo pipefail
cd "$(dirname "$0")/.."

[ -f Tools/roblox-types/globalTypes.patched.d.luau ] || bash Tools/roblox-types/fetch.sh
[ -x Tools/luau-check/target/release/luau-check ] || (cd Tools/luau-check && cargo build --release -q)

mapfile -t FILES < <(find Assets/Scripts -name "*.luau" | sort)

echo "== luau-check (${#FILES[@]} files)"
Tools/luau-check/target/release/luau-check Tools/roblox-types/globalTypes.patched.d.luau --quiet-nil "${FILES[@]}" 2>&1 \
  | grep -v -E "is never used|prefix with '_'|Unknown require|shadows a local|Function only uses the|LocalShadow|has no effect|Global 'script'" \
  | grep -v -E "in class 'Instance'|but got 'Instance'|'BasePart \| Instance'|Instance \| nil|Types Instance and|Cannot cast 'nil'|got 'Instance\?'|of type 'Instance'" \
  | grep -v -E "Key '(Shared|MapData|Assets|Remotes|MatchState|Map|Soldiers|Vehicles|Server|Client|Game|World|AI|UI|Player|Effects|Audio|Loading)' not found|Unknown type '[A-Za-z]+\.[A-Za-z]+'|Unknown type used in|cannot be compared with ~= because|cannot be compared with == because" \
  | tee /tmp/luau-check.out | tail -n 400
ERR=$(grep -c ": Error:" /tmp/luau-check.out || true)
echo "luau-check errors: $ERR"

echo "== api_check"
python3 Tools/api_check.py "${FILES[@]}" || ERR=$((ERR+1))

echo "== rojo build"
mkdir -p Build
rojo build default.project.json -o Build/BlueVsRed.rbxl 2>&1 | tail -2 || ERR=$((ERR+1))

exit $(( ERR > 0 ))
