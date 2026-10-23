"""In-memory snapshot of the Gift Wiki reference data and MRKT <-> Gift Wiki matching.

The snapshot is built from the database (never from live requests), so classification of a listing
needs no network round trip. It is rebuilt after every Gift Wiki sync.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from gift_sniper.domain.enums import GiftWikiMonochromeType
from gift_sniper.domain.normalize import compact_name, normalize_name


@dataclass(frozen=True, slots=True)
class RefRecord:
    record_id: str
    gift_id: str
    gift_name: str | None
    model_name: str | None
    backdrop_name: str | None
    type_raw: str | None
    center_color: str | None = None
    edge_color: str | None = None
    photo_url: str | None = None

    @property
    def type(self) -> GiftWikiMonochromeType | None:
        return GiftWikiMonochromeType.parse(self.type_raw)


@dataclass(frozen=True, slots=True)
class GiftCoverage:
    gift_id: str
    gift_name: str | None
    records_count: int
    complete: bool
    synced_at: datetime | None


@dataclass(frozen=True, slots=True)
class GiftMatch:
    status: str  # matched | not_found | ambiguous | no_name
    gift_id: str | None = None
    method: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass
class ReferenceSnapshot:
    gifts: dict[str, GiftCoverage] = field(default_factory=dict)
    gifts_by_norm: dict[str, set[str]] = field(default_factory=dict)
    gifts_by_compact: dict[str, set[str]] = field(default_factory=dict)
    records: dict[tuple[str, str, str], list[RefRecord]] = field(default_factory=dict)
    monochrome_models: dict[str, dict[str, str]] = field(default_factory=dict)  # gift_id -> norm -> name
    manual_mappings: dict[str, str] = field(default_factory=dict)  # MRKT collection norm -> gift_id
    last_success_at: datetime | None = None
    loaded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def build(
        cls,
        gifts: list[GiftCoverage],
        records: list[RefRecord],
        *,
        manual_mappings: dict[str, str] | None = None,
        last_success_at: datetime | None = None,
    ) -> ReferenceSnapshot:
        snap = cls(last_success_at=last_success_at)
        by_norm: dict[str, set[str]] = defaultdict(set)
        by_compact: dict[str, set[str]] = defaultdict(set)
        for gift in gifts:
            snap.gifts[gift.gift_id] = gift
            if gift.gift_name:
                by_norm[normalize_name(gift.gift_name)].add(gift.gift_id)
                by_compact[compact_name(gift.gift_name)].add(gift.gift_id)
        recs: dict[tuple[str, str, str], list[RefRecord]] = defaultdict(list)
        models: dict[str, dict[str, str]] = defaultdict(dict)
        for rec in records:
            if not rec.model_name or not rec.backdrop_name:
                continue  # incomplete record: cannot identify a model + backdrop pair
            key = (rec.gift_id, normalize_name(rec.model_name), normalize_name(rec.backdrop_name))
            recs[key].append(rec)
            if rec.type is not None:
                models[rec.gift_id].setdefault(normalize_name(rec.model_name), rec.model_name)
        snap.gifts_by_norm = dict(by_norm)
        snap.gifts_by_compact = dict(by_compact)
        snap.records = dict(recs)
        snap.monochrome_models = dict(models)
        snap.manual_mappings = {normalize_name(k): v for k, v in (manual_mappings or {}).items()}
        return snap

    @property
    def records_count(self) -> int:
        return sum(len(v) for v in self.records.values())

    def age_hours(self, now: datetime | None = None) -> float | None:
        if self.last_success_at is None:
            return None
        now = now or datetime.now(UTC)
        return (now - self.last_success_at).total_seconds() / 3600

    def match_collection(self, collection_name: str | None, collection_title: str | None = None) -> GiftMatch:
        """Map a MRKT collection to a Gift Wiki gift. Ambiguity is reported, never resolved by guessing."""
        names = [n for n in (collection_name, collection_title) if n]
        if not names:
            return GiftMatch("no_name")
        for name in names:
            manual = self.manual_mappings.get(normalize_name(name))
            if manual:
                return GiftMatch("matched", manual, "manual", (manual,))
        exact: set[str] = set()
        for name in names:
            exact |= self.gifts_by_norm.get(normalize_name(name), set())
        if len(exact) == 1:
            gift_id = next(iter(exact))
            return GiftMatch("matched", gift_id, "name", (gift_id,))
        if len(exact) > 1:
            return GiftMatch("ambiguous", candidates=tuple(sorted(exact)))
        compact: set[str] = set()
        for name in names:
            compact |= self.gifts_by_compact.get(compact_name(name), set())
        if len(compact) == 1:
            gift_id = next(iter(compact))
            return GiftMatch("matched", gift_id, "compact_name", (gift_id,))
        if len(compact) > 1:
            return GiftMatch("ambiguous", candidates=tuple(sorted(compact)))
        return GiftMatch("not_found")

    def records_for(self, gift_id: str, model_name: str, backdrop_name: str) -> list[RefRecord]:
        return self.records.get((gift_id, normalize_name(model_name), normalize_name(backdrop_name)), [])

    def records_of_gift(self, gift_id: str) -> list[RefRecord]:
        return [r for key, recs in self.records.items() if key[0] == gift_id for r in recs]
