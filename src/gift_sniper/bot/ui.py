"""Shared UI helpers: main menu, safe message editing, small keyboards."""

from __future__ import annotations

import contextlib

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from gift_sniper.bot.callbacks import Menu

MAIN_SECTIONS: list[tuple[str, str]] = [
    ("🎁 Автопокупка подарков", "auto"),
    ("⚫ Автопокупка монохромов", "mono"),
    ("🔎 Поиск по фильтрам", "search"),
    ("🆕 Новые листинги", "new"),
    ("📚 Gift Wiki", "wiki"),
    ("📊 Статистика рынка", "mstats"),
    ("📈 Моя статистика", "ustats"),
    ("⚙️ Настройки фильтров", "filters"),
    ("💰 Бюджет и лимиты", "budget"),
    ("📜 История операций", "history"),
    ("⏸ Управление ботом", "control"),
]


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, section in MAIN_SECTIONS:
        builder.button(text=text, callback_data=Menu(section=section))
    builder.adjust(2, 2, 2, 2, 2, 1)
    return builder.as_markup()


def back_row(section: str = "main", text: str = "« Меню") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=text, callback_data=Menu(section=section).pack())]


def back_kb(section: str = "main", text: str = "« Меню") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_row(section, text)])


async def show(event: CallbackQuery | Message, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    """Edit the callback's message in place (or answer a message) without crashing on 'not modified'."""
    if isinstance(event, CallbackQuery):
        message = event.message
        if isinstance(message, Message):
            try:
                await message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc):
                    await message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        with contextlib.suppress(TelegramBadRequest):
            await event.answer()
        return
    await event.answer(text, reply_markup=kb, disable_web_page_preview=True)


def yes_no(value: bool) -> str:
    return "✅" if value else "❌"
