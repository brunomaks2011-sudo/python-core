from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import Settings
from gift_sniper.db.models import Purchase, PurchaseAttempt
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import giftwiki as giftwiki_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import BudgetScope, FilterKind, PurchaseMode
from gift_sniper.domain.types import MonochromeRecord
from gift_sniper.services.control import ControlService
from gift_sniper.services.enrichment import Enricher, ReferenceStore
from gift_sniper.services.filter_cache import FilterCache
from gift_sniper.services.filters import FilterCriteria, FilterLimits
from gift_sniper.services.floors import FloorService
from gift_sniper.services.notifications import Notifier
from gift_sniper.services.purchase import PurchaseRequest, PurchaseService
from tests.factories import TON, FakeMrkt, RecordingSender, make_settings

pytestmark = pytest.mark.db


@dataclass
class Env:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Any
    mrkt: FakeMrkt
    control: ControlService
    store: ReferenceStore
    enricher: Enricher
    sender: RecordingSender
    notifier: Notifier
    service: PurchaseService
    filter_cache: FilterCache

    async def add_user(
        self,
        user_id: int,
        *,
        can_purchase: bool = True,
        autobuy: bool = True,
        mono: bool = True,
        per_purchase: int | None = 100 * TON,
        daily: int | None = 1000 * TON,
        total: int | None = 10_000 * TON,
        notify: dict[str, Any] | None = None,
    ) -> None:
        async with self.sessionmaker() as session, session.begin():
            await users_repo.ensure_user(
                session,
                user_id,
                username=f"u{user_id}",
                full_name=None,
                is_admin=False,
                can_purchase=can_purchase,
            )
            prefs = await users_repo.get_settings(session, user_id)
            prefs.autobuy_enabled = autobuy
            prefs.monochrome_autobuy_enabled = mono
            prefs.notify = notify or {}
            budget = await users_repo.get_or_create_budget(session, user_id, BudgetScope.USER)
            budget.per_purchase_limit_nano = per_purchase
            budget.daily_limit_nano = daily
            budget.total_limit_nano = total

    async def set_mode_budget(self, user_id: int, scope: BudgetScope, **values: Any) -> None:
        async with self.sessionmaker() as session, session.begin():
            budget = await users_repo.get_or_create_budget(session, user_id, scope)
            for key, value in values.items():
                setattr(budget, key, value)

    async def add_filter(
        self,
        user_id: int,
        kind: FilterKind = FilterKind.REGULAR,
        *,
        name: str = "f",
        autobuy: bool = True,
        criteria: dict[str, Any] | None = None,
        limits: dict[str, Any] | None = None,
    ) -> int:
        async with self.sessionmaker() as session, session.begin():
            row = await filters_repo.create_filter(session, user_id, name, kind)
            filters_repo.set_enabled(row, True)
            row.activated_at = datetime(2000, 1, 1, tzinfo=UTC)
            row.autobuy = autobuy
            filters_repo.update_criteria(row, FilterCriteria.model_validate(criteria or {}))
            filters_repo.update_limits(row, FilterLimits.model_validate(limits or {}))
            await session.flush()
            filter_id = row.id
        await self.filter_cache.invalidate()
        return filter_id

    async def add_giftwiki(
        self,
        gift_name: str,
        pairs: list[tuple[str, str, str]],
        *,
        gift_id: str = "gw-1",
        complete: bool = True,
    ) -> None:
        now = datetime.now(UTC)
        records = [
            MonochromeRecord(
                record_id=f"{gift_id}-{i}",
                gift_id=gift_id,
                gift_name=gift_name,
                model_name=m,
                backdrop_name=b,
                type_raw=t,
                raw={"_id": f"{gift_id}-{i}"},
            )
            for i, (m, b, t) in enumerate(pairs)
        ]
        async with self.sessionmaker() as session, session.begin():
            await giftwiki_repo.upsert_gift(
                session,
                gift_id,
                gift_name,
                records_count=len(records),
                complete=complete,
                coverage_source="gift_lookup",
                synced_at=now,
                source_url="test",
            )
            await giftwiki_repo.upsert_records(session, gift_id, records, seen_at=now, source_url="test")
            run = await giftwiki_repo.start_run(session, "test")
            run.status = "success"
            run.finished_at = now
        await self.store.reload()

    def request(
        self,
        user_id: int,
        gift_id: str,
        price: int,
        *,
        filter_id: int | None = None,
        mode: PurchaseMode = PurchaseMode.REGULAR,
        trigger: str = "auto",
        event_type: str = "listing",
    ) -> PurchaseRequest:
        return PurchaseRequest(
            user_id=user_id,
            gift_id=gift_id,
            expected_price_nano=price,
            mode=mode,
            filter_id=filter_id,
            trigger=trigger,
            event_type=event_type,
            first_sighting=True,
            detected_at=datetime.now(UTC),
        )

    async def attempts(self) -> list[PurchaseAttempt]:
        async with self.sessionmaker() as session:
            return list(
                (await session.execute(select(PurchaseAttempt).order_by(PurchaseAttempt.id))).scalars()
            )

    async def purchases_count(self) -> int:
        async with self.sessionmaker() as session:
            return int((await session.execute(select(func.count()).select_from(Purchase))).scalar_one())


@pytest_asyncio.fixture
async def env(sessionmaker: async_sessionmaker[AsyncSession], redis: Any) -> Env:
    settings = make_settings()
    mrkt = FakeMrkt()
    control = ControlService(settings, redis, sessionmaker)
    store = ReferenceStore(sessionmaker, redis, settings.redis_prefix)
    await store.reload()
    enricher = Enricher(settings, store, sessionmaker, cache_ttl=0)
    sender = RecordingSender()
    notifier = Notifier(settings, sender, sessionmaker, redis)
    service = PurchaseService(
        settings,
        sessionmaker,
        redis,
        mrkt,  # type: ignore[arg-type]
        control,
        enricher,
        notifier,
        floors=FloorService(mrkt),
    )

    async def no_sleep(_: float) -> None:
        return None

    service.sleep = no_sleep  # type: ignore[assignment]
    filter_cache = FilterCache(sessionmaker, redis, settings.redis_prefix, ttl=0)
    return Env(
        settings, sessionmaker, redis, mrkt, control, store, enricher, sender, notifier, service, filter_cache
    )
