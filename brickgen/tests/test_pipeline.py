import csv
import json

from brickgen.pipeline import Builder, recolour
from brickgen.planner import Draft
from conftest import BOM, REVIEW


def plan_with(colours_by_section):
    return {"version": 1, "sections": [
        {"name": name, "steps": [[{"id": f"p{i}", "ref": "3001.dat", "colour": c, "at": [0, 0, 0]}
                                  for i, c in enumerate(colours)]]}
        for name, colours in colours_by_section.items()]}


def colours_of(plan):
    return {s["name"]: [p["colour"] for step in s["steps"] for p in step] for s in plan["sections"]}


def test_recolour_matches_codes_and_names_within_sections():
    plan = plan_with({"walls.ldr": [4, "@colours.Red", 15], "roof.ldr": [4]})
    changed = recolour(plan, [(4, "@colours.Blue", ("walls.ldr",))], {"Red": 4, "White": 15})
    assert changed == 2
    assert colours_of(plan) == {"walls.ldr": ["@colours.Blue", "@colours.Blue", 15], "roof.ldr": [4]}


def test_recolour_applies_the_first_matching_rule_once():
    plan = plan_with({"a.ldr": [4, 1]})
    recolour(plan, [(4, "@colours.Blue", ()), (1, "@colours.Red", ())], {"Blue": 1, "Red": 4})
    assert colours_of(plan) == {"a.ldr": ["@colours.Blue", "@colours.Red"]}


def test_example_plan_is_recoloured_and_attributed(settings, tmp_path):
    source = settings.nova_dir / "examples/building-atlas/cottage/scene.plan.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(plan_with({"cottage-shell.ldr": [19, 72], "porch-15-72-8-4-144.ldr": [72, 19]})))
    settings.ldraw_dir.mkdir()
    (settings.ldraw_dir / "LDConfig.ldr").write_text("0 !COLOUR Blue CODE 1 VALUE #1E5AA8 EDGE #333333\n")
    workdir = tmp_path / "job"
    workdir.mkdir()

    draft = Draft(template="cottage", colours={"walls": "Blue"}, title="Дом", summary="")
    plan = json.loads(Builder(settings).make_plan(draft, workdir).read_text())

    assert colours_of(plan) == {"cottage-shell.ldr": ["@colours.Blue", 72], "porch-15-72-8-4-144.ldr": [72, 19]}
    assert plan["license"].startswith("Licensed under CC BY-SA 4.0") and plan["license"].endswith("recoloured by BrickGen")


def test_generator_plan_needs_no_attribution(settings, tmp_path):
    draft = Draft(template="robot", colours={"body": "Red"}, title="Робот", summary="")
    plan = json.loads(Builder(settings).make_plan(draft, tmp_path).read_text())
    assert "license" not in plan and plan["sections"][0]["name"] == "robot.ldr"


def test_collect_summarises_checks_and_writes_the_parts_list(settings, tmp_path):
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "bom.json").write_text(json.dumps(BOM))
    (tmp_path / "review" / "model.mpd").write_text("0 FILE model.ldr\n")
    result = Builder(settings).collect(tmp_path, REVIEW, glb_error="no GLB")

    assert result["checks"]["passed"] and [s["status"] for s in result["checks"]["stages"]] == ["passed"] * 4
    notes = {n["code"]: n["text"] for n in result["checks"]["notes"]}
    assert "3 отдельных групп" in notes["assembly.disconnected_evidence"]
    assert notes["custom.unknown"] == "Something LDraw Nova said"
    assert result["bom"] == [dict(part="3001.dat", description="Brick 2 x 4", colour="Red", code=4,
                                  hex="#B40000", quantity=2)]
    assert result["files"] == ["model.mpd", "parts.csv"] and result["glb_error"] == "no GLB"
    with open(tmp_path / "parts.csv", encoding="utf-8") as f:
        assert list(csv.reader(f))[1] == ["3001.dat", "Brick 2 x 4", "Red", "4", "2"]


def test_collect_survives_diagnostics_without_details(settings, tmp_path):
    review = {"checks_passed": False, "stages": {"validation": "failed"},
              "diagnostics": [{"code": "assembly.disconnected_evidence", "severity": "warning", "message": "m"}]}
    result = Builder(settings).collect(tmp_path, review, None)
    assert "? отдельных групп" in result["checks"]["notes"][0]["text"] and not result["checks"]["passed"]
