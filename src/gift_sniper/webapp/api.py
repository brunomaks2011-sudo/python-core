"""Data behind the Mini App screens.

A rule chosen in the Mini App is stored as an ordinary filter (one collection, optionally one model and a
backdrop choice), so the processor, budgets and the purchase service treat it exactly like a filter made in
the chat interface: every purchase still re-checks price, budgets, monochrome status and the run mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import RunMode, Settings
from gift_sniper.db.models import Filter, Gift, MarketCollection
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import giftwiki as giftwiki_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import misc
from gift_sniper.db.repo import purchases as purchases_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import BudgetScope, FilterKind, PurchaseMode, PurchaseRunMode
from gift_sniper.domain.money import NANO_PER_TON, ton_to_nano
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import ListingSnapshot, MonochromeVerdict
from gift_sniper.integrations.mrkt import MrktAttribute, MrktError, SalingQuery
from gift_sniper.services.filters import (
    MAX_LIST_ITEMS,
    PRICE_RULE_TEXT,
    FilterCriteria,
    FilterLimits,
    FilterSpec,
    Pick,
    PriceRule,
    clean_number_pattern,
    describe_criteria,
    number_matches,
)
from gift_sniper.services.percentages import monochrome_model_share
from gift_sniper.services.reference import ReferenceSnapshot, RefRecord
from gift_sniper.services.texts import listing_url, nft_url, telegram_nft_url
from gift_sniper.services.user_prefs import NotificationSettings
from gift_sniper.webapp.auth import WebAppIdentity
from gift_sniper.webapp.images import absolute_url, collection_thumb, color_hex, gift_image, giftname

log = logging.getLogger(__name__)

ATTRIBUTES_TTL_SECONDS = 3600
# notification switches the Mini App shows (the chat menu has the same ones plus filters and limits)
NOTIFY_SWITCHES = ("purchases", "errors", "matching_only", "monochrome", "all_listings", "price_drops")
ATTRIBUTES_FAILURE_TTL_SECONDS = 120
FLOOR_DEPTH = 5  # cheapest listings read for a floor: auction lots are skipped
FLOOR_CARDS = 3  # chosen models (and backdrops) that get their own floor card
MARKET_PAGES = 3  # MRKT pages read for "На продаже"
MARKET_LIMIT = 40
SOLD_SCAN = 300  # recent sales read to pick those matching a number pattern or monochrome pairs
LEADER_PERIODS = (1, 7, 30)
MONO_SEEN_DAYS = 3  # a monochrome listing not seen for longer is not shown as on sale
STATUS_LABELS = {
    "confirmed": "куплено",
    "dry_run": "тест: был бы куплен",
    "failed": "не куплено",
    "cancelled": "отменено",
    "unknown": "проверяется",
    "submitted": "проверяется",
    "reserved": "проверяется",
}


class _Mrkt(Protocol):
    @property
    def configured(self) -> bool: ...

    async def collection_attributes(self, kind: str, collection_name: str) -> list[MrktAttribute]: ...

    async def search_listings(
        self, query: SalingQuery, *, priority: bool = False
    ) -> tuple[list[ListingSnapshot], str | None]: ...


class _Search(Protocol):
    """The chat's 🔎 search of current MRKT listings (services.search.SearchService)."""

    async def search(self, spec: FilterSpec, *, max_pages: int = 3, limit: int = 10) -> Any: ...


class _Store(Protocol):
    snapshot: ReferenceSnapshot

    async def maybe_reload(self, min_interval: float = 15.0) -> None: ...


class _FilterCache(Protocol):
    async def invalidate(self) -> None: ...


class _Purchase(Protocol):
    async def scope_states(
        self, session: AsyncSession, *, user_id: int, prun: PurchaseRunMode, mode: PurchaseMode, spec: Any
    ) -> tuple[Any, Any, Any]: ...


class _Control(Protocol):
    async def run_mode(self) -> Any: ...
    async def set_run_mode(self, mode: RunMode, *, by_user: int | None) -> Any: ...
    async def poll_interval(self) -> float: ...
    async def set_poll_interval(self, seconds: float, *, by_user: int | None) -> float: ...
    async def is_stopped(self) -> bool: ...
    async def stop_all(self, *, by_user: int | None, reason: str = "") -> None: ...
    async def resume(self, *, by_user: int | None) -> None: ...


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def ton(nano: int | None) -> float | None:
    return None if nano is None else float(Decimal(nano) / NANO_PER_TON)


def _price(value: str | float | int | None) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        nano = ton_to_nano(value)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    if nano <= 0:
        raise ApiError("Сумма должна быть больше нуля")
    return nano


