"""/start, main menu, emergency stop command, cancel."""

from __future__ import annotations

import time
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from gift_sniper.bot.callbacks import Menu
from gift_sniper.bot.ui import main_menu_kb, show
from gift_sniper.config import RunMode
from gift_sniper.services.container import Services
from gift_sniper.webapp.menu import current_url

router = Router(name="common")

RUN_MODE_LABEL = {
    RunMode.NOTIFY_ONLY: "🔔 только уведомления (покупки отключены)",
    RunMode.DRY_RUN: "🧪 тестовый (показывает, что было бы куплено)",
    RunMode.LIVE: "💸 боевой (реальные покупки)",
}


async def header(services: Services) -> str:
    mode = await services.control.run_mode()
    stopped = await services.control.is_stopped()
    age = services.store.snapshot.age_hours()
    monitor = services.monitor
    if monitor is None or not services.settings.mrkt_configured:
        monitor_line = "не подключён (нет MRKT_ACCESS_TOKEN)"
    elif monitor.last_success is None:
        monitor_line = "ожидает первого успешного опроса" + (
            f" — ошибка: {escape(monitor.last_error[:200])}" if monitor.last_error else ""
        )
    else:
        monitor_line = f"последний опрос {time.time() - monitor.last_success:.0f} с назад"
    gw_line = (
        "нет данных"
        if age is None
        else f"обновлено {age:.1f} ч назад, записей: {services.store.snapshot.records_count}"
    )
    if not services.settings.giftwiki_configured:
        gw_line += " (GIFTWIKI_API_KEY не задан)"
    return "\n".join(
        [
            "🎯 <b>Gift Sniper для MRKT</b>",
            f"Режим: {RUN_MODE_LABEL[mode]}",
            f"Аварийная остановка: {'⛔ АКТИВНА' if stopped else 'нет'}",
            f"Мониторинг MRKT: {monitor_line}",
            f"Gift Wiki: {gw_line}",
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, services: Services, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await header(services), reply_markup=await _menu(services))


async def _menu(services: Services) -> InlineKeyboardMarkup:
    return main_menu_kb(await current_url(services.redis, services.settings.redis_prefix))


@router.message(Command("menu"))
async def cmd_menu(message: Message, services: Services, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await header(services), reply_markup=await _menu(services))


@router.message(Command("app"))
async def cmd_app(message: Message, services: Services) -> None:
    url = await current_url(services.redis, services.settings.redis_prefix)
    if not url:
        await message.answer(
            "Мини-приложение ещё не запущено: нет адреса. Проверьте сервис `tunnel` "
            "(docker compose logs tunnel) или задайте WEBAPP_URL."
        )
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть мини-приложение", web_app=WebAppInfo(url=url))]
        ]
    )
    await message.answer("Выберите коллекции, модели и фоны, которые покупать:", reply_markup=kb)


@router.callback_query(Menu.filter(F.section == "main"))
async def cb_main(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    await state.clear()
    await show(callback, await header(services), await _menu(services))


@router.message(Command("stop"))
async def cmd_stop(message: Message, services: Services, is_admin: bool, can_purchase: bool) -> None:
    """Emergency stop of all automatic purchases (admins and users with purchase rights)."""
    if not (is_admin or can_purchase):
        await message.answer("Команда доступна администраторам и пользователям с правом покупок.")
        return
    await services.control.stop_all(
        by_user=message.from_user.id if message.from_user else None, reason="/stop"
    )
    await message.answer("⛔ Все автоматические покупки остановлены. Возобновить: ⏸ Управление ботом.")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ввод отменён.", reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n/start — главное меню\n/app — мини-приложение\n/stop — немедленно остановить все автопокупки\n"
        "/cancel — отменить ввод\n\nВсе действия доступны через кнопки меню."
    )
