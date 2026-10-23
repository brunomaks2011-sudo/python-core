"""Filter criteria, purchase limits and the (pure) matching engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from gift_sniper.domain.enums import FeedEventType, FilterKind, GiftWikiMonochromeType, MonochromeStatus
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import Enrichment, ListingSnapshot
from gift_sniper.services.percentages import format_percent

MAX_LIST_ITEMS = 50


def _clean_names(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = " ".join(str(value).split())
        key = normalize_name(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result[:MAX_LIST_ITEMS]


class FilterCriteria(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    min_price_nano: int | None = None
    max_price_nano: int | None = None
    collections: list[str] = []
    models: list[str] = []
    backdrops: list[str] = []
    symbols: list[str] = []
    exclude_collections: list[str] = []
    exclude_models: list[str] = []
    model_rarity_min_permille: int | None = None
    model_rarity_max_permille: int | None = None
    backdrop_rarity_min_permille: int | None = None
    backdrop_rarity_max_permille: int | None = None
    symbol_rarity_min_permille: int | None = None
    symbol_rarity_max_permille: int | None = None
    only_new_listings: bool = False
    min_discount_percent: float | None = None
    # monochrome mode only
    monochrome_types: list[str] = []
    min_monochrome_model_share_percent: float | None = None

    @field_validator(
        "collections", "models", "backdrops", "symbols", "exclude_collections", "exclude_models", mode="after"
    )
    @classmethod
    def _names(cls, value: list[str]) -> list[str]:
        return _clean_names(value)

    @field_validator("monochrome_types", mode="after")
    @classmethod
    def _types(cls, value: list[str]) -> list[str]:
        parsed = [GiftWikiMonochromeType.parse(v) for v in value]
        return [t.value for t in GiftWikiMonochromeType if t in parsed]


class FilterLimits(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    max_count: int | None = None  # how many gifts this filter may buy in total
    max_price_per_gift_nano: int | None = None
    max_per_operation_nano: int | None = None
    daily_limit_nano: int | None = None
    total_limit_nano: int | None = None
    period_max_count: int | None = None
    period_hours: int | None = None


@dataclass(frozen=True, slots=True)
class FilterSpec:
    """What the matching engine needs to know about a stored filter."""

    id: int
    user_id: int
    name: str
    kind: FilterKind
    enabled: bool
    autobuy: bool
    criteria: FilterCriteria
    limits: FilterLimits
    activated_at: datetime | None


@dataclass(frozen=True, slots=True)
class MatchContext:
    event_type: str
    detected_at: datetime
    is_first_sighting: bool = True


@dataclass(slots=True)
class MatchResult:
    matched: bool
    failed: list[str] = field(default_factory=list)


def _name_in(value: str | None, allowed: list[str]) -> bool:
    if value is None:
        return False
    target = normalize_name(value)
    return any(normalize_name(a) == target for a in allowed)


def _check_range(failed: list[str], label: str, value: int | None, low: int | None, high: int | None) -> None:
    if low is None and high is None:
        return
    if value is None:
        failed.append(f"{label}: нет данных")
        return
    if low is not None and value < low:
        failed.append(f"{label} {value}‰ меньше {low}‰")
    if high is not None and value > high:
        failed.append(f"{label} {value}‰ больше {high}‰")


def evaluate(
    kind: FilterKind,
    criteria: FilterCriteria,
    listing: ListingSnapshot,
    enrichment: Enrichment,
    ctx: MatchContext,
    *,
    activated_at: datetime | None = None,
) -> MatchResult:
    failed: list[str] = []
    price = listing.price_nano
    if price is None:
        failed.append("нет цены")
    else:
        if criteria.min_price_nano is not None and price < criteria.min_price_nano:
            failed.append(f"цена ниже {format_ton(criteria.min_price_nano)}")
        if criteria.max_price_nano is not None and price > criteria.max_price_nano:
            failed.append(f"цена выше {format_ton(criteria.max_price_nano)}")

    collection_names = [n for n in (listing.collection_name, listing.collection_title) if n]
    if criteria.collections and not any(_name_in(n, criteria.collections) for n in collection_names):
        failed.append("коллекция не выбрана")
    if criteria.exclude_collections and any(
        _name_in(n, criteria.exclude_collections) for n in collection_names
    ):
        failed.append("коллекция исключена")
    if criteria.models and not _name_in(listing.model_name, criteria.models):
        failed.append("модель не выбрана")
    if criteria.exclude_models and _name_in(listing.model_name, criteria.exclude_models):
        failed.append("модель исключена")
    if criteria.backdrops and not _name_in(listing.backdrop_name, criteria.backdrops):
        failed.append("фон не выбран")
    if criteria.symbols and not _name_in(listing.symbol_name, criteria.symbols):
        failed.append("символ не выбран")

    _check_range(
        failed,
        "редкость модели",
        listing.model_rarity_permille,
        criteria.model_rarity_min_permille,
        criteria.model_rarity_max_permille,
    )
    _check_range(
        failed,
        "редкость фона",
        listing.backdrop_rarity_permille,
        criteria.backdrop_rarity_min_permille,
        criteria.backdrop_rarity_max_permille,
    )
    _check_range(
        failed,
        "редкость символа",
        listing.symbol_rarity_permille,
        criteria.symbol_rarity_min_permille,
        criteria.symbol_rarity_max_permille,
    )

    if criteria.only_new_listings:
        is_new_event = (
            ctx.event_type in (FeedEventType.LISTING, FeedEventType.OBSERVED) and ctx.is_first_sighting
        )
        if not is_new_event:
            failed.append("не новый листинг")
        elif activated_at is not None and ctx.detected_at < activated_at:
            failed.append("листинг появился до включения фильтра")

    if criteria.min_discount_percent is not None:
        if enrichment.discount_percent is None:
            failed.append("скидку нельзя рассчитать: недостаточно истории сопоставимых цен")
        elif enrichment.discount_percent < criteria.min_discount_percent:
            failed.append(f"скидка {format_percent(enrichment.discount_percent)} меньше требуемой")

    if kind is FilterKind.MONOCHROME:
        verdict = enrichment.verdict
        if verdict.status is not MonochromeStatus.MONOCHROME:
            failed.append(f"монохром не подтверждён Gift Wiki ({verdict.status.value})")
        elif criteria.monochrome_types and (
            verdict.gw_type is None or verdict.gw_type.value not in criteria.monochrome_types
        ):
            failed.append("тип монохрома не выбран")
        if criteria.min_monochrome_model_share_percent is not None:
            share = enrichment.model_share.percent if enrichment.model_share else None
            if share is None:
                failed.append("доля монохромных моделей: нет данных")
            elif share < criteria.min_monochrome_model_share_percent:
                failed.append("доля монохромных моделей ниже порога")

    return MatchResult(matched=not failed, failed=failed)


def describe_criteria(kind: FilterKind, c: FilterCriteria) -> list[str]:
    """Human-readable summary used in filter cards and statistics ("применённый набор фильтров")."""
    lines: list[str] = []
    if c.min_price_nano is not None or c.max_price_nano is not None:
        lines.append(
            f"Цена: {format_ton(c.min_price_nano, none='—')} … {format_ton(c.max_price_nano, none='—')}"
        )
    for label, values in (
        ("Коллекции", c.collections),
        ("Модели", c.models),
        ("Фоны", c.backdrops),
        ("Символы", c.symbols),
        ("Исключить коллекции", c.exclude_collections),
        ("Исключить модели", c.exclude_models),
    ):
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    for label, low, high in (
        ("Редкость модели", c.model_rarity_min_permille, c.model_rarity_max_permille),
        ("Редкость фона", c.backdrop_rarity_min_permille, c.backdrop_rarity_max_permille),
        ("Редкость символа", c.symbol_rarity_min_permille, c.symbol_rarity_max_permille),
    ):
        if low is not None or high is not None:
            lines.append(
                f"{label}: {low if low is not None else '—'}‰ … {high if high is not None else '—'}‰"
            )
    if c.only_new_listings:
        lines.append("Только новые листинги")
    if c.min_discount_percent is not None:
        lines.append(f"Мин. скидка: {format_percent(c.min_discount_percent)}")
    if kind is FilterKind.MONOCHROME:
        lines.append("Статус: только MONOCHROME (Gift Wiki)")
        if c.monochrome_types:
            lines.append(f"Типы Gift Wiki: {', '.join(c.monochrome_types)}")
        if c.min_monochrome_model_share_percent is not None:
            lines.append(
                f"Мин. доля монохромных моделей: {format_percent(c.min_monochrome_model_share_percent)}"
            )
    return lines or ["Без ограничений"]


def describe_limits(limits: FilterLimits) -> list[str]:
    lines: list[str] = []
    if limits.max_count is not None:
        lines.append(f"Купить штук: {limits.max_count}")
    if limits.max_price_per_gift_nano is not None:
        lines.append(f"Макс. цена подарка: {format_ton(limits.max_price_per_gift_nano)}")
    if limits.max_per_operation_nano is not None:
        lines.append(f"Макс. сумма операции: {format_ton(limits.max_per_operation_nano)}")
    if limits.daily_limit_nano is not None:
        lines.append(f"Бюджет на день: {format_ton(limits.daily_limit_nano)}")
    if limits.total_limit_nano is not None:
        lines.append(f"Бюджет всего: {format_ton(limits.total_limit_nano)}")
    if limits.period_max_count is not None and limits.period_hours is not None:
        lines.append(f"Не больше {limits.period_max_count} покупок за {limits.period_hours} ч")
    return lines or ["Лимиты фильтра не заданы"]
