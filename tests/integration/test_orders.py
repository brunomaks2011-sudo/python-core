"""📋 Orders: outbid alerts with a one-tap button, outbidding by 0.01 TON with checks, results MRKT confirms."""

from __future__ import annotations

import pytest

from gift_sniper.config import RunMode
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.types import MrktOrder
from gift_sniper.integrations.mrkt import MrktError
from gift_sniper.services.floors import FloorService
from gift_sniper.services.orders import OrdersService
from tests.factories import TON, make_listing
from tests.integration.conftest import Env

pytestmark = pytest.mark.db

UID = 701
ATTRS = ("Plush Pepe", "Onyx", None, None)


def service(env: Env) -> OrdersService:
    return OrdersService(
        env.settings,
        env.sessionmaker,
        env.redis,
        env.mrkt,
        FloorService(env.mrkt, ttl=0),
        env.control,
        env.notifier,
    )


def order(order_id: str, price: int, *, mine: bool = True, **kw: object) -> MrktOrder:
    values: dict[str, object] = {
        "collection_name": "Plush Pepe",
        "model_name": "Onyx",
        "backdrop_name": None,
        "symbol_name": None,
    }
    values.update(kw)
    return MrktOrder(order_id=order_id, price_nano=price, is_mine=mine, raw={"id": order_id}, **values)  # type: ignore[arg-type]


async def outbid_setup(env: Env, *, per_purchase: int | None = 100 * TON) -> OrdersService:
    await env.add_user(UID, per_purchase=per_purchase)
    env.mrkt.my_orders_list = [order("mine", 10 * TON, min_price_nano=9 * TON, quantity=1)]
    env.mrkt.top_orders[ATTRS] = order("other", 10_500_000_000, mine=False)
    env.mrkt.market = [  # type: ignore[attr-defined]
        make_listing("f1", price_nano=12_300_000_000),
        make_listing("f2", price_nano=11 * TON, model_name="Ivory"),
    ]
    return service(env)


async def test_watch_alerts_once_with_floors_and_a_button(env: Env) -> None:
    orders = await outbid_setup(env)
    assert await orders.watch() == 1
    [text] = env.sender.texts_for(UID)
    assert "Ваш ордер перебили" in text and "Plush Pepe · модель: Onyx" in text
    assert "Ваш ордер: <b>10 TON</b>" in text and "Перебили: <b>10.5 TON</b>" in text
    assert "Флор модели: 12.3 TON — на 1.79 TON выше нового ордера" in text
    assert "Перебить на 0.01 → <b>10.51 TON</b>" in text
    button = env.sender.keyboards[-1].inline_keyboard[0][0]
    assert button.text == "⚡ Перебить → 10.51 TON" and button.callback_data.startswith("ob:")
    payload = await env.notifier.read_token(button.callback_data[3:])
    assert payload == {"order_id": "mine", "price": 10_510_000_000}

    assert await orders.watch() == 0  # the same outbid is not reported twice
    env.mrkt.top_orders[ATTRS] = order("other", 10_700_000_000, mine=False)
    assert await orders.watch() == 1  # outbid again: a new alert


async def test_watch_respects_the_switch_and_rights(env: Env) -> None:
    orders = await outbid_setup(env)
    async with env.sessionmaker() as session, session.begin():
        prefs = await users_repo.get_settings(session, UID)
        prefs.notify = {"orders_outbid": False}
    assert await orders.watch() == 0 and env.sender.messages == []


async def test_outbid_replaces_the_order_and_reports_what_mrkt_shows(env: Env) -> None:
    orders = await outbid_setup(env)
    result = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert result.status == "done" and result.ok and "10 TON → 10.51 TON" in result.text
    kinds = [kind for kind, _ in env.mrkt.order_calls if kind in ("cancel", "create")]
    assert kinds == ["cancel", "create"]  # never two orders that could both buy
    create = next(args for kind, args in env.mrkt.order_calls if kind == "create")
    assert create["price_nano"] == 10_510_000_000 and create["min_price_nano"] == 9 * TON
    assert (create["collection"], create["model"], create["quantity"]) == ("Plush Pepe", "Onyx", 1)
    assert [o.price_nano for o in env.mrkt.my_orders_list] == [10_510_000_000]


