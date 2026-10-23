"""Reference data store (Gift Wiki snapshot cache) and listing enrichment."""

from __future__ import annotations

import logging
import statistics
import time
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import Settings
from gift_sniper.db.repo import giftwiki as giftwiki_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import Enrichment, ListingSnapshot, MonochromeVerdict, Share
from gift_sniper.metrics import GIFTWIKI_RECORDS
from gift_sniper.services.monochrome import ClassifierConfig, classify
from gift_sniper.services.percentages import monochrome_model_share
from gift_sniper.services.reference import ReferenceSnapshot

log = logging.getLogger(__name__)


class ReferenceStore:
    """Current Gift Wiki snapshot. Reloaded from PostgreSQL when the version key in Redis changes."""

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], redis: Redis | None, prefix: str
    ) -> None:
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.version_key = f"{prefix}:reference:version"
        self.snapshot = ReferenceSnapshot()
        self._version: str | None = None
        self._last_check = 0.0

    async def reload(self) -> ReferenceSnapshot:
        async with self.sessionmaker() as session:
            self.snapshot = await giftwiki_repo.load_snapshot(session)
        GIFTWIKI_RECORDS.set(self.snapshot.records_count)
        log.info(
            "reference snapshot loaded",
            extra={"gifts": len(self.snapshot.gifts), "records": self.snapshot.records_count},
        )
        return self.snapshot

    async def bump(self) -> None:
        if self.redis is not None:
            self._version = str(await self.redis.incr(self.version_key))
        await self.reload()

    async def maybe_reload(self, min_interval: float = 15.0) -> None:
        if self.redis is None or time.monotonic() - self._last_check < min_interval:
            return
        self._last_check = time.monotonic()
        raw = await self.redis.get(self.version_key)
        version = raw.decode() if isinstance(raw, bytes) else raw
        if version != self._version:
            self._version = version
            await self.reload()


class Enricher:
    def __init__(
        self,
        settings: Settings,
        store: ReferenceStore,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        cache_ttl: float = 60.0,
    ) -> None:
        self.settings = settings
        self.store = store
        self.sessionmaker = sessionmaker
        self.cache_ttl = cache_ttl
        self.classifier_config = ClassifierConfig(
            absent_pair_policy=settings.monochrome_absent_pair_policy,
            stale_after_hours=settings.giftwiki_stale_after_hours,
            color_check=settings.monochrome_color_check,
        )
        self._models_cache: dict[str, tuple[float, dict[str, int | None]]] = {}
        self._prices_cache: dict[tuple[str, str], tuple[float, list[int]]] = {}

    def classify(self, listing: ListingSnapshot) -> MonochromeVerdict:
        return classify(listing, self.store.snapshot, self.classifier_config)

    async def _observed_models(self, listing: ListingSnapshot) -> dict[str, int | None]:
        names = [n for n in (listing.collection_name, listing.collection_title) if n]
        key = "|".join(sorted(normalize_name(n) for n in names))
        cached = self._models_cache.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            return cached[1]
        async with self.sessionmaker() as session:
            models = await listings_repo.observed_models(session, names)
        self._models_cache[key] = (time.monotonic(), models)
        return models

    async def model_share(self, listing: ListingSnapshot, verdict: MonochromeVerdict) -> Share | None:
        """A: monochrome models of the matched Gift Wiki gift / known models of the collection."""
        if verdict.gift_id is None:
            return None
        mono = set(self.store.snapshot.monochrome_models.get(verdict.gift_id, {}))
        observed = await self._observed_models(listing)
        return monochrome_model_share(mono, observed.keys(), rarity_by_model=observed)

    async def discount(self, listing: ListingSnapshot) -> tuple[float | None, int | None, int]:
        """Discount vs the median of comparable observed prices (same collection and model, N days)."""
        if listing.price_nano is None or not listing.collection_name or not listing.model_name:
            return None, None, 0
        key = (normalize_name(listing.collection_name), normalize_name(listing.model_name))
        cached = self._prices_cache.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            prices = cached[1]
        else:
            async with self.sessionmaker() as session:
                prices = await listings_repo.comparable_prices(
                    session,
                    listing.collection_name,
                    listing.model_name,
                    days=self.settings.discount_window_days,
                    exclude_gift=listing.gift_id,
                )
            self._prices_cache[key] = (time.monotonic(), prices)
        if len(prices) < self.settings.discount_min_samples:
            return None, None, len(prices)
        median = int(statistics.median(prices))
        if median <= 0:
            return None, None, len(prices)
        return (median - listing.price_nano) / median * 100.0, median, len(prices)

    async def enrich(self, listing: ListingSnapshot, verdict: MonochromeVerdict | None = None) -> Enrichment:
        await self.store.maybe_reload()
        verdict = verdict or self.classify(listing)
        share = await self.model_share(listing, verdict)
        discount, reference, samples = await self.discount(listing)
        age = None
        if verdict.data_as_of is not None:
            age = (datetime.now(UTC) - verdict.data_as_of).total_seconds() / 3600
        elif self.store.snapshot.last_success_at is not None:
            age = self.store.snapshot.age_hours()
        return Enrichment(
            verdict=verdict,
            model_share=share,
            model_drop_probability=None,  # not published by the documented Gift Wiki API
            discount_percent=discount,
            discount_reference_nano=reference,
            discount_samples=samples,
            giftwiki_data_age_hours=age,
        )
