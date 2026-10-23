"""Monochrome percentages: correct formulas, no zero for missing data, no mixing of metrics."""

from __future__ import annotations

from datetime import UTC, datetime

from gift_sniper.domain.enums import MonochromeStatus
from gift_sniper.services.percentages import (
    NO_DATA,
    format_listing_share,
    format_model_share,
    format_percent,
    format_permille,
    monochrome_listing_share,
    monochrome_model_share,
)


class TestModelShare:
    def test_formula_numerator_over_known_models(self) -> None:
        share = monochrome_model_share({"onyx", "ivory"}, {"onyx", "ivory", "red", "blue", "green"})
        assert share is not None
        assert (share.numerator, share.denominator) == (2, 5)
        assert share.percent == 40.0

    def test_monochrome_models_are_part_of_known_models(self) -> None:
        # a model with a Gift Wiki record is known even if MRKT never listed it
        share = monochrome_model_share({"onyx", "ghost"}, {"onyx", "red", "blue"})
        assert share is not None
        assert (share.numerator, share.denominator) == (2, 4)

    def test_no_observed_models_gives_no_data_not_fake_hundred_percent(self) -> None:
        assert monochrome_model_share({"onyx"}, set()) is None

    def test_no_monochrome_models_is_a_real_zero(self) -> None:
        share = monochrome_model_share(set(), {"red", "blue"})
        assert share is not None
        assert share.percent == 0.0

    def test_always_flagged_as_based_on_known_models(self) -> None:
        share = monochrome_model_share({"onyx"}, {"onyx", "red"})
        assert share is not None
        assert "по известным моделям" in share.note
        assert not share.complete

    def test_rarity_coverage_reported(self) -> None:
        share = monochrome_model_share({"a"}, {"a", "b"}, rarity_by_model={"a": 500, "b": 498})
        assert share is not None
        assert "998‰" in share.note
        assert share.complete

    def test_rarity_coverage_not_claimed_with_missing_rarity(self) -> None:
        share = monochrome_model_share({"a"}, {"a", "b"}, rarity_by_model={"a": 500, "b": None})
        assert share is not None
        assert "‰" not in share.note
        assert not share.complete

    def test_formatting(self) -> None:
        share = monochrome_model_share({"a"}, {"a", "b", "c", "d"})
        assert format_model_share(share).startswith("1 из 4 моделей — 25%")
        assert format_model_share(None) == NO_DATA


class TestListingShare:
    def test_formula_and_unknown_never_counted_as_monochrome(self) -> None:
        statuses = (
            [MonochromeStatus.MONOCHROME] * 12
            + [MonochromeStatus.NOT_MONOCHROME] * 63
            + [MonochromeStatus.UNKNOWN] * 5
        )
        share = monochrome_listing_share(statuses)
        assert (share.numerator, share.denominator, share.unknown) == (12, 80, 5)
        assert share.percent == 15.0

    def test_string_statuses_accepted(self) -> None:
        share = monochrome_listing_share(["MONOCHROME", "UNKNOWN"])
        assert (share.numerator, share.denominator) == (1, 2)

    def test_empty_set_has_no_percentage(self) -> None:
        share = monochrome_listing_share([])
        assert share.percent is None
        assert format_listing_share(share) == NO_DATA

    def test_format_shows_numerator_denominator_time_and_scope(self) -> None:
        share = monochrome_listing_share(
            [MonochromeStatus.MONOCHROME] * 12 + [MonochromeStatus.NOT_MONOCHROME] * 68
        )
        text = format_listing_share(
            share, computed_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC), scope="фильтр X"
        )
        assert text.startswith("12 из 80 объявлений — 15%")
        assert "фильтр X" in text
        assert "2026-01-02 03:04 UTC" in text


class TestFormatting:
    def test_percent(self) -> None:
        assert format_percent(None) == NO_DATA
        assert format_percent(15.0) == "15%"
        assert format_percent(15.625) == "15.6%"
        assert format_percent(0.05) == "0.05%"
        assert format_percent(0.0) == "0%"

    def test_permille_is_converted_not_zero_filled(self) -> None:
        assert format_permille(15) == "1.5%"
        assert format_permille(None) == NO_DATA
        assert format_permille(0) == "0%"
