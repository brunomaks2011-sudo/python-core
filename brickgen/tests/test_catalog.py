import re

import pytest

from brickgen import generators
from brickgen.catalog import COLOURS, TEMPLATES
from conftest import ldconfig_names

# Fixed colours the generators use besides the recolourable roles.
FIXED = {"Dark_Bluish_Grey", "Black", "Trans_Black", "Trans_Orange", "Trans_Red", "Trans_Bright_Green"}


def placements(plan):
    for section in plan["sections"]:
        for step in section["steps"]:
            yield from step


def test_templates_are_consistent():
    for template in TEMPLATES.values():
        keys = [r.key for r in template.roles]
        assert len(keys) == len(set(keys)), template.key
        if template.palettes:
            assert template.palette(template.default_palette), template.key
        else:
            assert template.default_palette is None, template.key
        if template.kind == "generator":
            assert template.attribution is None
        else:
            assert "CC BY-SA 4.0" in template.attribution


def test_colours_have_labels_and_hex():
    for colour in COLOURS.values():
        assert re.fullmatch(r"#[0-9A-F]{6}", colour.hex) and colour.label and colour.stems


@pytest.mark.parametrize("name", ["excavator", "robot"])
def test_generators_build_plans(name):
    plan = generators.build(name, {})
    items = list(placements(plan))
    assert plan["version"] == 1 and len(items) > 30
    assert len({p["id"] for p in items}) == len(items)
    for p in items:
        assert p["ref"].endswith(".dat")
        assert len(p["at"]) == 3
        assert p["colour"].removeprefix("@colours.") in set(COLOURS) | FIXED


@pytest.mark.parametrize("name, role, default", [("excavator", "body", "Yellow"), ("robot", "body", "White")])
def test_generators_take_role_colours(name, role, default):
    used = {p["colour"] for p in placements(generators.build(name, {role: "Dark_Red"}))}
    assert "@colours.Dark_Red" in used and f"@colours.{default}" not in used


def test_generator_templates_have_generators():
    generators.build("robot", {})  # registers all generators
    for template in TEMPLATES.values():
        if template.kind == "generator":
            assert template.source in generators.GENERATORS


def test_colours_and_parts_exist_in_the_library(library):
    names = ldconfig_names(library)
    assert set(COLOURS) | FIXED <= names
    for name in ("excavator", "robot"):
        for p in placements(generators.build(name, {})):
            assert (library / "parts" / p["ref"]).exists(), p["ref"]


def test_example_templates_exist_in_ldraw_nova(nova_dir):
    for template in TEMPLATES.values():
        if template.kind == "example":
            assert (nova_dir / template.source).exists(), template.source


def test_excavator_cab_follows_the_body_unless_asked():
    def cab(colours):
        plan = generators.build("excavator", colours)
        return next(p["colour"] for p in placements(plan) if p.get("purpose") == "cab roof")

    assert cab({}) == "@colours.Yellow"
    assert cab({"body": "Red"}) == "@colours.Red"
    assert cab({"body": "Red", "cab": "White"}) == "@colours.White"
