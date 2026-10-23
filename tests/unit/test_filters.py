"""Filter engine: every criterion, exclusions, only-new, discount, monochrome-mode rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from gift_sniper.domain.enums import FilterKind, GiftWikiMonochromeType, MonochromeStatus
from gift_sniper.domain.types import Share
from gift_sniper.services.filters import FilterCriteria, MatchContext, describe_criteria, evaluate
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
