#!/bin/sh
# Install BrickGen and the tools it drives on Ubuntu 24.04 (a server or a Claude Code cloud session).
#
#   LeoCAD 25.09   Ubuntu archive pool (Qt5 build): renders and the BOM cross-check
#   Xvfb, Mesa     software OpenGL so LeoCAD renders without a display
#   LDraw library  github.com/kulits/ldraw-parts, a daily mirror of ldraw.org's complete.zip
#   LDraw Nova     github.com/anteloc/ldraw-nova, set up by its own setup.sh
#   mpd2glb 0.9.1  github.com/anteloc/mpd2glb, run with Bun (it needs Node 24.11+ or Bun 1.3.10+)
#   BrickGen       Python packages with uv (or pip), three.js with npm
#
# Folders: LDRAW_NOVA_DIR (~/ldraw-nova), LDRAW_DIR (~/ldraw), BRICKGEN_TOOLS (~/.local/share/brickgen).
set -eu
APP=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
NOVA=${LDRAW_NOVA_DIR:-$HOME/ldraw-nova}
LIB=${LDRAW_DIR:-$HOME/ldraw}
TOOLS=${BRICKGEN_TOOLS:-$HOME/.local/share/brickgen}
SUDO=$([ "$(id -u)" -eq 0 ] || echo sudo)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "== System packages"
PACKAGES="poppler-utils xvfb xauth libgl1-mesa-dri libglx-mesa0 git curl python3-venv"
command -v npm >/dev/null 2>&1 || PACKAGES="$PACKAGES npm"  # keep a newer Node if one is installed
$SUDO apt-get update -q
curl -fsSL -o "$TMP/leocad.deb" http://archive.ubuntu.com/ubuntu/pool/universe/l/leocad/leocad_25.09-1_amd64.deb
# shellcheck disable=SC2086
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$TMP/leocad.deb" $PACKAGES

echo "== LDraw parts library -> $LIB"
if [ ! -f "$LIB/LDConfig.ldr" ]; then
  git clone -q --depth 1 --filter=blob:none --sparse https://github.com/kulits/ldraw-parts "$TMP/lib"
  git -C "$TMP/lib" sparse-checkout set ldraw
  mv "$TMP/lib/ldraw" "$LIB"
fi

echo "== LDraw Nova -> $NOVA"
[ -d "$NOVA" ] || git clone -q --depth 1 https://github.com/anteloc/ldraw-nova "$NOVA"
LDRAW_DIR="$LIB" "$NOVA/setup.sh"

echo "== mpd2glb -> $TOOLS"
mkdir -p "$TOOLS/bin"
[ -d "$TOOLS/mpd2glb" ] || git clone -q --depth 1 --branch v0.9.1 https://github.com/anteloc/mpd2glb "$TOOLS/mpd2glb"
BUN=$(command -v bun || true)
[ -n "$BUN" ] || [ ! -x "$HOME/.bun/bin/bun" ] || BUN=$HOME/.bun/bin/bun
if [ -z "$BUN" ]; then
  npm install --prefix "$TOOLS/bun" --no-audit --no-fund bun@1.3
  BUN=$TOOLS/bun/node_modules/.bin/bun
fi
# The tag has no prebuilt bundle: build the self-contained mpd2glb.mjs from main.mjs.
(cd "$TOOLS/mpd2glb" && "$BUN" install && "$BUN" build.mjs)
printf '#!/bin/sh\nexec "%s" "%s" "$@"\n' "$BUN" "$TOOLS/mpd2glb/mpd2glb.mjs" > "$TOOLS/bin/mpd2glb.sh"
chmod +x "$TOOLS/bin/mpd2glb.sh"

echo "== BrickGen -> $APP"
cd "$APP"
if command -v uv >/dev/null 2>&1; then
  uv sync --extra test
else
  python3 -m venv .venv
  .venv/bin/python -m pip install -e '.[test]'
fi
npm install --no-audit --no-fund

cat <<MSG

Done. Start the site with:
  cd $APP
  export LDRAW_NOVA_DIR=$NOVA LDRAW_DIR=$LIB BRICKGEN_EXTRA_PATH=$TOOLS/bin
  export ANTHROPIC_API_KEY=...   # optional: Claude picks the draft; without it keyword rules do
  .venv/bin/python -m brickgen --port 8000
MSG
