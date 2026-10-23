"""Monochrome classification based exclusively on Gift Wiki records.

A listing is MONOCHROME only when Gift Wiki has a record for the same gift, model and backdrop.
Names alone (e.g. a model called "Black") never make a gift monochrome.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from gift_sniper.config import AbsentPairPolicy
from gift_sniper.domain.enums import MonochromeStatus
from gift_sniper.domain.normalize import color_candidates
from gift_sniper.domain.types import ListingSnapshot, MonochromeVerdict
from gift_sniper.services.reference import ReferenceSnapshot, RefRecord


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    absent_pair_policy: AbsentPairPolicy = AbsentPairPolicy.NOT_MONOCHROME
    stale_after_hours: float = 24.0
    color_check: bool = True


def _color_check(listing: ListingSnapshot, record: RefRecord) -> str:
    pairs = [
        (listing.backdrop_center_color, record.center_color),
        (listing.backdrop_edge_color, record.edge_color),
    ]
    compared = False
    for mrkt_value, gw_value in pairs:
        candidates = color_candidates(gw_value)
        if mrkt_value is None or not candidates:
            continue
        compared = True
        if (mrkt_value & 0xFFFFFF) not in candidates:
            return "mismatch"
    return "match" if compared else "not_available"


def _best_record(records: list[RefRecord]) -> RefRecord:
    def key(rec: RefRecord) -> tuple[int, str]:
        t = rec.type
        return (t.priority if t is not None else 99, rec.record_id)

    return sorted(records, key=key)[0]


def classify(
    listing: ListingSnapshot,
    snapshot: ReferenceSnapshot,
    config: ClassifierConfig,
    *,
    now: datetime | None = None,
) -> MonochromeVerdict:
    now = now or datetime.now(UTC)
    match = snapshot.match_collection(listing.collection_name, listing.collection_title)
    if match.status == "no_name":
        return MonochromeVerdict(MonochromeStatus.UNKNOWN, "В листинге нет названия коллекции")
    if match.status == "ambiguous":
        return MonochromeVerdict(
            MonochromeStatus.UNKNOWN,
            f"Коллекция неоднозначно сопоставляется с Gift Wiki (кандидатов: {len(match.candidates)})",
        )
    if match.status != "matched" or match.gift_id is None:
        return MonochromeVerdict(MonochromeStatus.UNKNOWN, "Коллекция не найдена в данных Gift Wiki")

    coverage = snapshot.gifts.get(match.gift_id)
    data_as_of = coverage.synced_at if coverage else snapshot.last_success_at
    gift_name = coverage.gift_name if coverage else None
    gift_id = match.gift_id

    def verdict(
        status: MonochromeStatus,
        reason: str,
        *,
        record: RefRecord | None = None,
        color_check: str = "not_available",
    ) -> MonochromeVerdict:
        return MonochromeVerdict(
            status,
            reason,
            gw_type=record.type if record is not None and status is MonochromeStatus.MONOCHROME else None,
            record_id=record.record_id if record is not None else None,
            gift_id=gift_id,
            gift_name=gift_name,
            photo_url=record.photo_url if record is not None else None,
            data_as_of=data_as_of,
            color_check=color_check,
        )

    if not listing.model_name or not listing.backdrop_name:
        return verdict(MonochromeStatus.UNKNOWN, "В листинге не указаны модель или фон")

    records = snapshot.records_for(match.gift_id, listing.model_name, listing.backdrop_name)
    if records:
        record = _best_record(records)
        if record.type is None:
            return verdict(
                MonochromeStatus.UNKNOWN,
                f"Недокументированный тип классификации Gift Wiki: {record.type_raw!r}",
                record=record,
            )
        color = _color_check(listing, record) if config.color_check else "disabled"
        if color == "mismatch":
            return verdict(
                MonochromeStatus.UNKNOWN,
                "Цвета фона в MRKT и в записи Gift Wiki не совпадают",
                record=record,
                color_check=color,
            )
        return verdict(
            MonochromeStatus.MONOCHROME,
            f"Запись Gift Wiki: {record.model_name} + {record.backdrop_name}, тип {record.type.value}",
            record=record,
            color_check=color,
        )

    if config.absent_pair_policy is AbsentPairPolicy.UNKNOWN:
        return verdict(MonochromeStatus.UNKNOWN, "Пары модель + фон нет в записях Gift Wiki")
    if coverage is None or not coverage.complete:
        return verdict(
            MonochromeStatus.UNKNOWN, "Полный список монохромов этого подарка из Gift Wiki не получен"
        )
    if coverage.records_count == 0:
        return verdict(
            MonochromeStatus.UNKNOWN, "В Gift Wiki нет ни одной монохромной записи для этого подарка"
        )
    if coverage.synced_at is None:
        return verdict(MonochromeStatus.UNKNOWN, "Нет даты синхронизации Gift Wiki")
    age_hours = (now - coverage.synced_at).total_seconds() / 3600
    if age_hours > config.stale_after_hours:
        return verdict(
            MonochromeStatus.UNKNOWN,
            f"Данные Gift Wiki устарели ({age_hours:.0f} ч), отсутствие пары не подтверждено",
        )
    return verdict(
        MonochromeStatus.NOT_MONOCHROME,
        f"Пары модель + фон нет в полном списке монохромов Gift Wiki ({coverage.records_count} записей)",
    )
