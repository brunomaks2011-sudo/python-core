"""Filter engine: every criterion, exclusions, only-new, discount, monochrome-mode rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from gift_sniper.domain.enums import FilterKind, GiftWikiMonochromeType, MonochromeStatus
from gift_sniper.domain.types import Share
from gift_sniper.services.filters import (
    FilterCriteria,
    MatchContext,
    Pick,
    PriceRule,
    describe_criteria,
    evaluate,
    floor_rules,
)
from tests.factories import TON, make_enrichment, make_listing

NOW = datetime.now(UTC)
NEW = MatchContext(event_type="listing", detected_at=NOW, is_first_sighting=True)


def check(
    criteria: FilterCriteria,
    *,
    kind: FilterKind = FilterKind.REGULAR,
    ctx: MatchContext = NEW,
    enrichment=None,
    activated_at=None,
    **listing,
):
    return evaluate(
        kind,
        criteria,
        make_listing(**listing),
        enrichment or make_enrichment(),
        ctx,
        activated_at=activated_at,
    )


def test_empty_filter_matches() -> None:
    assert check(FilterCriteria()).matched


def test_price_bounds() -> None:
    c = FilterCriteria(min_price_nano=5 * TON, max_price_nano=10 * TON)
    assert check(c, price_nano=7 * TON).matched
    assert not check(c, price_nano=4 * TON).matched
    assert not check(c, price_nano=11 * TON).matched


def test_missing_price_never_matches() -> None:
    assert not check(FilterCriteria(), price_nano=None).matched


def test_collections_models_backdrops_symbols_case_insensitive() -> None:
    c = FilterCriteria(collections=["plush pepe"], models=["ONYX"], backdrops=["black"], symbols=["star"])
    assert check(c).matched
    assert not check(c.model_copy(update={"models": ["Ivory"]})).matched
    assert not check(c.model_copy(update={"backdrops": ["White"]})).matched
    assert not check(c.model_copy(update={"symbols": ["Moon"]})).matched
    assert not check(c.model_copy(update={"collections": ["Lunar Snake"]})).matched


def test_exclusions() -> None:
    assert not check(FilterCriteria(exclude_collections=["Plush Pepe"])).matched
    assert not check(FilterCriteria(exclude_models=["Onyx"])).matched
    assert check(FilterCriteria(exclude_models=["Ivory"])).matched


def test_rarity_ranges_and_missing_rarity() -> None:
    c = FilterCriteria(model_rarity_max_permille=20)
    assert check(c, model_rarity_permille=15).matched
    assert not check(c, model_rarity_permille=25).matched
    result = check(c, model_rarity_permille=None)
    assert not result.matched
    assert any("нет данных" in r for r in result.failed)
    assert not check(FilterCriteria(backdrop_rarity_min_permille=30), backdrop_rarity_permille=20).matched
    assert check(FilterCriteria(symbol_rarity_min_permille=1, symbol_rarity_max_permille=10)).matched


def test_only_new_listings() -> None:
    c = FilterCriteria(only_new_listings=True)
    assert check(c).matched
    price_change = MatchContext(event_type="change_price", detected_at=NOW, is_first_sighting=False)
    assert not check(c, ctx=price_change).matched
    assert not check(c, activated_at=NOW + timedelta(minutes=1)).matched
    assert check(c, activated_at=NOW - timedelta(minutes=1)).matched


def test_discount_requires_reliable_data() -> None:
    c = FilterCriteria(min_discount_percent=10)
    result = check(c, enrichment=make_enrichment(discount=None))
    assert not result.matched
    assert "недостаточно истории" in result.failed[0]
    assert check(c, enrichment=make_enrichment(discount=12.5)).matched
    assert not check(c, enrichment=make_enrichment(discount=5)).matched


def test_monochrome_mode_requires_confirmed_status() -> None:
    c = FilterCriteria()
    for status in (MonochromeStatus.UNKNOWN, MonochromeStatus.NOT_MONOCHROME):
        assert not check(c, kind=FilterKind.MONOCHROME, enrichment=make_enrichment(status)).matched
    ok = make_enrichment(MonochromeStatus.MONOCHROME, gw_type=GiftWikiMonochromeType.HIGH)
    assert check(c, kind=FilterKind.MONOCHROME, enrichment=ok).matched
    # the regular mode does not care about the monochrome status
    assert check(c, kind=FilterKind.REGULAR, enrichment=make_enrichment(MonochromeStatus.UNKNOWN)).matched


def test_monochrome_types_restriction() -> None:
    c = FilterCriteria(monochrome_types=["high", "medium"])
    low = make_enrichment(MonochromeStatus.MONOCHROME, gw_type=GiftWikiMonochromeType.LOW)
    high = make_enrichment(MonochromeStatus.MONOCHROME, gw_type=GiftWikiMonochromeType.HIGH)
    assert not check(c, kind=FilterKind.MONOCHROME, enrichment=low).matched
    assert check(c, kind=FilterKind.MONOCHROME, enrichment=high).matched


def test_min_monochrome_model_share() -> None:
    c = FilterCriteria(min_monochrome_model_share_percent=20)
    mono = MonochromeStatus.MONOCHROME
    high_share = make_enrichment(mono, share=Share(3, 10), gw_type=GiftWikiMonochromeType.HIGH)
    low_share = make_enrichment(mono, share=Share(1, 10), gw_type=GiftWikiMonochromeType.HIGH)
    no_share = make_enrichment(mono, share=None, gw_type=GiftWikiMonochromeType.HIGH)
    assert check(c, kind=FilterKind.MONOCHROME, enrichment=high_share).matched
    assert not check(c, kind=FilterKind.MONOCHROME, enrichment=low_share).matched
    assert not check(c, kind=FilterKind.MONOCHROME, enrichment=no_share).matched


def test_criteria_normalization() -> None:
    c = FilterCriteria(
        collections=["  Plush   Pepe ", "plush pepe", "Lunar Snake"], monochrome_types=["LOW", "x", "high"]
    )
    assert c.collections == ["Plush Pepe", "Lunar Snake"]
    assert c.monochrome_types == ["high", "low"]


def test_description_lists_applied_filter() -> None:
    lines = describe_criteria(FilterKind.MONOCHROME, FilterCriteria(max_price_nano=5 * TON, models=["Onyx"]))
    text = "\n".join(lines)
    assert "5 TON" in text and "Onyx" in text and "MONOCHROME" in text


def test_picks_take_the_most_specific_choice_and_its_price() -> None:
    picks = [
        Pick(max_price_nano=5 * TON),  # the whole collection
        Pick(model="Onyx", max_price_nano=7 * TON),  # every Onyx
        Pick(model="Onyx", backdrops=["Black"], max_price_nano=9 * TON),  # Onyx on Black
    ]
    c = FilterCriteria(collections=["Plush Pepe"], picks=picks)
    assert check(c, model_name="Onyx", backdrop_name="Black", price_nano=8 * TON).matched
    on_white = check(c, model_name="onyx", backdrop_name="White", price_nano=8 * TON)
    assert not on_white.matched and "7 TON" in on_white.failed[0]
    assert check(c, model_name="Ivory", backdrop_name="White", price_nano=4 * TON).matched
    assert not check(c, model_name="Ivory", backdrop_name="White", price_nano=6 * TON).matched
    only_pairs = FilterCriteria(picks=[Pick(model="Onyx", backdrops=["Black"], max_price_nano=9 * TON)])
    assert check(only_pairs, model_name="Ivory", price_nano=TON).failed == [
        "модель и фон не выбраны в мини-приложении"
    ]
    assert "Выбрано (3)" in describe_criteria(FilterKind.REGULAR, c)[-1]


def test_monochrome_picks_still_require_gift_wiki_confirmation() -> None:
    c = FilterCriteria(picks=[Pick(model="Onyx", backdrops=["Black"], max_price_nano=9 * TON)])
    unknown = check(c, kind=FilterKind.MONOCHROME, model_name="Onyx", backdrop_name="Black", price_nano=TON)
    assert not unknown.matched
    confirmed = make_enrichment(MonochromeStatus.MONOCHROME)
    assert check(
        c,
        kind=FilterKind.MONOCHROME,
        enrichment=confirmed,
        model_name="Onyx",
        backdrop_name="Black",
        price_nano=TON,
    ).matched


def test_monochromes_up_to_the_collection_or_model_floor() -> None:
    by_model = Pick(model="Onyx", price_rule=PriceRule.MODEL_FLOOR)
    c = FilterCriteria(collections=["Plush Pepe"], picks=[by_model])
    mono = make_enrichment(MonochromeStatus.MONOCHROME)
    floors = replace(mono, model_floor_nano=10 * TON, collection_floor_nano=4 * TON)

    def judge(enrichment, price):
        return check(
            c, kind=FilterKind.MONOCHROME, enrichment=enrichment, model_name="Onyx", price_nano=price
        )

    assert judge(floors, 10 * TON).matched  # not above the cheapest other Onyx
    above = judge(floors, 11 * TON)
    assert not above.matched and "10 TON" in above.failed[0] and "флор модели" in above.failed[0]
    unknown = judge(mono, TON)  # no floor known: nothing is bought
    assert not unknown.matched and "флор модели неизвестен" in unknown.failed[0]

    by_collection = FilterCriteria(picks=[Pick(price_rule=PriceRule.COLLECTION_FLOOR)])
    assert check(by_collection, kind=FilterKind.MONOCHROME, enrichment=floors, price_nano=4 * TON).matched
    assert not check(by_collection, kind=FilterKind.MONOCHROME, enrichment=floors, price_nano=5 * TON).matched

    capped = Pick(model="Onyx", price_rule=PriceRule.MODEL_FLOOR, max_price_nano=8 * TON)
    assert capped.limit_nano(floors) == 8 * TON  # a cap below the floor wins
    assert floor_rules(c, make_listing(model_name="Onyx")) == {PriceRule.MODEL_FLOOR}
    assert floor_rules(c, make_listing(model_name="Ivory")) == set()  # the pick does not concern this model
    summary = describe_criteria(FilterKind.MONOCHROME, c)
    assert any("Onyx · все монохромные фоны ≤ флор модели" in line for line in summary)


def test_a_fixed_price_pick_needs_its_price() -> None:
    with pytest.raises(ValidationError):
        Pick(model="Onyx")
    assert Pick(model="Onyx", price_rule=PriceRule.MODEL_FLOOR).max_price_nano is None
    old = FilterCriteria.model_validate({"picks": [{"model": "Onyx", "max_price_nano": 5 * TON}]})
    assert old.picks[0].price_rule is PriceRule.FIXED  # picks saved before the floor rules
