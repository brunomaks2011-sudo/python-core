"""Purchase attempts, confirmed purchases and budget usage aggregates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gift_sniper.db.models import Purchase, PurchaseAttempt
from gift_sniper.domain.enums import (
    ACTIVE_LIVE_STATUSES,
    BUDGET_CONSUMING_STATUSES,
    PurchaseMode,
    PurchaseRunMode,
    PurchaseStatus,
)
from gift_sniper.services.budget import Usage

_CONSUMING = [s.value for s in BUDGET_CONSUMING_STATUSES]


def _spend_statuses(run_mode: PurchaseRunMode) -> list[str]:
    return _CONSUMING if run_mode is PurchaseRunMode.LIVE else [PurchaseStatus.DRY_RUN.value]


async def usage(
    session: AsyncSession,
    *,
    user_id: int,
    run_mode: PurchaseRunMode,
    day_start: datetime,
    mode: PurchaseMode | None = None,
    filter_id: int | None = None,
    period_hours: int | None = None,
) -> Usage:
    amount = func.coalesce(PurchaseAttempt.final_price_nano, PurchaseAttempt.expected_price_nano)
    conditions: list[Any] = [
        PurchaseAttempt.user_id == user_id,
        PurchaseAttempt.run_mode == run_mode.value,
        PurchaseAttempt.status.in_(_spend_statuses(run_mode)),
    ]
    if mode is not None:
        conditions.append(PurchaseAttempt.mode == mode.value)
    if filter_id is not None:
        conditions.append(PurchaseAttempt.filter_id == filter_id)
    period_start = datetime.now(UTC) - timedelta(hours=period_hours) if period_hours else datetime.now(UTC)
    stmt = select(
        func.coalesce(func.sum(amount), 0),
        func.coalesce(func.sum(amount).filter(PurchaseAttempt.created_at >= day_start), 0),
        func.count(),
        func.count().filter(PurchaseAttempt.created_at >= period_start),
    ).where(*conditions)
    total, daily, count, period_count = (await session.execute(stmt)).one()
    return Usage(
        total_spent=int(total),
        daily_spent=int(daily),
        total_count=int(count),
        period_count=int(period_count) if period_hours else 0,
    )


async def has_active_attempt(
    session: AsyncSession, *, gift_id: str, run_mode: PurchaseRunMode, user_id: int
) -> bool:
    if run_mode is PurchaseRunMode.LIVE:
        cond = [
            PurchaseAttempt.gift_id == gift_id,
            PurchaseAttempt.run_mode == PurchaseRunMode.LIVE.value,
            PurchaseAttempt.status.in_([s.value for s in ACTIVE_LIVE_STATUSES]),
        ]
    else:
        cond = [
            PurchaseAttempt.gift_id == gift_id,
            PurchaseAttempt.user_id == user_id,
            PurchaseAttempt.run_mode == PurchaseRunMode.DRY_RUN.value,
            PurchaseAttempt.status == PurchaseStatus.DRY_RUN.value,
        ]
    stmt = select(func.count()).select_from(PurchaseAttempt).where(*cond)
    return int((await session.execute(stmt)).scalar_one()) > 0


async def attempts_for_gift(session: AsyncSession, gift_id: str) -> list[PurchaseAttempt]:
    stmt = select(PurchaseAttempt).where(PurchaseAttempt.gift_id == gift_id).order_by(PurchaseAttempt.id)
    return list((await session.execute(stmt)).scalars())


async def set_status(
    session: AsyncSession,
    attempt_id: int,
    status: PurchaseStatus,
    *,
    reason: str | None = None,
    final_price_nano: int | None = None,
    response: Any = None,
    verification: Any = None,
    submitted: bool = False,
    finished: bool = False,
) -> None:
    values: dict[str, Any] = {"status": status.value}
    if reason is not None:
        values["reason"] = reason[:2000]
    if final_price_nano is not None:
        values["final_price_nano"] = final_price_nano
    if response is not None:
        values["response"] = response if isinstance(response, dict) else {"data": response}
    if verification is not None:
        values["verification"] = verification
    now = datetime.now(UTC)
    if submitted:
        values["submitted_at"] = now
    if finished:
        values["finished_at"] = now
    await session.execute(update(PurchaseAttempt).where(PurchaseAttempt.id == attempt_id).values(**values))


async def add_purchase(
    session: AsyncSession, attempt: PurchaseAttempt, *, price_nano: int | None, source: str, response: Any
) -> Purchase:
    existing = (
        await session.execute(select(Purchase).where(Purchase.attempt_id == attempt.id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    purchase = Purchase(
        attempt_id=attempt.id,
        user_id=attempt.user_id,
        filter_id=attempt.filter_id,
        mode=attempt.mode,
        gift_id=attempt.gift_id,
        collection_name=attempt.collection_name,
        model_name=attempt.model_name,
        price_nano=price_nano,
        confirmation_source=source,
        mrkt_response=response if isinstance(response, dict) else {"data": response},
    )
    session.add(purchase)
    await session.flush()
    return purchase


async def list_attempts(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 10,
    offset: int = 0,
    statuses: list[str] | None = None,
) -> list[PurchaseAttempt]:
    stmt = select(PurchaseAttempt).where(PurchaseAttempt.user_id == user_id)
    if statuses:
        stmt = stmt.where(PurchaseAttempt.status.in_(statuses))
    stmt = stmt.order_by(PurchaseAttempt.id.desc()).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())


async def attempts_in_status(
    session: AsyncSession,
    statuses: list[PurchaseStatus],
    *,
    older_than: datetime | None = None,
    limit: int = 50,
) -> list[PurchaseAttempt]:
    stmt = select(PurchaseAttempt).where(PurchaseAttempt.status.in_([s.value for s in statuses]))
    if older_than is not None:
        stmt = stmt.where(PurchaseAttempt.updated_at < older_than)
    stmt = stmt.order_by(PurchaseAttempt.id).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def get_attempt(session: AsyncSession, attempt_id: int) -> PurchaseAttempt | None:
    return await session.get(PurchaseAttempt, attempt_id)
