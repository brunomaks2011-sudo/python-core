"""Listing processing: store the event, classify, evaluate all filters, decide purchases, notify.

Purchase decisions are published before notifications are sent, because sniping is latency critical.
A listing the bot is about to buy is not announced separately: the purchase result is the message.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import RunMode, Settings
from gift_sniper.db.models import FilterHit
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.domain.enums import FeedEventType, FilterKind, ListingStatus, MonochromeStatus, PurchaseMode
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import Enrichment, FeedEvent, ListingSnapshot
from gift_sniper.integrations.mrkt.parsing import parse_datetime, parse_gift
from gift_sniper.metrics import EVENT_TO_DECISION, FILTER_PROCESSING
from gift_sniper.services.enrichment import Enricher
from gift_sniper.services.filter_cache import FilterCache, UserFlags
from gift_sniper.services.filters import FilterSpec, MatchContext, PriceRule, evaluate, floor_rules
from gift_sniper.services.floors import FloorService
from gift_sniper.services.notifications import Notifier
from gift_sniper.services.purchase import PurchaseRequest
from gift_sniper.services.resale import ResaleAssistant

log = logging.getLogger(__name__)

ACTIONABLE = {FeedEventType.LISTING.value, FeedEventType.CHANGE_PRICE.value, FeedEventType.OBSERVED.value}


class Publisher(Protocol):
    async def publish(self, payload: dict[str, Any]) -> str: ...


class RunControl(Protocol):
    async def run_mode(self) -> RunMode: ...
    async def is_stopped(self) -> bool: ...


def event_to_payload(event: FeedEvent, *, detected_at: datetime, backlog: bool) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "type": event.type,
        "amount": event.amount_nano,
        "date": event.date.isoformat() if event.date else None,
        "gift": event.listing.raw,
        "source": event.source,
        "detected_at": detected_at.isoformat(),
        "backlog": backlog,
    }


def payload_to_event(payload: dict[str, Any]) -> tuple[FeedEvent | None, datetime, bool]:
    detected = parse_datetime(payload.get("detected_at")) or datetime.now(UTC)
    listing = parse_gift(payload.get("gift"), detected)
    if listing is None or not payload.get("event_id") or not payload.get("type"):
        return None, detected, bool(payload.get("backlog"))
    amount = payload.get("amount")
    event = FeedEvent(
        event_id=str(payload["event_id"]),
        type=str(payload["type"]),
        listing=listing,
        amount_nano=int(amount) if isinstance(amount, int) else None,
        date=parse_datetime(payload.get("date")),
        source=str(payload.get("source") or "feed"),
    )
    return event, detected, bool(payload.get("backlog"))


@dataclass(slots=True)
class ProcessReport:
    duplicate: bool = False
    skipped: str | None = None
    listing_id: int | None = None
    matched_filters: list[int] = field(default_factory=list)
    purchase_requests: list[PurchaseRequest] = field(default_factory=list)
    notified_users: list[int] = field(default_factory=list)
    enrichment: Enrichment | None = None


class ListingProcessor:
    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        enricher: Enricher,
        filter_cache: FilterCache,
        notifier: Notifier | None,
        purchase_queue: Publisher | None,
        control: RunControl | None = None,
        floors: FloorService | None = None,
        background_notifications: bool = False,
        assistant: ResaleAssistant | None = None,
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.enricher = enricher
        self.filter_cache = filter_cache
        self.notifier = notifier
        self.purchase_queue = purchase_queue
        self.control = control
        self.floors = floors
        self.assistant = assistant
        # the bot sends listing messages while the next listing is already being judged
        self.background_notifications = background_notifications
        self._notifying: set[asyncio.Task[None]] = set()

    async def handle_payload(self, payload: dict[str, Any]) -> None:
        event, detected_at, backlog = payload_to_event(payload)
        if event is None:
            log.warning("malformed listing event dropped", extra={"payload": str(payload)[:300]})
            return
        await self.process(event, detected_at=detected_at, backlog=backlog)

    @staticmethod
    def event_price(event: FeedEvent) -> int | None:
        if event.type in ACTIONABLE and event.amount_nano is not None and event.amount_nano > 0:
            return event.amount_nano
        return event.listing.price_nano

    async def process(
        self, event: FeedEvent, *, detected_at: datetime, backlog: bool = False
    ) -> ProcessReport:
        report = ProcessReport()
        started = time.perf_counter()
        price = self.event_price(event)
        listing: ListingSnapshot = replace(event.listing, price_nano=price)
        await self.enricher.store.maybe_reload()
        verdict = self.enricher.classify(listing)

        async with self.sessionmaker() as session, session.begin():
            if not await listings_repo.record_feed_event(session, event):
                report.duplicate = True
                return report
            await listings_repo.upsert_gift(session, listing)
            await listings_repo.observe_model(session, listing)
            change = await listings_repo.apply_event(
                session,
                event.type,
                listing,
                price_nano=price,
                event_date=event.date,
                source=event.source,
                source_event_id=event.event_id,
                monochrome_status=verdict.status,
            )
            await listings_repo.set_classification(session, listing.gift_id, verdict)
        report.listing_id = change.listing_id

        if event.type == FeedEventType.SALE.value and self.assistant is not None:
            # a gift the assistant listed may have been sold, also while the bot was down (backlog)
            try:
                await self.assistant.on_sale(listing.gift_id, price, is_mine=listing.is_mine)
            except Exception:  # the sale stays in the price history
                log.exception("resale sale check failed", extra={"gift_id": listing.gift_id})
        if backlog:
            report.skipped = "backlog"
            return report
        if event.type not in ACTIONABLE or change.status is not ListingStatus.ACTIVE:
            report.skipped = "not actionable"
            return report
        # the account's own listing (e.g. the assistant selling): nothing to buy or announce
        if listing.is_mine:
            report.skipped = "own listing"
            return report
        price_changed = (
            change.previous_price_nano is not None and change.previous_price_nano != change.price_nano
        )
        if not change.is_new_listing and not price_changed:
            report.skipped = "no material change"
            return report
        if listing.is_on_auction:
            report.skipped = "auction"
            return report

        enrichment = await self.enricher.enrich(listing, verdict)
        specs, users = await self.filter_cache.get()
        if self.floors is not None:  # floors cost a MRKT request: only when a floor-priced pick may match
            rules = self._floor_rules(specs, listing, enrichment)
            enrichment = await self.floors.with_floors(listing, enrichment, rules)
        report.enrichment = enrichment
        ctx = MatchContext(
            event_type=event.type, detected_at=detected_at, is_first_sighting=change.is_new_listing
        )
        matched_by_user: dict[int, list[FilterSpec]] = defaultdict(list)
        for spec in specs:
            if not spec.enabled or spec.criteria.resale is not None:
                continue  # the assistant's settings are not a rule: it values the listing below
            result = evaluate(
                spec.kind, spec.criteria, listing, enrichment, ctx, activated_at=spec.activated_at
            )
            if result.matched:
                matched_by_user[spec.user_id].append(spec)
                report.matched_filters.append(spec.id)
        FILTER_PROCESSING.observe(time.perf_counter() - started)

        # 1) purchases first (latency critical)
        for user_id, matched in matched_by_user.items():
            request = self._purchase_request(
                users.get(user_id), matched, listing, enrichment, change, event, detected_at
            )
            if request is not None:
                report.purchase_requests.append(request)
                if self.purchase_queue is not None:
                    await self.purchase_queue.publish(request.to_payload())
        await self._assistant_requests(
            specs, users, listing, enrichment, change, event, detected_at, ctx, report
        )
        if report.purchase_requests:
            EVENT_TO_DECISION.observe((datetime.now(UTC) - detected_at).total_seconds())

        # 2) filter hit statistics
        if report.matched_filters and change.listing_id is not None:
            try:
                await self._store_hits(matched_by_user, change.listing_id, listing, enrichment)
            except Exception:  # e.g. a filter deleted meanwhile; statistics must not block notifications
                log.exception("failed to store filter hits", extra={"listing_id": change.listing_id})

        # 3) notifications
        if self.notifier is not None:
            price_drop_from: int | None = None
            if price_changed:
                previous, current = change.previous_price_nano, change.price_nano
                if previous is None or current is None or current >= previous:
                    return report  # the price went up: nothing to notify
                price_drop_from = previous
            buying = await self._buying_users(report)
            notified = [(user_id, flags) for user_id, flags in users.items() if user_id not in buying]
            sending = self._notify_all(
                notified, listing, enrichment, matched_by_user, change.listing_id, price_drop_from, report
            )
            if self.background_notifications:
                task = asyncio.create_task(sending)
                self._notifying.add(task)
                task.add_done_callback(self._notifying.discard)
            else:
                await sending
        return report

    async def _notify_all(
        self,
        notified: list[tuple[int, UserFlags]],
        listing: ListingSnapshot,
        enrichment: Enrichment,
        matched_by_user: dict[int, list[FilterSpec]],
        listing_id: int | None,
        price_drop_from: int | None,
        report: ProcessReport,
    ) -> None:
        results = await asyncio.gather(
            *(
                self._notify_user(
                    flags, listing, enrichment, matched_by_user.get(user_id, []), listing_id, price_drop_from
                )
                for user_id, flags in notified
            ),
            return_exceptions=True,
        )
        for (user_id, _), res in zip(notified, results, strict=True):
            if res is True:
                report.notified_users.append(user_id)
            elif isinstance(res, Exception):
                log.error("notification failed", exc_info=res, extra={"user_id": user_id})

    async def _assistant_requests(
        self,
        specs: list[FilterSpec],
        users: dict[int, UserFlags],
        listing: ListingSnapshot,
        enrichment: Enrichment,
        change: listings_repo.ListingChange,
        event: FeedEvent,
        detected_at: datetime,
        ctx: MatchContext,
        report: ProcessReport,
    ) -> None:
        """🤖 The resale assistant of each user who has one: buy when the listing can be resold with a profit."""
        if self.assistant is None or listing.price_nano is None:
            return
        buying = {request.user_id for request in report.purchase_requests}
        for spec in specs:
            rules = spec.criteria.resale
            if rules is None or not spec.enabled or not spec.autobuy or spec.user_id in buying:
                continue
            flags = users.get(spec.user_id)
            if flags is None or flags.is_blocked or not flags.can_purchase or flags.purchases_paused:
                continue
            # the assistant's own bounds: collections, prices and the like
            if not evaluate(
                spec.kind, spec.criteria, listing, enrichment, ctx, activated_at=spec.activated_at
            ).matched:
                continue
            try:
                plan = await self.assistant.plan(listing, rules)
            except Exception:
                log.exception("resale valuation failed", extra={"gift_id": listing.gift_id})
                return
            if not plan.ok:
                continue
            await self.assistant.remember(spec.user_id, plan)
            request = PurchaseRequest(
                user_id=spec.user_id,
                gift_id=listing.gift_id,
                expected_price_nano=listing.price_nano,
                mode=PurchaseMode.RESALE,
                filter_id=spec.id,
                listing_id=change.listing_id,
                trigger="assistant",
                event_type=event.type,
                first_sighting=change.is_new_listing,
                detected_at=detected_at,
            )
            buying.add(spec.user_id)
            report.purchase_requests.append(request)
            if self.purchase_queue is not None:
                await self.purchase_queue.publish(request.to_payload())

    @staticmethod
    def _floor_rules(
        specs: list[FilterSpec], listing: ListingSnapshot, enrichment: Enrichment
    ) -> set[PriceRule]:
        is_mono = enrichment.verdict.status is MonochromeStatus.MONOCHROME
        names = {normalize_name(n) for n in (listing.collection_name, listing.collection_title) if n}
        rules: set[PriceRule] = set()
        for spec in specs:
            if not spec.enabled or (spec.kind is FilterKind.MONOCHROME and not is_mono):
                continue
            if spec.criteria.resale is not None:
                continue
            wanted = {normalize_name(c) for c in spec.criteria.collections}
            if wanted and not wanted & names:
                continue
            rules |= floor_rules(spec.criteria, listing)
        return rules

    async def _buying_users(self, report: ProcessReport) -> set[int]:
        """Users whose purchase request will really run (live or test mode, no emergency stop): they hear
        about the listing from the purchase result. In notify-only mode the listing message is all they get."""
        if not report.purchase_requests or self.control is None:
            return set()
        if await self.control.run_mode() is RunMode.NOTIFY_ONLY or await self.control.is_stopped():
            return set()
        return {request.user_id for request in report.purchase_requests}

    async def _notify_user(
        self,
        flags: UserFlags,
        listing: ListingSnapshot,
        enrichment: Enrichment,
        matched: list[FilterSpec],
        listing_id: int | None,
        price_drop_from: int | None,
    ) -> bool:
        assert self.notifier is not None
        return await self.notifier.listing_for_user(
            flags, listing, enrichment, matched, listing_id=listing_id, price_drop_from=price_drop_from
        )

    def _purchase_request(
        self,
        flags: UserFlags | None,
        matched: list[FilterSpec],
        listing: ListingSnapshot,
        enrichment: Enrichment,
        change: listings_repo.ListingChange,
        event: FeedEvent,
        detected_at: datetime,
    ) -> PurchaseRequest | None:
        if flags is None or flags.is_blocked or not flags.can_purchase or flags.purchases_paused:
            return None
        if listing.price_nano is None:
            return None
        is_mono = enrichment.verdict.status is MonochromeStatus.MONOCHROME
        candidates: list[tuple[int, FilterSpec, PurchaseMode]] = []
        for spec in matched:
            if not spec.autobuy:
                continue
            if spec.kind is FilterKind.MONOCHROME and flags.monochrome_autobuy_enabled and is_mono:
                candidates.append((0, spec, PurchaseMode.MONOCHROME))
            elif spec.kind is FilterKind.REGULAR and flags.autobuy_enabled:
                candidates.append((1, spec, PurchaseMode.REGULAR))
        if not candidates:
            return None
        _, spec, mode = sorted(candidates, key=lambda c: (c[0], c[1].id))[0]
        return PurchaseRequest(
            user_id=spec.user_id,
            gift_id=listing.gift_id,
            expected_price_nano=listing.price_nano,
            mode=mode,
            filter_id=spec.id,
            listing_id=change.listing_id,
            trigger="auto",
            event_type=event.type,
            first_sighting=change.is_new_listing,
            detected_at=detected_at,
        )

    async def _store_hits(
        self,
        matched_by_user: dict[int, list[FilterSpec]],
        listing_id: int,
        listing: ListingSnapshot,
        enrichment: Enrichment,
    ) -> None:
        rows = [
            {
                "filter_id": spec.id,
                "user_id": spec.user_id,
                "listing_id": listing_id,
                "gift_id": listing.gift_id,
                "price_nano": listing.price_nano,
                "monochrome_status": enrichment.verdict.status.value,
            }
            for specs in matched_by_user.values()
            for spec in specs
        ]
        if not rows:
            return
        async with self.sessionmaker() as session, session.begin():
            await session.execute(
                pg_insert(FilterHit).values(rows).on_conflict_do_nothing(constraint="uq_filter_hits_key")
            )
