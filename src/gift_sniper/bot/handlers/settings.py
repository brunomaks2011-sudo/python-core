"""💰 budgets and limits, 🔔 notification settings, ⏸ bot control (emergency stop, pause, run mode)."""

from __future__ import annotations

import time
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gift_sniper.bot.callbacks import BudgetCb, ControlCb, Menu, NotifyCb
from gift_sniper.bot.handlers.common import RUN_MODE_LABEL
from gift_sniper.bot.parsing import (
    InputError,
    parse_int,
    parse_names,
    parse_percent,
    parse_period,
    parse_ton,
    parse_ton_range,
)
from gift_sniper.bot.states import Input
from gift_sniper.bot.ui import show
from gift_sniper.config import RunMode
from gift_sniper.db.repo import misc
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import BudgetScope, PurchaseMode, PurchaseRunMode
from gift_sniper.domain.money import format_ton
from gift_sniper.services.container import Services
from gift_sniper.services.percentages import format_percent
from gift_sniper.services.user_prefs import NotificationSettings

router = Router(name="settings")

SCOPE_LABEL = {
    BudgetScope.USER: "Общие лимиты (все режимы)",
    BudgetScope.REGULAR: "Режим «Автопокупка подарков»",
    BudgetScope.MONOCHROME: "Режим «Автопокупка монохромов»",
}
SCOPE_SHORT = {BudgetScope.USER: "общий", BudgetScope.REGULAR: "подарки", BudgetScope.MONOCHROME: "монохромы"}
BUDGET_FIELDS = {
    "pp": ("per_purchase_limit_nano", "Лимит на одну покупку, TON"),
    "day": ("daily_limit_nano", "Лимит на день, TON"),
    "tot": ("total_limit_nano", "Общий бюджет, TON"),
    "per": ("period", "Максимум покупок за период («количество/часы»)"),
}


# ================================================================== budgets
async def render_budget(
    callback: CallbackQuery | Message, services: Services, user_id: int, focus: str = ""
) -> None:
    lines = [
        "💰 <b>Бюджет и лимиты</b>",
        "Расходы считаются по подтверждённым покупкам и операциям с неизвестным "
        "результатом (до проверки). Тестовый режим учитывается отдельно и реальный бюджет не тратит.",
        "",
    ]
    async with services.sessionmaker() as session:
        budgets = await users_repo.get_budgets(session, user_id)
        user_state, regular_state, _ = await services.purchase.scope_states(
            session, user_id=user_id, prun=PurchaseRunMode.LIVE, mode=PurchaseMode.REGULAR, spec=None
        )
        _, mono_state, _ = await services.purchase.scope_states(
            session, user_id=user_id, prun=PurchaseRunMode.LIVE, mode=PurchaseMode.MONOCHROME, spec=None
        )
    states = {
        BudgetScope.USER: user_state,
        BudgetScope.REGULAR: regular_state,
        BudgetScope.MONOCHROME: mono_state,
    }
    b = InlineKeyboardBuilder()
    for scope in BudgetScope:
        state = states[scope]
        assert state is not None
        lim, use = state.limits, state.usage
        budget = budgets.get(scope)
        lines += [
            f"<b>{SCOPE_LABEL[scope]}</b>"
            + (" ⚠️ обязательно для покупок" if scope is BudgetScope.USER else ""),
            f"• На покупку: {format_ton(lim.per_purchase, none='не задан')}",
            f"• На день: {format_ton(lim.daily, none='не задан')} (потрачено сегодня {format_ton(use.daily_spent)})",
            f"• Всего: {format_ton(lim.total, none='не задан')} (потрачено {format_ton(use.total_spent)})",
        ]
        if budget is not None and budget.period_max_count and budget.period_hours:
            lines.append(
                f"• Не больше {budget.period_max_count} покупок за {budget.period_hours} ч "
                f"(сейчас {use.period_count})"
            )
        lines.append("")
        if focus and focus != scope.value:
            continue
        for key, (_attr, label) in BUDGET_FIELDS.items():
            if key == "per" and scope is BudgetScope.USER:
                continue
            short = label.split(",")[0].split("(")[0].strip()
            b.button(
                text=f"✏️ {short} · {SCOPE_SHORT[scope]}",
                callback_data=BudgetCb(action="edit", scope=scope.value, field=key),
            )
    b.button(text="« Меню", callback_data=Menu(section="main"))
    b.adjust(2)
    await show(callback, "\n".join(lines), b.as_markup())


