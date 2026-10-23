"""Callback data factories (Telegram limits callback data to 64 bytes)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class Menu(CallbackData, prefix="m"):
    section: str


class FilterCb(CallbackData, prefix="f"):
    action: str
    id: int = 0
    field: str = ""


class BudgetCb(CallbackData, prefix="b"):
    action: str
    scope: str = ""
    field: str = ""


class ControlCb(CallbackData, prefix="c"):
    action: str
    value: str = ""


class NotifyCb(CallbackData, prefix="n"):
    action: str
    field: str = ""


class HistoryCb(CallbackData, prefix="h"):
    page: int = 0


class WikiCb(CallbackData, prefix="w"):
    action: str
    page: int = 0
    token: str = ""


class StatsCb(CallbackData, prefix="s"):
    scope: str
    hours: int = 24


class ModeCb(CallbackData, prefix="a"):
    mode: str  # regular | monochrome
    action: str = "view"
