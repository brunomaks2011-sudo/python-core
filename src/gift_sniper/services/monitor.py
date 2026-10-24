"""MRKT listing monitor.

MRKT has no documented WebSocket/stream API, so the monitor polls the documented `POST /feed`
(or `POST /gifts/saling` sorted by listing time as a fallback) within the configured rate limit.
New events are deduplicated in Redis (SET NX) and in PostgreSQL (feed_events primary key) and
published to the processing queue. The first poll after start is published as backlog: stored,
but never notified or bought, so a restart does not replay old listings as "new".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime

from redis.asyncio import Redis

from gift_sniper.config import MonitorSource, Settings
from gift_sniper.domain.enums import FeedEventType
from gift_sniper.domain.types import FeedEvent
from gift_sniper.integrations.mrkt import MrktAuthError, MrktClient, MrktError, SalingQuery
from gift_sniper.metrics import DETECTION_LATENCY, EVENTS_SEEN, MONITOR_LAST_POLL
from gift_sniper.services.notifications import Notifier
from gift_sniper.services.processor import Publisher, event_to_payload

log = logging.getLogger(__name__)

FEED_TYPES = frozenset(
    {
        FeedEventType.LISTING.value,
        FeedEventType.CHANGE_PRICE.value,
        FeedEventType.SALE.value,
        FeedEventType.UNLISTING.value,
    }
)


class ListingMonitor:
    def __init__(
        self,
        settings: Settings,
        mrkt: MrktClient,
        queue: Publisher,
        redis: Redis,
        notifier: Notifier | None = None,
    ) -> None:
        self.settings = settings
        self.mrkt = mrkt
        self.queue = queue
        self.redis = redis
        self.notifier = notifier
        self.seen_prefix = f"{settings.redis_prefix}:seen:"
        self.first_poll = True
        self.last_success: float | None = None
        self.last_error: str | None = None

    async def _is_new(self, event_id: str) -> bool:
        return bool(await self.redis.set(self.seen_prefix + event_id, "1", nx=True, ex=3 * 24 * 3600))

    async def poll_feed(self) -> list[FeedEvent]:
        events: list[FeedEvent] = []
        cursor = ""
        for _ in range(max(1, self.settings.mrkt_feed_max_pages)):
            page, cursor_next = await self.mrkt.feed(count=self.settings.mrkt_feed_page_size, cursor=cursor)
            events.extend(e for e in page if e.type in FEED_TYPES)  # the feed holds every event type
            if not page or not cursor_next or self.first_poll:
                break
            # keep paging only while the whole page is unseen (we may have missed events); other event
            # types are never marked as seen, so a page of only those keeps paging up to the limit
            if await self.redis.exists(*[self.seen_prefix + e.event_id for e in page]):
                break
            cursor = cursor_next
        return events

    async def poll_saling(self) -> list[FeedEvent]:
        listings, _ = await self.mrkt.search_listings(
            SalingQuery(ordering="None", low_to_high=False, count=20)
        )
        return [
            FeedEvent(
                event_id=f"saling:{item.gift_id}:{item.price_nano}",
                type=FeedEventType.OBSERVED.value,
                listing=item,
                amount_nano=item.price_nano,
                date=None,
                source="saling",
            )
            for item in listings
        ]

    async def poll_once(self) -> int:
        if self.settings.mrkt_monitor_source is MonitorSource.SALING:
            events = await self.poll_saling()
        else:
            events = await self.poll_feed()
        detected_at = datetime.now(UTC)
        backlog = self.first_poll
        published = 0
        for event in reversed(events):  # oldest first
            is_new = await self._is_new(event.event_id)
            EVENTS_SEEN.labels(event.type, str(is_new).lower()).inc()
            if not is_new:
                continue
            if event.date is not None and not backlog:
                DETECTION_LATENCY.observe(max(0.0, (detected_at - event.date).total_seconds()))
            await self.queue.publish(event_to_payload(event, detected_at=detected_at, backlog=backlog))
            published += 1
        self.first_poll = False
        self.last_success = time.time()
        MONITOR_LAST_POLL.set(self.last_success)
        return published

    async def run(self, stop: asyncio.Event) -> None:
        interval = self.settings.mrkt_feed_poll_interval_seconds
        failures = 0
        log.info("listing monitor started", extra={"source": self.settings.mrkt_monitor_source.value})
        while not stop.is_set():
            started = time.monotonic()
            try:
                await self.poll_once()
                failures = 0
                self.last_error = None
            except MrktAuthError as exc:
                self.last_error = str(exc)
                log.error("MRKT authorization failed", extra={"error": str(exc)})
                if self.notifier is not None:
                    hour = datetime.now(UTC).strftime("%Y%m%d%H")
                    if self.mrkt.can_reauthenticate:
                        hint = "Бот повторит авторизацию через сохранённую Telegram-сессию через минуту."
                    else:
                        hint = (
                            "Обновите MRKT_ACCESS_TOKEN или выполните `python -m gift_sniper mrkt-login` "
                            "и перезапустите бота."
                        )
                    await self.notifier.admins(
                        f"🔐 MRKT отклонил авторизацию: {exc}\n{hint}", dedup_key=f"mrkt-auth:{hour}"
                    )
                await self._sleep(stop, 60)
                continue
            except MrktError as exc:
                failures += 1
                self.last_error = str(exc)
                delay = min(60.0, interval * (2 ** min(failures, 5)))
                log.warning("MRKT poll failed", extra={"error": str(exc), "retry_in": delay})
                await self._sleep(stop, delay)
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures += 1
                self.last_error = str(exc)
                log.exception("unexpected monitor error")
                await self._sleep(stop, min(60.0, interval * (2 ** min(failures, 5))))
                continue
            await self._sleep(stop, max(0.0, interval - (time.monotonic() - started)))

    @staticmethod
    async def _sleep(stop: asyncio.Event, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=seconds)