async def test_outbid_takes_the_lower_price_when_the_top_fell(env: Env) -> None:
    orders = await outbid_setup(env)
    env.mrkt.top_orders[ATTRS] = order("other2", 10_200_000_000, mine=False)
    result = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert result.status == "done" and result.price_nano == 10_210_000_000


async def test_outbid_checks_before_touching_mrkt(env: Env) -> None:
    orders = await outbid_setup(env)
    env.mrkt.top_orders[ATTRS] = order("other", 10_600_000_000, mine=False)
    moved = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert moved.status == "moved" and moved.price_nano == 10_610_000_000 and "10.6 TON" in moved.text

    env.mrkt.top_orders[ATTRS] = None
    first = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert first.status == "refused" and "уже самый высокий" in first.text

    gone = await orders.outbid(user_id=UID, order_id="nope", price_nano=10_510_000_000)
    assert gone.status == "refused" and "уже нет" in gone.text
    assert not [k for k, _ in env.mrkt.order_calls if k in ("cancel", "create")]


async def test_outbid_limits_rights_and_modes(env: Env) -> None:
    orders = await outbid_setup(env, per_purchase=10 * TON)
    over = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert over.status == "refused" and "выше лимита на одну покупку 10 TON" in over.text
    stranger = await orders.outbid(user_id=999, order_id="mine", price_nano=10_510_000_000)
    assert stranger.status == "refused" and "Нет прав" in stranger.text

    await env.add_user(UID, per_purchase=None)
    no_limit = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert no_limit.status == "refused" and "Задайте лимит" in no_limit.text

    await env.add_user(UID)
    await env.control.set_run_mode(RunMode.DRY_RUN, by_user=None)
    dry = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert dry.status == "dry_run" and dry.ok and "Тестовый режим" in dry.text
    await env.control.set_run_mode(RunMode.NOTIFY_ONLY, by_user=None)
    off = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert off.status == "refused" and "только уведомлений" in off.text
    await env.control.set_run_mode(RunMode.LIVE, by_user=None)
    await env.control.stop_all(by_user=None)
    stopped = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert stopped.status == "refused" and "Аварийная остановка" in stopped.text
    assert not [k for k, _ in env.mrkt.order_calls if k in ("cancel", "create")]


async def test_outbid_failures_are_reported_as_they_are(env: Env) -> None:
    orders = await outbid_setup(env)
    env.mrkt.cancel_error = MrktError("HTTP 400")
    kept = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert kept.status == "refused" and "ничего не изменено" in kept.text
    assert [o.order_id for o in env.mrkt.my_orders_list] == ["mine"]

    env.mrkt.cancel_error = None
    env.mrkt.create_error = MrktError("HTTP 400")
    lost = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert lost.status == "lost" and "Сейчас ордера нет" in lost.text and not lost.ok


async def test_outbid_not_shown_by_mrkt_is_not_called_done(env: Env) -> None:
    orders = await outbid_setup(env)
    env.mrkt.hide_created = True
    result = await orders.outbid(user_id=UID, order_id="mine", price_nano=10_510_000_000)
    assert result.status == "unconfirmed" and "пока нет" in result.text and not result.ok


async def test_market_orders_mark_the_accounts_own(env: Env) -> None:
    orders = await outbid_setup(env)
    env.mrkt.market_orders = [order("other", 10_500_000_000, mine=False), env.mrkt.my_orders_list[0]]
    rows, floors = await orders.market("Plush Pepe", model="Onyx")
    assert [(r["id"], r["mine"]) for r in rows] == [("other", False), ("mine", True)]
    assert [(f.label, f.price_nano) for f in floors] == [("модели", 12_300_000_000)]
    views = await orders.mine()
    assert views[0].outbid and [f.label for f in views[0].floors] == ["модели"]
