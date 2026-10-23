"""Notifications dedup, error log, audit log and persistent bot state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from gift_sniper.db.models import AuditLog, BotState, ErrorLog, Notification


async def claim_notification(
    session: AsyncSession, *, user_id: int, kind: str, dedup_key: str, listing_id: int | None
) -> bool:
    """Reserve a dedup key; False when this notification was already sent."""
    stmt = (
        pg_insert(Notification)
        .values(
            user_id=user_id, kind=kind[:32], dedup_key=dedup_key[:256], listing_id=listing_id, status="sent"
        )
        .on_conflict_do_nothing(constraint="uq_notifications_user_dedup")
        .returning(Notification.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def set_notification_status(
    session: AsyncSession, *, user_id: int, dedup_key: str, status: str
) -> None:
    row = (
        await session.execute(
            select(Notification).where(
                Notification.user_id == user_id, Notification.dedup_key == dedup_key[:256]
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        row.status = status[:16]


async def log_error(
    session: AsyncSession, component: str, message: str, *, level: str = "ERROR", **context: Any
) -> None:
    session.add(
        ErrorLog(
            component=component[:64], level=level[:16], message=message[:4000], context=_jsonable(context)
        )
    )


async def audit(session: AsyncSession, action: str, *, user_id: int | None = None, **details: Any) -> None:
    session.add(AuditLog(user_id=user_id, action=action[:64], details=_jsonable(details)))


async def recent_errors(session: AsyncSession, limit: int = 10) -> list[ErrorLog]:
    return list((await session.execute(select(ErrorLog).order_by(ErrorLog.id.desc()).limit(limit))).scalars())


async def get_state(session: AsyncSession, key: str) -> dict[str, Any] | None:
    row = await session.get(BotState, key)
    return dict(row.value) if row else None


async def set_state(session: AsyncSession, key: str, value: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    stmt = pg_insert(BotState).values(key=key, value=value, updated_at=now)
    stmt = stmt.on_conflict_do_update(index_elements=[BotState.key], set_={"value": value, "updated_at": now})
    await session.execute(stmt)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
