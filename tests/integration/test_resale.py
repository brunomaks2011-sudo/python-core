"""🤖 Resale assistant: valuation from seen sales, purchase decisions, listing after MRKT confirms, sales."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from gift_sniper.config import RunMode
from gift_sniper.db.models import ResalePosition
from gift_sniper.domain.enums import PurchaseMode, PurchaseStatus, ResaleStatus
from gift_sniper.domain.types import FeedEvent
from gift_sniper.integrations.mrkt import MrktError
from gift_sniper.services.filters import ResaleRules
from gift_sniper.services.floors import FloorService
from gift_sniper.services.processor import ListingProcessor
from gift_sniper.services.queue import MemoryQueue
from gift_sniper.services.resale import MAX_LIST_TRIES, ResaleAssistant
from tests.factories import TON, make_listing
from tests.integration.conftest import Env

pytestmark = pytest.mark.db

UID = 601
RULES = ResaleRules().model_dump()  # 0.30 TON profit after 2% fee, 7 days, at least 3 sales


def assistant(env: Env) -> ResaleAssistant:
    helper = ResaleAssistant(
        env.settings,
        env.sessionmaker,
        env.redis,
        env.mrkt,
        FloorService(env.mrkt, ttl=0),
        env.control,
        env.notifier,
    )
    helper.cache_ttl = 0

    async def no_sleep(_: float) -> None:
        return None

    helper.sleep = no_sleep  # type: ignore[assignment]
    env.service.resale = helper
    return helper


def processor(env: Env, queue: MemoryQueue, helper: ResaleAssistant) -> ListingProcessor:
    return ListingProcessor(
        env.settings,
        env.sessionmaker,
        env.enricher,
        env.filter_cache,
        env.notifier,
        queue,
        floors=FloorService(env.mrkt, ttl=0),
        assistant=helper,
    )


def event(event_id: str, kind: str, gift_id: str, price: int, **kw: object) -> FeedEvent:
    listing = make_listing(gift_id, price_nano=price, **kw)  # type: ignore[arg-type]
    return FeedEvent(event_id, kind, listing, price, datetime.now(UTC) - timedelta(seconds=1))


async def sales(
    proc: ListingProcessor, prices: list[float], *, backdrop: str = "Black", start: int = 0
) -> None:
    for i, price in enumerate(prices, start=start):
        sold = event(
            f"sale-{backdrop}-{i}", "sale", f"s-{backdrop}-{i}", int(price * TON), backdrop_name=backdrop
        )
        await proc.process(sold, detected_at=datetime.now(UTC))


async def setup_user(env: Env, **rules: object) -> int:
    await env.add_user(UID)
    return await env.add_filter(UID, name="🤖 ИИ-ассистент", criteria={"resale": RULES | rules})


async def positions(env: Env) -> list[ResalePosition]:
    async with env.sessionmaker() as session:
        return list((await session.execute(select(ResalePosition).order_by(ResalePosition.id))).scalars())


# ------------------------------------------------------------------ valuation
async def test_value_of_the_same_picture_and_the_competitor_cap(env: Env) -> None:
    helper = assistant(env)
    proc = processor(env, MemoryQueue(), helper)
    await sales(proc, [13.0, 13.1, 13.2])
    await sales(proc, [20, 20], backdrop="Red")
    listing = make_listing("g1", price_nano=12 * TON)
    env.mrkt.market = [listing, make_listing("g9", price_nano=13_500_000_000)]  # type: ignore[attr-defined]

    plan = await helper.plan(listing, ResaleRules())
    assert plan.ok and plan.basis == "picture"
    assert (plan.picture_sales, plan.picture_median_nano) == (3, 13_100_000_000)
    assert (plan.model_sales, plan.model_median_nano) == (5, 13_200_000_000)
    assert plan.competitor_nano == 13_500_000_000  # the listing itself is no competitor
    assert (plan.target_nano, plan.list_price_nano, plan.profit_nano) == (
        13_100_000_000,
        12_840_000_000,
        840_000_000,
    )

    # a cheaper copy of the picture on sale: 0.01 TON under it
    env.mrkt.market = [listing, make_listing("g9", price_nano=12_900_000_000)]  # type: ignore[attr-defined]
    plan = await helper.plan(listing, ResaleRules())
    assert plan.ok and plan.target_nano == 12_890_000_000 and plan.list_price_nano == 12_630_000_000

    env.mrkt.market = [listing, make_listing("g9", price_nano=12_300_000_000)]  # type: ignore[attr-defined]
    plan = await helper.plan(listing, ResaleRules())
    assert not plan.ok and plan.profit_nano == 40_000_000 and "меньше 0.3 TON" in plan.reason


async def test_model_median_without_enough_sales_of_the_picture(env: Env) -> None:
    helper = assistant(env)
    proc = processor(env, MemoryQueue(), helper)
    await sales(proc, [15])
    await sales(proc, [14, 14, 16], backdrop="Red")
    env.mrkt.market = []  # type: ignore[attr-defined]
    plan = await helper.plan(make_listing("g1", price_nano=12 * TON), ResaleRules())
    assert plan.basis == "model" and plan.model_median_nano == 14_500_000_000 and plan.ok

    few = await helper.plan(make_listing("g1", price_nano=12 * TON), ResaleRules(min_sales=5))
    assert not few.ok and few.basis is None
    assert "мало продаж за 7 дн.: модель + фон — 1, вся модель — 4, нужно от 5" in few.reason


async def test_unknown_competitors_do_not_buy(env: Env) -> None:
    helper = assistant(env)
    proc = processor(env, MemoryQueue(), helper)
    await sales(proc, [13, 13, 13])

    async def down(query: object, *, priority: bool = False) -> object:
        raise MrktError("down")

    env.mrkt.search_listings = down  # type: ignore[method-assign]
    plan = await helper.plan(make_listing("g1", price_nano=12 * TON), ResaleRules())
    assert not plan.ok and "MRKT не ответил" in plan.reason


# ------------------------------------------------------------------ decisions in the processor
async def test_processor_asks_to_buy_only_with_the_profit(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env)
    queue = MemoryQueue()
    proc = processor(env, queue, helper)
    await sales(proc, [13.0, 13.1, 13.2])
    env.mrkt.market = []  # type: ignore[attr-defined]

    report = await proc.process(event("l1", "listing", "g1", 12 * TON), detected_at=datetime.now(UTC))
    assert filter_id not in report.matched_filters  # the assistant's settings are not a matching rule
    [request] = report.purchase_requests
    assert (request.mode, request.trigger, request.filter_id) == (PurchaseMode.RESALE, "assistant", filter_id)
    plan = await helper.recall(UID, "g1")
    assert plan is not None and plan.list_price_nano == 12_840_000_000 and len(queue.published) == 1

    dear = await proc.process(event("l2", "listing", "g2", 12_700_000_000), detected_at=datetime.now(UTC))
    assert not dear.purchase_requests  # 12.84 − 12.70 = 0.14 TON < 0.30 TON

    own = await proc.process(
        event("l3", "listing", "g3", 5 * TON, is_mine=True), detected_at=datetime.now(UTC)
    )
    assert own.skipped == "own listing" and not own.purchase_requests


async def test_assistant_respects_its_own_bounds(env: Env) -> None:
    helper = assistant(env)
    await env.add_user(UID)
    await env.add_filter(UID, criteria={"resale": RULES, "collections": ["Lol Pop"]})
    proc = processor(env, MemoryQueue(), helper)
    await sales(proc, [13, 13, 13])
    env.mrkt.market = []  # type: ignore[attr-defined]
    report = await proc.process(event("l1", "listing", "g1", 12 * TON), detected_at=datetime.now(UTC))
    assert not report.purchase_requests  # Plush Pepe is not among the assistant's collections


# ------------------------------------------------------------------ purchase and listing
async def bought(
    env: Env, helper: ResaleAssistant, filter_id: int, price: int = 12 * TON
) -> PurchaseStatus | None:
    listing = make_listing("g1", price_nano=price)
    env.mrkt.add(listing)
    env.mrkt.market = [listing]  # type: ignore[attr-defined]
    proc = processor(env, MemoryQueue(), helper)
    await sales(proc, [13.0, 13.1, 13.2])
    plan = await helper.plan(listing, ResaleRules())
    await helper.remember(UID, plan)
    request = env.request(
        UID, "g1", price, filter_id=filter_id, mode=PurchaseMode.RESALE, trigger="assistant"
    )
    result = await env.service.execute(request)
    return result.status


async def test_live_purchase_is_listed_after_mrkt_confirms_it(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env)
    assert await bought(env, helper, filter_id) is PurchaseStatus.CONFIRMED
    assert env.mrkt.sale_calls == [("g1", 12_840_000_000)]
    [position] = await positions(env)
    assert position.status == ResaleStatus.LISTED.value and position.run_mode == "live"
    assert (position.buy_price_nano, position.list_price_nano, position.expected_profit_nano) == (
        12 * TON,
        12_840_000_000,
        840_000_000,
    )
    assert position.target_price_nano == 13_096_800_000  # what MRKT shows buyers
    texts = env.sender.texts_for(UID)
    confirmed = next(t for t in texts if "Покупка подтверждена" in t)
    assert "Выставить за 12.84 TON" in confirmed and "Профит: 0.84 TON" in confirmed
    listed = next(t for t in texts if "выставлен на продажу" in t)
    assert "13.0968 TON для покупателей, вам 12.84 TON" in listed and "профит 0.84 TON" in listed


async def test_test_mode_records_what_would_be_listed(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env)
    await env.control.set_run_mode(RunMode.DRY_RUN, by_user=None)
    assert await bought(env, helper, filter_id) is PurchaseStatus.DRY_RUN
    assert env.mrkt.sale_calls == [] and env.mrkt.buy_calls == []
    [position] = await positions(env)
    assert position.status == ResaleStatus.DRY_RUN.value and "был бы выставлен за 12.84 TON" in (
        position.reason or ""
    )
    dry = next(t for t in env.sender.texts_for(UID) if "Тестовый режим" in t)
    assert "Выставить за 12.84 TON" in dry


async def test_a_higher_fresh_price_or_no_plan_cancels(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env)
    listing = make_listing("g1", price_nano=12 * TON)
    env.mrkt.market = [listing]  # type: ignore[attr-defined]
    proc = processor(env, MemoryQueue(), helper)
    await sales(proc, [13.0, 13.1, 13.2])
    await helper.remember(UID, await helper.plan(listing, ResaleRules()))
    env.mrkt.add(replace(listing, price_nano=12_700_000_000))  # the price went up meanwhile
    req = env.request(UID, "g1", 12 * TON, filter_id=filter_id, mode=PurchaseMode.RESALE, trigger="assistant")
    result = await env.service.execute(req)
    assert result.status is PurchaseStatus.CANCELLED and "Профит при цене 12.7 TON: 0.14 TON" in result.reason
    assert env.mrkt.buy_calls == []

    other = env.request(
        UID, "g2", 12 * TON, filter_id=filter_id, mode=PurchaseMode.RESALE, trigger="assistant"
    )
    env.mrkt.add(make_listing("g2", price_nano=12 * TON))
    result = await env.service.execute(other)
    assert result.status is PurchaseStatus.CANCELLED and "Оценка ассистента устарела" in result.reason

    regular = env.request(UID, "g2", 12 * TON, filter_id=filter_id, mode=PurchaseMode.REGULAR)
    result = await env.service.execute(regular)
    assert result.status is None and "только через ассистента" in result.reason


async def test_listing_waits_for_mrkts_resale_date(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env)
    later = datetime.now(UTC) + timedelta(hours=3)
    original_buy = env.mrkt.buy

    async def buy_locked(gift_id: str):  # type: ignore[no-untyped-def]
        outcome = await original_buy(gift_id)
        env.mrkt.gifts[gift_id] = replace(env.mrkt.gifts[gift_id], next_resale_at=later)
        return outcome

    env.mrkt.buy = buy_locked  # type: ignore[method-assign]
    assert await bought(env, helper, filter_id) is PurchaseStatus.CONFIRMED
    [position] = await positions(env)
    assert position.status == ResaleStatus.WAITING.value and position.resale_at == later
    assert env.mrkt.sale_calls == []
    assert any("MRKT разрешит выставить подарок" in t for t in env.sender.texts_for(UID))

    assert await helper.relist_due() == 0  # not yet
    env.mrkt.gifts["g1"] = replace(env.mrkt.gifts["g1"], next_resale_at=None)
    async with env.sessionmaker() as session, session.begin():
        await session.execute(
            update(ResalePosition).values(resale_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    assert await helper.relist_due() == 1
    [position] = await positions(env)
    assert position.status == ResaleStatus.LISTED.value


async def test_failed_listing_is_retried_with_pauses_and_then_given_up(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env)
    env.mrkt.sale_outcomes.extend([MrktError("HTTP 400"), MrktError("HTTP 400")])
    assert await bought(env, helper, filter_id) is PurchaseStatus.CONFIRMED
    [position] = await positions(env)
    assert position.status == ResaleStatus.FAILED.value and position.tries == 1
    assert "Бот попробует ещё раз" in (position.reason or "")
    assert await helper.relist_due() == 0  # within the pause

    async def rewind() -> None:
        async with env.sessionmaker() as session, session.begin():
            await session.execute(
                update(ResalePosition).values(updated_at=datetime.now(UTC) - timedelta(hours=2))
            )

    await rewind()
    assert await helper.relist_due() == 1
    [position] = await positions(env)
    assert position.status == ResaleStatus.FAILED.value and position.tries == 2
    await rewind()
    assert await helper.relist_due() == 1
    [position] = await positions(env)
    assert position.status == ResaleStatus.LISTED.value
    failures = [t for t in env.sender.texts_for(UID) if "Не удалось выставить" in t]
    assert len(failures) == 1  # the first failure is reported, not every retry

    async with env.sessionmaker() as session, session.begin():
        await session.execute(
            update(ResalePosition).values(status=ResaleStatus.FAILED.value, tries=MAX_LIST_TRIES)
        )
    await rewind()
    assert await helper.relist_due() == 0  # no tries left


async def test_without_auto_listing_the_gift_waits_for_the_owner(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env, auto_list=False)
    assert await bought(env, helper, filter_id) is PurchaseStatus.CONFIRMED
    [position] = await positions(env)
    assert position.status == ResaleStatus.BOUGHT.value and "Автовыставление выключено" in (
        position.reason or ""
    )
    assert env.mrkt.sale_calls == []
    result = await helper.list_position(position.id, user_id=UID)  # the Mini App button
    assert result.status == ResaleStatus.LISTED.value and env.mrkt.sale_calls == [("g1", 12_840_000_000)]
    assert (await helper.list_position(position.id, user_id=UID)).text == "Подарок уже выставлен или продан"
    assert (await helper.list_position(position.id, user_id=999)).status == "missing"


async def test_sale_of_a_listed_gift_is_reported_after_mrkt_shows_it_left(env: Env) -> None:
    helper = assistant(env)
    filter_id = await setup_user(env)
    assert await bought(env, helper, filter_id) is PurchaseStatus.CONFIRMED
    proc = processor(env, MemoryQueue(), helper)

    # the feed reporting the account's own purchase: still the account's gift, not a sale
    await proc.process(event("buy-g1", "sale", "g1", 12 * TON, is_mine=True), detected_at=datetime.now(UTC))
    await proc.process(event("echo-g1", "sale", "g1", 12 * TON), detected_at=datetime.now(UTC))
    [position] = await positions(env)
    assert position.status == ResaleStatus.LISTED.value  # MRKT still shows the gift as the account's

    env.mrkt.gifts["g1"] = replace(env.mrkt.gifts["g1"], is_mine=False, is_on_sale=False)
    await proc.process(event("sold-g1", "sale", "g1", 13_096_800_000), detected_at=datetime.now(UTC))
    [position] = await positions(env)
    assert position.status == ResaleStatus.SOLD.value and position.sold_price_nano == 13_096_800_000
    sold = next(t for t in env.sender.texts_for(UID) if "продан" in t and "MRKT сообщил" in t)
    assert "Покупатель заплатил: 13.0968 TON" in sold and "профит 0.84 TON" in sold
