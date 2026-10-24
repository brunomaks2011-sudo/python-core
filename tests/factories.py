"""Test data builders and fakes (used only by tests, never by the application)."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from gift_sniper.config import Settings
from gift_sniper.domain.enums import MonochromeStatus
from gift_sniper.domain.types import Enrichment, ListingSnapshot, MonochromeVerdict, Share
from gift_sniper.integrations.mrkt import BuyOutcome, BuyOutcomeKind, MrktError
from gift_sniper.services.reference import GiftCoverage, ReferenceSnapshot, RefRecord

TON = 1_000_000_000


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "telegram_bot_token": None,
        "admin_user_ids": [1],
        "allowed_user_ids": [],
        "purchase_user_ids": [],
        "run_mode": "live",
        "database_url": "postgresql+asyncpg://unused/unused",
        "redis_url": "redis://unused",
        "redis_prefix": "test",
        "mrkt_access_token": "test-token",
        "giftwiki_api_key": "gw-key",
        "purchase_verify_delay_seconds": 0.0,
        "purchase_verify_attempts": 4,
        "purchase_max_snapshot_age_seconds": 60.0,
        "mrkt_requests_per_second": 1000.0,
        "mrkt_priority_requests_per_second": 1000.0,
        "giftwiki_requests_per_second": 1000.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def make_listing(gift_id: str = "g1", **overrides: Any) -> ListingSnapshot:
    raw = {
        "id": gift_id,
        "collectionName": overrides.get("collection_name", "Plush Pepe"),
        "collectionTitle": overrides.get("collection_title", "Plush Pepe"),
        "name": overrides.get("name", f"PlushPepe-{overrides.get('number', 100)}"),
        "number": overrides.get("number", 100),
        "modelName": overrides.get("model_name", "Onyx"),
        "backdropName": overrides.get("backdrop_name", "Black"),
        "symbolName": overrides.get("symbol_name", "Star"),
        "modelRarityPerMille": overrides.get("model_rarity_permille", 15),
        "backdropRarityPerMille": overrides.get("backdrop_rarity_permille", 20),
        "symbolRarityPerMille": overrides.get("symbol_rarity_permille", 5),
        "salePrice": overrides.get("price_nano", 10 * TON),
        "isOnSale": overrides.get("is_on_sale", True),
        "isOnAuction": overrides.get("is_on_auction", False),
        "isMine": overrides.get("is_mine", False),
    }
    if "backdrop_center_color" in overrides:
        raw["backdropColorsCenterColor"] = overrides["backdrop_center_color"]
    if "backdrop_edge_color" in overrides:
        raw["backdropColorsEdgeColor"] = overrides["backdrop_edge_color"]
    base = ListingSnapshot(
        gift_id=gift_id,
        collection_name=raw["collectionName"],
        collection_title=raw["collectionTitle"],
        name=raw["name"],
        number=raw["number"],
        model_name=raw["modelName"],
        backdrop_name=raw["backdropName"],
        symbol_name=raw["symbolName"],
        model_rarity_permille=raw["modelRarityPerMille"],
        backdrop_rarity_permille=raw["backdropRarityPerMille"],
        symbol_rarity_permille=raw["symbolRarityPerMille"],
        price_nano=raw["salePrice"],
        is_on_sale=raw["isOnSale"],
        is_on_auction=raw["isOnAuction"],
        is_mine=raw["isMine"],
        backdrop_center_color=overrides.get("backdrop_center_color"),
        backdrop_edge_color=overrides.get("backdrop_edge_color"),
        fetched_at=datetime.now(UTC),
        raw=raw,
    )
    return base


def make_snapshot(
    *,
    records: list[tuple[str, str, str]] | None = None,
    gift_id: str = "gw-pepe",
    gift_name: str = "Plush Pepe",
    complete: bool = True,
    synced_at: datetime | None = None,
    extra_gifts: list[GiftCoverage] | None = None,
    colors: dict[tuple[str, str], tuple[str | None, str | None]] | None = None,
) -> ReferenceSnapshot:
    records = records if records is not None else [("Onyx", "Black", "high")]
    synced_at = synced_at or datetime.now(UTC)
    refs = [
        RefRecord(
            record_id=f"r{i}",
            gift_id=gift_id,
            gift_name=gift_name,
            model_name=model,
            backdrop_name=backdrop,
            type_raw=kind,
            center_color=(colors or {}).get((model, backdrop), (None, None))[0],
            edge_color=(colors or {}).get((model, backdrop), (None, None))[1],
            photo_url=f"https://example.invalid/{i}.png",
        )
        for i, (model, backdrop, kind) in enumerate(records)
    ]
    gifts = [GiftCoverage(gift_id, gift_name, len(refs), complete, synced_at), *(extra_gifts or [])]
    return ReferenceSnapshot.build(gifts, refs, last_success_at=synced_at)


def make_enrichment(
    status: MonochromeStatus = MonochromeStatus.UNKNOWN,
    *,
    share: Share | None = None,
    discount: float | None = None,
    gw_type: Any = None,
    age_hours: float | None = 1.0,
) -> Enrichment:
    return Enrichment(
        verdict=MonochromeVerdict(status, "test", gw_type=gw_type),
        model_share=share,
        model_drop_probability=None,
        discount_percent=discount,
        discount_reference_nano=None,
        discount_samples=0,
        giftwiki_data_age_hours=age_hours,
    )


class FakeMrkt:
    """Scriptable stand-in for MrktClient used in purchase tests."""

    def __init__(self) -> None:
        self.gifts: dict[str, ListingSnapshot] = {}
        self.buy_calls: list[str] = []
        self.buy_outcomes: deque[BuyOutcome] = deque()
        self.get_scripts: dict[str, deque[Any]] = {}
        self.inventory: list[ListingSnapshot] = []
        self.balance: int | None = 10_000 * TON
        self.buy_delay = 0.02
        self.configured = True
        self.can_reauthenticate = False

    def add(self, listing: ListingSnapshot) -> None:
        self.gifts[listing.gift_id] = listing

    async def get_gift(self, gift_id: str, *, priority: bool = True) -> ListingSnapshot | None:
        script = self.get_scripts.get(gift_id)
        if script:
            item = script.popleft()
            if isinstance(item, Exception):
                raise item
            if item is None:
                return None
            return replace(item, fetched_at=datetime.now(UTC))
        gift = self.gifts.get(gift_id)
        return replace(gift, fetched_at=datetime.now(UTC)) if gift else None

    async def buy(self, gift_id: str) -> BuyOutcome:
        self.buy_calls.append(gift_id)
        await asyncio.sleep(self.buy_delay)
        outcome = self.buy_outcomes.popleft() if self.buy_outcomes else None
        if outcome is None:
            outcome = BuyOutcome(BuyOutcomeKind.CONFIRMED, "ok", price_nano=self.gifts[gift_id].price_nano)
        if outcome.kind is BuyOutcomeKind.CONFIRMED and gift_id in self.gifts:
            self.gifts[gift_id] = replace(self.gifts[gift_id], is_on_sale=False, is_mine=True)
        return outcome

    async def balance_nano(self) -> int | None:
        return self.balance

    async def find_in_inventory(self, collection_name: str, number: int) -> list[ListingSnapshot]:
        return [g for g in self.inventory if g.collection_name == collection_name and g.number == number]

    # --- monitor / search
    feed_pages: deque[list[Any]]
    saling_pages: deque[tuple[list[ListingSnapshot], str | None]]

    async def feed(
        self, *, types: list[str], count: int = 20, cursor: str = ""
    ) -> tuple[list[Any], str | None]:
        pages = getattr(self, "feed_pages", deque())
        if not pages:
            return [], None
        page = pages.popleft()
        if isinstance(page, Exception):
            raise page
        return page, ("next" if pages else None)

    async def search_listings(self, query: Any) -> tuple[list[ListingSnapshot], str | None]:
        pages = getattr(self, "saling_pages", deque())
        if not pages:
            return [], None
        return pages.popleft()


class RecordingSender:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send(self, chat_id: int, text: str, keyboard: Any = None) -> bool:
        self.messages.append((chat_id, text))
        return True

    def texts_for(self, chat_id: int) -> list[str]:
        return [t for c, t in self.messages if c == chat_id]


class FailingMrkt(FakeMrkt):
    async def get_gift(self, gift_id: str, *, priority: bool = True) -> ListingSnapshot | None:
        raise MrktError("network down")
