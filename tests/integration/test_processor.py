"""Listing processing: storage, dedup, filter evaluation, purchase decisions, notifications."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from gift_sniper.db.models import FeedEventLog, FilterHit, Gift, Listing, PriceHistory
from gift_sniper.domain.enums import FilterKind, PurchaseMode
from gift_sniper.domain.types import FeedEvent
from gift_sniper.services.processor import ListingProcessor, event_to_payload, payload_to_event
from gift_sniper.services.queue import MemoryQueue
from tests.factories import TON, make_listing
from tests.integration.conftest import Env

pytestmark = pytest.mark.db

UID = 501


def event(
    event_id: str, kind: str = "listing", *, gift_id: str = "g1", price: int = 10 * TON, **kw: object
) -> FeedEvent:
    listing = make_listing(gift_id, price_nano=price, **kw)  # type: ignore[arg-type]
    return FeedEvent(
        event_id=event_id,
        type=kind,
        listing=listing,
        amount_nano=price,
        date=datetime.now(UTC) - timedelta(seconds=1),
    )


def processor(env: Env, queue: MemoryQueue) -> ListingProcessor:
    return ListingProcessor(
        env.settings, env.sessionmaker, env.enricher, env.filter_cache, env.notifier, queue
    )


async def count(env: Env, model: type) -> int:
    async with env.sessionmaker() as session:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_new_listing_matches_filter_publishes_purchase_and_notifies(env: Env) -> None:
    await env.add_user(UID)
    fid = await env.add_filter(UID, name="cheap pepe", criteria={"max_price_nano": 20 * TON})
    queue = MemoryQueue()
    report = await processor(env, queue).process(event("e1"), detected_at=datetime.now(UTC))
    assert report.matched_filters == [fid]
    assert len(queue.published) == 1
    request = queue.published[0]
    assert (request["gift_id"], request["filter_id"], request["mode"]) == ("g1", fid, "regular")
    texts = env.sender.texts_for(UID)
    assert len(texts) == 1
    assert "Новый листинг" in texts[0] and "cheap pepe" in texts[0] and "10 TON" in texts[0]
    # compact: no source lines and no rows of missing values
    assert "Источник" not in texts[0] and "MRKT" not in texts[0] and "Нет данных" not in texts[0]
    assert "Монохром" not in texts[0]  # no Gift Wiki data loaded: nothing to claim
    # the title links to the gift in Telegram, and the notification shows the gift card
    assert '<a href="https://t.me/nft/PlushPepe-100">Plush Pepe #100</a>' in texts[0]
    assert env.sender.previews == ["https://t.me/nft/PlushPepe-100"]
    # buying comes first; without a known gift link there is no button that would open only the market
    rows = env.sender.keyboards[0].inline_keyboard
    assert rows[0][0].text == "🛒 Купить" and rows[0][0].callback_data.startswith("mb:")
    assert rows[0][1].url == "https://t.me/nft/PlushPepe-100"
    assert [b.text for b in rows[1]] == ["Подробнее"]
    assert await count(env, Listing) == 1 and await count(env, Gift) == 1
    assert await count(env, FilterHit) == 1 and await count(env, PriceHistory) == 1


async def test_duplicate_event_is_processed_once(env: Env) -> None:
    await env.add_user(UID)
    await env.add_filter(UID)
    queue = MemoryQueue()
    proc = processor(env, queue)
    await proc.process(event("e1"), detected_at=datetime.now(UTC))
    again = await proc.process(event("e1"), detected_at=datetime.now(UTC))
    assert again.duplicate
    assert len(queue.published) == 1 and len(env.sender.texts_for(UID)) == 1
    assert await count(env, FeedEventLog) == 1


async def test_backlog_is_stored_but_not_acted_upon(env: Env) -> None:
    await env.add_user(UID)
    await env.add_filter(UID)
    queue = MemoryQueue()
    report = await processor(env, queue).process(event("old"), detected_at=datetime.now(UTC), backlog=True)
    assert report.skipped == "backlog"
    assert queue.published == [] and env.sender.messages == []
    assert await count(env, Listing) == 1


async def test_same_listing_seen_again_without_change_is_not_renotified(env: Env) -> None:
    await env.add_user(UID)
    await env.add_filter(UID)
    queue = MemoryQueue()
    proc = processor(env, queue)
    await proc.process(event("e1"), detected_at=datetime.now(UTC))
    report = await proc.process(event("e2", "observed"), detected_at=datetime.now(UTC))
    assert report.skipped == "no material change"
    assert len(env.sender.texts_for(UID)) == 1


async def test_price_drop_notification_and_only_new_filters(env: Env) -> None:
    await env.add_user(UID, notify={"price_drops": True, "no_repeats": False, "price_drop_min_percent": 5})
    only_new = await env.add_filter(UID, name="new only", criteria={"only_new_listings": True})
    watcher = await env.add_filter(UID, name="watch", autobuy=False)
    queue = MemoryQueue()
    proc = processor(env, queue)
    await proc.process(event("e1", price=10 * TON), detected_at=datetime.now(UTC))
    queue.published.clear()
    report = await proc.process(event("e2", "change_price", price=8 * TON), detected_at=datetime.now(UTC))
    assert only_new not in report.matched_filters  # a price change is not a new listing
    assert watcher in report.matched_filters
    assert queue.published == []  # the only autobuy filter requires new listings
    texts = env.sender.texts_for(UID)
    assert len(texts) == 2 and "Цена снижена" in texts[1] and "−20.0%" in texts[1] and "8 TON" in texts[1]
    # a small change below the threshold is not notified
    await proc.process(event("e3", "change_price", price=int(7.8 * TON)), detected_at=datetime.now(UTC))
    assert len(env.sender.texts_for(UID)) == 2


async def test_sale_closes_listing(env: Env) -> None:
    await env.add_user(UID)
    queue = MemoryQueue()
    proc = processor(env, queue)
    await proc.process(event("e1"), detected_at=datetime.now(UTC))
    await proc.process(event("e2", "sale"), detected_at=datetime.now(UTC))
    async with env.sessionmaker() as session:
        listing = (await session.execute(select(Listing))).scalar_one()
    assert listing.status == "sold" and listing.closed_at is not None


async def test_monochrome_listing_goes_to_monochrome_mode(env: Env) -> None:
    await env.add_user(UID)
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high"), ("Ivory", "White", "low")])
    reg = await env.add_filter(UID, name="regular")
    mono = await env.add_filter(UID, FilterKind.MONOCHROME, name="mono")
    queue = MemoryQueue()
    proc = processor(env, queue)
    report = await proc.process(
        event("e1", model_name="Onyx", backdrop_name="Black"), detected_at=datetime.now(UTC)
    )
    assert set(report.matched_filters) == {reg, mono}
    assert queue.published[-1]["mode"] == PurchaseMode.MONOCHROME.value
    assert queue.published[-1]["filter_id"] == mono
    assert report.enrichment is not None and report.enrichment.verdict.status.value == "MONOCHROME"
    texts = env.sender.texts_for(UID)
    assert "⚫ <b>Монохром</b> · high" in texts[-1] and "Монохромных моделей: 2 из 2 — 100%" in texts[-1]
    assert "Источник" not in texts[-1] and "Gift Wiki" not in texts[-1]
    # the same pair with another backdrop matches only the regular filter
    report2 = await proc.process(
        event("e2", gift_id="g2", model_name="Onyx", backdrop_name="Ivory"), detected_at=datetime.now(UTC)
    )
    assert report2.matched_filters == [reg]
    assert queue.published[-1]["mode"] == "regular"


async def test_unknown_listing_never_reaches_monochrome_mode(env: Env) -> None:
    await env.add_user(UID)
    await env.add_filter(UID, FilterKind.MONOCHROME, name="mono")
    queue = MemoryQueue()
    report = await processor(env, queue).process(event("e1"), detected_at=datetime.now(UTC))
    assert report.matched_filters == [] and queue.published == []


async def test_disabled_toggles_and_rights_prevent_purchase_requests(env: Env) -> None:
    await env.add_user(UID, autobuy=False)
    await env.add_filter(UID)
    await env.add_user(777, can_purchase=False)
    await env.add_filter(777)
    queue = MemoryQueue()
    report = await processor(env, queue).process(event("e1"), detected_at=datetime.now(UTC))
    assert len(report.matched_filters) == 2
    assert queue.published == []


async def test_all_listings_mode_notifies_without_filters(env: Env) -> None:
    await env.add_user(UID, notify={"all_listings": True, "max_price_nano": 50 * TON})
    queue = MemoryQueue()
    await processor(env, queue).process(event("e1"), detected_at=datetime.now(UTC))
    texts = env.sender.texts_for(UID)
    assert texts and "Не подходит под ваши фильтры" in texts[0]


async def test_listing_link_template_adds_open_in_mrkt(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        env.settings, "mrkt_listing_url_template", "https://t.me/mrkt/app?startapp={gift_id_hex}"
    )
    await env.add_user(UID)
    await env.add_filter(UID)
    await processor(env, MemoryQueue()).process(event("e1", gift_id="ab-12"), detected_at=datetime.now(UTC))
    rows = env.sender.keyboards[0].inline_keyboard
    assert rows[1][1].text == "Открыть в MRKT" and rows[1][1].url == "https://t.me/mrkt/app?startapp=ab12"


def test_payload_roundtrip() -> None:
    original = event("e9")
    payload = event_to_payload(original, detected_at=datetime.now(UTC), backlog=False)
    restored, detected, backlog = payload_to_event(payload)
    assert restored is not None and not backlog
    assert (restored.event_id, restored.type, restored.amount_nano) == ("e9", "listing", 10 * TON)
    assert restored.listing.gift_id == "g1" and restored.listing.model_name == "Onyx"
    assert detected.tzinfo is not None
