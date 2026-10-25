import json
from types import SimpleNamespace

import pytest

from brickgen.catalog import COLOURS, TEMPLATES, THEMES
from brickgen.planner import ClaudePlanner, NotUnderstood, Planner, _schema, draft_from_answer, plan_with_rules


@pytest.mark.parametrize("prompt, template", [
    ("красная спортивная машина", "grand-tourer"),
    ("жёлтый экскаватор", "excavator"),
    ("робот", "robot"),
    ("самолёт", "courier-jet"),
    ("космический корабль", "halcyon"),
    ("дом", "cottage"),
    ("домик на дереве", "treehouse"),
    ("пожарная машина", "tipper-truck"),
    ("fire station", "fire-station"),
    ("A yellow digger", "excavator"),
])
def test_rules_pick_template(prompt, template):
    assert plan_with_rules(prompt).template == template


def test_every_theme_chip_is_understood():
    for _, prompt in THEMES:
        assert plan_with_rules(prompt).template in TEMPLATES


@pytest.mark.parametrize("prompt, colours", [
    ("красная спортивная машина с белой крышей", {"body": "Red", "roof": "White"}),
    ("синий дом с красной крышей", {"walls": "Blue", "roof": "Red"}),
    ("красный робот с синими руками", {"body": "Red", "limbs": "Blue"}),
    ("зелёный экскаватор с чёрными гусеницами", {"body": "Green", "tracks": "Black"}),
    ("робот", {}),
])
def test_rules_assign_colours_to_roles(prompt, colours):
    assert plan_with_rules(prompt).colours == colours


def test_rules_reject_unrelated_requests():
    with pytest.raises(NotUnderstood):
        plan_with_rules("напиши стихи про осень")


def test_answer_is_checked_against_the_catalog():
    draft = draft_from_answer({
        "template": "grand-tourer", "match": "close", "palette": "no-such-palette",
        "colours": [{"role": "body", "colour": "Red"}, {"role": "wings", "colour": "Blue"},
                    {"role": "roof", "colour": "Plaid"}],
        "title": "x" * 100, "summary": "Машина", "caveats": ["a", "b", "c", "d", " "],
    })
    assert draft.palette == TEMPLATES["grand-tourer"].default_palette
    assert draft.colours == {"body": "Red"}
    assert len(draft.title) == 60 and draft.title.endswith("…")
    assert draft.caveats == ["a", "b", "c"]
    assert draft.match == "close" and draft.planner == "claude"
    with pytest.raises(ValueError):
        draft_from_answer({"template": "unicorn"})


def test_schema_is_strict():
    schema = _schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["template"]["enum"] == list(TEMPLATES)
    item = schema["properties"]["colours"]["items"]
    assert item["additionalProperties"] is False and item["properties"]["colour"]["enum"] == list(COLOURS)


class FakeClient:
    """Stands in for anthropic.Anthropic: records the request, returns or raises the given outcome."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def reply(answer: dict, stop_reason: str = "end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, usage=None, content=[
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text=json.dumps(answer, ensure_ascii=False)),
    ])


ROBOT = {"template": "robot", "match": "exact", "palette": "default",
         "colours": [{"role": "body", "colour": "Red"}], "title": "Красный робот",
         "summary": "Робот с красным корпусом.", "caveats": []}


def test_claude_planner_sends_a_cached_structured_request():
    client = FakeClient(reply(ROBOT))
    draft = ClaudePlanner("claude-test", client=client).plan("красный робот")
    assert draft.template == "robot" and draft.colours == {"body": "Red"} and draft.planner == "claude"
    request = client.calls[0]
    assert request["model"] == "claude-test"
    assert request["messages"] == [{"role": "user", "content": "красный робот"}]
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "robot" in request["system"][0]["text"]
    assert request["output_config"]["format"]["type"] == "json_schema"


def test_planner_falls_back_to_rules_when_claude_fails():
    planner = Planner(ClaudePlanner("claude-test", client=FakeClient(ConnectionError("offline"))))
    draft = planner.plan("жёлтый экскаватор")
    assert draft.template == "excavator" and draft.planner == "rules" and draft.planner_note


def test_planner_falls_back_when_the_answer_is_malformed():
    planner = Planner(ClaudePlanner("claude-test", client=FakeClient(reply({"template": "unicorn"}))))
    assert planner.plan("робот").planner == "rules"


@pytest.mark.parametrize("outcome", [reply(ROBOT, stop_reason="refusal"), reply({**ROBOT, "match": "none"})])
def test_planner_reports_requests_it_cannot_build(outcome):
    planner = Planner(ClaudePlanner("claude-test", client=FakeClient(outcome)))
    with pytest.raises(NotUnderstood):
        planner.plan("что-то непонятное")


def test_planner_trims_long_prompts():
    client = FakeClient(reply(ROBOT))
    Planner(ClaudePlanner("claude-test", client=client)).plan("робот " * 200)
    assert len(client.calls[0]["messages"][0]["content"]) <= 300
