"""Gifts, listings, price history and feed events (MRKT market data)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from gift_sniper.db.models import FeedEventLog, Gift, GiftModel, Listing, MarketCollection, PriceHistory
from gift_sniper.domain.enums import FeedEventType, ListingStatus, MonochromeStatus
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import FeedEvent, ListingSnapshot, MonochromeVerdict


@dataclass(frozen=True, slots=True)
class ListingChange:
    listing_id: int | None
    is_new_listing: bool  # first sighting of this sale listing
    previous_price_nano: int | None
    price_nano: int | None
    status: ListingStatus


async def record_feed_event(session: AsyncSession, event: FeedEvent) -> bool:
    """Insert the event id; False when it was already processed (database-level dedup)."""
    stmt = (
        pg_insert(FeedEventLog)
        .values(
            event_id=event.event_id[:160],
            type=event.type[:16],
            gift_id=event.listing.gift_id,
            amount_nano=event.amount_nano,
            event_date=event.date,
        )
        .on_conflict_do_nothing(index_elements=[FeedEventLog.event_id])
        .returning(FeedEventLog.event_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def upsert_gift(session: AsyncSession, snap: ListingSnapshot) -> None:
    now = datetime.now(UTC)
    values = {
        "id": snap.gift_id,
        "collection_name": snap.collection_name,
        "collection_title": snap.collection_title,
        "name": snap.name,
        "number": snap.number,
        "model_name": snap.model_name,
        "backdrop_name": snap.backdrop_name,
        "symbol_name": snap.symbol_name,
        "model_rarity_permille": snap.model_rarity_permille,
        "backdrop_rarity_permille": snap.backdrop_rarity_permille,
        "symbol_rarity_permille": snap.symbol_rarity_permille,
        "backdrop_center_color": snap.backdrop_center_color,
        "backdrop_edge_color": snap.backdrop_edge_color,
        "last_seen_at": now,
        "raw": snap.raw,
    }
    update_values = {k: v for k, v in values.items() if k != "id"}
    await session.execute(
        pg_insert(Gift).values(**values).on_conflict_do_update(index_elements=[Gift.id], set_=update_values)
    )


async def observe_model(session: AsyncSession, snap: ListingSnapshot) -> None:
    if not snap.collection_name or not snap.model_name:
        return
    now = datetime.now(UTC)
    stmt = pg_insert(GiftModel).values(
        collection_name=snap.collection_name,
        collection_norm=normalize_name(snap.collection_name),
        model_name=snap.model_name,
        model_norm=normalize_name(snap.model_name),
        rarity_permille=snap.model_rarity_permille,
        source="mrkt",
        last_seen_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_gift_models_key",
        set_={
            "last_seen_at": now,
            "rarity_permille": func.coalesce(stmt.excluded.rarity_permille, GiftModel.rarity_permille),
        },
    )
    await session.execute(stmt)


async def _active_listing(session: AsyncSession, gift_id: str, *, lock: bool = False) -> Listing | None:
    stmt = select(Listing).where(Listing.gift_id == gift_id, Listing.status == ListingStatus.ACTIVE.value)
    if lock:
        stmt = stmt.with_for_update()
    row: Listing | None = (await session.execute(stmt)).scalar_one_or_none()
    return row


async def _add_price(
    session: AsyncSession, snap: ListingSnapshot, listing_id: int | None, price: int, kind: str
) -> None:
    session.add(
        PriceHistory(
            gift_id=snap.gift_id,
            listing_id=listing_id,
            collection_norm=normalize_name(snap.collection_name),
            model_norm=normalize_name(snap.model_name),
            price_nano=price,
            event_type=kind[:16],
        )
    )


async def apply_event(
    session: AsyncSession,
    event_type: str,
    snap: ListingSnapshot,
    *,
    price_nano: int | None,
    event_date: datetime | None,
    source: str,
    source_event_id: str | None,
    monochrome_status: MonochromeStatus = MonochromeStatus.UNKNOWN,
) -> ListingChange:
    """Update the listing state of a gift according to a market event."""
    now = datetime.now(UTC)
    # Serialize concurrent events of the same gift (processors may run in parallel).
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(snap.gift_id, 0))))
    current = await _active_listing(session, snap.gift_id, lock=True)
    kind = event_type.lower()

    if kind in (FeedEventType.LISTING, FeedEventType.CHANGE_PRICE, FeedEventType.OBSERVED):
        if current is None:
            latency = int((now - event_date).total_seconds() * 1000) if event_date else None
            listing = Listing(
                gift_id=snap.gift_id,
                status=ListingStatus.ACTIVE.value,
                price_nano=price_nano,
                currency=snap.currency,
                collection_name=snap.collection_name,
                model_name=snap.model_name,
                monochrome_status=monochrome_status.value,
                listed_at=event_date,
                last_seen_at=now,
                source=source,
                source_event_id=source_event_id,
                detection_latency_ms=latency if latency is not None and latency >= 0 else None,
            )
            session.add(listing)
            await session.flush()
            if price_nano is not None:
                await _add_price(session, snap, listing.id, price_nano, kind)
            return ListingChange(listing.id, True, None, price_nano, ListingStatus.ACTIVE)
        previous = current.price_nano
        current.last_seen_at = now
        current.monochrome_status = monochrome_status.value
        if price_nano is not None and price_nano != previous:
            current.price_nano = price_nano
            await _add_price(session, snap, current.id, price_nano, kind)
        return ListingChange(current.id, False, previous, current.price_nano, ListingStatus.ACTIVE)

    if kind in (FeedEventType.SALE, FeedEventType.UNLISTING, FeedEventType.RETURN):
        status = ListingStatus.SOLD if kind == FeedEventType.SALE else ListingStatus.REMOVED
        if current is None:
            if kind == FeedEventType.SALE and price_nano is not None:
                await _add_price(session, snap, None, price_nano, kind)
            return ListingChange(None, False, None, price_nano, status)
        current.status = status.value
        current.closed_at = now
        current.close_reason = kind
        current.last_seen_at = now
        if kind == FeedEventType.SALE and price_nano is not None:
            await _add_price(session, snap, current.id, price_nano, kind)
        return ListingChange(current.id, False, current.price_nano, price_nano, status)

    return ListingChange(current.id if current else None, False, None, price_nano, ListingStatus.UNKNOWN)


async def close_listing(session: AsyncSession, gift_id: str, status: ListingStatus, reason: str) -> None:
    await session.execute(
        update(Listing)
        .where(Listing.gift_id == gift_id, Listing.status == ListingStatus.ACTIVE.value)
        .values(status=status.value, closed_at=datetime.now(UTC), close_reason=reason[:32])
    )


async def set_classification(session: AsyncSession, gift_id: str, verdict: MonochromeVerdict) -> None:
    now = datetime.now(UTC)
    await session.execute(
        update(Gift)
        .where(Gift.id == gift_id)
        .values(
            monochrome_status=verdict.status.value,
            monochrome_type=verdict.gw_type.value if verdict.gw_type else None,
            monochrome_record_id=verdict.record_id,
            monochrome_reason=verdict.reason,
            classified_at=now,
        )
    )
    await session.execute(
        update(Listing)
        .where(Listing.gift_id == gift_id, Listing.status == ListingStatus.ACTIVE.value)
        .values(monochrome_status=verdict.status.value)
    )


async def comparable_prices(
    session: AsyncSession,
    collection_name: str | None,
    model_name: str | None,
    *,
    days: int,
    exclude_gift: str,
) -> list[int]:
    """Observed prices of other gifts with the same collection and model in the last `days` days."""
    if not collection_name or not model_name:
        return []
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = select(PriceHistory.price_nano).where(
        PriceHistory.collection_norm == normalize_name(collection_name),
        PriceHistory.model_norm == normalize_name(model_name),
        PriceHistory.observed_at >= since,
        PriceHistory.gift_id != exclude_gift,
        PriceHistory.event_type.in_(["listing", "change_price", "sale", "observed"]),
    )
    return [int(p) for p in (await session.execute(stmt)).scalars()]


async def recent_listings(session: AsyncSession, limit: int = 10) -> list[tuple[Listing, Gift]]:
    stmt = (
        select(Listing, Gift)
        .join(Gift, Gift.id == Listing.gift_id)
        .order_by(Listing.first_seen_at.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]


async def active_listings_since(
    session: AsyncSession, since: datetime, limit: int = 5000
) -> list[tuple[Listing, Gift]]:
    stmt = (
        select(Listing, Gift)
        .join(Gift, Gift.id == Listing.gift_id)
        .where(Listing.status == ListingStatus.ACTIVE.value, Listing.last_seen_at >= since)
        .order_by(Listing.first_seen_at.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]


async def collection_statuses(session: AsyncSession, collection_name: str, since: datetime) -> list[str]:
    """Monochrome statuses of active listings of a collection seen since `since` (for share C)."""
    stmt = select(Listing.monochrome_status).where(
        Listing.collection_name == collection_name,
        Listing.status == ListingStatus.ACTIVE.value,
        Listing.last_seen_at >= since,
    )
    return list((await session.execute(stmt)).scalars())


async def active_gift_rows(session: AsyncSession) -> list[Gift]:
    stmt = (
        select(Gift)
        .join(Listing, Listing.gift_id == Gift.id)
        .where(Listing.status == ListingStatus.ACTIVE.value)
    )
    return list((await session.execute(stmt)).scalars())


async def observed_models(session: AsyncSession, collection_names: list[str]) -> dict[str, int | None]:
    """Known models of a collection seen on MRKT: normalized model name -> rarity per mille."""
    norms = sorted({normalize_name(n) for n in collection_names if n})
    if not norms:
        return {}
    stmt = select(GiftModel.model_norm, GiftModel.rarity_permille).where(GiftModel.collection_norm.in_(norms))
    return {row[0]: row[1] for row in (await session.execute(stmt)).all()}


async def upsert_collections(session: AsyncSession, items: list[tuple[str, str | None, int | None]]) -> None:
    now = datetime.now(UTC)
    for name, title, floor in items:
        stmt = pg_insert(MarketCollection).values(
            name=name, title=title, floor_price_nano=floor, updated_at=now
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[MarketCollection.name],
            set_={"title": title, "floor_price_nano": floor, "updated_at": now},
        )
        await session.execute(stmt)


async def known_collection_names(session: AsyncSession) -> list[str]:
    names = set((await session.execute(select(MarketCollection.name))).scalars())
    names |= {n for n in (await session.execute(select(Gift.collection_name).distinct())).scalars() if n}
    return sorted(names)


async def get_gift_row(session: AsyncSession, gift_id: str) -> Gift | None:
    return await session.get(Gift, gift_id)


async def latest_listing(session: AsyncSession, gift_id: str) -> Listing | None:
    stmt = select(Listing).where(Listing.gift_id == gift_id).order_by(Listing.first_seen_at.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


# ------------------------------------------------------------------ catalog for the Mini App
async def market_collections(session: AsyncSession) -> list[MarketCollection]:
    stmt = select(MarketCollection).order_by(MarketCollection.title, MarketCollection.name)
    return list((await session.execute(stmt)).scalars())


async def models_by_collection(session: AsyncSession) -> dict[str, set[str]]:
    """Normalized collection name -> normalized names of the models MRKT has shown for it."""
    result: dict[str, set[str]] = {}
    for collection_norm, model_norm in (
        await session.execute(select(GiftModel.collection_norm, GiftModel.model_norm))
    ).all():
        result.setdefault(collection_norm, set()).add(model_norm)
    return result


async def collection_models(session: AsyncSession, collection_name: str) -> list[GiftModel]:
    stmt = select(GiftModel).where(GiftModel.collection_norm == normalize_name(collection_name))
    return list((await session.execute(stmt)).scalars())


async def upsert_models(
    session: AsyncSession, collection_name: str, models: list[tuple[str, int | None]], *, source: str
) -> None:
    """Models of a collection listed by MRKT itself (not only those seen in listings)."""
    now = datetime.now(UTC)
    for model_name, rarity in models:
        stmt = pg_insert(GiftModel).values(
            collection_name=collection_name,
            collection_norm=normalize_name(collection_name),
            model_name=model_name,
            model_norm=normalize_name(model_name),
            rarity_permille=rarity,
            source=source,
            last_seen_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_gift_models_key",
            set_={
                "last_seen_at": now,
                "rarity_permille": func.coalesce(stmt.excluded.rarity_permille, GiftModel.rarity_permille),
            },
        )
        await session.execute(stmt)


async def collection_backdrops(session: AsyncSession, collection_name: str) -> dict[str, int | None]:
    """Backdrops seen on MRKT gifts of a collection: name -> rarity per mille."""
    stmt = (
        select(Gift.backdrop_name, func.max(Gift.backdrop_rarity_permille))
        .where(Gift.collection_name == collection_name, Gift.backdrop_name.is_not(None))
        .group_by(Gift.backdrop_name)
    )
    return {str(name): rarity for name, rarity in (await session.execute(stmt)).all()}


async def model_floors(session: AsyncSession, collection_name: str) -> dict[str, tuple[int | None, int]]:
    """Cheapest active listing and number of active listings per model, as seen by the monitor."""
    stmt = (
        select(Listing.model_name, func.min(Listing.price_nano), func.count())
        .where(
            Listing.status == ListingStatus.ACTIVE.value,
            Listing.collection_name == collection_name,
            Listing.model_name.is_not(None),
        )
        .group_by(Listing.model_name)
    )
    return {str(model): (price, int(count)) for model, price, count in (await session.execute(stmt)).all()}


async def collection_slugs(session: AsyncSession) -> dict[str, str]:
    """One gift name seen per collection (e.g. PlushPepe-12), for picture URLs."""
    stmt = (
        select(Gift.collection_name, func.min(Gift.name))
        .where(Gift.collection_name.is_not(None), Gift.name.is_not(None))
        .group_by(Gift.collection_name)
    )
    return {str(c): str(n) for c, n in (await session.execute(stmt)).all()}


async def pair_slugs(session: AsyncSession, collection_name: str) -> dict[tuple[str, str], str]:
    """A gift name seen for each (model, backdrop) of a collection."""
    stmt = (
        select(Gift.model_name, Gift.backdrop_name, func.min(Gift.name))
        .where(
            Gift.collection_name == collection_name,
            Gift.model_name.is_not(None),
            Gift.backdrop_name.is_not(None),
            Gift.name.is_not(None),
        )
        .group_by(Gift.model_name, Gift.backdrop_name)
    )
    return {(normalize_name(m), normalize_name(b)): str(n) for m, b, n in (await session.execute(stmt)).all()}


async def backdrop_colors(session: AsyncSession) -> dict[str, tuple[int | None, int | None]]:
    """Normalized backdrop name -> (center, edge) colors seen on MRKT gifts; backdrops are shared by all gifts."""
    stmt = (
        select(Gift.backdrop_name, func.max(Gift.backdrop_center_color), func.max(Gift.backdrop_edge_color))
        .where(Gift.backdrop_name.is_not(None))
        .group_by(Gift.backdrop_name)
    )
    return {normalize_name(str(b)): (c, e) for b, c, e in (await session.execute(stmt)).all()}
