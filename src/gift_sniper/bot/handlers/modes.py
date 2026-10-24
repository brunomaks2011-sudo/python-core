"""🎁 Regular autobuy and ⚫ monochrome autobuy screens (independent toggles and budgets)."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gift_sniper.bot.callbacks import BudgetCb, ControlCb, FilterCb, Menu, ModeCb
from gift_sniper.bot.handlers.common import RUN_MODE_LABEL
from gift_sniper.bot.ui import show
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import misc
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.enums import FilterKind, PurchaseMode, PurchaseRunMode
from gift_sniper.domain.money import format_ton
from gift_sniper.services.container import Services

router = Router(name="modes")


async def render_mode(callback: CallbackQuery, services: Services, mode: str, *, can_purchase: bool) -> None:
    is_mono = mode == "monochrome"
    kind = FilterKind.MONOCHROME if is_mono else FilterKind.REGULAR
    purchase_mode = PurchaseMode.MONOCHROME if is_mono else PurchaseMode.REGULAR
    user_id = callback.from_user.id
    async with services.sessionmaker() as session:
        prefs = await users_repo.get_settings(session, user_id)
        rows, plans = filters_repo.without_plans(await filters_repo.list_filters(session, user_id, kind))
        live_user, live_mode, _ = await services.purchase.scope_states(
            session, user_id=user_id, prun=PurchaseRunMode.LIVE, mode=purchase_mode, spec=None
        )
    enabled = prefs.monochrome_autobuy_enabled if is_mono else prefs.autobuy_enabled
    run_mode = await services.control.run_mode()
    stopped = await services.control.is_stopped()
    title = "⚫ <b>Автопокупка монохромов</b>" if is_mono else "🎁 <b>Автопокупка подарков</b>"
    lines = [
        title,
        f"Режим: {'✅ включён' if enabled else '⛔ выключен'}",
        f"Работа бота: {RUN_MODE_LABEL[run_mode]}",
    ]
    if stopped:
        lines.append("⛔ Аварийная остановка активна — покупки не выполняются.")
    if prefs.purchases_paused:
        lines.append("⏸ Ваши автопокупки на паузе.")
    if not can_purchase:
        lines.append("ℹ️ У вас нет права покупок: работают только уведомления.")
    assert live_mode is not None
    lim, use = live_mode.limits, live_mode.usage
    lines += [
        "",
        "<b>Бюджет режима</b> (независим от другого режима, общий лимит тоже соблюдается):",
        f"Сегодня: {format_ton(use.daily_spent)} из {format_ton(lim.daily, none='не ограничено')}",
        f"Всего: {format_ton(use.total_spent)} из {format_ton(lim.total, none='не ограничено')}",
        f"Макс. за покупку: {format_ton(lim.per_purchase, none='не ограничено')}",
    ]
    if is_mono:
        if lim.period_count and lim.period_hours:
            lines.append(f"Покупок за {lim.period_hours} ч: {use.period_count} из {lim.period_count}")
        age = services.store.snapshot.age_hours()
        lines += [
            "",
            "Покупаются только листинги со статусом <b>MONOCHROME</b> (подтверждён записью Gift Wiki для пары "
            "модель + фон). Статус UNKNOWN никогда не покупается.",
            f"Данные Gift Wiki: {'нет' if age is None else f'{age:.1f} ч назад'}, "
            f"автопокупка требует данных не старше {services.settings.monochrome_autobuy_max_data_age_hours:.0f} ч.",
        ]
    ulim = live_user.limits
    if None in (ulim.per_purchase, ulim.daily, ulim.total):
        lines.append(
            "\n⚠️ Не заданы общие лимиты (на покупку, на день, всего) — покупки блокируются. "
            "Задайте их в 💰 Бюджет и лимиты."
        )
    lines.append("")
    lines.append("<b>Фильтры режима</b>:" if rows else "Фильтров этого режима пока нет.")
    if plans:
        lines.append(f"📱 Правил мини-приложения: {plans} (настраиваются в мини-приложении, /app)")
    for row in rows:
        lines.append(
            f"{'✅' if row.enabled else '⏸'} {escape(row.name)} — автопокупка {'вкл' if row.autobuy else 'выкл'}"
        )
    b = InlineKeyboardBuilder()
    b.button(
        text="⛔ Выключить режим" if enabled else "✅ Включить режим",
        callback_data=ModeCb(mode=mode, action="toggle"),
    )
    for row in rows:
        b.button(
            text=f"{'✅' if row.enabled else '⏸'} {row.name}",
            callback_data=FilterCb(action="view", id=row.id),
        )
    b.button(text="➕ Новый фильтр", callback_data=FilterCb(action="new", field=kind.value))
    b.button(text="💰 Бюджет режима", callback_data=BudgetCb(action="view", scope=kind.value))
    b.button(text="⛔ Остановить все покупки", callback_data=ControlCb(action="stop"))
    b.button(text="« Меню", callback_data=Menu(section="main"))
    b.adjust(1)
    await show(callback, "\n".join(lines), b.as_markup())


@router.callback_query(Menu.filter(F.section.in_({"auto", "mono"})))
async def cb_mode(
    callback: CallbackQuery, callback_data: Menu, services: Services, can_purchase: bool
) -> None:
    await render_mode(
        callback,
        services,
        "monochrome" if callback_data.section == "mono" else "regular",
        can_purchase=can_purchase,
    )


@router.callback_query(ModeCb.filter(F.action == "toggle"))
async def cb_toggle(
    callback: CallbackQuery, callback_data: ModeCb, services: Services, can_purchase: bool
) -> None:
    is_mono = callback_data.mode == "monochrome"
    async with services.sessionmaker() as session, session.begin():
        prefs = await users_repo.get_settings(session, callback.from_user.id)
        if is_mono:
            prefs.monochrome_autobuy_enabled = not prefs.monochrome_autobuy_enabled
            value = prefs.monochrome_autobuy_enabled
        else:
            prefs.autobuy_enabled = not prefs.autobuy_enabled
            value = prefs.autobuy_enabled
        await misc.audit(
            session, "mode_toggle", user_id=callback.from_user.id, mode=callback_data.mode, enabled=value
        )
    await services.filter_cache.invalidate()
    await render_mode(callback, services, callback_data.mode, can_purchase=can_purchase)


@router.callback_query(ModeCb.filter(F.action == "view"))
async def cb_view(
    callback: CallbackQuery, callback_data: ModeCb, services: Services, can_purchase: bool
) -> None:
    await render_mode(callback, services, callback_data.mode, can_purchase=can_purchase)
