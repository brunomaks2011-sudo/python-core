"""Persistence of Gift Wiki reference data, sync history and MRKT <-> Gift Wiki mappings."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from gift_sniper.db.models import (
    CollectionMapping,
    GiftWikiAttribute,
    GiftWikiGift,
    GiftWikiMonochrome,
    GiftWikiSyncRun,
)
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import MonochromeRecord
from gift_sniper.services.reference import GiftCoverage, ReferenceSnapshot, RefRecord


def gift_key(record: MonochromeRecord) -> str | None:
    """Stable key of the Gift Wiki gift: its documented `gift_id`, else a name-based key."""
    if record.gift_id:
        return record.gift_id[:64]
    if record.gift_name:
        return f"name:{normalize_name(record.gift_name)}"[:64]
    return None


async def start_run(session: AsyncSession, trigger: str) -> GiftWikiSyncRun:
    run = GiftWikiSyncRun(trigger=trigger, status="running")
    session.add(run)
    await session.flush()
    return run


async def last_success(session: AsyncSession) -> GiftWikiSyncRun | None:
    stmt = (
        select(GiftWikiSyncRun)
        .where(GiftWikiSyncRun.status.in_(["success", "partial"]))
        .order_by(GiftWikiSyncRun.finished_at.desc().nulls_last())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def last_runs(session: AsyncSession, limit: int = 5) -> list[GiftWikiSyncRun]:
    stmt = select(GiftWikiSyncRun).order_by(GiftWikiSyncRun.started_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def upsert_gift(
    session: AsyncSession,
    key: str,
    gift_name: str | None,
    *,
    records_count: int,
    complete: bool,
    coverage_source: str | None,
    synced_at: datetime,
    source_url: str,
) -> None:
    stmt = pg_insert(GiftWikiGift).values(
        gift_id=key,
        gift_name=gift_name,
        name_norm=normalize_name(gift_name),
        records_count=records_count,
        coverage_complete=complete,
        coverage_source=coverage_source,
        last_synced_at=synced_at,
        source_url=source_url,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[GiftWikiGift.gift_id],
        set_={
            "gift_name": func.coalesce(stmt.excluded.gift_name, GiftWikiGift.gift_name),
            "name_norm": func.coalesce(func.nullif(stmt.excluded.name_norm, ""), GiftWikiGift.name_norm),
            "records_count": records_count,
            "coverage_complete": complete,
            "coverage_source": coverage_source,
            "last_synced_at": synced_at,
            "source_url": source_url,
        },
    )
    await session.execute(stmt)


async def upsert_records(
    session: AsyncSession,
    key: str,
    records: Iterable[MonochromeRecord],
    *,
    seen_at: datetime,
    source_url: str,
) -> int:
    """Insert or refresh records; returns how many were new."""
    added = 0
    for rec in records:
        values = {
            "record_id": rec.record_id[:64],
            "gift_id": key,
            "gift_name": rec.gift_name,
            "model_name": rec.model_name,
            "model_norm": normalize_name(rec.model_name),
            "backdrop_name": rec.backdrop_name,
            "backdrop_norm": normalize_name(rec.backdrop_name),
            "type": rec.type_raw,
            "center_color": rec.center_color,
            "edge_color": rec.edge_color,
            "pattern_color": rec.pattern_color,
            "text_color": rec.text_color,
            "photo_url": rec.photo_url,
            "animation_url": rec.animation_url,
            "raw": rec.raw,
            "source_url": source_url,
            "last_seen_at": seen_at,
            "removed_at": None,
        }
        insert = pg_insert(GiftWikiMonochrome).values(fetched_at=seen_at, **values)
        upsert = insert.on_conflict_do_update(
            index_elements=[GiftWikiMonochrome.record_id],
            set_={k: v for k, v in values.items() if k != "record_id"},
        ).returning(GiftWikiMonochrome.fetched_at)
        fetched_at = (await session.execute(upsert)).scalar_one()
        if fetched_at == seen_at:
            added += 1
        await _upsert_attributes(session, key, rec, seen_at=seen_at, source_url=source_url)
    return added


async def _upsert_attributes(
    session: AsyncSession, key: str, rec: MonochromeRecord, *, seen_at: datetime, source_url: str
) -> None:
    items: list[tuple[str, str, dict[str, str | None]]] = []
    if rec.model_name:
        items.append(("model", rec.model_name, {}))
    if rec.backdrop_name:
        items.append(
            (
                "backdrop",
                rec.backdrop_name,
                {
                    "center_color": rec.center_color,
                    "edge_color": rec.edge_color,
                    "pattern_color": rec.pattern_color,
                    "text_color": rec.text_color,
                },
            )
        )
    for kind, name, details in items:
        stmt = pg_insert(GiftWikiAttribute).values(
            gift_id=key,
            kind=kind,
            name=name,
            name_norm=normalize_name(name),
            details=details,
            source_url=source_url,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_giftwiki_attributes_key",
            set_={"last_seen_at": seen_at, "details": details, "source_url": source_url},
        )
        await session.execute(stmt)


async def mark_removed(session: AsyncSession, key: str, keep_ids: set[str], *, now: datetime) -> int:
    """Soft-delete records of a gift that are absent from a complete fresh list."""
    stmt = (
        update(GiftWikiMonochrome)
        .where(
            GiftWikiMonochrome.gift_id == key,
            GiftWikiMonochrome.removed_at.is_(None),
            GiftWikiMonochrome.record_id.not_in(keep_ids)
            if keep_ids
            else GiftWikiMonochrome.record_id.is_not(None),
        )
        .values(removed_at=now)
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def clear_missing_gifts(session: AsyncSession, present_keys: set[str], *, now: datetime) -> int:
    """After a complete pagination: gifts absent from it lose their (removed) records."""
    stmt = select(GiftWikiGift.gift_id).where(GiftWikiGift.records_count > 0)
    missing = [key for key in (await session.execute(stmt)).scalars() if key not in present_keys]
    removed = 0
    for key in missing:
        removed += await mark_removed(session, key, set(), now=now)
        await session.execute(
            update(GiftWikiGift)
            .where(GiftWikiGift.gift_id == key)
            .values(records_count=0, coverage_complete=True, coverage_source="pagination", last_synced_at=now)
        )
    return removed


async def drop_name_placeholders(session: AsyncSession) -> None:
    """Remove name-keyed gifts once a real `gift_id` row exists for the same name (avoids ambiguity)."""
    real = select(GiftWikiGift.name_norm).where(~GiftWikiGift.gift_id.startswith("name:"))
    await session.execute(
        delete(GiftWikiGift).where(GiftWikiGift.gift_id.startswith("name:"), GiftWikiGift.name_norm.in_(real))
    )


async def load_snapshot(session: AsyncSession) -> ReferenceSnapshot:
    gifts = [
        GiftCoverage(
            gift_id=row.gift_id,
            gift_name=row.gift_name,
            records_count=row.records_count,
            complete=row.coverage_complete,
            synced_at=row.last_synced_at,
        )
        for row in (await session.execute(select(GiftWikiGift))).scalars()
    ]
    records = [
        RefRecord(
            record_id=row.record_id,
            gift_id=row.gift_id,
            gift_name=row.gift_name,
            model_name=row.model_name,
            backdrop_name=row.backdrop_name,
            type_raw=row.type,
            center_color=row.center_color,
            edge_color=row.edge_color,
            photo_url=row.photo_url,
        )
        for row in (
            await session.execute(select(GiftWikiMonochrome).where(GiftWikiMonochrome.removed_at.is_(None)))
        ).scalars()
    ]
    manual = {
        row.mrkt_collection_name: row.giftwiki_gift_id
        for row in (
            await session.execute(select(CollectionMapping).where(CollectionMapping.status == "manual"))
        ).scalars()
        if row.giftwiki_gift_id
    }
    success = await last_success(session)
    return ReferenceSnapshot.build(
        gifts, records, manual_mappings=manual, last_success_at=success.finished_at if success else None
    )


async def save_mapping(
    session: AsyncSession,
    mrkt_collection_name: str,
    *,
    gift_id: str | None,
    status: str,
    method: str | None,
    candidates: list[str],
    verified_by: int | None = None,
) -> None:
    now = datetime.now(UTC)
    values = {
        "giftwiki_gift_id": gift_id,
        "status": status,
        "method": method,
        "candidates": candidates,
        "checked_at": now,
        "verified_by": verified_by,
    }
    stmt = pg_insert(CollectionMapping).values(mrkt_collection_name=mrkt_collection_name[:128], **values)
    if status != "manual":
        # never overwrite a manual (admin-verified) mapping with an automatic one
        stmt = stmt.on_conflict_do_update(
            index_elements=[CollectionMapping.mrkt_collection_name],
            set_=values,
            where=CollectionMapping.status != "manual",
        )
    else:
        stmt = stmt.on_conflict_do_update(
            index_elements=[CollectionMapping.mrkt_collection_name], set_=values
        )
    await session.execute(stmt)


async def delete_mapping(session: AsyncSession, mrkt_collection_name: str) -> None:
    await session.execute(
        delete(CollectionMapping).where(CollectionMapping.mrkt_collection_name == mrkt_collection_name)
    )


async def mapping_counts(session: AsyncSession) -> dict[str, int]:
    stmt = select(CollectionMapping.status, func.count()).group_by(CollectionMapping.status)
    return {row[0]: int(row[1]) for row in (await session.execute(stmt)).all()}


async def list_mappings(session: AsyncSession) -> list[CollectionMapping]:
    return list(
        (
            await session.execute(select(CollectionMapping).order_by(CollectionMapping.mrkt_collection_name))
        ).scalars()
    )


async def gifts_overview(session: AsyncSession) -> list[GiftWikiGift]:
    stmt = select(GiftWikiGift).order_by(GiftWikiGift.records_count.desc(), GiftWikiGift.gift_name)
    return list((await session.execute(stmt)).scalars())


async def get_gift(session: AsyncSession, gift_id: str) -> GiftWikiGift | None:
    return await session.get(GiftWikiGift, gift_id)


async def records_of_gift(session: AsyncSession, gift_id: str) -> list[GiftWikiMonochrome]:
    stmt = (
        select(GiftWikiMonochrome)
        .where(GiftWikiMonochrome.gift_id == gift_id, GiftWikiMonochrome.removed_at.is_(None))
        .order_by(GiftWikiMonochrome.type, GiftWikiMonochrome.model_name, GiftWikiMonochrome.backdrop_name)
    )
    return list((await session.execute(stmt)).scalars())


async def counts(session: AsyncSession) -> tuple[int, int]:
    gifts = (await session.execute(select(func.count()).select_from(GiftWikiGift))).scalar_one()
    records = (
        await session.execute(
            select(func.count())
            .select_from(GiftWikiMonochrome)
            .where(GiftWikiMonochrome.removed_at.is_(None))
        )
    ).scalar_one()
    return int(gifts), int(records)
