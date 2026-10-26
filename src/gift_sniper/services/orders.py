"""📋 Orders: the account's buy orders on MRKT, the orders of others above them, outbidding by 0.01 TON.

An order is outbid when the highest order for the same attributes (orders/top) belongs to someone else and
pays more. Outbidding replaces the order by one 0.01 TON above that order: MRKT documents no price change for
orders, so the old order is cancelled first and the new one created after it. That order of steps never
leaves two orders that could both buy a gift; if the new order fails, the user is told that no order is left.
The result is reported only after MRKT's list of the account's orders shows it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import RunMode, Settings
from gift_sniper.db.repo import misc
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import BudgetScope
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.types import MrktOrder
from gift_sniper.integrations.mrkt import MrktError
from gift_sniper.services import texts
from gift_sniper.services.notifications import Notifier
from gift_sniper.services.user_prefs import NotificationSettings

log = logging.getLogger(__name__)

STEP = 10_000_000  # 0.01 TON
MAX_WATCHED = 20  # orders checked per round: each costs a request to MRKT
SEEN_TTL = 7 * 24 * 3600


class _Orders(Protocol):
    @property
    def configured(self) -> bool: ...
    async def my_orders(self, *, count: int = 20) -> list[MrktOrder]: ...
    async def orders(
        self,
        collection: str,
        *,
        models: list[str] | None = None,
        backdrops: list[str] | None = None,
        symbols: list[str] | None = None,
        count: int = 20,
    ) -> list[MrktOrder]: ...
    async def top_order(
        self,
        collection: str,
        model: str | None = None,
        backdrop: str | None = None,
        symbol: str | None = None,
    ) -> MrktOrder | None: ...
    async def create_order(
        self,
        *,
        collection: str,
        model: str | None,
        backdrop: str | None,
        symbol: str | None,
        price_nano: int,
        min_price_nano: int | None = None,
        quantity: int = 1,
        is_transferable: bool = False,
    ) -> Any: ...
    async def cancel_order(self, order_id: str) -> None: ...


class _Floors(Protocol):
    async def lowest(
        self,
        collection: str,
        *,
        model: str | None = None,
        backdrop: str | None = None,
        exclude_gift: str | None = None,
    ) -> int | None: ...


class _Control(Protocol):
    async def run_mode(self) -> RunMode: ...
    async def is_stopped(self) -> bool: ...


def attributes_text(order: MrktOrder) -> str:
    parts = [order.collection_name or "Коллекция не указана"]
    parts += [
        f"{label}: {value}"
        for label, value in (
            ("модель", order.model_name),
            ("фон", order.backdrop_name),
            ("символ", order.symbol_name),
        )
        if value
    ]
    return " · ".join(parts)


def same_attributes(a: MrktOrder, b: MrktOrder) -> bool:
    def norm(values: tuple[str | None, ...]) -> tuple[str, ...]:
        return tuple((v or "").strip().lower() for v in values)

    return norm(a.attributes) == norm(b.attributes)


@dataclass(slots=True)
class Floor:
    label: str  # "модели", "фона", ...
    price_nano: int | None


@dataclass(slots=True)
class OrderView:
    order: MrktOrder
    top: MrktOrder | None  # the highest order for the same attributes; None: MRKT shows none
    floors: list[Floor] = field(default_factory=list)

    @property
    def outbid(self) -> bool:
        return (
            self.top is not None
            and self.top.order_id != self.order.order_id
            and self.top.price_nano > self.order.price_nano
        )

    @property
    def next_price_nano(self) -> int | None:
        """The price that beats the highest order by 0.01 TON."""
        return self.top.price_nano + STEP if self.outbid and self.top is not None else None

    def lines(self) -> list[str]:
        """HTML lines for messages."""
        lines = [
            f"🎁 {texts.e(attributes_text(self.order))}",
            f"Ваш ордер: <b>{format_ton(self.order.price_nano)}</b>",
        ]
        if self.top is not None and self.outbid:
            lines.append(f"Перебили: <b>{format_ton(self.top.price_nano)}</b> — ордер другого покупателя")
        elif self.top is not None and self.top.order_id != self.order.order_id:
            lines.append(f"Такая же цена у другого ордера: {format_ton(self.top.price_nano)}")
        for floor in self.floors:
            if floor.price_nano is None:
                lines.append(f"Флор {floor.label}: нет объявлений или MRKT не ответил")
                continue
            line = f"Флор {floor.label}: {format_ton(floor.price_nano)}"
            if self.next_price_nano is not None:
                gap = floor.price_nano - self.next_price_nano
                side = "выше" if gap >= 0 else "ниже"
                line += f" — на {format_ton(abs(gap))} {side} нового ордера"
            lines.append(line)
        if self.next_price_nano is not None:
            lines.append(f"Перебить на 0.01 → <b>{format_ton(self.next_price_nano)}</b>")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": order_dict(self.order),
            "top": order_dict(self.top) if self.top is not None else None,
            "outbid": self.outbid,
            "next_price_nano": self.next_price_nano,
            "floors": [{"label": f.label, "price_nano": f.price_nano} for f in self.floors],
        }


def order_dict(order: MrktOrder, *, mine: bool | None = None) -> dict[str, Any]:
    return {
        "id": order.order_id,
        "collection": order.collection_name,
        "model": order.model_name,
        "backdrop": order.backdrop_name,
        "symbol": order.symbol_name,
        "price_nano": order.price_nano,
        "min_price_nano": order.min_price_nano,
        "quantity": order.quantity,
        "mine": order.is_mine if mine is None else mine,
    }


@dataclass(slots=True)
class OutbidResult:
    status: str  # done | dry_run | refused | moved | lost | unconfirmed
    text: str  # plain text, no HTML
    price_nano: int | None = None  # the new order's price; with "moved", the price that beats the new top

    @property
    def ok(self) -> bool:
        return self.status in ("done", "dry_run")


class OrdersService:
    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        mrkt: _Orders,
        floors: _Floors | None,
        control: _Control,
        notifier: Notifier | None = None,
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.mrkt = mrkt
        self.floors = floors
        self.control = control
        self.notifier = notifier
        self.prefix = settings.redis_prefix

    # ================================================================== reading
    async def floors_for(self, order: MrktOrder) -> list[Floor]:
        """The lowest asking prices the order competes with: of its model, its backdrop, or the collection."""
        if self.floors is None or not order.collection_name:
            return []
        wanted: list[tuple[str, str | None, str | None]] = []
        if order.model_name and order.backdrop_name:
            wanted.append(("модели на этом фоне", order.model_name, order.backdrop_name))
        if order.model_name:
            wanted.append(("модели", order.model_name, None))
        if order.backdrop_name:
            wanted.append(("фона", None, order.backdrop_name))
        if not wanted:
            wanted.append(("коллекции", None, None))
        return [
            Floor(label, await self.floors.lowest(order.collection_name, model=model, backdrop=backdrop))
            for label, model, backdrop in wanted
        ]

    async def view(self, order: MrktOrder, *, with_floors: bool = True) -> OrderView:
        top = None
        if order.collection_name:
            top = await self.mrkt.top_order(
                order.collection_name, order.model_name, order.backdrop_name, order.symbol_name
            )
        floors = await self.floors_for(order) if with_floors else []
        return OrderView(order, top, floors)

    async def mine(self, *, limit: int = MAX_WATCHED, with_floors: bool = True) -> list[OrderView]:
        """The account's orders, each with the highest order for its attributes."""
        orders = await self.mrkt.my_orders(count=limit)
        return [await self.view(order, with_floors=with_floors) for order in orders[:limit]]

    async def market(
        self, collection: str, *, model: str | None = None, backdrop: str | None = None
    ) -> tuple[list[dict[str, Any]], list[Floor]]:
        """Everyone's orders for a collection (optionally one model / backdrop), the highest first."""
        orders = await self.mrkt.orders(
            collection, models=[model] if model else None, backdrops=[backdrop] if backdrop else None
        )
        mine_ids = {o.order_id for o in await self.mrkt.my_orders()}
        probe = MrktOrder("", collection, model, backdrop, None, 1)
        floors = await self.floors_for(probe)
        rows = [order_dict(o, mine=o.order_id in mine_ids or o.is_mine is True) for o in orders]
        rows.sort(key=lambda r: -int(r["price_nano"]))
        return rows, floors

    # ================================================================== outbidding
    async def _refusal(self, user_id: int, price_nano: int) -> str | None:
        if await self.control.run_mode() is RunMode.NOTIFY_ONLY:
            return "Режим только уведомлений: ордера не меняются"
        if await self.control.is_stopped():
            return "Аварийная остановка: ордера не меняются"
        async with self.sessionmaker() as session:
            user = await users_repo.get_user(session, user_id)
            budgets = await users_repo.get_budgets(session, user_id)
        if user is None or not user.can_purchase or user.is_blocked:
            return "Нет прав на покупки"
        limit = budgets[BudgetScope.USER].per_purchase_limit_nano if BudgetScope.USER in budgets else None
        if limit is None:
            return "Задайте лимит на одну покупку в профиле: ордер покупает подарок без подтверждения"
        if price_nano > limit:
            return f"Ордер {format_ton(price_nano)} выше лимита на одну покупку {format_ton(limit)}"
        return None

    async def outbid(self, *, user_id: int, order_id: str, price_nano: int) -> OutbidResult:
        """Replace the account's order by one at `price_nano` (the price shown on the button)."""
        refusal = await self._refusal(user_id, price_nano)
        if refusal:
            return OutbidResult("refused", refusal)
        try:
            current = next((o for o in await self.mrkt.my_orders() if o.order_id == order_id), None)
        except MrktError as exc:
            return OutbidResult("refused", f"MRKT не ответил: {exc}")
        if current is None or not current.collection_name:
            return OutbidResult("refused", "Этого ордера уже нет среди ваших ордеров на MRKT")
        if price_nano <= current.price_nano:
            return OutbidResult("refused", "Новая цена не выше текущей цены ордера")
        try:
            view = await self.view(current, with_floors=False)
        except MrktError as exc:
            return OutbidResult("refused", f"MRKT не показал лучший ордер: {exc}")
        if not view.outbid or view.top is None:
            return OutbidResult("refused", "Ваш ордер уже самый высокий, перебивать не нужно")
        if view.top.price_nano >= price_nano:  # outbid again since the message was sent
            return OutbidResult(
                "moved",
                f"Ордер уже перебили выше: {format_ton(view.top.price_nano)}. Перебить можно за "
                f"{format_ton(view.next_price_nano)}",
                view.next_price_nano,
            )
        # 0.01 TON above the highest order now; never above the price the user agreed to
        price_nano = min(price_nano, view.top.price_nano + STEP)
        old = format_ton(current.price_nano)
        if await self.control.run_mode() is not RunMode.LIVE:
            return OutbidResult(
                "dry_run",
                f"Тестовый режим: ордер был бы перебит {old} → {format_ton(price_nano)}, MRKT не менялся",
                price_nano,
            )
        await self._audit("order_outbid_started", user_id, order_id=order_id, price=price_nano)
        try:
            await self.mrkt.cancel_order(order_id)
        except MrktError as exc:
            return OutbidResult("refused", f"MRKT не отменил старый ордер, ничего не изменено: {exc}")
        min_price = current.min_price_nano
        try:
            await self.mrkt.create_order(
                collection=current.collection_name,
                model=current.model_name,
                backdrop=current.backdrop_name,
                symbol=current.symbol_name,
                price_nano=price_nano,
                min_price_nano=min_price if min_price is not None and min_price <= price_nano else None,
                quantity=current.quantity or 1,
                is_transferable=bool(current.raw.get("isTransferable")),
            )
        except MrktError as exc:
            await self._audit("order_outbid_lost", user_id, order_id=order_id, error=str(exc)[:300])
            return OutbidResult(
                "lost",
                f"Старый ордер {old} отменён, но MRKT не создал новый: {exc}. Сейчас ордера нет — "
                "создайте его в MRKT заново",
            )
        try:
            after = await self.mrkt.my_orders()
        except MrktError:
            after = []
        placed = next(
            (
                o
                for o in after
                if same_attributes(o, current) and o.price_nano == price_nano and o.order_id != order_id
            ),
            None,
        )
        if placed is None:
            await self._audit("order_outbid_unconfirmed", user_id, order_id=order_id, price=price_nano)
            return OutbidResult(
                "unconfirmed",
                f"Старый ордер {old} отменён, MRKT принял новый за {format_ton(price_nano)}, но в списке "
                "ваших ордеров его пока нет. Проверьте ордера в MRKT",
                price_nano,
            )
        await self._audit("order_outbid_done", user_id, order_id=placed.order_id, price=price_nano)
        return OutbidResult(
            "done",
            f"Ордер перебит: {old} → {format_ton(price_nano)}. MRKT показывает новый ордер",
            price_nano,
        )

    async def _audit(self, action: str, user_id: int, **details: Any) -> None:
        async with self.sessionmaker() as session, session.begin():
            await misc.audit(session, action, user_id=user_id, **details)

    # ================================================================== watching
    async def _recipients(self) -> list[int]:
        async with self.sessionmaker() as session:
            users = await users_repo.list_active_users(session)
            wanted = []
            for user in users:
                if not user.can_purchase:
                    continue
                prefs = NotificationSettings.model_validate(
                    (await users_repo.get_settings(session, user.id)).notify or {}
                )
                if prefs.orders_outbid:
                    wanted.append(user.id)
        return wanted

    async def watch(self) -> int:
        """Tell users once about every order of others that is now above one of the account's orders."""
        if self.notifier is None or self.settings.orders_poll_seconds <= 0 or not self.mrkt.configured:
            return 0
        recipients = await self._recipients()
        if not recipients:
            return 0
        try:
            views = await self.mine(with_floors=False)
        except MrktError as exc:
            log.warning("MRKT orders check failed", extra={"error": str(exc)})
            return 0
        sent = 0
        for view in views:
            if not view.outbid or view.top is None or view.next_price_nano is None:
                continue
            key = (
                f"{self.prefix}:orders:outbid:{view.order.order_id}:{view.top.order_id}:{view.top.price_nano}"
            )
            if not await self.redis.set(key, "1", nx=True, ex=SEEN_TTL):
                continue  # this outbid was already reported
            view.floors = await self.floors_for(view.order)
            text = "\n".join(["🔔 <b>Ваш ордер перебили</b>", *view.lines()])
            for user_id in recipients:
                token = await self.notifier.make_token(
                    {"order_id": view.order.order_id, "price": view.next_price_nano}, ttl=24 * 3600
                )
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=f"⚡ Перебить → {format_ton(view.next_price_nano)}",
                                callback_data=f"ob:{token}",
                            )
                        ]
                    ]
                )
                await self.notifier.send(user_id, text, kind="orders", keyboard=keyboard, critical=True)
            sent += 1
        return sent
