"""Plain domain data structures shared by integrations, services and the bot."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from gift_sniper.domain.enums import GiftWikiMonochromeType, MonochromeStatus

_SLUG_RE = re.compile(r"^[A-Za-z0-9]+-\d+$")


@dataclass(frozen=True, slots=True)
class ListingSnapshot:
    """A MRKT gift as returned by the API at `fetched_at`. Missing values stay None (never zero)."""

    gift_id: str  # MRKT id used by gifts/buy
    collection_name: str | None
    collection_title: str | None = None
    name: str | None = None
    number: int | None = None
    model_name: str | None = None
    backdrop_name: str | None = None
    symbol_name: str | None = None
    model_rarity_permille: int | None = None
    backdrop_rarity_permille: int | None = None
    symbol_rarity_permille: int | None = None
    price_nano: int | None = None
    currency: str = "TON"
    is_on_sale: bool | None = None
    is_on_auction: bool | None = None
    is_mine: bool | None = None
    backdrop_center_color: int | None = None
    backdrop_edge_color: int | None = None
    backdrop_text_color: int | None = None
    backdrop_symbol_color: int | None = None
    floor_collection_nano: int | None = None
    floor_model_backdrop_nano: int | None = None
    fetched_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def title(self) -> str:
        base = self.collection_title or self.collection_name or "Подарок"
        return f"{base} #{self.number}" if self.number is not None else base

    @property
    def telegram_slug(self) -> str | None:
        if self.name and _SLUG_RE.match(self.name):
            return self.name
        return None


@dataclass(frozen=True, slots=True)
class FeedEvent:
    event_id: str
    type: str
    listing: ListingSnapshot
    amount_nano: int | None
    date: datetime | None
    source: str = "feed"


@dataclass(frozen=True, slots=True)
class MonochromeRecord:
    """One record of Gift Wiki GET /gifts/monochromes (documented fields only)."""

    record_id: str
    gift_id: str | None
    gift_name: str | None
    model_name: str | None
    backdrop_name: str | None
    type_raw: str | None
    center_color: str | None = None
    edge_color: str | None = None
    pattern_color: str | None = None
    text_color: str | None = None
    photo_url: str | None = None
    animation_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def type(self) -> GiftWikiMonochromeType | None:
        return GiftWikiMonochromeType.parse(self.type_raw)


@dataclass(frozen=True, slots=True)
class MonochromeVerdict:
    status: MonochromeStatus
    reason: str
    gw_type: GiftWikiMonochromeType | None = None
    record_id: str | None = None
    gift_id: str | None = None
    gift_name: str | None = None
    photo_url: str | None = None
    data_as_of: datetime | None = None
    color_check: str = "not_available"  # match | mismatch | not_available | disabled

    @property
    def is_monochrome(self) -> bool:
        return self.status is MonochromeStatus.MONOCHROME


@dataclass(frozen=True, slots=True)
class Share:
    """A percentage with its numerator and denominator. None percent means "Нет данных"."""

    numerator: int
    denominator: int
    note: str = ""
    complete: bool = True
    unknown: int = 0

    @property
    def percent(self) -> float | None:
        if self.denominator <= 0:
            return None
        return self.numerator / self.denominator * 100.0


@dataclass(frozen=True, slots=True)
class Enrichment:
    """Everything the bot knows about a listing beyond the raw MRKT data."""

    verdict: MonochromeVerdict
    model_share: Share | None  # A: monochrome models of the gift (Gift Wiki)
    model_drop_probability: float | None  # B: Gift Wiki published probability (not documented -> None)
    discount_percent: float | None
    discount_reference_nano: int | None
    discount_samples: int
    giftwiki_data_age_hours: float | None
