from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gift_sniper.db.models import Filter, FilterHit, Purchase, PurchaseAttempt
from gift_sniper.domain.enums import FilterKind, PurchaseStatus
from gift_sniper.services.filters import FilterCriteria, FilterLimits, FilterSpec

MAX_FILTERS_PER_USER = 30
# Mini App collection plans (filters with picks): at most two per collection, regular and monochrome
MAX_PLANS_PER_USER = 300


def is_plan(row: Filter) -> bool:
    """A filter managed by the Mini App: per-collection picks of models and backdrops with their prices."""
    return bool((row.criteria or {}).get("picks"))


def is_assistant(row: Filter) -> bool:
    """The resale assistant's settings: a filter with resale rules (one per user, set in the Mini App)."""
    return (row.criteria or {}).get("resale") is not None


def managed(row: Filter) -> bool:
    return is_plan(row) or is_assistant(row)


def without_plans(rows: list[Filter]) -> tuple[list[Filter], int]:
    """Filters for the chat interface and the number of Mini App plans (and the assistant) left out of it."""
    kept = [r for r in rows if not managed(r)]
    return kept, len(rows) - len(kept)


def to_spec(row: Filter) -> FilterSpec:
    return FilterSpec(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        kind=FilterKind(row.kind),
        enabled=row.enabled,
        autobuy=row.autobuy,
        criteria=FilterCriteria.model_validate(row.criteria or {}),
        limits=FilterLimits.model_validate(row.limits or {}),
        activated_at=row.activated_at,
    )


async def list_filters(session: AsyncSession, user_id: int, kind: FilterKind | None = None) -> list[Filter]:
    stmt = select(Filter).where(Filter.user_id == user_id).order_by(Filter.id)
    if kind is not None:
        stmt = stmt.where(Filter.kind == kind.value)
    return list((await session.execute(stmt)).scalars())


async def get_filter(session: AsyncSession, user_id: int, filter_id: int) -> Filter | None:
    row = await session.get(Filter, filter_id)
    if row is None or row.user_id != user_id:
        return None
    return row


async def assistant_filter(session: AsyncSession, user_id: int) -> Filter | None:
    return next((r for r in await list_filters(session, user_id) if is_assistant(r)), None)


async def _check_room(session: AsyncSession, user_id: int, *, plan: bool) -> None:
    rows = await list_filters(session, user_id)
    plans = sum(1 for r in rows if managed(r))
    if plan and plans >= MAX_PLANS_PER_USER:
        raise ValueError(f"Не больше {MAX_PLANS_PER_USER} правил мини-приложения на пользователя")
    if not plan and len(rows) - plans >= MAX_FILTERS_PER_USER:
        raise ValueError(f"Не больше {MAX_FILTERS_PER_USER} фильтров на пользователя")


async def create_filter(
    session: AsyncSession, user_id: int, name: str, kind: FilterKind, *, plan: bool = False
) -> Filter:
    await _check_room(session, user_id, plan=plan)
    row = Filter(
        user_id=user_id,
        name=name[:64],
        kind=kind.value,
        enabled=False,
        autobuy=False,
        criteria=FilterCriteria().model_dump(),
        limits=FilterLimits().model_dump(),
    )
    session.add(row)
    await session.flush()
    return row


async def copy_filter(session: AsyncSession, source: Filter) -> Filter:
    await _check_room(session, source.user_id, plan=managed(source))
    row = Filter(
        user_id=source.user_id,
        name=(f"{source.name} (копия)")[:64],
        kind=source.kind,
        enabled=False,  # a copy starts disabled so it never buys unexpectedly
        autobuy=False,
        criteria=dict(source.criteria or {}),
        limits=dict(source.limits or {}),
    )
    session.add(row)
    await session.flush()
    return row


def set_enabled(row: Filter, enabled: bool) -> None:
    if enabled and not row.enabled:
        row.activated_at = datetime.now(UTC)
    row.enabled = enabled


def update_criteria(row: Filter, criteria: FilterCriteria) -> None:
    row.criteria = criteria.model_dump()


def update_limits(row: Filter, limits: FilterLimits) -> None:
    row.limits = limits.model_dump()


async def delete_filter(session: AsyncSession, row: Filter) -> None:
    await session.execute(delete(Filter).where(Filter.id == row.id))


async def load_enabled_specs(session: AsyncSession) -> list[FilterSpec]:
    rows = (
        await session.execute(select(Filter).where(Filter.enabled.is_(True)).order_by(Filter.id))
    ).scalars()
    return [to_spec(r) for r in rows]


async def filter_stats(session: AsyncSession, filter_id: int) -> dict[str, int]:
    hits = (
        await session.execute(
            select(func.count()).select_from(FilterHit).where(FilterHit.filter_id == filter_id)
        )
    ).scalar_one()
    attempts = (
        await session.execute(
            select(func.count()).select_from(PurchaseAttempt).where(PurchaseAttempt.filter_id == filter_id)
        )
    ).scalar_one()
    confirmed, spent = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Purchase.price_nano), 0)).where(
                Purchase.filter_id == filter_id
            )
        )
    ).one()
    dry = (
        await session.execute(
            select(func.count())
            .select_from(PurchaseAttempt)
            .where(
                PurchaseAttempt.filter_id == filter_id, PurchaseAttempt.status == PurchaseStatus.DRY_RUN.value
            )
        )
    ).scalar_one()
    return {
        "hits": int(hits or 0),
        "attempts": int(attempts or 0),
        "confirmed": int(confirmed or 0),
        "spent_nano": int(spent or 0),
        "dry_run": int(dry or 0),
    }