class RuleInput(BaseModel):
    """One Mini App rule: a collection, optionally one model, and which backdrops to take."""

    model_config = ConfigDict(extra="ignore")

    collection: str = Field(min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    backdrop_mode: Literal["any", "monochrome", "selected"] = "any"
    backdrops: list[str] = Field(default_factory=list, max_length=200)
    max_price_ton: str | float | None = None
    autobuy: bool = False
    max_count: int | None = Field(default=None, ge=1, le=1000)
    enabled: bool = True

    @field_validator("model", mode="after")
    @classmethod
    def _blank_model(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


class LimitsInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    per_purchase_ton: str | float | None = None
    daily_ton: str | float | None = None
    total_ton: str | float | None = None
    autobuy_enabled: bool | None = None
    monochrome_autobuy_enabled: bool | None = None
    purchases_paused: bool | None = None
    notify: dict[str, bool] = Field(default_factory=dict)  # NOTIFY_SWITCHES that change


FloorRule = Literal["collection_floor", "model_floor"]


class SelectionInput(BaseModel):
    """The search screen's choice: a collection, optionally models, backdrops, patterns and a number."""

    model_config = ConfigDict(extra="ignore")

    collection: str = Field(min_length=1, max_length=128)
    models: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    backdrops: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    symbols: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    monochrome: bool = False  # only pairs Gift Wiki confirms as monochrome
    pattern: str | None = Field(default=None, max_length=16)  # "777" or a shape such as "ABABAB"

    @field_validator("pattern", mode="after")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        return clean_number_pattern(value)


class MarketInput(SelectionInput):
    view: Literal["on_sale", "sold"] = "on_sale"


class SubscriptionInput(SelectionInput):
    """A subscription made on the search screen, stored as an ordinary filter with its own switches."""

    name: str = Field(default="", max_length=64)
    min_price_ton: str | float | None = None
    max_price_ton: str | float | None = None
    autobuy: bool = False
    notify_new: bool = True
    notify_price: bool = False


class PairPick(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backdrop: str = Field(min_length=1, max_length=128)
    price_ton: str | float | None = None
    min_ton: str | float | None = None  # "от": cheaper listings are not taken
    rule: FloorRule | None = None  # instead of a price: up to the collection or model floor


class ModelPicks(BaseModel):
    """What to take for one model (or the whole collection when model is empty) and up to which price."""

    model_config = ConfigDict(extra="ignore")

    model: str | None = Field(default=None, max_length=128)
    any_price_ton: str | float | None = None  # every copy of the model, any backdrop
    any_min_ton: str | float | None = None
    monochrome_price_ton: str | float | None = None  # every pair Gift Wiki confirms as monochrome
    monochrome_min_ton: str | float | None = None
    monochrome_rule: FloorRule | None = None  # the same up to the collection or model floor instead
    pairs: list[PairPick] = Field(default_factory=list, max_length=200)  # single monochrome pairs
    autobuy: bool | None = None

    @field_validator("model", mode="after")
    @classmethod
    def _blank_model(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


def _picks_of(row: Filter | None) -> list[Pick]:
    return FilterCriteria.model_validate(row.criteria or {}).picks if row is not None else []


def _find_pick(picks: list[Pick], model_norm: str | None, backdrop_norm: str | None) -> Pick | None:
    """The pick for exactly this model (None: whole collection) and backdrop (None: no backdrop)."""
    wanted = [backdrop_norm] if backdrop_norm else []
    for pick in picks:
        if (normalize_name(pick.model) if pick.model else None) == model_norm and [
            normalize_name(b) for b in pick.backdrops
        ] == wanted:
            return pick
    return None


def _pick_price(picks: list[Pick], model_norm: str | None, backdrop_norm: str | None) -> float | None:
    pick = _find_pick(picks, model_norm, backdrop_norm)
    return ton(pick.max_price_nano) if pick is not None and pick.price_rule is PriceRule.FIXED else None


def _pick_min(picks: list[Pick], model_norm: str | None, backdrop_norm: str | None) -> float | None:
    pick = _find_pick(picks, model_norm, backdrop_norm)
    return ton(pick.min_price_nano) if pick is not None else None


def _pick_rule(picks: list[Pick], model_norm: str | None, backdrop_norm: str | None) -> str | None:
    """The floor the pick follows instead of a price, if it does."""
    pick = _find_pick(picks, model_norm, backdrop_norm)
    return pick.price_rule.value if pick is not None and pick.price_rule is not PriceRule.FIXED else None


def _same_picks(a: list[Pick], b: list[Pick]) -> bool:
    def key(picks: list[Pick]) -> list[str]:
        return sorted(json.dumps(p.model_dump(mode="json"), sort_keys=True) for p in picks)

    return key(a) == key(b)


def _whole_floor_pick(picks: list[Pick]) -> Pick | None:
    """The pick "any monochrome of the collection up to a floor", if there is one."""
    return next(
        (p for p in picks if p.model is None and not p.backdrops and p.price_rule is not PriceRule.FIXED),
        None,
    )


def _everywhere(rows: list[Filter]) -> Filter | None:
    """The mode "every monochrome of every collection up to a floor": a monochrome plan without collections."""
    for row in rows:
        if row.kind != FilterKind.MONOCHROME.value or not filters_repo.is_plan(row):
            continue
        criteria = FilterCriteria.model_validate(row.criteria or {})
        if not criteria.collections and _whole_floor_pick(criteria.picks) is not None:
            return row
    return None


def _everywhere_rule(rows: list[Filter]) -> str | None:
    row = _everywhere(rows)
    pick = _whole_floor_pick(_picks_of(row)) if row is not None and row.enabled else None
    return pick.price_rule.value if pick is not None else None


def _floor_pick(
    model: str | None, rule: str, backdrops: list[str] | None = None, low: int | None = None
) -> Pick:
    return Pick(model=model, backdrops=backdrops or [], price_rule=PriceRule(rule), min_price_nano=low)


def _range(low_ton: str | float | None, high: int | None, what: str) -> int | None:
    """ "от" of a price range; it may not be above "до"."""
    low = _price(low_ton)
    if low is not None and high is not None and low > high:
        raise ApiError(f"«От» больше «до» у {what}")
    return low


def _percent(permille: int | None) -> float | None:
    return permille / 10 if permille is not None else None


def _editable(c: FilterCriteria) -> bool:
    """A filter the search screen can show and save without losing anything: one collection, no Mini App
    picks and none of the criteria only the chat edits."""
    chat_only = (
        c.exclude_collections,
        c.exclude_models,
        c.model_rarity_min_permille,
        c.model_rarity_max_permille,
        c.backdrop_rarity_min_permille,
        c.backdrop_rarity_max_permille,
        c.symbol_rarity_min_permille,
        c.symbol_rarity_max_permille,
        c.min_discount_percent,
        c.monochrome_types,
        c.min_monochrome_model_share_percent,
    )
    return len(c.collections) == 1 and not c.picks and not c.only_new_listings and not any(chat_only)


def _mono_type(verdict: MonochromeVerdict) -> str | None:
    if not verdict.is_monochrome:
        return None
    return verdict.gw_type.value if verdict.gw_type else "monochrome"


def _pair_key(model: str | None, backdrop: str | None) -> tuple[str, str]:
    return normalize_name(model), normalize_name(backdrop)


def _in_query(item: ListingSnapshot, query: SalingQuery) -> bool:
    """MRKT filters by these names itself; checked again so a floor never comes from another model or backdrop."""
    for value, names in (
        (item.model_name, query.model_names),
        (item.backdrop_name, query.backdrop_names),
        (item.symbol_name, query.symbol_names),
    ):
        if names and normalize_name(value) not in {normalize_name(n) for n in names}:
            return False
    return True


def _records_by_model(records: list[RefRecord]) -> dict[str, list[RefRecord]]:
    by_model: dict[str, list[RefRecord]] = {}
    for record in records:
        if record.model_name and record.backdrop_name:
            by_model.setdefault(normalize_name(record.model_name), []).append(record)
    return by_model


class MiniAppApi:
    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        mrkt: _Mrkt,
        store: _Store,
        filter_cache: _FilterCache,
        purchase: _Purchase,
        control: _Control,
        search: _Search | None = None,
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.mrkt = mrkt
        self.store = store
        self.filter_cache = filter_cache
        self.purchase = purchase
        self.control = control
        self.search = search
        self.prefix = settings.redis_prefix

    async def register(self, identity: WebAppIdentity) -> None:
        """A user may open the Mini App before ever pressing /start in the chat."""
        async with self.sessionmaker() as session, session.begin():
            await users_repo.ensure_user(
                session,
                identity.user_id,
                username=identity.username,
                full_name=identity.full_name,
                is_admin=self.settings.is_admin(identity.user_id),
                can_purchase=self.settings.can_purchase(identity.user_id),
            )

    # ------------------------------------------------------------------ status
    async def me(self, user_id: int) -> dict[str, Any]:
        await self.store.maybe_reload(min_interval=5)  # a sync may have run in another process
        async with self.sessionmaker() as session:
            prefs = await users_repo.get_settings(session, user_id)
            user_state, _, _ = await self.purchase.scope_states(
                session, user_id=user_id, prun=PurchaseRunMode.LIVE, mode=PurchaseMode.REGULAR, spec=None
            )
            rows = await filters_repo.list_filters(session, user_id)
            last_sync = next(iter(await giftwiki_repo.last_runs(session, 1)), None)
        limits, usage = user_state.limits, user_state.usage
        notify = NotificationSettings.model_validate(prefs.notify or {})
        snapshot = self.store.snapshot
        sync_error = last_sync.error if last_sync is not None and last_sync.status == "failed" else None
        run_mode = (await self.control.run_mode()).value
        stopped = await self.control.is_stopped()
        buying = [r for r in rows if r.enabled and r.autobuy]
        kinds = {r.kind for r in buying}
        limits_ok = None not in (limits.per_purchase, limits.daily, limits.total)
        # the autobuy switches that are off although a buying rule needs them
        modes_missing = sorted(
            {
                "monochrome_autobuy_enabled" if kind == FilterKind.MONOCHROME.value else "autobuy_enabled"
                for kind in kinds
                if not (
                    prefs.monochrome_autobuy_enabled
                    if kind == FilterKind.MONOCHROME.value
                    else prefs.autobuy_enabled
                )
            }
        )
        can_purchase = self.settings.can_purchase(user_id)
        checklist = [
            {
                "id": "limits",
                "ok": limits_ok,
                "text": "Общие лимиты: на покупку, на день и всего",
                "action": "settings",
            },
            {
                "id": "rule",
                "ok": bool(buying),
                "text": "Хотя бы одно правило с автопокупкой",
                "action": "collections",
            },
            {
                "id": "modes",
                "ok": bool(buying) and not modes_missing,
                "text": "Автопокупка включена",
                "action": "settings",
            },
            {
                "id": "live",
                "ok": run_mode == "live",
                "text": {
                    "live": "Реальные покупки",
                    "dry_run": "Реальные покупки (сейчас покупки только имитируются)",
                    "notify_only": "Реальные покупки (сейчас «Покупать» выключено)",
                }.get(run_mode, "Реальные покупки"),
                "action": None,
            },
        ]
        if prefs.purchases_paused:
            checklist.append(
                {"id": "paused", "ok": False, "text": "Пауза покупок включена", "action": "settings"}
            )
        if FilterKind.MONOCHROME.value in kinds or not snapshot.records_count:
            checklist.append(
                {
                    "id": "giftwiki",
                    "ok": bool(snapshot.records_count),
                    "text": "Данные Gift Wiki для монохромов"
                    + (f" — последняя загрузка не удалась: {sync_error}" if sync_error else ""),
                    "action": None,
                }
            )
        if stopped:
            checklist.append(
                {"id": "stopped", "ok": False, "text": "Аварийная остановка включена", "action": "settings"}
            )
        if not can_purchase:
            checklist.append(
                {"id": "rights", "ok": False, "text": "У вас нет права на покупки", "action": None}
            )
        return {
            "user_id": user_id,
            "is_admin": self.settings.is_admin(user_id),
            "can_purchase": can_purchase,
            "run_mode": run_mode,
            "max_run_mode": self.settings.run_mode.value,  # RUN_MODE in .env: the mode can go up to it
            "poll_interval": await self.control.poll_interval(),
            "monochrome_everywhere": _everywhere_rule(rows),
            "stopped": stopped,
            "autobuy_enabled": prefs.autobuy_enabled,
            "monochrome_autobuy_enabled": prefs.monochrome_autobuy_enabled,
            "modes_missing": modes_missing,
            "purchases_paused": prefs.purchases_paused,
            "notify": {key: getattr(notify, key) for key in NOTIFY_SWITCHES},
            "limits": {
                "per_purchase": ton(limits.per_purchase),
                "daily": ton(limits.daily),
                "total": ton(limits.total),
            },
            "spent": {"today": ton(usage.daily_spent), "total": ton(usage.total_spent)},
            "giftwiki": {"records": snapshot.records_count, "age_hours": snapshot.age_hours()},
            "mrkt_configured": self.mrkt.configured,
            "rules": {"total": len(rows), "enabled": sum(r.enabled for r in rows), "autobuy": len(buying)},
            "checklist": checklist,
            "ready": all(item["ok"] for item in checklist),
        }

    # ------------------------------------------------------------------ catalog
    async def collections(self, user_id: int) -> dict[str, Any]:
        await self.store.maybe_reload(min_interval=5)
        async with self.sessionmaker() as session:
            rows = await listings_repo.market_collections(session)
            models = await listings_repo.models_by_collection(session)
            rules = await filters_repo.list_filters(session, user_id)
            slugs = await listings_repo.collection_slugs(session)
        snapshot = self.store.snapshot
        taken: dict[str, int] = {}
        buying: dict[str, bool] = {}
        other_rules: dict[str, int] = {}
        floor_rule: dict[str, str] = {}  # "any monochrome up to the floor" of the collection
        for rule in rules:
            if not rule.enabled:
                continue
            criteria = FilterCriteria.model_validate(rule.criteria or {})
            whole = _whole_floor_pick(criteria.picks) if rule.kind == FilterKind.MONOCHROME.value else None
            for collection_name in criteria.collections:
                key = normalize_name(collection_name)
                if criteria.picks:
                    taken[key] = taken.get(key, 0) + len(criteria.picks)
                    buying[key] = buying.get(key, False) or rule.autobuy
                else:
                    other_rules[key] = other_rules.get(key, 0) + 1
                if whole is not None:
                    floor_rule[key] = whole.price_rule.value
        items = []
        for row in rows:
            records = self._records(snapshot, row.name, row.title)
            mono_models = {normalize_name(r.model_name) for r in records if r.model_name}
            observed = models.get(normalize_name(row.name), set())
            share = monochrome_model_share(mono_models, observed) if mono_models else None
            key = normalize_name(row.name)
            items.append(
                {
                    "name": row.name,
                    "title": row.title or row.name,
                    "floor": ton(row.floor_price_nano),
                    "image": collection_thumb(giftname(row.name, slug=slugs.get(row.name))),
                    "monochrome_pairs": len(records),
                    "monochrome_models": len(mono_models),
                    "known_models": share.denominator if share else len(observed),
                    "monochrome_share": share.percent if share else None,
                    "taken": taken.get(key, 0),
                    "autobuy": buying.get(key),
                    "rules": other_rules.get(key, 0),
                    "monochrome_floor": floor_rule.get(key),
                }
            )
        return {"items": items, "giftwiki_records": snapshot.records_count}

    async def set_monochrome_mode(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """The modes "every monochrome up to the collection floor / up to the model floor": one rule for all
        collections, also those MRKT adds later (rule: null turns the mode off)."""
        raw = payload.get("rule")
        if raw not in (None, PriceRule.COLLECTION_FLOOR.value, PriceRule.MODEL_FLOOR.value):
            raise ApiError("Неизвестное правило цены")
        async with self.sessionmaker() as session, session.begin():
            row = _everywhere(await filters_repo.list_filters(session, user_id))
            if raw is None:
                if row is not None:
                    await filters_repo.delete_filter(session, row)
            else:
                rule = PriceRule(raw)
                if row is None:
                    try:
                        row = await filters_repo.create_filter(
                            session, user_id, "📱 Все монохромы", FilterKind.MONOCHROME, plan=True
                        )
                    except ValueError as exc:
                        raise ApiError(str(exc)) from exc
                filters_repo.update_criteria(row, FilterCriteria(picks=[Pick(price_rule=rule)]))
                row.name = f"📱 Все монохромы · {PRICE_RULE_TEXT[rule]}"[:64]
                filters_repo.set_enabled(row, True)
                row.autobuy = self.settings.can_purchase(user_id)
                await self._enable_mode(session, user_id, row)
            await misc.audit(session, "webapp_monochrome_mode", user_id=user_id, rule=raw)
        await self.filter_cache.invalidate()
        return await self.me(user_id)

    async def monochromes_everywhere(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Any monochrome up to the collection or model floor in every collection with monochrome data
        (rule: null turns these off again). Models and backdrops chosen one by one keep their own prices."""
        raw = payload.get("rule")
        if raw not in (None, PriceRule.COLLECTION_FLOOR.value, PriceRule.MODEL_FLOOR.value):
            raise ApiError("Неизвестное правило цены")
        rule = PriceRule(raw) if raw else None
        await self.store.maybe_reload(min_interval=5)
        snapshot = self.store.snapshot
        can_purchase = self.settings.can_purchase(user_id)
        changed, error = 0, None
        async with self.sessionmaker() as session, session.begin():
            rows = await listings_repo.market_collections(session)
            rules = await filters_repo.list_filters(session, user_id)
            targets = [row for row in rows if self._records(snapshot, row.name, row.title)]
            for row in targets:
                plans = self._plans(rules, row.name)
                plan = plans.get(FilterKind.MONOCHROME)
                current = _picks_of(plan)
                # turning on replaces "any monochrome" of the collection; turning off removes only a floor one
                picks = [
                    p
                    for p in current
                    if not (
                        p.model is None
                        and not p.backdrops
                        and (rule is not None or p.price_rule is not PriceRule.FIXED)
                    )
                ]
                if rule is not None:
                    picks.append(Pick(price_rule=rule))
                if _same_picks(picks, current) and (plan is None or plan.enabled or rule is None):
                    continue
                if not picks:
                    if plan is not None:
                        await filters_repo.delete_filter(session, plan)
                        changed += 1
                    continue
                title = row.title or row.name
                if plan is None:
                    try:
                        plan = await filters_repo.create_filter(
                            session, user_id, title, FilterKind.MONOCHROME, plan=True
                        )
                    except ValueError as exc:
                        error = str(exc)
                        break
                    plan.autobuy = (
                        any(r.autobuy for r in plans.values()) if plans else True
                    ) and can_purchase
                criteria = FilterCriteria.model_validate(
                    {"collections": [row.name], "picks": [p.model_dump() for p in picks]}
                )
                filters_repo.update_criteria(plan, criteria)
                plan.name = f"📱 {title} · монохромы"[:64]
                filters_repo.set_enabled(plan, True)
                await self._enable_mode(session, user_id, plan)
                changed += 1
            await misc.audit(
                session,
                "webapp_monochromes_everywhere",
                user_id=user_id,
                rule=rule.value if rule else None,
                changed=changed,
            )
        await self.filter_cache.invalidate()
        return {"changed": changed, "collections": len(targets), "error": error}

    async def collection(self, user_id: int, name: str) -> dict[str, Any]:
        await self.store.maybe_reload(min_interval=5)
        async with self.sessionmaker() as session:
            row = await session.get(MarketCollection, name)
            if row is None:
                raise ApiError("Коллекция не найдена", 404)
        mrkt_models = await self._attributes("model", name)
        mrkt_backdrops = await self._attributes("backdrop", name)
        if mrkt_models:
            async with self.sessionmaker() as session, session.begin():
                await listings_repo.upsert_models(
                    session, name, [(m.name, m.rarity_permille) for m in mrkt_models], source="mrkt_models"
                )
        async with self.sessionmaker() as session:
            stored_models = await listings_repo.collection_models(session, name)
            seen_backdrops = await listings_repo.collection_backdrops(session, name)
            floors = await listings_repo.model_floors(session, name)
            rules = await filters_repo.list_filters(session, user_id)
            seen_pairs = await listings_repo.pair_slugs(session, name)
            colors = await listings_repo.backdrop_colors(session)
            symbols = await listings_repo.collection_symbols(session, name)
        snapshot = self.store.snapshot
        records = self._records(snapshot, row.name, row.title)
        mono_by_model = _records_by_model(records)
        plans = self._plans(rules, name)
        regular = _picks_of(plans.get(FilterKind.REGULAR))
        mono = _picks_of(plans.get(FilterKind.MONOCHROME))

        rarity: dict[str, int | None] = {normalize_name(b.name): b.rarity_permille for b in mrkt_backdrops}
        for backdrop_name, value in seen_backdrops.items():
            if rarity.get(normalize_name(backdrop_name)) is None:
                rarity[normalize_name(backdrop_name)] = value

        models: dict[str, dict[str, Any]] = {}
        floor_by_model = {normalize_name(m.name): m.floor_price_nano for m in mrkt_models}
        for stored in stored_models:
            models[stored.model_norm] = {"name": stored.model_name, "rarity": stored.rarity_permille}
        for norm, recs in mono_by_model.items():
            models.setdefault(norm, {"name": recs[0].model_name, "rarity": None})
        thumb = collection_thumb(giftname(name, slug=next(iter(seen_pairs.values()), None)))

        model_items = []
        for norm, model in models.items():
            recs = sorted(
                {normalize_name(r.backdrop_name or ""): r for r in mono_by_model.get(norm, [])}.values(),
                key=lambda r: r.backdrop_name or "",
            )
            pairs = []
            for record in recs:
                backdrop_norm = normalize_name(record.backdrop_name or "")
                center, edge = colors.get(backdrop_norm, (None, None))
                pairs.append(
                    {
                        "backdrop": record.backdrop_name,
                        "type": record.type.value if record.type else record.type_raw,
                        "rarity": _percent(rarity.get(backdrop_norm)),
                        "image": absolute_url(record.photo_url, self.settings.giftwiki_api_base_url)
                        or gift_image(seen_pairs.get((norm, backdrop_norm))),
                        "center": color_hex(record.center_color) or color_hex(center),
                        "edge": color_hex(record.edge_color) or color_hex(edge),
                        "price": _pick_price(mono, norm, backdrop_norm),
                        "min": _pick_min(mono, norm, backdrop_norm),
                        "rule": _pick_rule(mono, norm, backdrop_norm),
                    }
                )
            # share of this model's copies with a monochrome backdrop, from MRKT backdrop rarities
            rarities = [rarity.get(normalize_name(r.backdrop_name or "")) for r in recs]
            known = [int(v) for v in rarities if v is not None]
            chance = sum(known) / 10 if rarities and len(known) == len(rarities) else None
            seen_floor, on_sale = floors.get(model["name"], (None, 0))
            observed_image = next(
                (gift_image(slug) for (m, _), slug in seen_pairs.items() if m == norm and gift_image(slug)),
                None,
            )
            model_items.append(
                {
                    "name": model["name"],
                    "rarity": _percent(model["rarity"]),
                    "floor": ton(floor_by_model.get(norm)),
                    "seen_floor": ton(seen_floor),
                    "on_sale": on_sale,
                    "image": next((p["image"] for p in pairs if p["image"]), None) or observed_image,
                    "monochrome_chance": chance,
                    "any": _pick_price(regular, norm, None),
                    "any_min": _pick_min(regular, norm, None),
                    "monochrome": _pick_price(mono, norm, None),
                    "monochrome_min": _pick_min(mono, norm, None),
                    "monochrome_rule": _pick_rule(mono, norm, None),
                    "taken": sum(1 for p in [*regular, *mono] if p.model and normalize_name(p.model) == norm),
                    "pairs": pairs,
                }
            )
        model_items.sort(
            key=lambda m: (-m["taken"], -len(m["pairs"]), m["rarity"] if m["rarity"] is not None else 1e9)
        )
        mono_models = {n for n, recs in mono_by_model.items() if recs}
        share = monochrome_model_share(mono_models, set(models)) if mono_models else None
        return {
            **self._backdrops_and_symbols(records, mrkt_backdrops, seen_backdrops, rarity, colors, symbols),
            "name": row.name,
            "title": row.title or row.name,
            "floor": ton(row.floor_price_nano),
            "image": thumb,
            "giftwiki": bool(records),
            "monochrome_pairs": len(records),
            "monochrome_share": share.percent if share else None,
            "monochrome_models": len(mono_models),
            "known_models": share.denominator if share else len(models),
            "models_source": "mrkt" if mrkt_models else "observed",
            "autobuy": any(r.autobuy for r in plans.values())
            if plans
            else self.settings.can_purchase(user_id),
            "whole": {
                "any": _pick_price(regular, None, None),
                "any_min": _pick_min(regular, None, None),
                "monochrome": _pick_price(mono, None, None),
                "monochrome_min": _pick_min(mono, None, None),
                "monochrome_rule": _pick_rule(mono, None, None),
            },
            "taken": len(regular) + len(mono),
            "plans": [r.id for r in plans.values()],
            "models": model_items,
            "rules": [
                self._rule_view(r)
                for r in rules
                if not filters_repo.is_plan(r) and self._rule_collection(r) == normalize_name(name)
            ],
        }

    @staticmethod
    def _backdrops_and_symbols(
        records: list[RefRecord],
        mrkt_backdrops: list[MrktAttribute],
        seen_backdrops: dict[str, int | None],
        rarity: dict[str, int | None],
        colors: dict[str, tuple[int | None, int | None]],
        symbols: dict[str, int | None],
    ) -> dict[str, Any]:
        """Every backdrop of the collection (MRKT's list, those seen on gifts, Gift Wiki's) with its colours and
        the models it is a monochrome for; the patterns (symbols) seen on its gifts."""
        mono: dict[str, list[dict[str, Any]]] = {}
        record_colors: dict[str, tuple[str | None, str | None]] = {}
        names: dict[str, str] = {}
        for item in mrkt_backdrops:
            names.setdefault(normalize_name(item.name), item.name)
        for seen in seen_backdrops:
            names.setdefault(normalize_name(seen), seen)
        for record in records:
            if not record.backdrop_name:
                continue
            norm = normalize_name(record.backdrop_name)
            names.setdefault(norm, record.backdrop_name)
            record_colors.setdefault(norm, (color_hex(record.center_color), color_hex(record.edge_color)))
            if record.model_name:
                kind = record.type.value if record.type else record.type_raw
                mono.setdefault(norm, []).append({"model": record.model_name, "type": kind})
        floors = {normalize_name(b.name): b.floor_price_nano for b in mrkt_backdrops}
        backdrops = []
        for norm, backdrop in names.items():
            center, edge = record_colors.get(norm, (None, None))
            seen_center, seen_edge = colors.get(norm, (None, None))
            backdrops.append(
                {
                    "name": backdrop,
                    "rarity": _percent(rarity.get(norm)),
                    "center": center or color_hex(seen_center),
                    "edge": edge or color_hex(seen_edge),
                    "floor": ton(floors.get(norm)),
                    "mono": mono.get(norm, []),
                }
            )
        return {
            "backdrops": sorted(backdrops, key=lambda b: str(b["name"]).casefold()),
            "symbols": [
                {"name": symbol, "rarity": _percent(value)}
                for symbol, value in sorted(symbols.items(), key=lambda kv: kv[0].casefold())
            ],
        }

    @staticmethod
    def _plans(rules: list[Filter], collection_name: str) -> dict[FilterKind, Filter]:
        """The Mini App plan filters (regular and monochrome) of one collection."""
        key = normalize_name(collection_name)
        plans: dict[FilterKind, Filter] = {}
        for rule in rules:
            collections = FilterCriteria.model_validate(rule.criteria or {}).collections
            if filters_repo.is_plan(rule) and [normalize_name(c) for c in collections] == [key]:
                plans.setdefault(FilterKind(rule.kind), rule)
        return plans

    async def save_picks(self, user_id: int, collection_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Replace what the bot takes for one model (or the whole collection) of a collection."""
        data = ModelPicks.model_validate(payload)
        model_norm = normalize_name(data.model) if data.model else None
        new: dict[FilterKind, list[Pick]] = {FilterKind.REGULAR: [], FilterKind.MONOCHROME: []}
        if (price := _price(data.any_price_ton)) is not None:
            low = _range(data.any_min_ton, price, "«Любой фон»")
            new[FilterKind.REGULAR].append(Pick(model=data.model, max_price_nano=price, min_price_nano=low))
        if data.monochrome_rule is not None:
            low = _range(data.monochrome_min_ton, None, "«Все монохромы»")
            new[FilterKind.MONOCHROME].append(_floor_pick(data.model, data.monochrome_rule, low=low))
        elif (price := _price(data.monochrome_price_ton)) is not None:
            low = _range(data.monochrome_min_ton, price, "«Все монохромы»")
            new[FilterKind.MONOCHROME].append(
                Pick(model=data.model, max_price_nano=price, min_price_nano=low)
            )
        for pair in data.pairs:
            if pair.rule is not None:
                low = _range(pair.min_ton, None, f"фона {pair.backdrop}")
                new[FilterKind.MONOCHROME].append(_floor_pick(data.model, pair.rule, [pair.backdrop], low))
                continue
            price = _price(pair.price_ton)
            if price is None:
                raise ApiError(f"Укажите цену для фона {pair.backdrop}")
            low = _range(pair.min_ton, price, f"фона {pair.backdrop}")
            new[FilterKind.MONOCHROME].append(
                Pick(model=data.model, backdrops=[pair.backdrop], max_price_nano=price, min_price_nano=low)
            )
        can_purchase = self.settings.can_purchase(user_id)
        async with self.sessionmaker() as session, session.begin():
            title = await self._collection_title(session, collection_name)
            plans = self._plans(await filters_repo.list_filters(session, user_id), collection_name)
            default = any(r.autobuy for r in plans.values()) if plans else True
            autobuy = (data.autobuy if data.autobuy is not None else default) and can_purchase
            for kind in (FilterKind.REGULAR, FilterKind.MONOCHROME):
                row = plans.get(kind)
                picks = [
                    p for p in _picks_of(row) if (normalize_name(p.model) if p.model else None) != model_norm
                ]
                picks += new[kind]
                if not picks:
                    if row is not None:
                        await filters_repo.delete_filter(session, row)
                    continue
                if row is None:
                    try:
                        row = await filters_repo.create_filter(session, user_id, title, kind, plan=True)
                    except ValueError as exc:
                        raise ApiError(str(exc)) from exc
                criteria = FilterCriteria.model_validate(
                    {"collections": [collection_name], "picks": [p.model_dump() for p in picks]}
                )
                filters_repo.update_criteria(row, criteria)
                row.name = (f"📱 {title}" + (" · монохромы" if kind is FilterKind.MONOCHROME else ""))[:64]
                filters_repo.set_enabled(row, True)
                row.autobuy = autobuy
                await self._enable_mode(session, user_id, row)
            await misc.audit(
                session, "webapp_picks", user_id=user_id, collection=collection_name, model=data.model
            )
        await self.filter_cache.invalidate()
        return await self.collection(user_id, collection_name)

    def _records(self, snapshot: ReferenceSnapshot, name: str, title: str | None) -> list[RefRecord]:
        match = snapshot.match_collection(name, title)
        return snapshot.records_of_gift(match.gift_id) if match.status == "matched" and match.gift_id else []

    async def _attributes(self, kind: str, collection_name: str) -> list[MrktAttribute]:
        """MRKT's model/backdrop list of a collection, cached in Redis; [] when MRKT cannot give it."""
        if not self.mrkt.configured:
            return []
        key = f"{self.prefix}:webapp:attr:{kind}:{collection_name}"
        cached = await self.redis.get(key)
        if cached is not None:
            return [MrktAttribute(**item) for item in json.loads(cached)]
        try:
            items = await self.mrkt.collection_attributes(kind, collection_name)
        except MrktError as exc:
            log.warning("MRKT attribute list failed", extra={"kind": kind, "error": str(exc)})
            await self.redis.set(key, "[]", ex=ATTRIBUTES_FAILURE_TTL_SECONDS)
            return []
        payload = [
            {"name": i.name, "rarity_permille": i.rarity_permille, "floor_price_nano": i.floor_price_nano}
            for i in items
        ]
        await self.redis.set(key, json.dumps(payload), ex=ATTRIBUTES_TTL_SECONDS)
        return items

    # ------------------------------------------------------------------ search screen
    async def _market_collection(self, name: str) -> MarketCollection:
        async with self.sessionmaker() as session:
            row = await session.get(MarketCollection, name)
        if row is None:
            raise ApiError("Коллекция не найдена", 404)
        return row

    def _mono_pairs(
        self, collection: MarketCollection, models: list[str]
    ) -> dict[tuple[str, str], RefRecord]:
        """Gift Wiki monochrome pairs (model, backdrop) of the collection, of the chosen models if there are any."""
        wanted = {normalize_name(m) for m in models}
        pairs: dict[tuple[str, str], RefRecord] = {}
        for record in self._records(self.store.snapshot, collection.name, collection.title):
            key = _pair_key(record.model_name, record.backdrop_name)
            if record.model_name and record.backdrop_name and (not wanted or key[0] in wanted):
                pairs.setdefault(key, record)
        return pairs

    @staticmethod
    def _search_criteria(data: SelectionInput, pairs: dict[tuple[str, str], RefRecord]) -> FilterCriteria:
        """The choice as filter criteria. For monochromes MRKT is asked only for models and backdrops that can
        make a monochrome pair; the pair itself is checked on each gift."""
        models, backdrops = data.models, data.backdrops
        if data.monochrome and pairs and not backdrops:
            models = models or sorted({str(r.model_name) for r in pairs.values()})
            backdrops = sorted({str(r.backdrop_name) for r in pairs.values()})
        return FilterCriteria(
            collections=[data.collection],
            models=models,
            backdrops=backdrops,
            symbols=data.symbols,
            number_pattern=data.pattern,
        )

    def _gift_view(self, gift: ListingSnapshot, price_nano: int | None, mono: str | None) -> dict[str, Any]:
        return {
            "id": gift.gift_id,
            "title": gift.title,
            "number": gift.number,
            "model": gift.model_name,
            "backdrop": gift.backdrop_name,
            "symbol": gift.symbol_name,
            "price": ton(price_nano),
            "mono": mono,
            "image": gift_image(gift.name),
            "url": listing_url(self.settings, gift),
            "tg_url": telegram_nft_url(gift),
            "center": color_hex(gift.backdrop_center_color),
            "edge": color_hex(gift.backdrop_edge_color),
        }

    def _stored_gift_view(self, gift: Gift, price_nano: int | None, mono: str | None) -> dict[str, Any]:
        snapshot = ListingSnapshot(
            gift_id=gift.id,
            collection_name=gift.collection_name,
            collection_title=gift.collection_title,
            name=gift.name,
            number=gift.number,
            model_name=gift.model_name,
            backdrop_name=gift.backdrop_name,
            symbol_name=gift.symbol_name,
            backdrop_center_color=gift.backdrop_center_color,
            backdrop_edge_color=gift.backdrop_edge_color,
        )
        return self._gift_view(snapshot, price_nano, mono)

    async def _cheapest(
        self, query: SalingQuery, keep: Callable[[ListingSnapshot], bool] | None, pages: int
    ) -> ListingSnapshot | None:
        """The cheapest gift on sale for the query (auction lots are not asking prices)."""
        for _ in range(pages):
            listings, cursor = await self.mrkt.search_listings(query)
            valid = [
                item
                for item in listings
                if item.price_nano is not None
                and not item.is_on_auction
                and _in_query(item, query)
                and (keep is None or keep(item))
            ]
            if valid:
                return min(valid, key=lambda item: item.price_nano or 0)
            if not cursor or not listings:
                break
            query.cursor = cursor
        return None

    async def prices(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """ "Получить цены": floors on MRKT right now — of the collection, of the whole choice and of each chosen
        model and backdrop — with the last sale of each that the bot saw in the MRKT feed."""
        data = SelectionInput.model_validate(payload)
        await self.store.maybe_reload(min_interval=5)
        collection = await self._market_collection(data.collection)
        pairs = self._mono_pairs(collection, data.models) if data.monochrome else {}

        def is_pair(item: ListingSnapshot) -> bool:
            return _pair_key(item.model_name, item.backdrop_name) in pairs

        name = collection.name
        cards: list[dict[str, Any]] = [{"kind": "collection", "title": collection.title or name}]
        searches = [SalingQuery(collection_names=[name], count=FLOOR_DEPTH)]
        sold_by: list[tuple[list[str], list[str], list[str]]] = [([], [], [])]
        if data.models or data.backdrops or data.symbols or data.monochrome:
            criteria = self._search_criteria(data, pairs)
            cards.append({"kind": "selection", "title": "Выбранное"})
            searches.append(
                SalingQuery(
                    collection_names=[name],
                    model_names=criteria.models,
                    backdrop_names=criteria.backdrops,
                    symbol_names=criteria.symbols,
                )
            )
            sold_by.append((data.models, data.backdrops, data.symbols))
        for model in data.models[:FLOOR_CARDS]:
            cards.append({"kind": "model", "title": model})
            searches.append(SalingQuery(collection_names=[name], model_names=[model], count=FLOOR_DEPTH))
            sold_by.append(([model], [], []))
        for backdrop in data.backdrops[:FLOOR_CARDS]:
            cards.append({"kind": "backdrop", "title": backdrop})
            searches.append(
                SalingQuery(collection_names=[name], backdrop_names=[backdrop], count=FLOOR_DEPTH)
            )
            sold_by.append(([], [backdrop], []))

        error = None if self.mrkt.configured else "MRKT не подключён: флор не узнать"
        found: list[ListingSnapshot | BaseException | None] = [None] * len(cards)
        if error is None:
            mono_card = 1 if data.monochrome else -1  # the whole choice: only monochrome pairs count
            found = await asyncio.gather(
                *(
                    self._cheapest(
                        query, is_pair if i == mono_card else None, MARKET_PAGES if i == mono_card else 1
                    )
                    for i, query in enumerate(searches)
                ),
                return_exceptions=True,
            )
            failures = [item for item in found if isinstance(item, BaseException)]
            for failure in failures:
                if not isinstance(failure, MrktError):
                    raise failure
            if failures:
                log.warning("MRKT floors failed", extra={"error": str(failures[0])})
                error = "MRKT ответил не на все запросы — попробуйте ещё раз"
        async with self.sessionmaker() as session:
            for i, (models, backdrops, symbols) in enumerate(sold_by):
                mono_only = data.monochrome and cards[i]["kind"] == "selection"
                sales = await listings_repo.recent_sales(
                    session,
                    name,
                    models=models,
                    backdrops=backdrops,
                    symbols=symbols,
                    limit=SOLD_SCAN if mono_only else 1,
                )
                last = next(
                    (
                        sale
                        for sale, gift in sales
                        if not mono_only or _pair_key(gift.model_name, gift.backdrop_name) in pairs
                    ),
                    None,
                )
                cards[i]["last_sale"] = ton(last.price_nano) if last else None
                cards[i]["last_sale_at"] = last.observed_at.isoformat() if last else None
        for card, item in zip(cards, found, strict=True):
            gift = item if isinstance(item, ListingSnapshot) else None
            card["floor"] = ton(gift.price_nano) if gift else None
            card["gift"] = self._gift_view(gift, gift.price_nano, None) if gift else None
            card["failed"] = isinstance(item, BaseException)
        return {"cards": cards, "error": error, "checked_at": datetime.now(UTC).isoformat()}

    async def market(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """ "Смотреть продажи": gifts on sale on MRKT now (the same search as the chat's 🔎) or the sales the bot
        saw in the MRKT feed."""
        data = MarketInput.model_validate(payload)
        await self.store.maybe_reload(min_interval=5)
        collection = await self._market_collection(data.collection)
        pairs = self._mono_pairs(collection, data.models) if data.monochrome else {}
        if data.view == "sold":
            return await self._sold(data, collection, pairs)
        if self.search is None or not self.mrkt.configured:
            raise ApiError("MRKT не подключён: объявления не загрузить", 503)
        spec = FilterSpec(
            id=0,
            user_id=user_id,
            name="Мини-приложение",
            kind=FilterKind.MONOCHROME if data.monochrome else FilterKind.REGULAR,
            enabled=True,
            autobuy=False,
            criteria=self._search_criteria(data, pairs),
            limits=FilterLimits(),
            activated_at=None,
        )
        try:
            result = await self.search.search(spec, max_pages=MARKET_PAGES, limit=MARKET_LIMIT)
        except MrktError as exc:
            raise ApiError(f"MRKT не ответил: {exc}", 502) from exc
        return {
            "view": "on_sale",
            "items": [
                self._gift_view(listing, listing.price_nano, _mono_type(enrichment.verdict))
                for listing, enrichment in result.items
            ],
            "scanned": result.scanned,
            "complete": result.exhausted,
        }

    async def _sold(
        self, data: MarketInput, collection: MarketCollection, pairs: dict[tuple[str, str], RefRecord]
    ) -> dict[str, Any]:
        known = self._mono_pairs(collection, [])
        async with self.sessionmaker() as session:
            sales = await listings_repo.recent_sales(
                session,
                collection.name,
                models=data.models,
                backdrops=data.backdrops,
                symbols=data.symbols,
                limit=SOLD_SCAN,
            )
            since = await listings_repo.first_sale_seen(session)
        items = []
        for sale, gift in sales:
            record = known.get(_pair_key(gift.model_name, gift.backdrop_name))
            if data.monochrome and _pair_key(gift.model_name, gift.backdrop_name) not in pairs:
                continue
            if data.pattern and not number_matches(data.pattern, gift.number):
                continue
            mono = (record.type.value if record.type else record.type_raw) if record else None
            items.append(
                {
                    **self._stored_gift_view(gift, sale.price_nano, mono),
                    "sold_at": sale.observed_at.isoformat(),
                }
            )
            if len(items) >= MARKET_LIMIT:
                break
        return {"view": "sold", "items": items, "since": since.isoformat() if since else None}

    async def leaders(self, user_id: int, days: int) -> dict[str, Any]:
        """Market leaders by what the bot saw in the MRKT feed: collections by sales volume, the most expensive
        sales, and the cheapest monochromes on sale."""
        if days not in LEADER_PERIODS:
            raise ApiError("Период — 1, 7 или 30 дней")
        now = datetime.now(UTC)
        since = now - timedelta(days=days)
        async with self.sessionmaker() as session:
            volume = await listings_repo.sales_by_collection(session, since)
            top = await listings_repo.top_sales(session, since)
            cheap = await listings_repo.cheapest_monochromes(session, now - timedelta(days=MONO_SEEN_DAYS))
            first = await listings_repo.first_sale_seen(session)
            slugs = await listings_repo.collection_slugs(session)
            titles = {c.name: c.title or c.name for c in await listings_repo.market_collections(session)}
        return {
            "days": days,
            "since": first.isoformat() if first else None,
            "collections": [
                {
                    "name": collection,
                    "title": titles.get(collection, collection),
                    "image": collection_thumb(giftname(collection, slug=slugs.get(collection))),
                    "sales": count,
                    "volume": ton(total),
                    "top": ton(highest),
                }
                for collection, count, total, highest in volume
            ],
            "sales": [
                {
                    **self._stored_gift_view(gift, sale.price_nano, gift.monochrome_type),
                    "sold_at": sale.observed_at.isoformat(),
                }
                for sale, gift in top
            ],
            "monochromes": [
                {
                    **self._stored_gift_view(gift, listing.price_nano, gift.monochrome_type or "monochrome"),
                    "seen_at": listing.last_seen_at.isoformat(),
                }
                for listing, gift in cheap
            ],
        }

    # ------------------------------------------------------------------ subscriptions
    async def create_subscription(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = SubscriptionInput.model_validate(payload)
        async with self.sessionmaker() as session, session.begin():
            title = await self._collection_title(session, data.collection)
            try:
                row = await filters_repo.create_filter(session, user_id, title, FilterKind.REGULAR)
            except ValueError as exc:
                raise ApiError(str(exc)) from exc
            self._apply_subscription(row, data, title, can_purchase=self.settings.can_purchase(user_id))
            await self._enable_mode(session, user_id, row)
            await session.flush()
            await misc.audit(session, "webapp_subscription_create", user_id=user_id, filter_id=row.id)
            view = self._rule_view(row)
        await self.filter_cache.invalidate()
        return view

    async def update_subscription(
        self, user_id: int, rule_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        data = SubscriptionInput.model_validate(payload)
        async with self.sessionmaker() as session, session.begin():
            row = await filters_repo.get_filter(session, user_id, rule_id)
            if row is None:
                raise ApiError("Подписка не найдена", 404)
            if not _editable(FilterCriteria.model_validate(row.criteria or {})):
                raise ApiError("Этот фильтр меняется в чате с ботом")
            title = await self._collection_title(session, data.collection)
            self._apply_subscription(row, data, title, can_purchase=self.settings.can_purchase(user_id))
            await self._enable_mode(session, user_id, row)
            await misc.audit(session, "webapp_subscription_update", user_id=user_id, filter_id=row.id)
            view = self._rule_view(row)
        await self.filter_cache.invalidate()
        return view

    @staticmethod
    def _apply_subscription(row: Filter, data: SubscriptionInput, title: str, *, can_purchase: bool) -> None:
        high = _price(data.max_price_ton)
        low = _range(data.min_price_ton, high, "цены")
        if data.autobuy and high is None:
            raise ApiError("Для покупок укажите цену «до»")
        criteria = FilterCriteria(
            collections=[data.collection],
            models=data.models,
            backdrops=data.backdrops,
            symbols=data.symbols,
            number_pattern=data.pattern,
            min_price_nano=low,
            max_price_nano=high,
        )
        filters_repo.update_criteria(row, criteria)
        limits = FilterLimits.model_validate(row.limits or {})
        limits.notify_new = data.notify_new
        limits.notify_price_drops = data.notify_price
        filters_repo.update_limits(row, limits)
        row.kind = (FilterKind.MONOCHROME if data.monochrome else FilterKind.REGULAR).value
        row.name = (data.name.strip() or title)[:64]
        filters_repo.set_enabled(row, True)
        row.autobuy = data.autobuy and can_purchase

    # ------------------------------------------------------------------ rules
    @staticmethod
    def _rule_collection(row: Filter) -> str | None:
        collections = FilterCriteria.model_validate(row.criteria or {}).collections
        return normalize_name(collections[0]) if len(collections) == 1 else None

    @staticmethod
    def _rule_view(row: Filter) -> dict[str, Any]:
        spec = filters_repo.to_spec(row)
        c = spec.criteria
        mode = "monochrome" if spec.kind is FilterKind.MONOCHROME else "selected" if c.backdrops else "any"
        simple = len(c.collections) == 1 and len(c.models) <= 1
        return {
            "id": row.id,
            "name": row.name,
            "kind": row.kind,
            "enabled": row.enabled,
            "autobuy": row.autobuy,
            "collection": c.collections[0] if len(c.collections) == 1 else None,
            "model": c.models[0] if len(c.models) == 1 else None,
            "backdrop_mode": mode,
            "backdrops": c.backdrops,
            "max_price": ton(c.max_price_nano),
            "max_count": spec.limits.max_count,
            "simple": simple and not c.picks,
            "plan": bool(c.picks),
            "picks": [p.label(monochrome=spec.kind is FilterKind.MONOCHROME) for p in c.picks],
            "pick_items": [
                {
                    "model": p.model,
                    "backdrops": p.backdrops,
                    "price": ton(p.max_price_nano),
                    "min": ton(p.min_price_nano),
                    "rule": p.price_rule.value,
                }
                for p in c.picks
            ],
            "summary": describe_criteria(spec.kind, c),
            "models": c.models,
            "symbols": c.symbols,
            "pattern": c.number_pattern,
            "min_price": ton(c.min_price_nano),
            "notify_new": spec.limits.notify_new,
            "notify_price": spec.limits.notify_price_drops,
            "editable": _editable(c),
        }

    async def rules(self, user_id: int) -> dict[str, Any]:
        async with self.sessionmaker() as session:
            rows = await filters_repo.list_filters(session, user_id)
            slugs = await listings_repo.collection_slugs(session)
        items = []
        for row in rows:
            view = self._rule_view(row)
            name = view["collection"]
            view["image"] = collection_thumb(giftname(name, slug=slugs.get(name))) if name else None
            items.append(view)
        return {"items": items}

    def _apply_rule(self, row: Filter, data: RuleInput, title: str, *, can_purchase: bool) -> None:
        if data.backdrop_mode == "selected" and not data.backdrops:
            raise ApiError("Выберите хотя бы один фон")
        max_price = _price(data.max_price_ton)
        if data.autobuy and max_price is None:
            raise ApiError("Для автопокупки укажите максимальную цену")
        current = FilterCriteria.model_validate(row.criteria or {})
        criteria = current.model_copy(
            update={
                "collections": [data.collection],
                "models": [data.model] if data.model else [],
                "backdrops": data.backdrops if data.backdrop_mode == "selected" else [],
                "max_price_nano": max_price,
            }
        )
        filters_repo.update_criteria(row, FilterCriteria.model_validate(criteria.model_dump()))
        limits = FilterLimits.model_validate(row.limits or {}).model_copy(
            update={"max_count": data.max_count}
        )
        filters_repo.update_limits(row, limits)
        row.kind = (FilterKind.MONOCHROME if data.backdrop_mode == "monochrome" else FilterKind.REGULAR).value
        label = {"any": "любой фон", "monochrome": "монохром", "selected": "выбранные фоны"}[
            data.backdrop_mode
        ]
        row.name = f"{title} · {data.model or 'все модели'} · {label}"[:64]
        filters_repo.set_enabled(row, data.enabled)
        row.autobuy = data.autobuy and can_purchase

    async def _collection_title(self, session: AsyncSession, name: str) -> str:
        row = await session.get(MarketCollection, name)
        if row is None:
            raise ApiError("Коллекция не найдена", 404)
        return row.title or row.name

    async def _enable_mode(self, session: AsyncSession, user_id: int, row: Filter) -> None:
        """Turning a rule's autobuy on also turns on its mode: the Mini App has a single switch per rule."""
        if not (row.enabled and row.autobuy):
            return
        prefs = await users_repo.get_settings(session, user_id)
        if row.kind == FilterKind.MONOCHROME.value:
            prefs.monochrome_autobuy_enabled = True
        else:
            prefs.autobuy_enabled = True

    async def create_rule(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = RuleInput.model_validate(payload)
        async with self.sessionmaker() as session, session.begin():
            title = await self._collection_title(session, data.collection)
            try:
                row = await filters_repo.create_filter(session, user_id, title, FilterKind.REGULAR)
            except ValueError as exc:
                raise ApiError(str(exc)) from exc
            self._apply_rule(row, data, title, can_purchase=self.settings.can_purchase(user_id))
            await self._enable_mode(session, user_id, row)
            await session.flush()
            await misc.audit(session, "webapp_rule_create", user_id=user_id, filter_id=row.id)
            view = self._rule_view(row)
        await self.filter_cache.invalidate()
        return view

    async def update_rule(self, user_id: int, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        async with self.sessionmaker() as session, session.begin():
            row = await filters_repo.get_filter(session, user_id, rule_id)
            if row is None:
                raise ApiError("Правило не найдено", 404)
            if set(payload) <= {"enabled", "autobuy", "notify_new", "notify_price"}:  # switches of the list
                if "enabled" in payload:
                    filters_repo.set_enabled(row, bool(payload["enabled"]))
                if "notify_new" in payload or "notify_price" in payload:
                    limits = FilterLimits.model_validate(row.limits or {})
                    if "notify_new" in payload:
                        limits.notify_new = bool(payload["notify_new"])
                    if "notify_price" in payload:
                        limits.notify_price_drops = bool(payload["notify_price"])
                    filters_repo.update_limits(row, limits)
                if "autobuy" in payload:
                    row.autobuy = bool(payload["autobuy"]) and self.settings.can_purchase(user_id)
                    criteria = FilterCriteria.model_validate(row.criteria or {})
                    if row.autobuy and criteria.max_price_nano is None and not criteria.picks:
                        raise ApiError("Для автопокупки укажите в правиле максимальную цену")
            elif filters_repo.is_plan(row):
                raise ApiError("Это правило меняется на странице коллекции")
            else:
                data = RuleInput.model_validate(payload)
                title = await self._collection_title(session, data.collection)
                self._apply_rule(row, data, title, can_purchase=self.settings.can_purchase(user_id))
            await self._enable_mode(session, user_id, row)
            await misc.audit(session, "webapp_rule_update", user_id=user_id, filter_id=row.id)
            view = self._rule_view(row)
        await self.filter_cache.invalidate()
        return view

    async def delete_rule(self, user_id: int, rule_id: int) -> None:
        async with self.sessionmaker() as session, session.begin():
            row = await filters_repo.get_filter(session, user_id, rule_id)
            if row is None:
                raise ApiError("Правило не найдено", 404)
            await filters_repo.delete_filter(session, row)
            await misc.audit(session, "webapp_rule_delete", user_id=user_id, filter_id=rule_id)
        await self.filter_cache.invalidate()

    # ------------------------------------------------------------------ settings
    async def save_settings(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = LimitsInput.model_validate(payload)
        async with self.sessionmaker() as session, session.begin():
            budget = await users_repo.get_or_create_budget(session, user_id, BudgetScope.USER)
            for field, attr in (
                ("per_purchase_ton", "per_purchase_limit_nano"),
                ("daily_ton", "daily_limit_nano"),
                ("total_ton", "total_limit_nano"),
            ):
                if field in payload:
                    setattr(budget, attr, _price(getattr(data, field)))
            prefs = await users_repo.get_settings(session, user_id)
            for field in ("autobuy_enabled", "monochrome_autobuy_enabled", "purchases_paused"):
                value = getattr(data, field)
                if value is not None:
                    setattr(prefs, field, value)
            if data.notify:
                unknown = set(data.notify) - set(NOTIFY_SWITCHES)
                if unknown:
                    raise ApiError("Неизвестная настройка уведомлений: " + ", ".join(sorted(unknown)))
                notify = NotificationSettings.model_validate(prefs.notify or {})
                for key, value in data.notify.items():
                    setattr(notify, key, value)
                prefs.notify = notify.model_dump()
            await misc.audit(session, "webapp_settings", user_id=user_id, changes=payload)
        await self.filter_cache.invalidate()
        return await self.me(user_id)

    async def set_mode(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Run mode switch for admins, up to RUN_MODE from .env (raising that ceiling is done on the host)."""
        if not self.settings.is_admin(user_id):
            raise ApiError("Режим работы меняет только администратор", 403)
        try:
            mode = RunMode(str(payload.get("mode", "")))
        except ValueError as exc:
            raise ApiError("Неизвестный режим работы") from exc
        if mode.rank > self.settings.run_mode.rank:
            raise ApiError(
                f"Сейчас разрешён режим не выше {self.settings.run_mode.value}: реальные покупки включаются "
                "на компьютере с ботом командой scripts\\live.cmd (Windows) или ./scripts/live.sh"
            )
        await self.control.set_run_mode(mode, by_user=user_id)
        return await self.me(user_id)

    async def set_speed(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """How often the bot polls MRKT for new listings (admins)."""
        if not self.settings.is_admin(user_id):
            raise ApiError("Скорость реакции меняет только администратор", 403)
        try:
            seconds = float(payload["interval"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError("Неверный интервал") from exc
        try:
            await self.control.set_poll_interval(seconds, by_user=user_id)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        return await self.me(user_id)

    async def emergency(self, user_id: int, *, stop: bool) -> dict[str, Any]:
        if stop:
            if not (self.settings.is_admin(user_id) or self.settings.can_purchase(user_id)):
                raise ApiError("Нет прав", 403)
            await self.control.stop_all(by_user=user_id, reason="мини-приложение")
        else:
            if not self.settings.is_admin(user_id):
                raise ApiError("Снять остановку может только администратор", 403)
            await self.control.resume(by_user=user_id)
        return await self.me(user_id)

    # ------------------------------------------------------------------ history
    async def history(self, user_id: int) -> dict[str, Any]:
        async with self.sessionmaker() as session:
            attempts = await purchases_repo.list_attempts(session, user_id, limit=30)
            ids = [a.gift_id for a in attempts]
            rows = (
                (await session.execute(select(Gift.id, Gift.name).where(Gift.id.in_(ids)))).all()
                if ids
                else []
            )
            names = {gift_id: gift_name for gift_id, gift_name in rows}
        items = []
        for a in attempts:
            title = (a.collection_name or a.gift_id) + (f" #{a.number}" if a.number is not None else "")
            items.append(
                {
                    "id": a.id,
                    "title": title,
                    "url": nft_url(names.get(a.gift_id)),
                    "image": gift_image(names.get(a.gift_id)),
                    "model": a.model_name,
                    "backdrop": a.backdrop_name,
                    "price": ton(a.final_price_nano or a.expected_price_nano),
                    "status": a.status,
                    "status_label": STATUS_LABELS.get(a.status, a.status),
                    "run_mode": a.run_mode,
                    "rule": a.filter_name,
                    "created_at": a.created_at.isoformat(),
                }
            )
        return {"items": items}
