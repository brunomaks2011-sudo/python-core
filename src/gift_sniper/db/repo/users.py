from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from gift_sniper.db.models import Budget, User, UserSettings
from gift_sniper.domain.enums import BudgetScope


async def ensure_user(
    session: AsyncSession,
    user_id: int,
    *,
    username: str | None,
    full_name: str | None,
    is_admin: bool,
    can_purchase: bool,
) -> User:
    now = datetime.now(UTC)
    stmt = (
        pg_insert(User)
        .values(
            id=user_id,
            username=username,
            full_name=full_name,
            is_admin=is_admin,
            can_purchase=can_purchase,
            last_seen_at=now,
        )
        .on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "username": username,
                "full_name": full_name,
                "is_admin": is_admin,
                "can_purchase": can_purchase,
                "is_blocked": False,
                "last_seen_at": now,
            },
        )
        .returning(User)
    )
    user = (await session.execute(stmt)).scalar_one()
    await session.execute(
        pg_insert(UserSettings)
        .values(user_id=user_id, notify={})
        .on_conflict_do_nothing(index_elements=[UserSettings.user_id])
    )
    return user


async def ensure_admin(session: AsyncSession, user_id: int, *, can_purchase: bool) -> None:
    """Create the admin row if missing without touching profile data of an existing user."""
    await session.execute(
        pg_insert(User)
        .values(id=user_id, is_admin=True, can_purchase=can_purchase)
        .on_conflict_do_update(
            index_elements=[User.id], set_={"is_admin": True, "can_purchase": can_purchase}
        )
    )
    await session.execute(
        pg_insert(UserSettings)
        .values(user_id=user_id, notify={})
        .on_conflict_do_nothing(index_elements=[UserSettings.user_id])
    )


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_settings(session: AsyncSession, user_id: int) -> UserSettings:
    settings = await session.get(UserSettings, user_id)
    if settings is None:
        await session.execute(
            pg_insert(UserSettings)
            .values(user_id=user_id, notify={})
            .on_conflict_do_nothing(index_elements=[UserSettings.user_id])
        )
        settings = await session.get(UserSettings, user_id)
    assert settings is not None
    return settings


async def mark_blocked(session: AsyncSession, user_id: int) -> None:
    user = await session.get(User, user_id)
    if user is not None:
        user.is_blocked = True


async def list_active_users(session: AsyncSession) -> list[User]:
    return list((await session.execute(select(User).where(User.is_blocked.is_(False)))).scalars())


async def get_budgets(session: AsyncSession, user_id: int) -> dict[BudgetScope, Budget]:
    rows = (await session.execute(select(Budget).where(Budget.user_id == user_id))).scalars()
    return {BudgetScope(row.scope): row for row in rows}


async def get_or_create_budget(session: AsyncSession, user_id: int, scope: BudgetScope) -> Budget:
    await session.execute(
        pg_insert(Budget)
        .values(user_id=user_id, scope=scope.value)
        .on_conflict_do_nothing(constraint="uq_budgets_user_scope")
    )
    budget = (
        await session.execute(select(Budget).where(Budget.user_id == user_id, Budget.scope == scope.value))
    ).scalar_one()
    return budget
