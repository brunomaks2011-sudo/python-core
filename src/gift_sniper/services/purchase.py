"""Purchase execution with double-purchase protection and verification of uncertain outcomes.

Order of operations for one request:
 1. global checks: run mode, emergency stop, user rights and toggles;
 2. Redis lock on the MRKT gift id (one purchase flow per gift across all workers/processes);
 3. database check: no active attempt for the gift (partial unique index enforces it as well);
 4. fresh re-check of the listing on MRKT: still on sale, current price, attributes;
 5. re-evaluation of the filter (and monochrome status for the monochrome mode) on the fresh data;
 6. budget reservation in one transaction under a per-user row lock;
 7. dry run -> record "would buy"; live -> balance check, emergency stop check, buy request;
 8. CONFIRMED / REJECTED are final; UNCERTAIN is verified (gift ownership) before any retry.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import RunMode, Settings
from gift_sniper.db.models import Budget, PurchaseAttempt, User
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import misc
from gift_sniper.db.repo import purchases as purchases_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import (
    BudgetScope,
    FilterKind,
    MonochromeStatus,
    PurchaseMode,
    PurchaseRunMode,
    PurchaseStatus,
)
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.types import Enrichment, ListingSnapshot
from gift_sniper.integrations.mrkt import BuyOutcomeKind, MrktClient, MrktError
from gift_sniper.metrics import PURCHASES
from gift_sniper.services import texts
from gift_sniper.services.budget import Limits, ScopeState, check_purchase, remaining
from gift_sniper.services.control import ControlService
from gift_sniper.services.enrichment import Enricher
from gift_sniper.services.filters import FilterSpec, MatchContext, evaluate
from gift_sniper.services.locks import RedisLock
from gift_sniper.services.notifications import Notifier
from gift_sniper.services.user_prefs import NotificationSettings

log = logging.getLogger(__name__)

# Redis lock held by the purchase flow running in the current task (extended before a retry).
_CURRENT_LOCK: ContextVar[RedisLock | None] = ContextVar("purchase_lock", default=None)


@dataclass(slots=True)
class PurchaseRequest:
    user_id: int
    gift_id: str
    expected_price_nano: int
    mode: PurchaseMode
    filter_id: int | None = None
    listing_id: int | None = None
    trigger: str = "auto"  # auto | manual
    event_type: str = "listing"
    first_sighting: bool = True
    detected_at: datetime | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "gift_id": self.gift_id,
            "expected_price_nano": self.expected_price_nano,
            "mode": self.mode.value,
            "filter_id": self.filter_id,
            "listing_id": self.listing_id,
            "trigger": self.trigger,
            "event_type": self.event_type,
            "first_sighting": self.first_sighting,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> PurchaseRequest:
        detected = data.get("detected_at")
        return cls(
            user_id=int(data["user_id"]),
            gift_id=str(data["gift_id"]),
            expected_price_nano=int(data["expected_price_nano"]),
            mode=PurchaseMode(data["mode"]),
            filter_id=int(data["filter_id"]) if data.get("filter_id") is not None else None,
            listing_id=int(data["listing_id"]) if data.get("listing_id") is not None else None,
            trigger=str(data.get("trigger") or "auto"),
            event_type=str(data.get("event_type") or "listing"),
            first_sighting=bool(data.get("first_sighting", True)),
            detected_at=datetime.fromisoformat(detected) if detected else None,
        )


@dataclass(slots=True)
class PurchaseResult:
    status: PurchaseStatus | None  # None: skipped before an attempt was recorded
    reason: str
    attempt_id: int | None = None
    price_nano: int | None = None


@dataclass(slots=True)
class Verification:
    outcome: str  # confirmed | not_executed | sold_to_other | inconclusive
    detail: str
    observations: list[dict[str, Any]]


class PurchaseService:
    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        mrkt: MrktClient,
        control: ControlService,
        enricher: Enricher,
        notifier: Notifier | None,
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.mrkt = mrkt
        self.control = control
        self.enricher = enricher
        self.notifier = notifier
        self.sleep = asyncio.sleep  # replaced in tests

    # ================================================================== entry point
    async def execute(self, req: PurchaseRequest) -> PurchaseResult:
        run_mode = await self.control.run_mode()
        if run_mode is RunMode.NOTIFY_ONLY:
            return PurchaseResult(None, "Режим только уведомлений: модуль покупок отключён")
        if await self.control.is_stopped():
            return PurchaseResult(None, "Аварийная остановка автоматических покупок активна")
        prun = PurchaseRunMode.LIVE if run_mode is RunMode.LIVE else PurchaseRunMode.DRY_RUN

        lock = RedisLock(
            self.redis,
            f"{self.settings.redis_prefix}:lock:purchase:{req.gift_id}",
            self.settings.purchase_lock_ttl_seconds,
        )
        if not await lock.acquire():
            return PurchaseResult(None, "Покупка этого подарка уже обрабатывается другой задачей")
        token = _CURRENT_LOCK.set(lock)
        try:
            result = await self._run(req, prun, attempt_no=1)
        finally:
            _CURRENT_LOCK.reset(token)
            await lock.release()
        if result.status is not None:
            PURCHASES.labels(prun.value, result.status.value).inc()
        return result

    # ================================================================== main flow
    async def _run(self, req: PurchaseRequest, prun: PurchaseRunMode, attempt_no: int) -> PurchaseResult:
        async with self.sessionmaker() as session:
            user = await users_repo.get_user(session, req.user_id)
            prefs_row = await users_repo.get_settings(session, req.user_id)
            filter_row = (
                await filters_repo.get_filter(session, req.user_id, req.filter_id) if req.filter_id else None
            )
            duplicate = await purchases_repo.has_active_attempt(
                session, gift_id=req.gift_id, run_mode=prun, user_id=req.user_id
            )
        prefs = NotificationSettings.model_validate(prefs_row.notify or {})
        if duplicate:
            return PurchaseResult(None, "Подарок уже куплен или покупка уже выполняется")
        if user is None or not user.can_purchase:
            return PurchaseResult(None, "У пользователя нет прав на покупки")
        if prefs_row.purchases_paused and req.trigger != "manual":
            return PurchaseResult(None, "Автоматические покупки приостановлены пользователем")

        spec: FilterSpec | None = filters_repo.to_spec(filter_row) if filter_row else None
        refusal = self._mode_refusal(
            req, spec, prefs_row.autobuy_enabled, prefs_row.monochrome_autobuy_enabled
        )
        if refusal:
            return PurchaseResult(None, refusal)

        # ---- fresh re-check on MRKT
        fresh, problem = await self._fresh_listing(req)
        if fresh is None:
            return await self._record_cancelled(req, prun, spec, None, problem, attempt_no, prefs)
        enrichment = await self.enricher.enrich(fresh)
        problem = self._recheck_problem(req, spec, fresh, enrichment)
        if problem:
            return await self._record_cancelled(
                req, prun, spec, fresh, problem, attempt_no, prefs, enrichment
            )
        price = fresh.price_nano
        assert price is not None

        # ---- budget reservation (atomic)
        attempt_id, reasons = await self._reserve(req, prun, spec, fresh, enrichment, price, attempt_no)
        if attempt_id is None:
            if reasons == ["duplicate"]:
                return PurchaseResult(None, "Подарок уже куплен или покупка уже выполняется")
            result = PurchaseResult(PurchaseStatus.CANCELLED, "Лимиты: " + "; ".join(reasons))
            # automatic triggers: at most one "limits reached" message per day and scope
            dedup = None
            if req.trigger != "manual":
                day = self._day_start().date().isoformat()
                dedup = f"limits:{req.mode.value}:{req.filter_id}:{day}"
            return await self._notify_result(req, spec, fresh, result, prefs, dedup_key=dedup)

        if prun is PurchaseRunMode.DRY_RUN:
            async with self.sessionmaker() as session, session.begin():
                await purchases_repo.set_status(
                    session,
                    attempt_id,
                    PurchaseStatus.DRY_RUN,
                    reason="Тестовый режим: была бы куплена",
                    final_price_nano=price,
                    finished=True,
                )
            result = PurchaseResult(PurchaseStatus.DRY_RUN, "Тестовый режим", attempt_id, price)
            return await self._notify_result(req, spec, fresh, result, prefs)

        return await self._submit(req, prun, spec, fresh, price, attempt_id, attempt_no, prefs)

    def _mode_refusal(
        self, req: PurchaseRequest, spec: FilterSpec | None, regular_on: bool, mono_on: bool
    ) -> str | None:
        if req.mode is PurchaseMode.MANUAL:
            return None
        if spec is None:
            return "Фильтр не найден"
        if not spec.enabled or not spec.autobuy:
            return "Автопокупка по фильтру выключена"
        if req.mode is PurchaseMode.REGULAR:
            if spec.kind is not FilterKind.REGULAR:
                return "Фильтр не относится к обычной автопокупке"
            if not regular_on:
                return "Автопокупка подарков выключена"
        if req.mode is PurchaseMode.MONOCHROME:
            if spec.kind is not FilterKind.MONOCHROME:
                return "Фильтр не относится к автопокупке монохромов"
            if not mono_on:
                return "Автопокупка монохромов выключена"
        return None

    async def _fresh_listing(self, req: PurchaseRequest) -> tuple[ListingSnapshot | None, str]:
        try:
            fresh = await self.mrkt.get_gift(req.gift_id)
        except MrktError as exc:
            return None, f"Не удалось перепроверить объявление на MRKT: {exc}"
        if fresh is None:
            return None, "Объявление не найдено на MRKT"
        if fresh.is_on_sale is not True:
            return None, "Объявление снято с продажи или продано"
        if fresh.is_on_auction:
            return None, "Подарок выставлен на аукцион, мгновенная покупка недоступна"
        if fresh.is_mine:
            return None, "Подарок уже принадлежит этому аккаунту"
        if fresh.price_nano is None:
            return None, "MRKT не вернул цену"
        return fresh, ""

    def _recheck_problem(
        self, req: PurchaseRequest, spec: FilterSpec | None, fresh: ListingSnapshot, enrichment: Enrichment
    ) -> str:
        price = fresh.price_nano
        assert price is not None
        if req.mode is PurchaseMode.MANUAL:
            if price > req.expected_price_nano:
                return (
                    f"Цена выросла: {format_ton(req.expected_price_nano)} → {format_ton(price)}. "
                    "Подтвердите покупку заново"
                )
            return ""
        assert spec is not None
        ctx = MatchContext(
            event_type=req.event_type,
            detected_at=req.detected_at or datetime.now(UTC),
            is_first_sighting=req.first_sighting,
        )
        match = evaluate(spec.kind, spec.criteria, fresh, enrichment, ctx, activated_at=spec.activated_at)
        if not match.matched:
            return "При повторной проверке не подходит под фильтр: " + "; ".join(match.failed)
        if req.mode is PurchaseMode.MONOCHROME:
            if enrichment.verdict.status is not MonochromeStatus.MONOCHROME:
                return "Монохром не подтверждён Gift Wiki"
            age = enrichment.giftwiki_data_age_hours
            if age is None or age > self.settings.monochrome_autobuy_max_data_age_hours:
                return "Данные Gift Wiki устарели для автопокупки монохромов"
        return ""

    # ================================================================== budget
    def _day_start(self) -> datetime:
        now_local = datetime.now(self.settings.tz)
        return now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    @staticmethod
    def _limits(budget: Budget | None) -> Limits:
        if budget is None:
            return Limits()
        return Limits(
            per_purchase=budget.per_purchase_limit_nano,
            daily=budget.daily_limit_nano,
            total=budget.total_limit_nano,
            period_count=budget.period_max_count,
            period_hours=budget.period_hours,
        )

    async def scope_states(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        prun: PurchaseRunMode,
        mode: PurchaseMode,
        spec: FilterSpec | None,
    ) -> tuple[ScopeState, ScopeState | None, ScopeState | None]:
        budgets = await users_repo.get_budgets(session, user_id)
        day_start = self._day_start()
        user_limits = self._limits(budgets.get(BudgetScope.USER))
        user_state = ScopeState(
            "Общий лимит",
            user_limits,
            await purchases_repo.usage(session, user_id=user_id, run_mode=prun, day_start=day_start),
        )
        mode_state = None
        if mode in (PurchaseMode.REGULAR, PurchaseMode.MONOCHROME):
            scope = BudgetScope.REGULAR if mode is PurchaseMode.REGULAR else BudgetScope.MONOCHROME
            limits = self._limits(budgets.get(scope))
            label = "Режим подарков" if mode is PurchaseMode.REGULAR else "Режим монохромов"
            mode_state = ScopeState(
                label,
                limits,
                await purchases_repo.usage(
                    session,
                    user_id=user_id,
                    run_mode=prun,
                    day_start=day_start,
                    mode=mode,
                    period_hours=limits.period_hours,
                ),
            )
        filter_state = None
        if spec is not None:
            fl = spec.limits
            limits = Limits(
                per_purchase=fl.max_price_per_gift_nano,
                per_operation=fl.max_per_operation_nano,
                daily=fl.daily_limit_nano,
                total=fl.total_limit_nano,
                max_count=fl.max_count,
                period_count=fl.period_max_count,
                period_hours=fl.period_hours,
            )
            filter_state = ScopeState(
                f"Фильтр «{spec.name}»",
                limits,
                await purchases_repo.usage(
                    session,
                    user_id=user_id,
                    run_mode=prun,
                    day_start=day_start,
                    filter_id=spec.id,
                    period_hours=fl.period_hours,
                ),
            )
        return user_state, mode_state, filter_state

    async def _reserve(
        self,
        req: PurchaseRequest,
        prun: PurchaseRunMode,
        spec: FilterSpec | None,
        fresh: ListingSnapshot,
        enrichment: Enrichment,
        price: int,
        attempt_no: int,
    ) -> tuple[int | None, list[str]]:
        try:
            async with self.sessionmaker() as session, session.begin():
                # serialize budget decisions of one user (concurrent workers, filters, modes)
                await session.execute(select(User.id).where(User.id == req.user_id).with_for_update())
                user_state, mode_state, filter_state = await self.scope_states(
                    session, user_id=req.user_id, prun=prun, mode=req.mode, spec=spec
                )
                check = check_purchase(
                    price,
                    user=user_state,
                    mode=mode_state,
                    filter_scope=filter_state,
                    require_user_limits=True,
                )
                attempt = self._new_attempt(req, prun, spec, fresh, enrichment, price, attempt_no)
                if not check.ok:
                    attempt.status = PurchaseStatus.CANCELLED.value
                    attempt.reason = "Лимиты: " + "; ".join(check.reasons)
                    attempt.finished_at = datetime.now(UTC)
                    session.add(attempt)
                    return None, check.reasons
                session.add(attempt)
                await session.flush()
                await misc.audit(
                    session,
                    "purchase_reserved",
                    user_id=req.user_id,
                    gift_id=req.gift_id,
                    price=price,
                    run_mode=prun.value,
                    mode=req.mode.value,
                    filter_id=req.filter_id,
                )
                return attempt.id, []
        except IntegrityError:
            # partial unique index: another attempt for this gift is active (double purchase prevented)
            return None, ["duplicate"]

    @staticmethod
    def _new_attempt(
        req: PurchaseRequest,
        prun: PurchaseRunMode,
        spec: FilterSpec | None,
        listing: ListingSnapshot | None,
        enrichment: Enrichment | None,
        price: int,
        attempt_no: int,
    ) -> PurchaseAttempt:
        verdict = enrichment.verdict if enrichment else None
        return PurchaseAttempt(
            user_id=req.user_id,
            filter_id=spec.id if spec else None,
            filter_name=spec.name if spec else None,
            mode=req.mode.value,
            run_mode=prun.value,
            listing_id=req.listing_id,
            gift_id=req.gift_id,
            collection_name=listing.collection_name if listing else None,
            model_name=listing.model_name if listing else None,
            backdrop_name=listing.backdrop_name if listing else None,
            symbol_name=listing.symbol_name if listing else None,
            number=listing.number if listing else None,
            expected_price_nano=price,
            status=PurchaseStatus.RESERVED.value,
            attempt_no=attempt_no,
            monochrome_status=verdict.status.value if verdict else None,
            monochrome_type=verdict.gw_type.value if verdict and verdict.gw_type else None,
        )

    async def _record_cancelled(
        self,
        req: PurchaseRequest,
        prun: PurchaseRunMode,
        spec: FilterSpec | None,
        listing: ListingSnapshot | None,
        reason: str,
        attempt_no: int,
        prefs: NotificationSettings,
        enrichment: Enrichment | None = None,
    ) -> PurchaseResult:
        async with self.sessionmaker() as session, session.begin():
            attempt = self._new_attempt(
                req,
                prun,
                spec,
                listing,
                enrichment,
                listing.price_nano if listing and listing.price_nano else req.expected_price_nano,
                attempt_no,
            )
            attempt.status = PurchaseStatus.CANCELLED.value
            attempt.reason = reason
            attempt.finished_at = datetime.now(UTC)
            session.add(attempt)
            await session.flush()
            attempt_id = attempt.id
        result = PurchaseResult(PurchaseStatus.CANCELLED, reason, attempt_id)
        if req.trigger == "manual":
            # automatic cancellations are visible in the history; manual ones need an answer right away
            await self._notify_result(req, spec, listing, result, prefs)
        return result

    # ================================================================== live purchase
    async def _submit(
        self,
        req: PurchaseRequest,
        prun: PurchaseRunMode,
        spec: FilterSpec | None,
        fresh: ListingSnapshot,
        price: int,
        attempt_id: int,
        attempt_no: int,
        prefs: NotificationSettings,
    ) -> PurchaseResult:
        if self.settings.purchase_check_balance:
            try:
                balance = await self.mrkt.balance_nano()
            except MrktError:
                balance = None  # unknown balance: MRKT itself rejects an unaffordable purchase
            if balance is not None and balance < price:
                return await self._finish(
                    req,
                    spec,
                    fresh,
                    attempt_id,
                    PurchaseStatus.FAILED,
                    f"Недостаточно средств на MRKT: баланс {format_ton(balance)}, нужно {format_ton(price)}",
                    prefs,
                )
        if await self.control.is_stopped():
            return await self._finish(
                req,
                spec,
                fresh,
                attempt_id,
                PurchaseStatus.CANCELLED,
                "Аварийная остановка активирована до отправки запроса",
                prefs,
            )

        # protection against stale prices: the snapshot used for the decision must be recent
        age = (datetime.now(UTC) - (fresh.fetched_at or datetime.now(UTC))).total_seconds()
        if age > self.settings.purchase_max_snapshot_age_seconds:
            latest, problem = await self._fresh_listing(req)
            if latest is None or latest.price_nano != price:
                reason = problem or (
                    f"Цена изменилась перед отправкой: {format_ton(price)} → "
                    f"{format_ton(latest.price_nano if latest else None)}"
                )
                return await self._finish(
                    req, spec, fresh, attempt_id, PurchaseStatus.CANCELLED, reason, prefs
                )
            fresh = latest

        async with self.sessionmaker() as session, session.begin():
            await purchases_repo.set_status(session, attempt_id, PurchaseStatus.SUBMITTED, submitted=True)
        outcome = await self.mrkt.buy(req.gift_id)

        if outcome.kind is BuyOutcomeKind.CONFIRMED:
            final_price = outcome.price_nano if outcome.price_nano is not None else price
            return await self._confirm(
                req, spec, fresh, attempt_id, final_price, "buy_response", outcome.response, prefs
            )
        if outcome.kind is BuyOutcomeKind.REJECTED:
            return await self._finish(
                req,
                spec,
                fresh,
                attempt_id,
                PurchaseStatus.FAILED,
                outcome.reason,
                prefs,
                response=outcome.response,
            )

        # ---- uncertain outcome: verify before deciding anything
        async with self.sessionmaker() as session, session.begin():
            await purchases_repo.set_status(
                session, attempt_id, PurchaseStatus.UNKNOWN, reason=outcome.reason, response=outcome.response
            )
        verification = await self.verify(fresh)
        return await self.apply_verification(
            req,
            spec,
            fresh,
            attempt_id,
            attempt_no,
            price,
            verification,
            prefs,
            prun=prun,
        )

    async def apply_verification(
        self,
        req: PurchaseRequest,
        spec: FilterSpec | None,
        fresh: ListingSnapshot,
        attempt_id: int,
        attempt_no: int,
        price: int,
        verification: Verification,
        prefs: NotificationSettings,
        *,
        prun: PurchaseRunMode,
        allow_retry: bool = True,
    ) -> PurchaseResult:
        details = {
            "outcome": verification.outcome,
            "detail": verification.detail,
            "obs": verification.observations,
        }
        if verification.outcome == "confirmed":
            return await self._confirm(
                req, spec, fresh, attempt_id, price, "verification", None, prefs, verification=details
            )
        if verification.outcome in ("not_executed", "sold_to_other"):
            reason = (
                "Проверено: покупка не выполнена, объявление всё ещё продаётся"
                if verification.outcome == "not_executed"
                else "Проверено: подарок купил другой покупатель"
            )
            lock = _CURRENT_LOCK.get()
            will_retry = (
                verification.outcome == "not_executed"
                and allow_retry
                and self._retry_allowed(attempt_no)
                and not await self.control.is_stopped()
                and (lock is None or await lock.extend(self.settings.purchase_lock_ttl_seconds))
            )
            result = await self._finish(
                req,
                spec,
                fresh,
                attempt_id,
                PurchaseStatus.FAILED,
                reason,
                prefs,
                verification=details,
                notify=not will_retry,
            )
            if will_retry:
                log.info("retrying purchase after verified non-execution", extra={"gift_id": req.gift_id})
                return await self._run(req, prun, attempt_no=attempt_no + 1)
            return result
        # inconclusive: keep the reservation, do not retry, verify later in the background
        async with self.sessionmaker() as session, session.begin():
            await purchases_repo.set_status(
                session,
                attempt_id,
                PurchaseStatus.UNKNOWN,
                reason="Результат покупки не удалось проверить, повторная покупка запрещена до проверки",
                verification=details,
            )
            await misc.log_error(
                session,
                "purchase",
                "uncertain purchase outcome",
                level="WARNING",
                attempt_id=attempt_id,
                gift_id=req.gift_id,
            )
        result = PurchaseResult(
            PurchaseStatus.UNKNOWN, "Результат неизвестен, ожидает проверки", attempt_id, price
        )
        await self._notify_result(req, spec, fresh, result, prefs)
        return result

    def _retry_allowed(self, attempt_no: int) -> bool:
        return attempt_no <= self.settings.purchase_retries_after_verified_failure

    async def verify(self, listing: ListingSnapshot) -> Verification:
        """Determine whether an uncertain purchase happened by observing the gift on MRKT.

        "not executed" requires two consistent observations, so a purchase that MRKT is still
        processing is not mistaken for a failure.
        """
        observations: list[dict[str, Any]] = []
        not_executed_streak = 0
        for i in range(self.settings.purchase_verify_attempts):
            await self.sleep(self.settings.purchase_verify_delay_seconds * (1 + i * 0.5))
            try:
                gift = await self.mrkt.get_gift(listing.gift_id)
            except MrktError as exc:
                observations.append({"try": i, "error": str(exc)[:200]})
                continue
            if gift is None:
                found = await self._inventory_has(listing)
                observations.append({"try": i, "gift": None, "inventory": found})
                if found:
                    return Verification("confirmed", "Подарок найден в инвентаре", observations)
                continue
            observations.append(
                {"try": i, "is_mine": gift.is_mine, "is_on_sale": gift.is_on_sale, "price": gift.price_nano}
            )
            if gift.is_mine is True:
                return Verification(
                    "confirmed", "MRKT показывает подарок как принадлежащий аккаунту", observations
                )
            if gift.is_on_sale is True and gift.is_mine is False:
                not_executed_streak += 1
                if not_executed_streak >= 2:
                    return Verification("not_executed", "Объявление продолжает продаваться", observations)
                continue
            not_executed_streak = 0
            if gift.is_on_sale is False and gift.is_mine is False:
                if await self._inventory_has(listing):
                    return Verification("confirmed", "Подарок найден в инвентаре", observations)
                return Verification(
                    "sold_to_other", "Подарок снят с продажи и не принадлежит аккаунту", observations
                )
        return Verification("inconclusive", "Недостаточно данных для проверки", observations)

    async def _inventory_has(self, listing: ListingSnapshot) -> bool:
        if not listing.collection_name or listing.number is None:
            return False
        try:
            items = await self.mrkt.find_in_inventory(listing.collection_name, listing.number)
        except MrktError:
            return False
        return any(
            item.number == listing.number and item.collection_name == listing.collection_name
            for item in items
        )

    # ================================================================== finishing
    async def _confirm(
        self,
        req: PurchaseRequest,
        spec: FilterSpec | None,
        listing: ListingSnapshot,
        attempt_id: int,
        price: int,
        source: str,
        response: Any,
        prefs: NotificationSettings,
        *,
        verification: dict[str, Any] | None = None,
    ) -> PurchaseResult:
        async with self.sessionmaker() as session, session.begin():
            await purchases_repo.set_status(
                session,
                attempt_id,
                PurchaseStatus.CONFIRMED,
                reason="MRKT подтвердил покупку"
                if source == "buy_response"
                else "Покупка подтверждена проверкой",
                final_price_nano=price,
                response=response,
                verification=verification,
                finished=True,
            )
            attempt = await purchases_repo.get_attempt(session, attempt_id)
            assert attempt is not None
            await purchases_repo.add_purchase(
                session, attempt, price_nano=price, source=source, response=response
            )
            await misc.audit(
                session,
                "purchase_confirmed",
                user_id=req.user_id,
                gift_id=req.gift_id,
                price=price,
                source=source,
            )
        result = PurchaseResult(PurchaseStatus.CONFIRMED, "Покупка подтверждена", attempt_id, price)
        return await self._notify_result(req, spec, listing, result, prefs)

    async def _finish(
        self,
        req: PurchaseRequest,
        spec: FilterSpec | None,
        listing: ListingSnapshot | None,
        attempt_id: int,
        status: PurchaseStatus,
        reason: str,
        prefs: NotificationSettings,
        *,
        response: Any = None,
        verification: dict[str, Any] | None = None,
        notify: bool = True,
    ) -> PurchaseResult:
        async with self.sessionmaker() as session, session.begin():
            await purchases_repo.set_status(
                session,
                attempt_id,
                status,
                reason=reason,
                response=response,
                verification=verification,
                finished=True,
            )
            await misc.audit(
                session, f"purchase_{status.value}", user_id=req.user_id, gift_id=req.gift_id, reason=reason
            )
        result = PurchaseResult(status, reason, attempt_id)
        if notify:
            await self._notify_result(req, spec, listing, result, prefs)
        return result

    async def remaining_text(self, user_id: int, mode: PurchaseMode, spec: FilterSpec | None) -> str:
        prun = PurchaseRunMode.LIVE
        async with self.sessionmaker() as session:
            user_state, mode_state, filter_state = await self.scope_states(
                session, user_id=user_id, prun=prun, mode=mode, spec=spec
            )
        parts = []
        for state in (user_state, mode_state, filter_state):
            if state is None:
                continue
            left = remaining(state)
            parts.append(f"{state.label}: {format_ton(left) if left is not None else 'не ограничен'}")
        return "; ".join(parts)

    async def _notify_result(
        self,
        req: PurchaseRequest,
        spec: FilterSpec | None,
        listing: ListingSnapshot | None,
        result: PurchaseResult,
        prefs: NotificationSettings,
        *,
        dedup_key: str | None = None,
    ) -> PurchaseResult:
        if self.notifier is None:
            return result
        title = listing.title if listing else req.gift_id
        url = texts.telegram_nft_url(listing) if listing else None
        collection = listing.collection_title or listing.collection_name if listing else None
        model = listing.model_name if listing else None
        try:
            if result.status is PurchaseStatus.CONFIRMED:
                text = texts.purchase_confirmed_text(
                    title=title,
                    url=url,
                    collection=collection,
                    model=model,
                    price_nano=result.price_nano,
                    filter_name=spec.name if spec else None,
                    remaining=await self.remaining_text(req.user_id, req.mode, spec),
                )
                await self.notifier.purchase_message(req.user_id, text, success=True, prefs=prefs)
            elif result.status is PurchaseStatus.DRY_RUN:
                text = texts.dry_run_text(
                    title=title,
                    url=url,
                    collection=collection,
                    model=model,
                    price_nano=result.price_nano,
                    filter_name=spec.name if spec else None,
                )
                await self.notifier.purchase_message(req.user_id, text, success=True, prefs=prefs)
            elif result.status is not None:
                text = texts.purchase_failed_text(
                    title=title, reason=result.reason, status=result.status, url=url
                )
                await self.notifier.purchase_message(
                    req.user_id, text, success=False, prefs=prefs, dedup_key=dedup_key
                )
        except Exception:
            log.exception("failed to send purchase notification", extra={"attempt_id": result.attempt_id})
        return result

    # ================================================================== recovery
    async def recover_on_startup(self) -> None:
        """RESERVED attempts were never sent (SUBMITTED is committed before sending): cancel them.
        SUBMITTED attempts may have reached MRKT: mark them UNKNOWN for verification."""
        async with self.sessionmaker() as session, session.begin():
            for attempt in await purchases_repo.attempts_in_status(
                session, [PurchaseStatus.RESERVED], limit=1000
            ):
                await purchases_repo.set_status(
                    session,
                    attempt.id,
                    PurchaseStatus.CANCELLED,
                    reason="Процесс перезапущен до отправки запроса покупки",
                    finished=True,
                )
            for attempt in await purchases_repo.attempts_in_status(
                session, [PurchaseStatus.SUBMITTED], limit=1000
            ):
                await purchases_repo.set_status(
                    session,
                    attempt.id,
                    PurchaseStatus.UNKNOWN,
                    reason="Процесс перезапущен во время покупки, требуется проверка",
                )

    async def reverify_unknown(self, *, max_age_hours: float = 24.0) -> int:
        """Background verification of attempts with an unknown outcome (never re-buys)."""
        async with self.sessionmaker() as session:
            pending = await purchases_repo.attempts_in_status(
                session,
                [PurchaseStatus.UNKNOWN],
                older_than=datetime.now(UTC) - timedelta(seconds=30),
                limit=20,
            )
        resolved = 0
        for attempt in pending:
            if attempt.run_mode != PurchaseRunMode.LIVE.value:
                continue
            listing = ListingSnapshot(
                gift_id=attempt.gift_id, collection_name=attempt.collection_name, number=attempt.number
            )
            verification = await self.verify(listing)
            req = PurchaseRequest(
                user_id=attempt.user_id,
                gift_id=attempt.gift_id,
                expected_price_nano=attempt.expected_price_nano,
                mode=PurchaseMode(attempt.mode),
                filter_id=attempt.filter_id,
                listing_id=attempt.listing_id,
            )
            async with self.sessionmaker() as session:
                prefs_row = await users_repo.get_settings(session, attempt.user_id)
                filter_row = (
                    await filters_repo.get_filter(session, attempt.user_id, attempt.filter_id)
                    if attempt.filter_id
                    else None
                )
            prefs = NotificationSettings.model_validate(prefs_row.notify or {})
            spec = filters_repo.to_spec(filter_row) if filter_row else None
            age_hours = (datetime.now(UTC) - attempt.created_at).total_seconds() / 3600
            if verification.outcome == "inconclusive" and age_hours < max_age_hours:
                async with self.sessionmaker() as session, session.begin():
                    await purchases_repo.set_status(
                        session,
                        attempt.id,
                        PurchaseStatus.UNKNOWN,
                        verification={"outcome": verification.outcome, "obs": verification.observations},
                    )
                continue
            if verification.outcome == "inconclusive":
                if self.notifier is not None:
                    await self.notifier.admins(
                        f"⚠️ Покупка #{attempt.id} ({texts.e(attempt.gift_id)}) остаётся с неизвестным результатом "
                        f"более {max_age_hours:.0f} ч. Проверьте инвентарь MRKT вручную.",
                        dedup_key=f"unknown-attempt:{attempt.id}",
                    )
                continue
            await self.apply_verification(
                req,
                spec,
                listing,
                attempt.id,
                attempt.attempt_no,
                attempt.expected_price_nano,
                verification,
                prefs,
                prun=PurchaseRunMode.LIVE,
                allow_retry=False,
            )
            resolved += 1
        return resolved
