"""End-to-end builds with the real tools: python -m pytest -m slow"""
import pytest

from brickgen.catalog import THEMES
from brickgen.pipeline import Builder
from brickgen.planner import plan_with_rules
from conftest import real_settings

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("prompt", [prompt for _, prompt in THEMES],
                         ids=["car", "excavator", "robot", "plane", "spaceship", "house"])
def test_theme_builds_and_passes_checks(prompt, tmp_path):
    settings = real_settings()
    if settings is None:
        pytest.skip("LDraw Nova or the parts library is not installed")
    builder = Builder(settings)
    draft = plan_with_rules(prompt)

    builder.make_plan(draft, tmp_path)
    review = builder.review(tmp_path)
    glb_error = builder.glb(tmp_path)
    result = builder.collect(tmp_path, review, glb_error)

    assert result["checks"]["passed"], result["checks"]
    assert glb_error is None
    assert {"model.mpd", "model.glb", "parts.csv", "preview.png"} <= set(result["files"])
