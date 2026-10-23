"""Composition root: builds every component and runs the selected ones as asyncio tasks."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import delete, text

from gift_sniper.config import Settings
from gift_sniper.db.models import FeedEventLog
from gift_sniper.db.repo import giftwiki as giftwiki_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.db.session import create_engine, create_sessionmaker
from gift_sniper.integrations.giftwiki import GiftWikiClient
from gift_sniper.integrations.mrkt import MrktClient, MrktError
from gift_sniper.metrics import QUEUE_BACKLOG, start_http_server
from gift_sniper.services.container import Services
from gift_sniper.services.control import ControlService
from gift_sniper.services.enrichment import Enricher, ReferenceStore
from gift_sniper.services.filter_cache import FilterCache
from gift_sniper.services.giftwiki_sync import GiftWikiSync
from gift_sniper.services.monitor import ListingMonitor
from gift_sniper.services.notifications import MessageSender, Notifier, TelegramSender
from gift_sniper.services.processor import ListingProcessor
from gift_sniper.services.purchase import PurchaseRequest, PurchaseService
from gift_sniper.services.queue import StreamQueue
from gift_sniper.services.search import SearchService
from gift_sniper.services.stats import StatsService

log = logging.getLogger(__name__)

ALL_COMPONENTS = {"bot", "monitor", "processor", "buyer", "scheduler", "metrics"}


class NullSender:
    """Used when TELEGRAM_BOT_TOKEN is not set (e.g. a worker-only process): logs instead of sending."""

    async def send(self, chat_id: int, text: str, keyboard: Any = None) -> bool:
        log.info("notification (no bot configured)", extra={"chat_id": chat_id, "text": text[:200]})
        return True


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stop = asyncio.Event()
        self.tasks: list[asyncio.Task[Any]] = []
        self.bot: Any = None
        self.services: Services | None = None
        self._http_runner: Any = None

    async def build(self) -> Services:
        s = self.settings
        engine = create_engine(s.database_url)
        sessionmaker = create_sessionmaker(engine)
        self._engine = engine
        redis = Redis.from_url(s.redis_url)
        await redis.ping()
        mrkt = MrktClient(s)
        await mrkt.start()
        giftwiki = GiftWikiClient(s)
        await giftwiki.start()

        sender: MessageSender = NullSender()
        if s.telegram_bot_token:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode

            self.bot = Bot(
                s.telegram_bot_token.get_secret_value(),
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            sender = TelegramSender(self.bot, s.telegram_global_messages_per_second)

        async with sessionmaker() as session, session.begin():
            for admin_id in s.admin_user_ids:  # admins receive alerts before they ever press /start
                await users_repo.ensure_admin(session, admin_id, can_purchase=s.can_purchase(admin_id))
        control = ControlService(s, redis, sessionmaker)
        await control.restore()
        store = ReferenceStore(sessionmaker, redis, s.redis_prefix)
        await store.reload()
        enricher = Enricher(s, store, sessionmaker)
        filter_cache = FilterCache(sessionmaker, redis, s.redis_prefix)
        notifier = Notifier(s, sender, sessionmaker, redis)
        purchase = PurchaseService(s, sessionmaker, redis, mrkt, control, enricher, notifier)
        events_queue = StreamQueue(redis, f"{s.redis_prefix}:events", "processors")
        purchase_queue = StreamQueue(redis, f"{s.redis_prefix}:purchases", "buyers", max_deliveries=3)
        monitor = ListingMonitor(s, mrkt, events_queue, redis, notifier) if mrkt.configured else None
        sync = GiftWikiSync(s, giftwiki, sessionmaker, redis, store, enricher)
        self.services = Services(
            settings=s,
            sessionmaker=sessionmaker,
            redis=redis,
            mrkt=mrkt,
            giftwiki=giftwiki,
            control=control,
            store=store,
            enricher=enricher,
            filter_cache=filter_cache,
            notifier=notifier,
            purchase=purchase,
            search=SearchService(mrkt, enricher, sessionmaker),
            stats=StatsService(sessionmaker, store),
            sync=sync,
            monitor=monitor,
            purchase_queue=purchase_queue,
            events_queue=events_queue,
        )
        self.processor = ListingProcessor(s, sessionmaker, enricher, filter_cache, notifier, purchase_queue)
        return self.services

    # ------------------------------------------------------------------ background loops
    async def _every(
        self, seconds: float, func: Callable[[], Awaitable[Any]], name: str, *, initial: float = 0
    ) -> None:
        await self._sleep(initial)
        while not self.stop.is_set():
            try:
                await func()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("periodic job failed", extra={"job": name})
            await self._sleep(seconds)

    async def _once(self, func: Callable[[], Awaitable[Any]], name: str) -> None:
        try:
            await func()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("startup job failed", extra={"job": name})

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)

    async def _giftwiki_job(self) -> None:
        assert self.services is not None
        await self.services.sync.run(trigger="schedule")

    async def _giftwiki_initial(self) -> None:
        """Sync on start only when the stored data is older than the sync interval."""
        assert self.services is not None
        async with self.services.sessionmaker() as session:
            success = await giftwiki_repo.last_success(session)
        interval = timedelta(minutes=self.settings.giftwiki_sync_interval_minutes)
        if (
            success is None
            or success.finished_at is None
            or datetime.now(UTC) - success.finished_at > interval
        ):
            await self.services.sync.run(trigger="startup")

    async def _collections_job(self) -> None:
        assert self.services is not None
        if not self.services.mrkt.configured:
            return
        try:
            items = await self.services.mrkt.collections()
        except MrktError as exc:
            log.warning("MRKT collections refresh failed", extra={"error": str(exc)})
            return
        async with self.services.sessionmaker() as session, session.begin():
            await listings_repo.upsert_collections(
                session, [(c.name, c.title, c.floor_price_nano) for c in items]
            )

    async def _cleanup_job(self) -> None:
        assert self.services is not None
        cutoff = datetime.now(UTC) - timedelta(days=30)
        async with self.services.sessionmaker() as session, session.begin():
            await session.execute(delete(FeedEventLog).where(FeedEventLog.received_at < cutoff))

    async def _queue_metrics(self) -> None:
        assert self.services is not None
        for queue in (self.services.events_queue, self.services.purchase_queue):
            QUEUE_BACKLOG.labels(queue.stream).set(await queue.backlog())

    async def _buy(self, payload: dict[str, Any]) -> None:
        assert self.services is not None
        request = PurchaseRequest.from_payload(payload)
        result = await self.services.purchase.execute(request)
        log.info(
            "purchase request processed",
            extra={
                "gift_id": request.gift_id,
                "status": result.status.value if result.status else None,
                "reason": result.reason,
            },
        )

    async def health(self) -> dict[str, Any]:
        assert self.services is not None
        details: dict[str, Any] = {}
        ok = True
        try:
            async with self.services.sessionmaker() as session:
                await session.execute(text("SELECT 1"))
            details["database"] = "ok"
        except Exception as exc:
            ok = False
            details["database"] = f"error: {exc}"
        try:
            await self.services.redis.ping()
            details["redis"] = "ok"
        except Exception as exc:
            ok = False
            details["redis"] = f"error: {exc}"
        monitor = self.services.monitor
        details["monitor_last_poll_age_s"] = (
            round(time.time() - monitor.last_success, 1) if monitor and monitor.last_success else None
        )
        details["giftwiki_age_h"] = self.services.store.snapshot.age_hours()
        details["kill_switch"] = await self.services.control.is_stopped()
        details["run_mode"] = (await self.services.control.run_mode()).value
        details["status"] = "ok" if ok else "error"
        return details

    # ------------------------------------------------------------------ run
    def _spawn(self, coro: Awaitable[Any], name: str) -> None:
        self.tasks.append(asyncio.create_task(coro, name=name))  # type: ignore[arg-type]

    async def run(self, components: set[str]) -> None:
        services = await self.build()
        s = self.settings
        unknown = components - ALL_COMPONENTS
        if unknown:
            raise ValueError(f"Unknown components: {', '.join(sorted(unknown))}")
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.stop.set)

        if "buyer" in components:
            await services.purchase.recover_on_startup()
        if "metrics" in components:
            self._http_runner = await start_http_server(s.metrics_host, s.metrics_port, self.health)
        if "monitor" in components and services.monitor is not None and s.mrkt_monitor_enabled:
            self._spawn(services.monitor.run(self.stop), "monitor")
        elif "monitor" in components:
            log.warning("MRKT monitor is not started: MRKT_ACCESS_TOKEN / MRKT_INIT_DATA is not configured")
        if "processor" in components:
            for i in range(max(1, s.processor_workers)):
                self._spawn(
                    services.events_queue.consume(self.processor.handle_payload, stop=self.stop), f"proc-{i}"
                )
        if "buyer" in components:
            for i in range(max(1, s.purchase_workers)):
                self._spawn(services.purchase_queue.consume(self._buy, stop=self.stop), f"buyer-{i}")
            self._spawn(
                self._every(60, services.purchase.reverify_unknown, "reverify", initial=10), "reverify"
            )
        if "scheduler" in components:
            self._spawn(self._once(self._giftwiki_initial, "giftwiki-initial"), "gw-initial")
            self._spawn(
                self._every(
                    s.giftwiki_sync_interval_minutes * 60,
                    self._giftwiki_job,
                    "giftwiki",
                    initial=s.giftwiki_sync_interval_minutes * 60,
                ),
                "giftwiki",
            )
            self._spawn(self._every(3600, self._collections_job, "collections"), "collections")
            self._spawn(self._every(24 * 3600, self._cleanup_job, "cleanup", initial=600), "cleanup")
            self._spawn(self._every(15, self._queue_metrics, "queue-metrics"), "queue-metrics")
        if "bot" in components:
            if self.bot is None:
                log.warning("Telegram bot is not started: TELEGRAM_BOT_TOKEN is not set")
            else:
                self._spawn(self._run_bot(services), "bot")
        log.info(
            "application started", extra={"components": sorted(components), "run_mode": s.run_mode.value}
        )
        await self.stop.wait()
        await self.shutdown()

    async def _run_bot(self, services: Services) -> None:
        from gift_sniper.bot.setup import build_dispatcher

        dispatcher = build_dispatcher(services)
        try:
            await dispatcher.start_polling(self.bot, handle_signals=False)
        finally:
            self.stop.set()

    async def shutdown(self) -> None:
        log.info("shutting down")
        self.stop.set()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self._http_runner is not None:
            await self._http_runner.cleanup()
        if self.services is not None:
            await self.services.mrkt.close()
            await self.services.giftwiki.close()
            await self.services.redis.aclose()
        if self.bot is not None:
            await self.bot.session.close()
        await self._engine.dispose()
