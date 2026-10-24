"""Scheduled synchronization of the Gift Wiki monochrome reference into PostgreSQL.

1. Walk the paginated GET /gifts/monochromes list (21 records per page) to discover all records.
2. For every discovered gift, request `gift_name=...`, which per the documentation returns ALL records
   of the gift. This gives a complete per-gift list, required for NOT_MONOCHROME decisions.
3. Store records with provenance (source URL, first fetch, last seen); records missing from a
   complete fresh list are soft-deleted (removed_at), never silently dropped.
On any error the previous data stays untouched and keeps being used, with its age shown to users.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import Settings
from gift_sniper.db.models import GiftWikiSyncRun
from gift_sniper.db.repo import giftwiki as repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import misc
from gift_sniper.domain.types import ListingSnapshot, MonochromeRecord
from gift_sniper.integrations.giftwiki import PAGE_SIZE, GiftWikiClient, GiftWikiError, GiftWikiForbiddenError
from gift_sniper.metrics import GIFTWIKI_LAST_SUCCESS
from gift_sniper.services.enrichment import Enricher, ReferenceStore
from gift_sniper.services.locks import RedisLock

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SyncReport:
    status: str = "running"
    pages: int = 0
    records: int = 0
    gifts: int = 0
    added: int = 0
    removed: int = 0
    lookups_done: int = 0
    lookups_failed: int = 0
    pagination_complete: bool = False
    error: str | None = None
    complete_gifts: set[str] = field(default_factory=set)


ALREADY_RUNNING = "синхронизация уже выполняется"
# short, renewed on every page and lookup: a killed process does not block syncs for long
LOCK_TTL_SECONDS = 300


class GiftWikiSync:
    def __init__(
        self,
        settings: Settings,
        client: GiftWikiClient,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        store: ReferenceStore,
        enricher: Enricher | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.store = store
        self.enricher = enricher
        self._lock: RedisLock | None = None

    def lock_key(self) -> str:
        return f"{self.settings.redis_prefix}:lock:giftwiki-sync"

    async def is_running(self) -> bool:
        return bool(await self.redis.exists(self.lock_key()))

    async def _heartbeat(self) -> None:
        """Keep the lock while the sync makes progress; a crashed process releases it within the TTL."""
        if self._lock is not None:
            await self._lock.extend(LOCK_TTL_SECONDS)

    async def run(self, trigger: str = "schedule") -> SyncReport:
        report = SyncReport()
        if not self.client.configured:
            report.status = "skipped"
            report.error = "GIFTWIKI_API_KEY не задан"
            return report
        lock = RedisLock(self.redis, self.lock_key(), LOCK_TTL_SECONDS)
        if not await lock.acquire():
            report.status = "skipped"
            report.error = ALREADY_RUNNING
            return report
        self._lock = lock
        async with self.sessionmaker() as session, session.begin():
            run = await repo.start_run(session, trigger)
            run_id = run.id
        started = time.monotonic()
        try:
            await self._sync(report)
            report.status = (
                "success" if report.pagination_complete and report.lookups_failed == 0 else "partial"
            )
        except GiftWikiError as exc:
            report.status = "failed"
            report.error = str(exc)
            log.error("Gift Wiki sync failed", extra={"error": str(exc)})
        except Exception as exc:
            report.status = "failed"
            report.error = f"{type(exc).__name__}: {exc}"
            log.exception("Gift Wiki sync crashed")
        finally:
            self._lock = None
            await lock.release()
            async with self.sessionmaker() as session, session.begin():
                run_row = await session.get(GiftWikiSyncRun, run_id)
                if run_row is not None:
                    run_row.status = report.status
                    run_row.finished_at = datetime.now(UTC)
                    run_row.pages_fetched = report.pages
                    run_row.records_fetched = report.records
                    run_row.gifts_covered = report.gifts
                    run_row.records_added = report.added
                    run_row.records_removed = report.removed
                    run_row.lookups_done = report.lookups_done
                    run_row.lookups_failed = report.lookups_failed
                    run_row.error = report.error
                if report.status == "failed":
                    await misc.log_error(session, "giftwiki_sync", report.error or "failed", trigger=trigger)
        if report.status in ("success", "partial"):
            GIFTWIKI_LAST_SUCCESS.set(time.time())
            await self.store.bump()
            await self.refresh_mappings()
            await self.reclassify_active()
        log.info(
            "Gift Wiki sync finished",
            extra={
                "status": report.status,
                "records": report.records,
                "seconds": round(time.monotonic() - started),
            },
        )
        return report

    async def _sync(self, report: SyncReport) -> None:
        records: dict[str, MonochromeRecord] = {}
        last_page_len = PAGE_SIZE
        async for page, batch in self.client.iter_all_pages(self.settings.giftwiki_max_pages):
            await self._heartbeat()
            report.pages = page
            last_page_len = len(batch)
            for rec in batch:
                records[rec.record_id] = rec
        report.pagination_complete = last_page_len < PAGE_SIZE

        by_gift: dict[str, list[MonochromeRecord]] = defaultdict(list)
        names: dict[str, str | None] = {}
        for rec in records.values():
            key = repo.gift_key(rec)
            if key is None:
                continue
            by_gift[key].append(rec)
            names.setdefault(key, rec.gift_name)

        complete: dict[str, str] = {}  # gift key -> coverage source
        if report.pagination_complete:
            complete = dict.fromkeys(by_gift, "pagination")
        if self.settings.giftwiki_per_gift_lookup:
            for key, gift_name in list(names.items()):
                if not gift_name:
                    continue
                await self._heartbeat()
                try:
                    recs = await self.client.monochromes_for_gift(gift_name=gift_name)
                except GiftWikiForbiddenError as exc:
                    log.warning(
                        "Gift Wiki gift lookups are forbidden for this key", extra={"error": str(exc)}
                    )
                    report.lookups_failed += 1
                    break
                except GiftWikiError as exc:
                    report.lookups_failed += 1
                    log.warning("Gift Wiki lookup failed", extra={"gift": gift_name, "error": str(exc)})
                    continue
                report.lookups_done += 1
                own = [r for r in recs if repo.gift_key(r) == key]
                for rec in own:
                    records[rec.record_id] = rec
                by_gift[key] = list({r.record_id: r for r in [*by_gift[key], *own]}.values())
                complete[key] = "gift_lookup"

        now = datetime.now(UTC)
        async with self.sessionmaker() as session, session.begin():
            for key, recs in by_gift.items():
                source_url = self.client.source_url(gift_name=names.get(key))
                await repo.upsert_gift(
                    session,
                    key,
                    names.get(key),
                    records_count=len(recs),
                    complete=key in complete,
                    coverage_source=complete.get(key),
                    synced_at=now,
                    source_url=source_url,
                )
                report.added += await repo.upsert_records(
                    session, key, recs, seen_at=now, source_url=source_url
                )
                if key in complete:
                    report.removed += await repo.mark_removed(
                        session, key, {r.record_id for r in recs}, now=now
                    )
            if report.pagination_complete:
                # gifts that disappeared from a complete list have no monochrome records any more
                report.removed += await repo.clear_missing_gifts(session, set(by_gift), now=now)
            await repo.drop_name_placeholders(session)
        report.records = sum(len(v) for v in by_gift.values())
        report.gifts = len(by_gift)
        report.complete_gifts = set(complete)

    async def refresh_mappings(self) -> dict[str, int]:
        """Store the MRKT collection -> Gift Wiki gift mapping table (manual mappings are kept)."""
        async with self.sessionmaker() as session:
            names = await listings_repo.known_collection_names(session)
        counts: dict[str, int] = defaultdict(int)
        snapshot = self.store.snapshot
        async with self.sessionmaker() as session, session.begin():
            for name in names:
                match = snapshot.match_collection(name)
                if match.method == "manual":
                    counts["manual"] += 1
                    continue
                await repo.save_mapping(
                    session,
                    name,
                    gift_id=match.gift_id,
                    status=match.status,
                    method=match.method,
                    candidates=list(match.candidates),
                )
                counts[match.status] += 1
        return dict(counts)

    async def reclassify_active(self) -> int:
        """Re-run the classification for gifts that currently have active listings."""
        if self.enricher is None:
            return 0
        async with self.sessionmaker() as session:
            gifts = await listings_repo.active_gift_rows(session)
        changed = 0
        async with self.sessionmaker() as session, session.begin():
            for gift in gifts:
                snap = ListingSnapshot(
                    gift_id=gift.id,
                    collection_name=gift.collection_name,
                    collection_title=gift.collection_title,
                    model_name=gift.model_name,
                    backdrop_name=gift.backdrop_name,
                    backdrop_center_color=gift.backdrop_center_color,
                    backdrop_edge_color=gift.backdrop_edge_color,
                )
                verdict = self.enricher.classify(snap)
                if verdict.status.value != gift.monochrome_status:
                    changed += 1
                await listings_repo.set_classification(session, gift.id, verdict)
        return changed
