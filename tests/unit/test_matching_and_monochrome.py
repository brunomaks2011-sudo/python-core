"""MRKT <-> Gift Wiki matching and monochrome classification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from gift_sniper.config import AbsentPairPolicy
from gift_sniper.domain.enums import GiftWikiMonochromeType, MonochromeStatus
from gift_sniper.domain.normalize import color_candidates, compact_name, normalize_name
from gift_sniper.services.monochrome import ClassifierConfig, classify
from gift_sniper.services.reference import GiftCoverage, ReferenceSnapshot, RefRecord
from tests.factories import make_listing, make_snapshot

CFG = ClassifierConfig()


class TestNormalization:
    def test_cosmetic_differences_removed(self) -> None:
        assert normalize_name("  Durov’s   Cap ") == normalize_name("durov's cap")
        assert normalize_name("Jack–in–the–Box") == normalize_name("jack-in-the-box")
        assert compact_name("Plush Pepe") == compact_name("PlushPepe")

    def test_different_words_stay_different(self) -> None:
        assert normalize_name("Black") != normalize_name("Onyx Black")

    def test_color_formats(self) -> None:
        assert color_candidates("#1A2B3C") == {0x1A2B3C}
        assert color_candidates("0x1a2b3c") == {0x1A2B3C}
        assert color_candidates("#FF1A2B3C") == {0x1A2B3C}
        assert color_candidates("rgb(26, 43, 60)") == {0x1A2B3C}
        assert color_candidates(1715004) == {1715004}
        # ambiguous: both decimal and hex readings are kept
        assert color_candidates("123456") == {123456, 0x123456}
        assert color_candidates("not a color") == set()
        assert color_candidates(None) == set()


class TestMatching:
    def test_exact_name(self) -> None:
        snap = make_snapshot()
        match = snap.match_collection("Plush Pepe")
        assert (match.status, match.gift_id, match.method) == ("matched", "gw-pepe", "name")

    def test_title_used_when_name_differs(self) -> None:
        snap = make_snapshot()
        match = snap.match_collection("unknown-slug", "Plush Pepe")
        assert match.status == "matched"

    def test_compact_name(self) -> None:
        snap = make_snapshot()
        match = snap.match_collection("PlushPepe")
        assert (match.status, match.method) == ("matched", "compact_name")

    def test_ambiguous_is_not_resolved(self) -> None:
        snap = make_snapshot(extra_gifts=[GiftCoverage("other-id", "Plush Pepe", 3, True, datetime.now(UTC))])
        match = snap.match_collection("Plush Pepe")
        assert match.status == "ambiguous"
        assert set(match.candidates) == {"gw-pepe", "other-id"}

    def test_not_found(self) -> None:
        assert make_snapshot().match_collection("Lunar Snake").status == "not_found"

    def test_manual_mapping_wins(self) -> None:
        refs = [RefRecord("r1", "gw-x", "Pepe Plushie", "Onyx", "Black", "high")]
        snap = ReferenceSnapshot.build(
            [GiftCoverage("gw-x", "Pepe Plushie", 1, True, datetime.now(UTC))],
            refs,
            manual_mappings={"Plush Pepe": "gw-x"},
        )
        match = snap.match_collection("Plush Pepe")
        assert (match.status, match.gift_id, match.method) == ("matched", "gw-x", "manual")


class TestClassification:
    def test_monochrome_requires_exact_gift_model_backdrop_record(self) -> None:
        snap = make_snapshot(records=[("Onyx", "Black", "high")])
        verdict = classify(make_listing(model_name="Onyx", backdrop_name="Black"), snap, CFG)
        assert verdict.status is MonochromeStatus.MONOCHROME
        assert verdict.gw_type is GiftWikiMonochromeType.HIGH
        assert verdict.record_id == "r0"
        assert verdict.gift_id == "gw-pepe"

    def test_same_model_other_backdrop_is_not_monochrome(self) -> None:
        snap = make_snapshot(records=[("Onyx", "Black", "high")])
        verdict = classify(make_listing(model_name="Onyx", backdrop_name="Ivory White"), snap, CFG)
        assert verdict.status is MonochromeStatus.NOT_MONOCHROME

    def test_name_with_color_word_is_not_enough(self) -> None:
        # "Black" model on "Black" backdrop without a Gift Wiki record is not a confirmed monochrome
        snap = make_snapshot(records=[("Onyx", "Black", "high")])
        verdict = classify(make_listing(model_name="Black", backdrop_name="Black"), snap, CFG)
        assert verdict.status is not MonochromeStatus.MONOCHROME

    def test_unknown_when_collection_missing_from_giftwiki(self) -> None:
        verdict = classify(
            make_listing(collection_name="Lunar Snake", collection_title="Lunar Snake"), make_snapshot(), CFG
        )
        assert verdict.status is MonochromeStatus.UNKNOWN

    def test_unknown_when_ambiguous(self) -> None:
        snap = make_snapshot(extra_gifts=[GiftCoverage("other", "Plush Pepe", 1, True, datetime.now(UTC))])
        assert classify(make_listing(), snap, CFG).status is MonochromeStatus.UNKNOWN

    def test_unknown_when_model_or_backdrop_missing(self) -> None:
        listing = make_listing(backdrop_name=None)
        assert classify(listing, make_snapshot(), CFG).status is MonochromeStatus.UNKNOWN

    def test_unknown_when_list_incomplete(self) -> None:
        snap = make_snapshot(complete=False)
        verdict = classify(make_listing(backdrop_name="Ivory White"), snap, CFG)
        assert verdict.status is MonochromeStatus.UNKNOWN

    def test_unknown_when_gift_has_no_records(self) -> None:
        snap = make_snapshot(records=[])
        verdict = classify(make_listing(), snap, CFG)
        assert verdict.status is MonochromeStatus.UNKNOWN

    def test_unknown_when_absent_pair_data_is_stale(self) -> None:
        snap = make_snapshot(synced_at=datetime.now(UTC) - timedelta(hours=48))
        verdict = classify(
            make_listing(backdrop_name="Ivory White"), snap, ClassifierConfig(stale_after_hours=24)
        )
        assert verdict.status is MonochromeStatus.UNKNOWN
        assert "устарели" in verdict.reason

    def test_stale_data_still_confirms_existing_record_with_its_age(self) -> None:
        synced = datetime.now(UTC) - timedelta(hours=48)
        snap = make_snapshot(synced_at=synced)
        verdict = classify(make_listing(), snap, ClassifierConfig(stale_after_hours=24))
        assert verdict.status is MonochromeStatus.MONOCHROME
        assert verdict.data_as_of == synced

    def test_policy_unknown_for_absent_pairs(self) -> None:
        cfg = ClassifierConfig(absent_pair_policy=AbsentPairPolicy.UNKNOWN)
        verdict = classify(make_listing(backdrop_name="Ivory White"), make_snapshot(), cfg)
        assert verdict.status is MonochromeStatus.UNKNOWN

    def test_undocumented_type_is_unknown(self) -> None:
        snap = make_snapshot(records=[("Onyx", "Black", "ultra")])
        verdict = classify(make_listing(), snap, CFG)
        assert verdict.status is MonochromeStatus.UNKNOWN
        assert "Недокументированный" in verdict.reason

    def test_best_type_chosen_by_giftwiki_order(self) -> None:
        snap = make_snapshot(records=[("Onyx", "Black", "low"), ("Onyx", "Black", "high")])
        assert classify(make_listing(), snap, CFG).gw_type is GiftWikiMonochromeType.HIGH

    def test_color_match_and_mismatch(self) -> None:
        colors = {("Onyx", "Black"): ("#000000", "#111111")}
        snap = make_snapshot(colors=colors)
        ok = classify(make_listing(backdrop_center_color=0, backdrop_edge_color=0x111111), snap, CFG)
        assert ok.status is MonochromeStatus.MONOCHROME
        assert ok.color_check == "match"
        bad = classify(make_listing(backdrop_center_color=0xFF0000), snap, CFG)
        assert bad.status is MonochromeStatus.UNKNOWN
        assert bad.color_check == "mismatch"

    def test_color_check_can_be_disabled(self) -> None:
        snap = make_snapshot(colors={("Onyx", "Black"): ("#000000", None)})
        verdict = classify(
            make_listing(backdrop_center_color=0xFF0000), snap, ClassifierConfig(color_check=False)
        )
        assert verdict.status is MonochromeStatus.MONOCHROME
        assert verdict.color_check == "disabled"

    def test_unparseable_colors_do_not_block(self) -> None:
        snap = make_snapshot(colors={("Onyx", "Black"): ("dark", None)})
        verdict = classify(make_listing(backdrop_center_color=0xFF0000), snap, CFG)
        assert verdict.status is MonochromeStatus.MONOCHROME
        assert verdict.color_check == "not_available"

    def test_monochrome_models_index(self) -> None:
        snap = make_snapshot(
            records=[("Onyx", "Black", "high"), ("Onyx", "Gray", "low"), ("Ivory", "White", "combo")]
        )
        assert set(snap.monochrome_models["gw-pepe"]) == {normalize_name("Onyx"), normalize_name("Ivory")}
