import dataclasses
import json
from pathlib import Path

import pytest

from brickgen.config import Settings
from brickgen.pipeline import Builder

REVIEW = {
    "checks_passed": True,
    "stages": {"validation": "passed", "bom": "passed", "render": "passed", "bom_comparison": "passed"},
    "diagnostics": [
        {"code": "assembly.disconnected_evidence", "severity": "warning", "message": "groups", "component_count": 3},
        {"code": "custom.unknown", "severity": "info", "message": "Something LDraw Nova said"},
    ],
    "physical_placements": 2,
    "physical_validity": "valid",
}

BOM = {"bom": [{"part": "3001.dat", "description": "Brick  2 x  4", "colour_name": "Red", "colour_code": 4, "quantity": 2}]}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "BRICKGEN_THREE_URL"):
        monkeypatch.delenv(name, raising=False)
    return dataclasses.replace(Settings.from_env(), data_dir=tmp_path / "data", nova_dir=tmp_path / "nova",
                               ldraw_dir=tmp_path / "ldraw", workers=1, xvfb=False)


class FakeBuilder(Builder):
    """Leaves the files a real build leaves behind, without running LDraw Nova."""

    def make_plan(self, draft, workdir: Path) -> Path:
        path = workdir / "model.plan.json"
        path.write_text(json.dumps({"version": 1, "sections": []}), encoding="utf-8")
        return path

    def review(self, workdir: Path) -> dict:
        previews = workdir / "review" / "previews"
        previews.mkdir(parents=True)
        (workdir / "review" / "model.mpd").write_text("0 FILE model.ldr\n", encoding="utf-8")
        (previews / "home.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (workdir / "review" / "bom.json").write_text(json.dumps(BOM), encoding="utf-8")
        (workdir / "review" / "review.json").write_text(json.dumps(REVIEW), encoding="utf-8")
        return REVIEW

    def glb(self, workdir: Path) -> str | None:
        (workdir / "model.glb").write_bytes(b"glTF")
        return None


def real_settings() -> Settings | None:
    """Settings for the installed tools, or None when LDraw Nova or the parts library is missing."""
    settings = Settings.from_env()
    if not (settings.nova_dir / "ldraw-agent").exists() or not (settings.ldraw_dir / "LDConfig.ldr").exists():
        return None
    return settings


@pytest.fixture
def library() -> Path:
    settings = real_settings()
    if not settings:
        pytest.skip("LDraw parts library not installed (set LDRAW_DIR and LDRAW_NOVA_DIR)")
    return settings.ldraw_dir


@pytest.fixture
def nova_dir() -> Path:
    settings = real_settings()
    if not settings:
        pytest.skip("LDraw Nova not installed (set LDRAW_NOVA_DIR and LDRAW_DIR)")
    return settings.nova_dir


def ldconfig_names(library: Path) -> set[str]:
    names = set()
    with open(library / "LDConfig.ldr", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) > 2 and parts[1] == "!COLOUR":
                names.add(parts[2])
    return names

