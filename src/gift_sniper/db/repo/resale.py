"""Positions of the resale assistant: gifts it bought to sell again."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gift_sniper.db.models import ResalePosition
from gift_sniper.domain.enums import PurchaseRunMode, ResaleStatus

OPEN = [ResaleStatus.BOUGHT.value, ResaleStatus.WAITING.value, ResaleStatus.FAILED.value]


async def get(session: AsyncSession, position_id: int, *, lock: bool = False) -> ResalePosition | None:
    stmt = select(ResalePosition).where(ResalePosition.id == position_id)
    if lock:
        stmt = stmt.with_for_update()
    row: ResalePosition | None = (await session.execute(stmt)).scalar_one_or_none()
    return row


async def for_user(session: AsyncSession, user_id: int, limit: int = 30) -> list[ResalePosition]:
    stmt = (
        select(ResalePosition)
        .where(ResalePosition.user_id == user_id)
        .order_by(ResalePosition.created_at.desc(), ResalePosition.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def listed_with_gift(session: AsyncSession, gift_id: str) -> list[ResalePosition]:
    stmt = select(ResalePosition).where(
        ResalePosition.gift_id == gift_id,
        ResalePosition.status == ResaleStatus.LISTED.value,
        ResalePosition.run_mode == PurchaseRunMode.LIVE.value,
    )
    return list((await session.execute(stmt)).scalars())


async def to_list(
    session: AsyncSession, now: datetime, max_tries: int, limit: int = 20
) -> list[ResalePosition]:
    """Live positions not on sale yet that may be listed now (oldest first)."""
    stmt = (
        select(ResalePosition)
        .where(
            ResalePosition.run_mode == PurchaseRunMode.LIVE.value,
            ResalePosition.status.in_(OPEN),
            ResalePosition.tries < max_tries,
            (ResalePosition.resale_at.is_(None)) | (ResalePosition.resale_at <= now),
        )
        .order_by(ResalePosition.updated_at)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def totals(session: AsyncSession, user_id: int) -> dict[str, tuple[int, int]]:
    """status -> (number of positions, expected or real profit of them) for one user."""
    profit = func.coalesce(
        func.sum(func.coalesce(ResalePosition.list_price_nano, 0) - ResalePosition.buy_price_nano),
        0,
    )
    stmt = (
        select(ResalePosition.status, func.count(), profit)
        .where(ResalePosition.user_id == user_id)
        .group_by(ResalePosition.status)
    )
    return {str(s): (int(n), int(p)) for s, n, p in (await session.execute(stmt)).all()}
