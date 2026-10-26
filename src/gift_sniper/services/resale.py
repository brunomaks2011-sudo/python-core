"""🤖 The resale assistant: buys a gift when it can be sold again with a profit, then lists it on MRKT.

The "AI" is a formula over market data the bot has seen, not a language model:

* value: the median price buyers paid for the same picture (the same model on the same backdrop) in the
  last `period_days` days, from the sales of the MRKT feed kept in the price history. A sale of this very gift
  counts as well. With fewer than `min_sales` such sales the median of the model on any backdrop is used, and
  with fewer than that of the model too, nothing is bought. The median keeps one odd sale from moving it;
* competitors: a cheaper copy of the same picture on sale right now caps the value, priced 0.01 TON under it,
  because buyers take the cheaper copy first;
* fee: MRKT adds its fee to the price a seller sets: a gift listed at L costs buyers L × (1 + fee). To be bought
  for the value V the gift is listed at V / (1 + fee), rounded down to 0.01 TON, and the seller gets that;
* decision: profit = list price − purchase price. The gift is bought when the profit is at least
  `min_profit_nano` (0.30 TON by default), and listed for sale once MRKT confirms the purchase.
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gift_sniper.config import RunMode, Settings
from gift_sniper.db.models import ResalePosition
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import misc
from gift_sniper.db.repo import resale as resale_repo
from gift_sniper.domain.enums import PurchaseRunMode, ResaleStatus
from gift_sniper.domain.money import format_ton
from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import ListingSnapshot
from gift_sniper.integrations.mrkt import MrktError
from gift_sniper.services import texts
from gift_sniper.services.filters import ResaleRules
from gift_sniper.services.notifications import Notifier

log = logging.getLogger(__name__)

CENT = 10_000_000  # 0.01 TON
PLAN_TTL = 2 * 24 * 3600  # a plan outlives its purchase: an uncertain purchase may be confirmed hours later
MAX_LIST_TRIES = 5
OWNERSHIP_READS = 3
OWNERSHIP_PAUSE = 2.0  # seconds
SALES_CACHE_LIMIT = 5000


def fee_permille(percent: float) -> int:
    return round(percent * 10)


def list_price_for(buyer_price_nano: int, fee: int) -> int:
    """The price to set on MRKT so that buyers pay at most `buyer_price_nano` with the fee (0.01 TON steps)."""
    return max(0, buyer_price_nano) * 1000 // (1000 + fee) // CENT * CENT


def buyer_price_for(list_price_nano: int, fee: int) -> int:
    """What buyers pay for a gift listed at `list_price_nano` (MRKT adds its fee on top)."""
    return list_price_nano * (1000 + fee) // 1000


def median(values: Sequence[int]) -> int | None:
    return int(statistics.median(values)) if values else None


def fee_text(fee: int) -> str:
    return f"{fee / 10:g}%"


class _Gifts(Protocol):
    async def get_gift(self, gift_id: str, *, priority: bool = True) -> ListingSnapshot | None: ...
    async def list_for_sale(self, gift_id: str, price_nano: int) -> list[str]: ...


class _Floors(Protocol):
    async def cheapest(
        self, collection: str, model: str | None = None, backdrop: str | None = None
    ) -> list[tuple[str, int]] | None: ...


class _Control(Protocol):
    async def run_mode(self) -> RunMode: ...
    async def is_stopped(self) -> bool: ...


@dataclass(slots=True)
class ResalePlan:
    """What the assistant knows about one listing and what it would do with it."""

    gift_id: str
    buy_price_nano: int
    fee_permille: int
    period_days: int
    min_sales: int
    min_profit_nano: int
    picture_sales: int = 0  # sales of the same model on the same backdrop
    picture_median_nano: int | None = None
    model_sales: int = 0  # sales of the model on any backdrop
    model_median_nano: int | None = None
    gift_sales: int = 0  # sales of this very gift
    gift_median_nano: int | None = None
    basis: str | None = None  # picture | model: which median is the value
    competitor_nano: int | None = None  # the cheapest other copy of the picture on sale now
    target_nano: int | None = None  # what buyers will pay, the fee included
    list_price_nano: int | None = None  # the price set on MRKT, what the seller gets
    profit_nano: int | None = None
    reason: str = ""  # why the assistant does not buy; empty when it does

    @property
    def ok(self) -> bool:
        return not self.reason and self.profit_nano is not None and self.profit_nano >= self.min_profit_nano

    @property
    def sales_count(self) -> int:
        return self.picture_sales if self.basis == "picture" else self.model_sales

    def at_price(self, price_nano: int) -> ResalePlan:
        """The same plan for another purchase price (the price MRKT confirmed, or a fresh one)."""
        profit = self.list_price_nano - price_nano if self.list_price_nano is not None else None
        return replace(self, buy_price_nano=price_nano, profit_nano=profit)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> ResalePlan | None:
        if not isinstance(data, dict):
            return None
        known = {f.name for f in fields(cls)}
        try:
            return cls(**{k: v for k, v in data.items() if k in known})
        except TypeError:
            return None

    def lines(self) -> list[str]:
        """What the decision rests on (HTML-safe: only numbers and fixed words)."""
        days = f"{self.period_days} дн."
        lines = [
            f"📊 Продажи за {days}: модель + фон — {self.picture_sales}"
            + (f" (медиана {format_ton(self.picture_median_nano)})" if self.picture_median_nano else "")
            + f", вся модель — {self.model_sales}"
            + (f" (медиана {format_ton(self.model_median_nano)})" if self.model_median_nano else "")
        ]
        if self.gift_sales:
            lines.append(
                f"🎁 Этот подарок продавался {self.gift_sales} раз(а), медиана {format_ton(self.gift_median_nano)}"
            )
        if self.competitor_nano is not None:
            lines.append(
                f"🏷 Такой же (модель + фон) сейчас дешевле всего: {format_ton(self.competitor_nano)}"
            )
        if self.list_price_nano is not None and self.target_nano is not None:
            lines.append(
                f"💰 Выставить за {format_ton(self.list_price_nano)} — покупатели увидят "
                f"{format_ton(buyer_price_for(self.list_price_nano, self.fee_permille))} "
                f"с комиссией MRKT {fee_text(self.fee_permille)}"
            )
        if self.profit_nano is not None:
            lines.append(
                f"📈 Профит: {format_ton(self.profit_nano)} (нужно от {format_ton(self.min_profit_nano)})"
            )
        if self.reason:
            lines.append(f"⛔️ {self.reason}")
        return lines


@dataclass(slots=True)
class ListResult:
    status: str
    text: str


class ResaleAssistant:
    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis,
        mrkt: _Gifts,
        floors: _Floors | None,
        control: _Control,
        notifier: Notifier | None = None,
        *,
        cache_ttl: float = 60.0,
    ) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.redis = redis
        self.mrkt = mrkt
        self.floors = floors
        self.control = control
        self.notifier = notifier
        self.cache_ttl = cache_ttl
        self.prefix = settings.redis_prefix
        self._sales: dict[tuple[str, str, int], tuple[float, list[tuple[int, str | None, str]]]] = {}
        self.sleep = asyncio.sleep  # replaced in tests

    # ================================================================== valuation
    async def model_sales(self, collection: str, model: str, days: int) -> list[tuple[int, str | None, str]]:
        """(price, backdrop, gift id) of the model's sales in the last `days` days, cached for a minute."""
        key = (normalize_name(collection), normalize_name(model), days)
        cached = self._sales.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            return cached[1]
        since = datetime.now(UTC) - timedelta(days=days)
        async with self.sessionmaker() as session:
            rows = await listings_repo.model_sales(session, collection, model, since)
        if len(self._sales) >= SALES_CACHE_LIMIT:
            self._sales.clear()
        self._sales[key] = (time.monotonic(), rows)
        return rows

    async def plan(self, listing: ListingSnapshot, rules: ResaleRules) -> ResalePlan:
        price = listing.price_nano
        plan = ResalePlan(
            gift_id=listing.gift_id,
            buy_price_nano=price or 0,
            fee_permille=fee_permille(rules.fee_percent),
            period_days=rules.period_days,
            min_sales=rules.min_sales,
            min_profit_nano=rules.min_profit_nano,
        )
        if price is None or price <= 0:
            plan.reason = "нет цены"
            return plan
        if not listing.collection_name or not listing.model_name or not listing.backdrop_name:
            plan.reason = "нет коллекции, модели или фона"
            return plan
        sales = await self.model_sales(listing.collection_name, listing.model_name, rules.period_days)
        backdrop = normalize_name(listing.backdrop_name)
        picture = [p for p, b, _ in sales if b is not None and normalize_name(b) == backdrop]
        own = [p for p, _, gift in sales if gift == listing.gift_id]
        plan.picture_sales, plan.picture_median_nano = len(picture), median(picture)
        plan.model_sales, plan.model_median_nano = len(sales), median([p for p, _, _ in sales])
        plan.gift_sales, plan.gift_median_nano = len(own), median(own)
        if plan.picture_sales >= rules.min_sales:
            plan.basis, value = "picture", plan.picture_median_nano
        elif plan.model_sales >= rules.min_sales:
            plan.basis, value = "model", plan.model_median_nano
        else:
            plan.reason = (
                f"мало продаж за {rules.period_days} дн.: модель + фон — {plan.picture_sales}, "
                f"вся модель — {plan.model_sales}, нужно от {rules.min_sales}"
            )
            return plan
        assert value is not None
        if not self._price(plan, value):
            return plan  # the sales alone do not pay: no need to ask MRKT about competitors
        if self.floors is None:
            plan.reason = "нет данных о других объявлениях MRKT"
            return plan
        cheapest = await self.floors.cheapest(
            listing.collection_name, listing.model_name, listing.backdrop_name
        )
        if cheapest is None:
            plan.reason = "MRKT не ответил, есть ли такой же подарок дешевле"
            return plan
        plan.competitor_nano = next((p for gift, p in cheapest if gift != listing.gift_id), None)
        if plan.competitor_nano is not None and plan.competitor_nano - CENT < value:
            value = plan.competitor_nano - CENT
        self._price(plan, value)
        return plan

    @staticmethod
    def _price(plan: ResalePlan, value: int) -> bool:
        plan.target_nano = value
        plan.list_price_nano = list_price_for(value, plan.fee_permille)
        plan.profit_nano = plan.list_price_nano - plan.buy_price_nano
        if plan.profit_nano < plan.min_profit_nano:
            plan.reason = f"профит {format_ton(plan.profit_nano)} меньше {format_ton(plan.min_profit_nano)}"
            return False
        plan.reason = ""
        return True

    # ================================================================== plans between decision and purchase
    def _plan_key(self, user_id: int, gift_id: str) -> str:
        return f"{self.prefix}:resale:plan:{user_id}:{gift_id}"

    async def remember(self, user_id: int, plan: ResalePlan) -> None:
        await self.redis.set(self._plan_key(user_id, plan.gift_id), json.dumps(plan.to_dict()), ex=PLAN_TTL)

    async def recall(self, user_id: int, gift_id: str) -> ResalePlan | None:
        raw = await self.redis.get(self._plan_key(user_id, gift_id))
        if not raw:
            return None
        try:
            return ResalePlan.from_dict(json.loads(raw))
        except ValueError:
            return None

    async def rules(self, user_id: int) -> ResaleRules | None:
        """The assistant's current settings of a user; None when the user has no assistant."""
        async with self.sessionmaker() as session:
            row = await filters_repo.assistant_filter(session, user_id)
        return filters_repo.to_spec(row).criteria.resale if row is not None else None

    # ================================================================== after a purchase
    async def after_purchase(
        self,
        *,
        user_id: int,
        attempt_id: int | None,
        listing: ListingSnapshot,
        price_nano: int,
        run_mode: PurchaseRunMode,
        rules: ResaleRules | None,
    ) -> ResalePosition:
        """Record the bought gift (test mode: what would have been bought) and list it for sale."""
        stored = await self.recall(user_id, listing.gift_id)
        plan = stored.at_price(price_nano) if stored is not None else None
        rules = rules or ResaleRules()
        dry = run_mode is PurchaseRunMode.DRY_RUN
        status = ResaleStatus.DRY_RUN if dry else ResaleStatus.BOUGHT
        reason, tries = None, 0
        if plan is None or plan.list_price_nano is None:
            reason = "Оценка ассистента не найдена: выставьте подарок на MRKT сами"
            if not dry:
                status, tries = ResaleStatus.FAILED, MAX_LIST_TRIES
        elif dry:
            reason = f"Тестовый режим: был бы выставлен за {format_ton(plan.list_price_nano)}"
        elif not rules.auto_list:
            reason = "Автовыставление выключено: нажмите «Выставить» в мини-приложении или выставьте на MRKT"
        position = ResalePosition(
            user_id=user_id,
            attempt_id=attempt_id,
            run_mode=run_mode.value,
            gift_id=listing.gift_id,
            name=listing.title[:128],
            collection_name=listing.collection_title or listing.collection_name,
            model_name=listing.model_name,
            backdrop_name=listing.backdrop_name,
            number=listing.number,
            buy_price_nano=price_nano,
            target_price_nano=plan.target_nano if plan else None,
            list_price_nano=plan.list_price_nano if plan else None,
            fee_permille=plan.fee_permille if plan else fee_permille(rules.fee_percent),
            expected_profit_nano=plan.profit_nano if plan else None,
            sales_count=plan.sales_count if plan else None,
            status=status.value,
            reason=reason,
            tries=tries,
        )
        async with self.sessionmaker() as session, session.begin():
            session.add(position)
            await session.flush()
            await misc.audit(
                session,
                "resale_position",
                user_id=user_id,
                gift_id=listing.gift_id,
                run_mode=run_mode.value,
                list_price=position.list_price_nano,
            )
        if status is ResaleStatus.FAILED:
            await self._tell(position, f"⚠️ <b>{texts.e(position.name)}</b>: {texts.e(reason)}")
        elif not dry and reason is None:
            await self.list_position(position.id)
        return position

    # ================================================================== listing
    async def list_position(self, position_id: int, *, user_id: int | None = None) -> ListResult:
        """Put a bought gift up for sale at the planned price; success only after MRKT confirms it."""
        async with self.sessionmaker() as session:
            position = await resale_repo.get(session, position_id)
        if position is None or (user_id is not None and position.user_id != user_id):
            return ListResult("missing", "Позиция не найдена")
        if position.run_mode != PurchaseRunMode.LIVE.value:
            return ListResult(position.status, "Это запись тестового режима: подарок не покупался")
        if position.status not in resale_repo.OPEN:
            return ListResult(position.status, "Подарок уже выставлен или продан")
        price = position.list_price_nano
        if price is None or price <= 0:
            return await self._failed(position, "Нет цены для выставления: выставьте подарок на MRKT сами")
        if await self.control.run_mode() is not RunMode.LIVE:
            return await self._postpone(position, "Бот не в боевом режиме: выставление отложено")
        if await self.control.is_stopped():
            return await self._postpone(position, "Аварийная остановка: выставление отложено")
        try:
            gift = await self._owned_gift(position.gift_id)
        except MrktError as exc:
            return await self._failed(position, f"MRKT не ответил: {exc}")
        if gift is None or gift.is_mine is False:
            return await self._failed(position, "MRKT не показывает подарок в аккаунте")
        now = datetime.now(UTC)
        if gift.is_on_sale:
            return await self._listed(position, gift, already=True)
        if gift.next_resale_at is not None and gift.next_resale_at > now:
            return await self._wait(position, gift.next_resale_at)
        try:
            ids = await self.mrkt.list_for_sale(position.gift_id, price)
        except MrktError as exc:
            return await self._failed(position, f"MRKT не выставил подарок: {exc}")
        try:
            after = await self.mrkt.get_gift(position.gift_id)
        except MrktError:
            after = None
        if after is not None and after.is_on_sale is True:
            return await self._listed(position, after)
        if after is None and position.gift_id in ids:  # MRKT's answer names the gift: listed
            return await self._listed(position, None)
        return await self._failed(position, "MRKT не подтвердил выставление на продажу")

    async def _owned_gift(self, gift_id: str) -> ListingSnapshot | None:
        """The gift as MRKT shows it; right after a purchase MRKT may need a moment to show it as the account's."""
        gift = await self.mrkt.get_gift(gift_id)
        for _ in range(OWNERSHIP_READS - 1):
            if gift is not None and gift.is_mine is not False:
                break
            await self.sleep(OWNERSHIP_PAUSE)
            gift = await self.mrkt.get_gift(gift_id)
        return gift

    async def _update(self, position_id: int, **values: Any) -> ResalePosition | None:
        async with self.sessionmaker() as session, session.begin():
            row = await resale_repo.get(session, position_id, lock=True)
            if row is None:
                return None
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(UTC)
            await session.flush()
            return row

    async def _postpone(self, position: ResalePosition, reason: str) -> ListResult:
        await self._update(position.id, reason=reason)
        return ListResult(position.status, reason)

    async def _wait(self, position: ResalePosition, until: datetime) -> ListResult:
        text = f"MRKT разрешит выставить подарок с {texts.utc_label(until)}, бот выставит его сам"
        await self._update(position.id, status=ResaleStatus.WAITING.value, resale_at=until, reason=text)
        if position.status != ResaleStatus.WAITING.value:
            await self._tell(position, f"⏳ <b>{texts.e(position.name)}</b>: {texts.e(text)}")
        return ListResult(ResaleStatus.WAITING.value, text)

    async def _failed(self, position: ResalePosition, reason: str) -> ListResult:
        tries = position.tries + 1
        final = tries >= MAX_LIST_TRIES
        text = reason + (
            ". Попытки закончились: выставьте подарок на MRKT сами" if final else ". Бот попробует ещё раз"
        )
        await self._update(position.id, status=ResaleStatus.FAILED.value, reason=text, tries=tries)
        log.warning("resale listing failed", extra={"position": position.id, "reason": reason})
        if tries == 1 or final:
            await self._tell(
                position, f"⚠️ <b>Не удалось выставить {texts.e(position.name)}</b>\n{texts.e(text)}"
            )
        return ListResult(ResaleStatus.FAILED.value, text)

    async def _listed(
        self, position: ResalePosition, gift: ListingSnapshot | None, *, already: bool = False
    ) -> ListResult:
        # what MRKT shows wins over the plan: the price without the fee is what the seller gets
        seller = (gift.price_without_fee_nano if gift else None) or position.list_price_nano
        buyer = (gift.price_nano if gift else None) or (
            buyer_price_for(seller, position.fee_permille) if seller is not None else None
        )
        profit = seller - position.buy_price_nano if seller is not None else None
        await self._update(
            position.id,
            status=ResaleStatus.LISTED.value,
            listed_at=datetime.now(UTC),
            list_price_nano=seller,
            target_price_nano=buyer,
            expected_profit_nano=profit,
            reason=None,
        )
        head = "уже на продаже" if already else "выставлен на продажу"
        lines = [
            f"📤 <b>{texts.e(position.name)}</b> {head}",
            f"Цена на MRKT: {format_ton(buyer)} для покупателей, вам {format_ton(seller)}",
            f"Куплен за {format_ton(position.buy_price_nano)} → профит {format_ton(profit)} после продажи",
        ]
        if gift is not None and position.list_price_nano and seller != position.list_price_nano:
            sent = format_ton(position.list_price_nano)
            lines.append(f"Отправлена цена {sent}, MRKT показывает без комиссии {format_ton(seller)}")
        await self._tell(position, "\n".join(lines))
        return ListResult(
            ResaleStatus.LISTED.value,
            f"Выставлен за {format_ton(seller)}, покупатели видят {format_ton(buyer)}",
        )

    async def relist_due(self) -> int:
        """Retry listings that failed or had to wait (with growing pauses); returns how many were tried."""
        now = datetime.now(UTC)
        async with self.sessionmaker() as session:
            due = await resale_repo.to_list(session, now, MAX_LIST_TRIES)
        tried = 0
        for position in due:
            pause = timedelta(minutes=min(60, 2**position.tries))
            if position.status == ResaleStatus.FAILED.value and now - position.updated_at < pause:
                continue
            fresh = now - position.updated_at < timedelta(minutes=2)
            if position.status == ResaleStatus.BOUGHT.value and fresh:
                continue  # the listing right after the purchase may still be running
            rules = await self.rules(position.user_id)
            if rules is None or not rules.auto_list:
                continue
            await self.list_position(position.id)
            tried += 1
        return tried

    # ================================================================== sales
    async def on_sale(self, gift_id: str, price_nano: int | None, *, is_mine: bool | None) -> int:
        """A sale of a gift the assistant listed: confirmed by MRKT that the gift left the account."""
        if is_mine is True:  # the feed reports the account's own purchase of the gift
            return 0
        async with self.sessionmaker() as session:
            positions = await resale_repo.listed_with_gift(session, gift_id)
        if not positions:
            return 0
        try:
            gift = await self.mrkt.get_gift(gift_id, priority=False)
        except MrktError as exc:
            log.warning("resale sale check failed", extra={"gift_id": gift_id, "error": str(exc)})
            return 0
        if gift is not None and gift.is_mine is not False:
            return 0  # still the account's gift
        sold = 0
        for position in positions:
            seller = position.list_price_nano
            profit = seller - position.buy_price_nano if seller is not None else None
            row = await self._update(
                position.id,
                status=ResaleStatus.SOLD.value,
                sold_at=datetime.now(UTC),
                sold_price_nano=price_nano,
                expected_profit_nano=profit,
            )
            if row is None:
                continue
            sold += 1
            await self._tell(
                position,
                "\n".join(
                    [
                        f"💰 <b>{texts.e(position.name)}</b> продан (MRKT сообщил о продаже)",
                        f"Покупатель заплатил: {format_ton(price_nano)}",
                        f"Вам по цене объявления без комиссии: {format_ton(seller)}",
                        f"Куплен за {format_ton(position.buy_price_nano)} → профит {format_ton(profit)}",
                    ]
                ),
            )
        return sold

    async def _tell(self, position: ResalePosition, text: str) -> None:
        if self.notifier is None:
            return
        await self.notifier.send(position.user_id, text, kind="resale", critical=True)
