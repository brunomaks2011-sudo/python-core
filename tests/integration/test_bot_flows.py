"""End-to-end Telegram UI flows: real aiogram dispatcher, handlers, middlewares and database.

Only the network session of the Bot is replaced: outgoing API calls are recorded instead of sent.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy import select

from gift_sniper.bot.callbacks import BudgetCb, ControlCb, FilterCb, Menu, ModeCb, NotifyCb, WikiCb
from gift_sniper.bot.middlewares import AccessMiddleware
from gift_sniper.bot.setup import build_dispatcher
from gift_sniper.bot.ui import MAIN_SECTIONS
from gift_sniper.db.models import Budget, Filter, UserSettings
from gift_sniper.services.container import Services
from gift_sniper.services.giftwiki_sync import GiftWikiSync
from gift_sniper.services.search import SearchService
from gift_sniper.services.stats import StatsService
from tests.factories import TON
from tests.integration.conftest import Env

pytestmark = pytest.mark.db

ADMIN = 1  # make_settings() -> ADMIN_USER_IDS=[1]
STRANGER = 666
_ids = itertools.count(1)


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 - signature defined by aiogram
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, SendMessage | EditMessageText):
            chat_id = getattr(method, "chat_id", None) or ADMIN
            return Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(chat_id), type="private"),
                text=method.text,
            )
        return True

    def texts(self) -> list[str]:
        return [m.text for m in self.calls if isinstance(m, SendMessage | EditMessageText)]

    def last_markup(self) -> Any:
        for m in reversed(self.calls):
            if isinstance(m, SendMessage | EditMessageText):
                return m.reply_markup
        return None

    def alerts(self) -> list[str]:
        return [m.text or "" for m in self.calls if isinstance(m, AnswerCallbackQuery)]


class Harness:
    def __init__(self, dp: Dispatcher, bot: Bot, session: RecordingSession) -> None:
        self.dp, self.bot, self.session = dp, bot, session

    def _user(self, user_id: int) -> User:
        return User(id=user_id, is_bot=False, first_name="Tester", username=f"user{user_id}")

    def _message(self, user_id: int, text: str) -> Message:
        return Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=Chat(id=user_id, type="private"),
            from_user=self._user(user_id),
            text=text,
        )

    async def send(self, text: str, user_id: int = ADMIN) -> str:
        before = len(self.session.calls)
        await self.dp.feed_update(
            self.bot, Update(update_id=next(_ids), message=self._message(user_id, text))
        )
        return "\n".join(t for t in self.session.texts()[self._text_index(before) :])

    async def click(self, data: str | Any, user_id: int = ADMIN) -> str:
        payload = data if isinstance(data, str) else data.pack()
        before = len(self.session.calls)
        callback = CallbackQuery(
            id=str(next(_ids)),
            from_user=self._user(user_id),
            chat_instance="ci",
            data=payload,
            message=Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=user_id, type="private"),
                from_user=self._user(user_id),
                text="old",
            ),
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(_ids), callback_query=callback))
        return "\n".join(t for t in self.session.texts()[self._text_index(before) :])

    def _text_index(self, call_index: int) -> int:
        return sum(1 for m in self.session.calls[:call_index] if isinstance(m, SendMessage | EditMessageText))


@pytest_asyncio.fixture
async def ui(env: Env) -> AsyncIterator[Harness]:
    env.settings.bot_flood_max_events = 1000
    services = Services(
        settings=env.settings,
        sessionmaker=env.sessionmaker,
        redis=env.redis,
        mrkt=env.mrkt,  # type: ignore[arg-type]
        giftwiki=None,  # type: ignore[arg-type]
        control=env.control,
        store=env.store,
        enricher=env.enricher,
        filter_cache=env.filter_cache,
        notifier=env.notifier,
        purchase=env.service,
        search=SearchService(env.mrkt, env.enricher, env.sessionmaker),  # type: ignore[arg-type]
        stats=StatsService(env.sessionmaker, env.store),
        sync=GiftWikiSync(env.settings, None, env.sessionmaker, env.redis, env.store, env.enricher),  # type: ignore[arg-type]
    )
    session = RecordingSession()
    bot = Bot("123456:" + "A" * 35, session=session)
    yield Harness(build_dispatcher(services), bot, session)


async def test_start_shows_main_menu_with_all_sections(ui: Harness) -> None:
    text = await ui.send("/start")
    assert "Gift Sniper" in text and "Режим:" in text
    markup = ui.session.last_markup()
    buttons = [b.text for row in markup.inline_keyboard for b in row]
    assert buttons == [t for t, _ in MAIN_SECTIONS]


async def test_users_are_registered_right_after_boot(env: Env) -> None:
    """time.monotonic() is close to zero shortly after the machine (or Docker's VM) starts."""
    services = SimpleNamespace(settings=env.settings, sessionmaker=env.sessionmaker)
    access = AccessMiddleware(services, clock=lambda: 5.0)  # type: ignore[arg-type]
    event = SimpleNamespace(from_user=User(id=ADMIN, is_bot=False, first_name="Admin"))

    async def handler(event: Any, data: dict[str, Any]) -> str:
        return "handled"

    assert await access(handler, event, {}) == "handled"  # type: ignore[arg-type]
    async with env.sessionmaker() as session:
        assert await session.get(UserSettings, ADMIN) is not None


async def test_access_is_denied_to_unknown_users(ui: Harness) -> None:
    text = await ui.send("/start", user_id=STRANGER)
    assert "Доступ запрещён" in text and str(STRANGER) in text


async def test_every_main_section_renders(ui: Harness) -> None:
    await ui.send("/start")
    for title, section in MAIN_SECTIONS:
        text = await ui.click(Menu(section=section))
        assert text, f"section {title} rendered nothing"
        assert "Traceback" not in text


async def test_create_edit_copy_toggle_and_delete_filter(ui: Harness, env: Env) -> None:
    await ui.send("/start")
    assert "Введите название" in await ui.click(FilterCb(action="new", field="regular"))
    created = await ui.send("Дешёвые Пепе")
    assert "Фильтр создан" in created and "Дешёвые Пепе" in created
    async with env.sessionmaker() as session:
        row = (await session.execute(select(Filter))).scalar_one()
    assert not row.enabled and not row.autobuy

    assert "Диапазон цены" in await ui.click(FilterCb(action="edit", id=row.id, field="price"))
    saved = await ui.send("1.5-10")
    assert "Сохранено" in saved and "1.5 TON" in saved and "10 TON" in saved
    await ui.click(FilterCb(action="edit", id=row.id, field="col"))
    warned = await ui.send("Plush Pepe, Lunar Snake")
    assert "Plush Pepe" in warned
    await ui.click(FilterCb(action="edit", id=row.id, field="tot"))
    assert "Бюджет всего: 50 TON" in await ui.send("50")
    await ui.click(FilterCb(action="edit", id=row.id, field="per"))
    assert "⚠️" in await ui.send("abc")  # invalid input is rejected with an explanation

    await ui.send("/cancel")
    await ui.click(FilterCb(action="toggle", id=row.id))
    await ui.click(FilterCb(action="autobuy", id=row.id))
    await ui.click(FilterCb(action="onlynew", id=row.id))
    async with env.sessionmaker() as session:
        row = await session.get(Filter, row.id)
    assert row is not None and row.enabled and row.autobuy and row.activated_at is not None
    assert row.criteria["min_price_nano"] == int(1.5 * TON) and row.criteria["max_price_nano"] == 10 * TON
    assert row.criteria["collections"] == ["Plush Pepe", "Lunar Snake"]
    assert row.criteria["only_new_listings"] is True
    assert row.limits["total_limit_nano"] == 50 * TON

    assert "Копия создана" in await ui.click(FilterCb(action="copy", id=row.id))
    async with env.sessionmaker() as session:
        rows = (await session.execute(select(Filter).order_by(Filter.id))).scalars().all()
    assert len(rows) == 2 and rows[1].criteria == rows[0].criteria and not rows[1].enabled

    await ui.click(FilterCb(action="delete", id=rows[1].id))
    assert "удалён" in await ui.click(FilterCb(action="delete_ok", id=rows[1].id))
    async with env.sessionmaker() as session:
        assert len((await session.execute(select(Filter))).scalars().all()) == 1


async def test_monochrome_filter_type_toggles(ui: Harness, env: Env) -> None:
    await ui.send("/start")
    await ui.click(FilterCb(action="new", field="monochrome"))
    card = await ui.send("Моно")
    assert "Фильтр монохромов" in card and "MONOCHROME" in card
    async with env.sessionmaker() as session:
        row = (await session.execute(select(Filter))).scalar_one()
    await ui.click(FilterCb(action="mtype", id=row.id, field="combo"))
    async with env.sessionmaker() as session:
        row = await session.get(Filter, row.id)
    assert row is not None and row.criteria["monochrome_types"] == ["high", "medium", "low"]


async def test_mode_toggles_budgets_and_notifications(ui: Harness, env: Env) -> None:
    await ui.send("/start")
    text = await ui.click(ModeCb(mode="monochrome", action="toggle"))
    assert "Автопокупка монохромов" in text and "включён" in text
    async with env.sessionmaker() as session:
        prefs = await session.get(UserSettings, ADMIN)
    assert prefs is not None and prefs.monochrome_autobuy_enabled and not prefs.autobuy_enabled

    await ui.click(BudgetCb(action="edit", scope="user", field="day"))
    assert "Бюджет и лимиты" in await ui.send("25")
    await ui.click(BudgetCb(action="edit", scope="monochrome", field="per"))
    await ui.send("3/24")
    async with env.sessionmaker() as session:
        budgets = {b.scope: b for b in (await session.execute(select(Budget))).scalars()}
    assert budgets["user"].daily_limit_nano == 25 * TON
    assert (budgets["monochrome"].period_max_count, budgets["monochrome"].period_hours) == (3, 24)

    await ui.click(NotifyCb(action="toggle", field="price_drops"))
    await ui.click(NotifyCb(action="edit", field="rate"))
    await ui.send("7")
    async with env.sessionmaker() as session:
        prefs = await session.get(UserSettings, ADMIN)
    assert prefs is not None and prefs.notify["price_drops"] is True and prefs.notify["max_per_minute"] == 7


async def test_emergency_stop_command_and_button(ui: Harness, env: Env) -> None:
    await ui.send("/start")
    assert "остановлены" in await ui.send("/stop")
    assert await env.control.is_stopped()
    text = await ui.click(Menu(section="control"))
    assert "АКТИВНА" in text
    await ui.click(ControlCb(action="resume"))
    assert not await env.control.is_stopped()
    await ui.click(ControlCb(action="stop"))
    assert await env.control.is_stopped()


async def test_stranger_cannot_stop_or_use_buttons(ui: Harness, env: Env) -> None:
    await ui.click(ControlCb(action="stop"), user_id=STRANGER)
    assert not await env.control.is_stopped()
    assert "Доступ запрещён" in ui.session.alerts()


async def test_flood_protection_drops_excess_events(ui: Harness, env: Env) -> None:
    env.settings.bot_flood_max_events = 3
    ui.dp.message.outer_middleware._middlewares[0].max_events = 3  # type: ignore[attr-defined]
    ui.dp.callback_query.outer_middleware._middlewares[0].max_events = 3  # type: ignore[attr-defined]
    for _ in range(3):
        await ui.click(Menu(section="main"))
    await ui.click(Menu(section="main"))
    assert "Слишком часто" in ui.session.alerts()[-1]


async def test_admin_manual_mapping_resolves_ambiguity(ui: Harness, env: Env) -> None:
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")], gift_id="gw-a")
    await env.add_giftwiki("Pepe Plush", [("Onyx", "Black", "high")], gift_id="gw-b")
    from tests.factories import make_listing

    listing = make_listing(collection_name="Pepe Toy", collection_title="Pepe Toy")
    assert env.enricher.classify(listing).status.value == "UNKNOWN"
    reply = await ui.send("/map Pepe Toy = gw-b")
    assert "gw-b" in reply
    assert env.enricher.classify(listing).status.value == "MONOCHROME"
    assert "удалено" in await ui.send("/map Pepe Toy = -")
    assert env.enricher.classify(listing).status.value == "UNKNOWN"


def _callback_buttons(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


async def test_search_details_manual_buy_history_and_stats(ui: Harness, env: Env) -> None:
    from collections import deque

    from gift_sniper.domain.enums import BudgetScope
    from tests.factories import make_listing

    await ui.send("/start")  # registers the admin
    await env.set_mode_budget(
        ADMIN,
        BudgetScope.USER,
        per_purchase_limit_nano=100 * TON,
        daily_limit_nano=100 * TON,
        total_limit_nano=100 * TON,
    )
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    fid = await env.add_filter(ADMIN, name="pepe", criteria={"collections": ["Plush Pepe"]})
    listing = make_listing("g-ui", model_name="Onyx", backdrop_name="Black", price_nano=7 * TON)
    env.mrkt.add(listing)
    env.mrkt.saling_pages = deque([([listing], None)])

    text = await ui.click(FilterCb(action="search", id=fid))
    assert "Поиск: «pepe»" in text and "1 из 1 объявлений — 100%" in text and "7 TON" in text
    details_cb = next(c for c in _callback_buttons(ui.session.last_markup()) if c.startswith("ld:"))

    details = await ui.click(details_cb)
    assert "MONOCHROME" in details and "A. Доля монохромных моделей" in details
    assert "B. Вероятность выпадения модели: Нет данных" in details and "(Gift Wiki)" not in details
    buy_cb = next(c for c in _callback_buttons(ui.session.last_markup()) if c.startswith("mb:"))

    confirm = await ui.click(buy_cb)
    assert "Купить" in confirm and "7 TON" in confirm and "реальная покупка" in confirm
    ok_cb = next(c for c in _callback_buttons(ui.session.last_markup()) if c.startswith("mbok:"))
    await ui.click(ok_cb)
    assert env.mrkt.buy_calls == ["g-ui"]
    assert any("Покупка подтверждена" in t for t in env.sender.texts_for(ADMIN))
    # the confirmation token is single-use
    await ui.click(ok_cb)
    assert env.mrkt.buy_calls == ["g-ui"]

    history = await ui.click(Menu(section="history"))
    assert "Plush Pepe #100" in history and "✅" in history
    mine = await ui.click(Menu(section="ustats"))
    assert "Подтверждённых покупок: 1 на 7 TON" in mine
    market = await ui.click(Menu(section="mstats"))
    assert "Новых листингов: 1" in market and "Период:" in market and "Источник" not in market


async def test_wiki_gift_card(ui: Harness, env: Env) -> None:
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high"), ("Ivory", "White", "low")])
    await ui.send("/start")
    listing_text = await ui.click(WikiCb(action="list", page=0))
    assert "Plush Pepe — записей: 2" in listing_text
    gift_cb = next(c for c in _callback_buttons(ui.session.last_markup()) if c.startswith("w:gift"))
    card = await ui.click(gift_cb)
    assert "Записей по типам: high: 1, low: 1" in card and "Onyx + Black — high" in card
    assert "Доля монохромных моделей: Нет данных" in card  # no MRKT models observed yet
