"""Persistence across restarts, statistics, notification dedup and rate limits, Redis primitives."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import purchases as purchases_repo
from gift_sniper.domain.enums import PurchaseRunMode
from gift_sniper.services.locks import RedisLock
from gift_sniper.services.queue import StreamQueue
from gift_sniper.services.stats import StatsService
from tests.factories import TON, make_listing
from tests.integration.conftest import Env

pytestmark = pytest.mark.db

UID = 900


async def test_history_and_statistics_survive_restart(env: Env, migrated_database: str) -> None:
    await env.add_user(UID)
    env.mrkt.add(make_listing("g1", price_nano=10 * TON))
    fid = await env.add_filter(UID, name="persist")
    await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    # "restart": a brand-new engine and session factory, nothing kept in memory
    engine = create_async_engine(migrated_database)
    try:
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        stats = await StatsService(sessionmaker, env.store).user(user_id=UID)
        async with sessionmaker() as session:
            attempts = await purchases_repo.list_attempts(session, UID)
            filters = await filters_repo.list_filters(session, UID)
            usage = await purchases_repo.usage(
                session,
                user_id=UID,
                run_mode=PurchaseRunMode.LIVE,
                day_start=datetime(2000, 1, 1, tzinfo=UTC),
            )
    finally:
        await engine.dispose()
    assert stats.confirmed == 1 and stats.spent_nano == 10 * TON
    assert [a.status for a in attempts] == ["confirmed"]
    assert filters[0].name == "persist"
    assert usage.total_spent == 10 * TON
    assert stats.filters[0].confirmed == 1


async def test_market_stats_have_period_and_formulas(env: Env) -> None:
    await env.add_user(UID)
    stats = await StatsService(env.sessionmaker, env.store).market(user_id=UID, period_hours=24)
    assert stats.period_end > stats.period_start
    assert stats.new_listings == 0 and stats.listing_share is None and stats.median_price_nano is None


async def test_notification_dedup(env: Env) -> None:
    await env.add_user(UID)
    first = await env.notifier.send(UID, "hello", kind="listing", dedup_key="listing:L1")
    second = await env.notifier.send(UID, "hello again", kind="listing", dedup_key="listing:L1")
    assert first and not second
    assert env.sender.texts_for(UID) == ["hello"]


async def test_notification_rate_limit_spares_critical_messages(env: Env) -> None:
    await env.add_user(UID)
    for i in range(5):
        await env.notifier.send(UID, f"m{i}", kind="listing", max_per_minute=2)
    await env.notifier.send(UID, "purchase", kind="purchase", critical=True, max_per_minute=2)
    texts = env.sender.texts_for(UID)
    assert texts[:2] == ["m0", "m1"]
    assert sum("лимит уведомлений" in t for t in texts) == 1  # a single notice about suppression
    assert texts[-1] == "purchase"
    assert not any(t in ("m2", "m3", "m4") for t in texts)


async def test_redis_lock_is_exclusive_and_owner_safe(env: Env) -> None:
    a = RedisLock(env.redis, "test:lock", 5)
    b = RedisLock(env.redis, "test:lock", 5)
    assert await a.acquire()
    assert not await b.acquire()
    await b.release()  # not the owner: must not release a's lock
    assert not await RedisLock(env.redis, "test:lock", 5).acquire()
    await a.release()
    assert await b.acquire()
    await b.release()


async def test_stream_queue_delivers_and_acknowledges(env: Env) -> None:
    queue = StreamQueue(env.redis, "test:stream", "workers", claim_idle_ms=10)
    await queue.ensure_group()
    await queue.publish({"n": 1})
    await queue.publish({"n": 2})
    received: list[int] = []
    stop = asyncio.Event()

    async def handler(payload: dict) -> None:
        received.append(payload["n"])
        if len(received) == 2:
            stop.set()

    await asyncio.wait_for(queue.consume(handler, stop=stop, block_ms=100), timeout=5)
    assert received == [1, 2]
    assert await queue.backlog() == 0


async def test_stream_queue_redelivers_failed_messages(env: Env) -> None:
    queue = StreamQueue(env.redis, "test:retry", "workers", claim_idle_ms=1, max_deliveries=5)
    await queue.ensure_group()
    await queue.publish({"n": 1})
    attempts: list[int] = []
    stop = asyncio.Event()

    async def flaky(payload: dict) -> None:
        attempts.append(payload["n"])
        if len(attempts) == 1:
            raise RuntimeError("temporary failure")
        stop.set()

    await asyncio.wait_for(queue.consume(flaky, stop=stop, block_ms=50), timeout=5)
    assert attempts == [1, 1]
