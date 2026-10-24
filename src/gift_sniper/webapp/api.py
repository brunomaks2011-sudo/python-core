"""Data behind the Mini App screens.

A rule chosen in the Mini App is stored as an ordinary filter (one collection, optionally one model and a
backdrop choice), so the processor, budgets and the purchase service treat it exactly like a filter made in
the chat interface: every purchase still re-checks price, budgets, monochrome status and the run mode.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import Settings
from gift_sniper.db.models import Filter, Gift, MarketCollection
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import misc
from gift_sniper.db.repo import purchases as purchases_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import BudgetScope, FilterKind, PurchaseMode, PurchaseRunMode
from gift_sniper.domain.money import NANO_PER_TON, ton_to_nano
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.integrations.mrkt import MrktAttribute, MrktError
from gift_sniper.services.filters import FilterCriteria, FilterLimits, describe_criteria
from gift_sniper.services.percentages import monochrome_model_share
from gift_sniper.services.reference import ReferenceSnapshot, RefRecord
from gift_sniper.services.texts import nft_url
from gift_sniper.webapp.auth import WebAppIdentity

log = logging.getLogger(__name__)

ATTRIBUTES_TTL_SECONDS = 3600
ATTRIBUTES_FAILURE_TTL_SECONDS = 120
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


class _Store(Protocol):
    snapshot: ReferenceSnapshot


class _FilterCache(Protocol):
    async def invalidate(self) -> None: ...


class _Purchase(Protocol):
    async def scope_states(
        self, session: AsyncSession, *, user_id: int, prun: PurchaseRunMode, mode: PurchaseMode, spec: Any
    ) -> tuple[Any, Any, Any]: ...


class _Control(Protocol):
    async def run_mode(self) -> Any: ...
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
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.mrkt = mrkt
        self.store = store
        self.filter_cache = filter_cache
        self.purchase = purchase
        self.control = control
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
        async with self.sessionmaker() as session:
            prefs = await users_repo.get_settings(session, user_id)
            user_state, _, _ = await self.purchase.scope_states(
                session, user_id=user_id, prun=PurchaseRunMode.LIVE, mode=PurchaseMode.REGULAR, spec=None
            )
            rows = await filters_repo.list_filters(session, user_id)
        limits, usage = user_state.limits, user_state.usage
        snapshot = self.store.snapshot
        run_mode = (await self.control.run_mode()).value
        stopped = await self.control.is_stopped()
        buying = [r for r in rows if r.enabled and r.autobuy]
        kinds = {r.kind for r in buying}
        limits_ok = None not in (limits.per_purchase, limits.daily, limits.total)
        modes_ok = all(
            prefs.monochrome_autobuy_enabled if kind == FilterKind.MONOCHROME.value else prefs.autobuy_enabled
            for kind in kinds
        )
        can_purchase = self.settings.can_purchase(user_id)
        checklist = [
            {"ok": limits_ok, "text": "Общие лимиты: на покупку, на день и всего", "action": "settings"},
            {"ok": bool(buying), "text": "Хотя бы одно правило с автопокупкой", "action": "collections"},
            {"ok": bool(buying) and modes_ok, "text": "Автопокупка включена", "action": "settings"},
            {
                "ok": run_mode == "live",
                "text": "Режим live (сейчас покупки только имитируются)"
                if run_mode != "live"
                else "Режим live",
                "action": None,
            },
        ]
        if FilterKind.MONOCHROME.value in kinds or not snapshot.records_count:
            checklist.append(
                {
                    "ok": bool(snapshot.records_count),
                    "text": "Данные Gift Wiki для монохромов",
                    "action": None,
                }
            )
        if stopped:
            checklist.append({"ok": False, "text": "Аварийная остановка включена", "action": "settings"})
        if not can_purchase:
            checklist.append({"ok": False, "text": "У вас нет права на покупки", "action": None})
        return {
            "user_id": user_id,
            "is_admin": self.settings.is_admin(user_id),
            "can_purchase": can_purchase,
            "run_mode": run_mode,
            "stopped": stopped,
            "autobuy_enabled": prefs.autobuy_enabled,
            "monochrome_autobuy_enabled": prefs.monochrome_autobuy_enabled,
            "purchases_paused": prefs.purchases_paused,
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
        async with self.sessionmaker() as session:
            rows = await listings_repo.market_collections(session)
            models = await listings_repo.models_by_collection(session)
            rules = await filters_repo.list_filters(session, user_id)
        snapshot = self.store.snapshot
        rules_by_collection: dict[str, int] = {}
        for rule in rules:
            if rule.enabled:
                for name in FilterCriteria.model_validate(rule.criteria or {}).collections:
                    rules_by_collection[normalize_name(name)] = (
                        rules_by_collection.get(normalize_name(name), 0) + 1
                    )
        items = []
        for row in rows:
            records = self._records(snapshot, row.name, row.title)
            mono_models = {normalize_name(r.model_name) for r in records if r.model_name}
            observed = models.get(normalize_name(row.name), set())
            share = monochrome_model_share(mono_models, observed) if mono_models else None
            items.append(
                {
                    "name": row.name,
                    "title": row.title or row.name,
                    "floor": ton(row.floor_price_nano),
                    "monochrome_pairs": len(records),
                    "monochrome_models": len(mono_models),
                    "known_models": share.denominator if share else len(observed),
                    "monochrome_share": share.percent if share else None,
                    "photo": next((r.photo_url for r in records if r.photo_url), None),
                    "rules": rules_by_collection.get(normalize_name(row.name), 0),
                }
            )
        return {"items": items, "giftwiki_records": snapshot.records_count}

    async def collection(self, user_id: int, name: str) -> dict[str, Any]:
        async with self.sessionmaker() as session:
            row = await session.get(MarketCollection, name)
            if row is None:
                raise ApiError("Коллекция не найдена", 404)
        mrkt_models = await self._attributes("model", name)
        mrkt_backdrops = await self._attributes("backdrop", name)
        async with self.sessionmaker() as session, session.begin():
            if mrkt_models:
                await listings_repo.upsert_models(
                    session, name, [(m.name, m.rarity_permille) for m in mrkt_models], source="mrkt_models"
                )
        async with self.sessionmaker() as session:
            stored_models = await listings_repo.collection_models(session, name)
            seen_backdrops = await listings_repo.collection_backdrops(session, name)
            floors = await listings_repo.model_floors(session, name)
            rules = await filters_repo.list_filters(session, user_id)
        snapshot = self.store.snapshot
        records = self._records(snapshot, row.name, row.title)
        mono_by_model = _records_by_model(records)

        backdrops: dict[str, dict[str, Any]] = {}
        for backdrop in mrkt_backdrops:
            backdrops[normalize_name(backdrop.name)] = {
                "name": backdrop.name,
                "rarity": backdrop.rarity_permille,
            }
        for backdrop_name, rarity in seen_backdrops.items():
            item = backdrops.setdefault(
                normalize_name(backdrop_name), {"name": backdrop_name, "rarity": None}
            )
            item["rarity"] = item["rarity"] if item["rarity"] is not None else rarity
        for record in records:
            if record.backdrop_name:
                backdrops.setdefault(
                    normalize_name(record.backdrop_name), {"name": record.backdrop_name, "rarity": None}
                )

        models: dict[str, dict[str, Any]] = {}
        floor_by_model = {m.name: m.floor_price_nano for m in mrkt_models}
        for stored in stored_models:
            models[stored.model_norm] = {"name": stored.model_name, "rarity": stored.rarity_permille}
        for norm, recs in mono_by_model.items():
            models.setdefault(norm, {"name": recs[0].model_name, "rarity": None})
        rules_view = [self._rule_view(r) for r in rules if self._rule_collection(r) == normalize_name(name)]
        model_items = []
        for norm, model in models.items():
            recs = mono_by_model.get(norm, [])
            mono_backdrops = sorted(
                {normalize_name(r.backdrop_name or ""): r for r in recs}.values(),
                key=lambda r: r.backdrop_name or "",
            )
            rarities = [
                backdrops.get(normalize_name(r.backdrop_name or ""), {}).get("rarity") for r in mono_backdrops
            ]
            # share of this model's copies with a monochrome backdrop, from MRKT backdrop rarities
            known = [int(r) for r in rarities if r is not None]
            chance = sum(known) / 10 if rarities and len(known) == len(rarities) else None
            seen_floor, on_sale = floors.get(model["name"], (None, 0))
            model_items.append(
                {
                    "name": model["name"],
                    "rarity": model["rarity"] / 10 if model["rarity"] is not None else None,
                    "floor": ton(floor_by_model.get(model["name"]))
                    if floor_by_model.get(model["name"])
                    else None,
                    "seen_floor": ton(seen_floor),
                    "on_sale": on_sale,
                    "monochrome_backdrops": [
                        {"name": r.backdrop_name, "type": r.type.value if r.type else r.type_raw}
                        for r in mono_backdrops
                    ],
                    "monochrome_chance": chance,
                    "photo": next((r.photo_url for r in mono_backdrops if r.photo_url), None),
                    "rules": [
                        rule["id"] for rule in rules_view if normalize_name(rule["model"] or "") == norm
                    ],
                }
            )
        model_items.sort(
            key=lambda m: (-len(m["monochrome_backdrops"]), m["rarity"] if m["rarity"] is not None else 1e9)
        )
        mono_models = {n for n, recs in mono_by_model.items() if recs}
        share = monochrome_model_share(mono_models, set(models)) if mono_models else None
        backdrop_items = sorted(
            (
                {
                    "name": b["name"],
                    "rarity": b["rarity"] / 10 if b["rarity"] is not None else None,
                    "monochrome_for": sorted(
                        {
                            r.model_name
                            for r in records
                            if r.model_name and normalize_name(r.backdrop_name or "") == key
                        }
                    ),
                }
                for key, b in backdrops.items()
            ),
            key=lambda b: b["name"],
        )
        return {
            "name": row.name,
            "title": row.title or row.name,
            "floor": ton(row.floor_price_nano),
            "giftwiki": bool(records),
            "monochrome_pairs": len(records),
            "monochrome_share": share.percent if share else None,
            "monochrome_models": len(mono_models),
            "known_models": share.denominator if share else len(models),
            "models_source": "mrkt" if mrkt_models else "observed",
            "models": model_items,
            "backdrops": backdrop_items,
            "rules": rules_view,
        }

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
            "simple": simple,
            "summary": describe_criteria(spec.kind, c),
        }

    async def rules(self, user_id: int) -> dict[str, Any]:
        async with self.sessionmaker() as session:
            rows = await filters_repo.list_filters(session, user_id)
        return {"items": [self._rule_view(r) for r in rows]}

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
            if set(payload) <= {"enabled", "autobuy"}:  # a switch on the rules screen
                if "enabled" in payload:
                    filters_repo.set_enabled(row, bool(payload["enabled"]))
                if "autobuy" in payload:
                    row.autobuy = bool(payload["autobuy"]) and self.settings.can_purchase(user_id)
                    if (
                        row.autobuy
                        and FilterCriteria.model_validate(row.criteria or {}).max_price_nano is None
                    ):
                        raise ApiError("Для автопокупки укажите в правиле максимальную цену")
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
            await misc.audit(session, "webapp_settings", user_id=user_id, changes=payload)
        await self.filter_cache.invalidate()
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
