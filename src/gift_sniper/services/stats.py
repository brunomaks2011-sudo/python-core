"""Market and user statistics. Every figure carries its period and data source."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.db.models import Filter, FilterHit, Gift, Listing, Purchase, PurchaseAttempt
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.domain.enums import MonochromeStatus, PurchaseStatus
from gift_sniper.domain.types import Share
from gift_sniper.services.enrichment import ReferenceStore
from gift_sniper.services.percentages import monochrome_model_share


@dataclass(slots=True)
class MarketStats:
    period_start: datetime
    period_end: datetime
    new_listings: int = 0
    matching_listings: int = 0
    avg_price_nano: int | None = None
    median_price_nano: int | None = None
    cheapest: list[tuple[str, str | None, str | None, int | None, str]] = field(default_factory=list)
    monochrome_listings: int = 0
    listing_share: Share | None = None
    collection_shares: list[tuple[str, Share | None]] = field(default_factory=list)
    daily_medians: list[tuple[str, int | None, int]] = field(default_factory=list)
    attempts: int = 0
    confirmed: int = 0
    spent_nano: int = 0
    errors: int = 0
    cancelled: int = 0
    dry_run: int = 0
    giftwiki_age_hours: float | None = None


@dataclass(slots=True)
class FilterStatsRow:
    filter_id: int
    name: str
    kind: str
    enabled: bool
    hits: int
    attempts: int
    confirmed: int
    spent_nano: int


@dataclass(slots=True)
class UserStats:
    period_start: datetime
    period_end: datetime
    filters: list[FilterStatsRow] = field(default_factory=list)
    attempts: int = 0
    confirmed: int = 0
    spent_nano: int = 0
    failed: int = 0
    unknown: int = 0
    cancelled: int = 0
    dry_run: int = 0
    dry_run_nano: int = 0


class StatsService:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], store: ReferenceStore) -> None:
        self.sessionmaker = sessionmaker
        self.store = store

    async def market(self, *, user_id: int, period_hours: int = 24) -> MarketStats:
        end = datetime.now(UTC)
        start = end - timedelta(hours=period_hours)
        stats = MarketStats(
            period_start=start, period_end=end, giftwiki_age_hours=self.store.snapshot.age_hours()
        )
        async with self.sessionmaker() as session:
            in_period = Listing.first_seen_at >= start
            stats.new_listings = int(
                (
                    await session.execute(select(func.count()).select_from(Listing).where(in_period))
                ).scalar_one()
            )
            avg, median = (
                await session.execute(
                    select(
                        func.avg(Listing.price_nano),
                        func.percentile_cont(0.5).within_group(cast(Listing.price_nano, Float)),
                    ).where(in_period, Listing.price_nano.is_not(None))
                )
            ).one()
            stats.avg_price_nano = int(avg) if avg is not None else None
            stats.median_price_nano = int(median) if median is not None else None
            stats.matching_listings = int(
                (
                    await session.execute(
                        select(func.count(func.distinct(FilterHit.listing_id))).where(
                            FilterHit.user_id == user_id, FilterHit.matched_at >= start
                        )
                    )
                ).scalar_one()
            )
            rows = (
                await session.execute(
                    select(
                        Gift.collection_name,
                        Gift.number,
                        Gift.model_name,
                        Listing.price_nano,
                        Listing.monochrome_status,
                    )
                    .join(Gift, Gift.id == Listing.gift_id)
                    .where(in_period, Listing.status == "active", Listing.price_nano.is_not(None))
                    .order_by(Listing.price_nano)
                    .limit(5)
                )
            ).all()
            stats.cheapest = [
                (f"{r[0] or 'Подарок'}" + (f" #{r[1]}" if r[1] is not None else ""), r[0], r[2], r[3], r[4])
                for r in rows
            ]
            status_rows = (
                await session.execute(
                    select(Listing.monochrome_status, func.count())
                    .where(in_period)
                    .group_by(Listing.monochrome_status)
                )
            ).all()
            counts = {row[0]: int(row[1]) for row in status_rows}
            total = sum(counts.values())
            stats.monochrome_listings = counts.get(MonochromeStatus.MONOCHROME.value, 0)
            if total:
                stats.listing_share = Share(
                    numerator=stats.monochrome_listings,
                    denominator=total,
                    unknown=counts.get(MonochromeStatus.UNKNOWN.value, 0),
                )
            day = func.date_trunc("day", Listing.first_seen_at)
            daily = (
                await session.execute(
                    select(
                        day,
                        func.percentile_cont(0.5).within_group(cast(Listing.price_nano, Float)),
                        func.count(),
                    )
                    .where(Listing.first_seen_at >= end - timedelta(days=7), Listing.price_nano.is_not(None))
                    .group_by(day)
                    .order_by(day)
                )
            ).all()
            stats.daily_medians = [
                (r[0].strftime("%Y-%m-%d"), int(r[1]) if r[1] is not None else None, int(r[2])) for r in daily
            ]
            attempt_rows = (
                await session.execute(
                    select(PurchaseAttempt.status, func.count())
                    .where(PurchaseAttempt.user_id == user_id, PurchaseAttempt.created_at >= start)
                    .group_by(PurchaseAttempt.status)
                )
            ).all()
            by_status = {row[0]: int(row[1]) for row in attempt_rows}
            stats.attempts = sum(by_status.values())
            stats.errors = by_status.get(PurchaseStatus.FAILED.value, 0) + by_status.get(
                PurchaseStatus.UNKNOWN.value, 0
            )
            stats.cancelled = by_status.get(PurchaseStatus.CANCELLED.value, 0)
            stats.dry_run = by_status.get(PurchaseStatus.DRY_RUN.value, 0)
            confirmed, spent = (
                await session.execute(
                    select(func.count(), func.coalesce(func.sum(Purchase.price_nano), 0)).where(
                        Purchase.user_id == user_id, Purchase.confirmed_at >= start
                    )
                )
            ).one()
            stats.confirmed, stats.spent_nano = int(confirmed or 0), int(spent or 0)
            stats.collection_shares = await self.collection_shares(session, limit=5)
        return stats

    async def collection_shares(
        self, session: AsyncSession, limit: int = 5
    ) -> list[tuple[str, Share | None]]:
        """A for the gifts with the most Gift Wiki monochrome records."""
        snap = self.store.snapshot
        result: list[tuple[str, Share | None]] = []
        ranked = sorted(snap.gifts.values(), key=lambda g: g.records_count, reverse=True)
        for gift in ranked[:limit]:
            if gift.records_count <= 0 or not gift.gift_name:
                continue
            mono = snap.monochrome_models.get(gift.gift_id, {})
            observed = await listings_repo.observed_models(session, [gift.gift_name])
            result.append(
                (gift.gift_name, monochrome_model_share(mono, observed.keys(), rarity_by_model=observed))
            )
        return result

    async def user(self, *, user_id: int, period_days: int = 30) -> UserStats:
        end = datetime.now(UTC)
        start = end - timedelta(days=period_days)
        stats = UserStats(period_start=start, period_end=end)
        async with self.sessionmaker() as session:
            filters = list(
                (
                    await session.execute(select(Filter).where(Filter.user_id == user_id).order_by(Filter.id))
                ).scalars()
            )
            for f in filters:
                hits = (
                    await session.execute(
                        select(func.count())
                        .select_from(FilterHit)
                        .where(FilterHit.filter_id == f.id, FilterHit.matched_at >= start)
                    )
                ).scalar_one()
                attempts = (
                    await session.execute(
                        select(func.count())
                        .select_from(PurchaseAttempt)
                        .where(PurchaseAttempt.filter_id == f.id, PurchaseAttempt.created_at >= start)
                    )
                ).scalar_one()
                confirmed, spent = (
                    await session.execute(
                        select(func.count(), func.coalesce(func.sum(Purchase.price_nano), 0)).where(
                            Purchase.filter_id == f.id, Purchase.confirmed_at >= start
                        )
                    )
                ).one()
                stats.filters.append(
                    FilterStatsRow(
                        f.id,
                        f.name,
                        f.kind,
                        f.enabled,
                        int(hits or 0),
                        int(attempts or 0),
                        int(confirmed or 0),
                        int(spent or 0),
                    )
                )
            rows = (
                await session.execute(
                    select(
                        PurchaseAttempt.status,
                        func.count(),
                        func.coalesce(
                            func.sum(
                                func.coalesce(
                                    PurchaseAttempt.final_price_nano, PurchaseAttempt.expected_price_nano
                                )
                            ),
                            0,
                        ),
                    )
                    .where(PurchaseAttempt.user_id == user_id, PurchaseAttempt.created_at >= start)
                    .group_by(PurchaseAttempt.status)
                )
            ).all()
            by_status = {row[0]: (int(row[1]), int(row[2])) for row in rows}
            stats.attempts = sum(v[0] for v in by_status.values())
            stats.failed = by_status.get(PurchaseStatus.FAILED.value, (0, 0))[0]
            stats.unknown = by_status.get(PurchaseStatus.UNKNOWN.value, (0, 0))[0]
            stats.cancelled = by_status.get(PurchaseStatus.CANCELLED.value, (0, 0))[0]
            stats.dry_run, stats.dry_run_nano = by_status.get(PurchaseStatus.DRY_RUN.value, (0, 0))
            confirmed, spent = (
                await session.execute(
                    select(func.count(), func.coalesce(func.sum(Purchase.price_nano), 0)).where(
                        Purchase.user_id == user_id, Purchase.confirmed_at >= start
                    )
                )
            ).one()
            stats.confirmed, stats.spent_nano = int(confirmed or 0), int(spent or 0)
        return stats
