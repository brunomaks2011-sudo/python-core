"""Settings, read once from the environment."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    nova_dir: Path  # LDraw Nova checkout with ./ldraw-agent and its .venv
    ldraw_dir: Path  # LDraw parts library
    data_dir: Path  # job folders
    model: str  # Claude model for the planner
    use_claude: bool
    workers: int  # jobs built at the same time
    max_queue: int  # waiting jobs before new ones are refused
    jobs_per_hour: int  # per client address
    extra_path: str  # prepended to PATH for LeoCAD, mpd2glb.sh and xvfb-run
    xvfb: bool  # wrap LeoCAD renders in xvfb-run
    review_timeout: int
    glb_timeout: int
    three_url: str  # where the browser loads three.js from

    @classmethod
    def from_env(cls) -> "Settings":
        home = Path.home()
        data = Path(os.environ.get("BRICKGEN_DATA_DIR", Path.cwd() / "data"))
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
        xvfb = os.environ.get("BRICKGEN_XVFB", "auto")
        if xvfb == "auto":
            use_xvfb = not os.environ.get("DISPLAY") and shutil.which("xvfb-run") is not None
        else:
            use_xvfb = xvfb.lower() in ("1", "true", "yes")
        return cls(
            nova_dir=Path(os.environ.get("LDRAW_NOVA_DIR", home / "ldraw-nova")),
            ldraw_dir=Path(os.environ.get("LDRAW_DIR") or os.environ.get("LDRAWDIR") or home / "ldraw"),
            data_dir=data,
            model=os.environ.get("BRICKGEN_MODEL", "claude-opus-5-5"),
            use_claude=has_key and os.environ.get("BRICKGEN_PLANNER", "auto") != "rules",
            workers=_int("BRICKGEN_WORKERS", 2),
            max_queue=_int("BRICKGEN_MAX_QUEUE", 20),
            jobs_per_hour=_int("BRICKGEN_JOBS_PER_HOUR", 30),
            extra_path=os.environ.get("BRICKGEN_EXTRA_PATH", ""),
            xvfb=use_xvfb,
            review_timeout=_int("BRICKGEN_REVIEW_TIMEOUT", 300),
            glb_timeout=_int("BRICKGEN_GLB_TIMEOUT", 300),
            three_url=os.environ.get("BRICKGEN_THREE_URL", ""),
        )
