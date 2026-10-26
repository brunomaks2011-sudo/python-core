"""Listing monitor (polling + dedup + backlog) and on-demand search."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime

import pytest

from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import FilterKind
from gift_sniper.domain.types import FeedEvent
from gift_sniper.integrations.http import AsyncRateLimiter
from gift_sniper.integrations.mrkt import MrktAuthError
from gift_sniper.services.monitor import ListingMonitor
from gift_sniper.services.queue import MemoryQueue
from gift_sniper.services.search import SearchService
from tests.factories import TON, make_listing
from tests.integration.conftest import Env

pytestmark = pytest.mark.db


def ev(event_id: str, gift_id: str = "g1", kind: str = "listing") -> FeedEvent:
    return FeedEvent(event_id, kind, make_listing(gift_id), 10 * TON, datetime.now(UTC))


async def test_first_poll_is_backlog_then_only_new_events(env: Env) -> None:
    queue = MemoryQueue()
    env.mrkt.feed_pages = deque([[ev("e2", "g2"), ev("e1", "g1")], [ev("e3", "g3"), ev("e2", "g2")]])
    monitor = ListingMonitor(env.settings, env.mrkt, queue, env.redis)  # type: ignore[arg-type]
    assert await monitor.poll_once() == 2
    assert [p["backlog"] for p in queue.published] == [True, True]
    assert [p["event_id"] for p in queue.published] == ["e1", "e2"]  # oldest first
    assert await monitor.poll_once() == 1
    assert queue.published[-1]["event_id"] == "e3" and queue.published[-1]["backlog"] is False
    assert monitor.last_success is not None


async def test_poll_interval_chosen_at_runtime_and_the_limiter_follows(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(env.settings, "mrkt_requests_per_second", 2.0)
    env.mrkt.limiter = AsyncRateLimiter(2.0)  # type: ignore[attr-defined]
    monitor = ListingMonitor(env.settings, env.mrkt, MemoryQueue(), env.redis, control=env.control)  # type: ignore[arg-type]
    assert await monitor.interval() == env.settings.mrkt_feed_poll_interval_seconds
    await env.control.set_poll_interval(0.5, by_user=1)
    assert await monitor.interval() == 0.5
    assert env.mrkt.limiter.rate == 3  # type: ignore[attr-defined]  # two feed polls a second and room for more
    with pytest.raises(ValueError):
        await env.control.set_poll_interval(0.1, by_user=1)
    await env.redis.delete(env.control.poll_key)  # Redis flushed: the choice is restored from PostgreSQL
    await env.control.restore()
    assert await env.control.poll_interval() == 0.5


async def test_monitor_keeps_only_tracked_event_types(env: Env) -> None:
    """The feed is requested without a type filter, so the monitor drops the types it does not track."""
    queue = MemoryQueue()
    env.mrkt.feed_pages = deque([[ev("u1", "g9", "upload"), ev("e2", "g2", "change_price"), ev("e1", "g1")]])
    monitor = ListingMonitor(env.settings, env.mrkt, queue, env.redis)  # type: ignore[arg-type]
    assert await monitor.poll_once() == 2
    assert [p["event_id"] for p in queue.published] == ["e1", "e2"]
    # a page holding only untracked types is never "seen": paging continues to the tracked events
    env.mrkt.feed_pages = deque([[ev("u2", "g8", "upload")], [ev("e3", "g3"), ev("e2", "g2")]])
    assert await monitor.poll_once() == 1
    assert queue.published[-1]["event_id"] == "e3"


async def test_monitor_alerts_admins_on_auth_failure(env: Env) -> None:
    async with env.sessionmaker() as session, session.begin():
        await users_repo.ensure_admin(session, 1, can_purchase=True)  # done by Application.build() on start
    queue = MemoryQueue()
    env.mrkt.feed_pages = deque([MrktAuthError("401")])  # type: ignore[list-item]
    monitor = ListingMonitor(env.settings, env.mrkt, queue, env.redis, env.notifier)  # type: ignore[arg-type]
    stop = asyncio.Event()

    async def stop_soon() -> None:
        await asyncio.sleep(0.2)
        stop.set()

    await asyncio.gather(monitor.run(stop), stop_soon())
    assert monitor.last_error == "401"
    assert any("MRKT отклонил авторизацию" in t for t in env.sender.texts_for(1))


async def test_search_filters_locally_and_reports_share(env: Env) -> None:
    await env.add_user(7)
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    fid = await env.add_filter(7, FilterKind.REGULAR, criteria={"max_price_nano": 15 * TON})
    env.mrkt.saling_pages = deque(
        [
            (
                [
                    make_listing("a", model_name="Onyx", backdrop_name="Black", price_nano=5 * TON),
                    make_listing("b", model_name="Ivory", backdrop_name="White", price_nano=8 * TON),
                    make_listing("c", model_name="Onyx", backdrop_name="Black", price_nano=20 * TON),
                ],
                None,
            )
        ]
    )
    async with env.sessionmaker() as session:
        spec = filters_repo.to_spec(await filters_repo.get_filter(session, 7, fid))  # type: ignore[arg-type]
    result = await SearchService(env.mrkt, env.enricher, env.sessionmaker).search(spec)  # type: ignore[arg-type]
    assert result.scanned == 3 and result.matched == 2
    assert [item.gift_id for item, _ in result.items] == ["a", "b"]
    assert result.share is not None and (result.share.numerator, result.share.denominator) == (1, 2)


async def test_monitor_survives_alert_failures(env: Env) -> None:
    """The admin never started the bot: the alert cannot be stored, but the monitor keeps running."""
    queue = MemoryQueue()
    env.mrkt.feed_pages = deque([MrktAuthError("401")])  # type: ignore[list-item]
    monitor = ListingMonitor(env.settings, env.mrkt, queue, env.redis, env.notifier)  # type: ignore[arg-type]
    stop = asyncio.Event()

    async def stop_soon() -> None:
        await asyncio.sleep(0.2)
        stop.set()

    await asyncio.gather(monitor.run(stop), stop_soon())  # must not raise
    assert monitor.last_error == "401"