@router.callback_query(Menu.filter(F.section == "budget"))
async def cb_budget(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    await state.clear()
    await render_budget(callback, services, callback.from_user.id)


@router.callback_query(BudgetCb.filter(F.action == "view"))
async def cb_budget_scope(callback: CallbackQuery, callback_data: BudgetCb, services: Services) -> None:
    await render_budget(callback, services, callback.from_user.id, focus=callback_data.scope)


@router.callback_query(BudgetCb.filter(F.action == "edit"))
async def cb_budget_edit(callback: CallbackQuery, callback_data: BudgetCb, state: FSMContext) -> None:
    if callback_data.field not in BUDGET_FIELDS:
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    await state.set_state(Input.budget_field)
    await state.update_data(scope=callback_data.scope, field=callback_data.field)
    _attr, label = BUDGET_FIELDS[callback_data.field]
    hint = "например 3/24" if callback_data.field == "per" else "например 25 или 2.5"
    await show(
        callback,
        f"✏️ {SCOPE_LABEL[BudgetScope(callback_data.scope)]}\n{label}: введите значение ({hint}). "
        "«-» — снять ограничение.\n/cancel — отмена.",
    )


@router.message(Input.budget_field)
async def msg_budget(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    scope = BudgetScope(str(data.get("scope")))
    field = str(data.get("field"))
    attr, label = BUDGET_FIELDS[field]
    try:
        value = parse_period(message.text or "") if field == "per" else parse_ton(message.text or "")
    except InputError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    user_id = message.from_user.id  # type: ignore[union-attr]
    async with services.sessionmaker() as session, session.begin():
        budget = await users_repo.get_or_create_budget(session, user_id, scope)
        if field == "per":
            assert isinstance(value, tuple)
            budget.period_max_count, budget.period_hours = value
        else:
            setattr(budget, attr, value)
        await misc.audit(
            session, "budget_changed", user_id=user_id, scope=scope.value, field=label, value=str(value)
        )
    await state.clear()
    await render_budget(message, services, user_id)


# ================================================================== notifications
NOTIFY_TOGGLES = {
    "all_listings": "Обо всех новых листингах",
    "matching_only": "О подходящих под фильтры",
    "monochrome": "Отдельно о монохромах",
    "price_drops": "О снижении цены",
    "purchases": "Об успешных покупках",
    "errors": "Об ошибках покупок",
    "no_repeats": "Без повторных сообщений",
}
NOTIFY_INPUTS = {
    "price": "Ценовой диапазон, TON («1-10», «-10», «2-», «-» — любой)",
    "collections": "Коллекции через запятую («-» — все)",
    "share": "Мин. доля монохромных моделей, % («-» — без порога)",
    "rate": "Макс. уведомлений в минуту (1–60)",
    "drop": "Мин. снижение цены для уведомления, %",
}


async def _prefs(services: Services, user_id: int) -> NotificationSettings:
    async with services.sessionmaker() as session:
        row = await users_repo.get_settings(session, user_id)
    return NotificationSettings.model_validate(row.notify or {})


async def render_notify(event: CallbackQuery | Message, services: Services, user_id: int) -> None:
    prefs = await _prefs(services, user_id)
    lines = ["🔔 <b>Настройки уведомлений</b>"]
    b = InlineKeyboardBuilder()
    for key, label in NOTIFY_TOGGLES.items():
        value = getattr(prefs, key)
        lines.append(f"{'✅' if value else '❌'} {label}")
        b.button(
            text=f"{'✅' if value else '❌'} {label}", callback_data=NotifyCb(action="toggle", field=key)
        )
    lines += [
        "",
        f"Цены: {format_ton(prefs.min_price_nano, none='—')} … {format_ton(prefs.max_price_nano, none='—')}",
        f"Коллекции: {escape(', '.join(prefs.collections)) if prefs.collections else 'все'}",
        f"Порог доли монохромных моделей: {format_percent(prefs.min_monochrome_share_percent)}",
        f"Частота: не больше {prefs.max_per_minute} в минуту (покупки и ошибки — всегда)",
        f"Снижение цены: от {format_percent(prefs.price_drop_min_percent)}",
        "",
        "Диапазон цен, коллекции и порог доли действуют на «все листинги» и «монохромы».",
    ]
    for key, label in NOTIFY_INPUTS.items():
        b.button(
            text=f"✏️ {label.split(',')[0].split('(')[0].strip()}",
            callback_data=NotifyCb(action="edit", field=key),
        )
    b.button(text="« Фильтры", callback_data=Menu(section="filters"))
    b.adjust(1)
    await show(event, "\n".join(lines), b.as_markup())


async def _save_prefs(services: Services, user_id: int, prefs: NotificationSettings) -> None:
    async with services.sessionmaker() as session, session.begin():
        row = await users_repo.get_settings(session, user_id)
        row.notify = prefs.model_dump()
    await services.filter_cache.invalidate()


@router.callback_query(NotifyCb.filter(F.action == "view"))
async def cb_notify(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    await state.clear()
    await render_notify(callback, services, callback.from_user.id)


@router.callback_query(NotifyCb.filter(F.action == "toggle"))
async def cb_notify_toggle(callback: CallbackQuery, callback_data: NotifyCb, services: Services) -> None:
    if callback_data.field not in NOTIFY_TOGGLES:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return
    prefs = await _prefs(services, callback.from_user.id)
    setattr(prefs, callback_data.field, not getattr(prefs, callback_data.field))
    await _save_prefs(services, callback.from_user.id, prefs)
    await render_notify(callback, services, callback.from_user.id)


@router.callback_query(NotifyCb.filter(F.action == "edit"))
async def cb_notify_edit(callback: CallbackQuery, callback_data: NotifyCb, state: FSMContext) -> None:
    if callback_data.field not in NOTIFY_INPUTS:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return
    await state.set_state(Input.notify_field)
    await state.update_data(field=callback_data.field)
    await show(callback, f"✏️ {NOTIFY_INPUTS[callback_data.field]}\n/cancel — отмена.")


@router.message(Input.notify_field)
async def msg_notify(message: Message, services: Services, state: FSMContext) -> None:
    field = str((await state.get_data()).get("field"))
    user_id = message.from_user.id  # type: ignore[union-attr]
    prefs = await _prefs(services, user_id)
    text = message.text or ""
    try:
        if field == "price":
            prefs.min_price_nano, prefs.max_price_nano = parse_ton_range(text)
        elif field == "collections":
            prefs.collections = parse_names(text)
        elif field == "share":
            prefs.min_monochrome_share_percent = parse_percent(text)
        elif field == "rate":
            value = parse_int(text, minimum=1, maximum=60)
            prefs.max_per_minute = value if value is not None else 20
        elif field == "drop":
            value_pct = parse_percent(text)
            prefs.price_drop_min_percent = value_pct if value_pct is not None else 5.0
    except InputError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    await _save_prefs(services, user_id, prefs)
    await state.clear()
    await render_notify(message, services, user_id)


# ================================================================== control
async def render_control(
    event: CallbackQuery | Message, services: Services, user_id: int, *, is_admin: bool, can_purchase: bool
) -> None:
    run_mode = await services.control.run_mode()
    stopped = await services.control.is_stopped()
    async with services.sessionmaker() as session:
        prefs = await users_repo.get_settings(session, user_id)
    monitor = services.monitor
    if monitor is None:
        monitor_line = "не запущен"
    elif monitor.last_success:
        monitor_line = f"работает, последний опрос {time.time() - monitor.last_success:.0f} с назад"
    else:
        monitor_line = "нет успешных опросов" + (
            f": {escape(monitor.last_error[:200])}" if monitor.last_error else ""
        )
    lines = [
        "⏸ <b>Управление ботом</b>",
        f"Режим: {RUN_MODE_LABEL[run_mode]} (максимум по настройке RUN_MODE: {services.settings.run_mode.value})",
        f"Аварийная остановка всех покупок: {'⛔ АКТИВНА' if stopped else 'не активна'}",
        f"Мои автопокупки: {'⏸ на паузе' if prefs.purchases_paused else '▶️ активны'}",
        f"Мониторинг MRKT: {monitor_line}",
    ]
    b = InlineKeyboardBuilder()
    if is_admin or can_purchase:
        if stopped:
            if is_admin:
                b.button(text="▶️ Снять аварийную остановку", callback_data=ControlCb(action="resume"))
        else:
            b.button(text="⛔ ОСТАНОВИТЬ ВСЕ ПОКУПКИ", callback_data=ControlCb(action="stop"))
    b.button(
        text="▶️ Возобновить мои автопокупки" if prefs.purchases_paused else "⏸ Пауза моих автопокупок",
        callback_data=ControlCb(action="pause"),
    )
    if is_admin:
        for mode in RunMode:
            if mode.rank <= services.settings.run_mode.rank and mode is not run_mode:
                b.button(
                    text=f"Режим: {mode.value}", callback_data=ControlCb(action="mode", value=mode.value)
                )
    b.button(text="« Меню", callback_data=Menu(section="main"))
    b.adjust(1)
    await show(event, "\n".join(lines), b.as_markup())


@router.callback_query(Menu.filter(F.section == "control"))
async def cb_control(callback: CallbackQuery, services: Services, is_admin: bool, can_purchase: bool) -> None:
    await render_control(
        callback, services, callback.from_user.id, is_admin=is_admin, can_purchase=can_purchase
    )


@router.callback_query(ControlCb.filter())
async def cb_control_action(
    callback: CallbackQuery, callback_data: ControlCb, services: Services, is_admin: bool, can_purchase: bool
) -> None:
    user_id = callback.from_user.id
    action = callback_data.action
    if action == "stop":
        if not (is_admin or can_purchase):
            await callback.answer("Нет прав", show_alert=True)
            return
        await services.control.stop_all(by_user=user_id, reason="кнопка в боте")
        await services.notifier.admins(
            f"⛔ Аварийная остановка всех покупок включена пользователем {user_id}."
        )
    elif action == "resume":
        if not is_admin:
            await callback.answer("Только администратор может снять остановку", show_alert=True)
            return
        await services.control.resume(by_user=user_id)
    elif action == "pause":
        async with services.sessionmaker() as session, session.begin():
            prefs = await users_repo.get_settings(session, user_id)
            prefs.purchases_paused = not prefs.purchases_paused
            await misc.audit(session, "user_pause", user_id=user_id, paused=prefs.purchases_paused)
        await services.filter_cache.invalidate()
    elif action == "mode":
        if not is_admin:
            await callback.answer("Только для администраторов", show_alert=True)
            return
        try:
            await services.control.set_run_mode(RunMode(callback_data.value), by_user=user_id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
    await render_control(callback, services, user_id, is_admin=is_admin, can_purchase=can_purchase)
