"""Parsing of values typed by users. Every parser raises InputError with a readable message."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from gift_sniper.domain.money import MoneyParseError, ton_to_nano

CLEAR = {"-", "—", "нет", "сброс", "clear", "none"}


class InputError(ValueError):
    pass


def is_clear(text: str) -> bool:
    return text.strip().lower() in CLEAR


def parse_ton(text: str) -> int | None:
    if is_clear(text):
        return None
    try:
        value = ton_to_nano(text)
    except MoneyParseError as exc:
        raise InputError(str(exc)) from exc
    if value == 0:
        raise InputError("Сумма должна быть больше нуля")
    return value


def _split_range(text: str) -> tuple[str, str]:
    cleaned = text.strip().replace("—", "-").replace("–", "-").replace("…", "-").replace("..", "-")
    if cleaned.count("-") != 1:
        raise InputError("Используйте формат «от-до», «-до» или «от-»")
    low, high = cleaned.split("-")
    return low.strip(), high.strip()


def parse_ton_range(text: str) -> tuple[int | None, int | None]:
    if is_clear(text):
        return None, None
    low_text, high_text = _split_range(text)
    low = parse_ton(low_text) if low_text else None
    high = parse_ton(high_text) if high_text else None
    if low is None and high is None:
        raise InputError("Укажите хотя бы одну границу")
    if low is not None and high is not None and low > high:
        raise InputError("Нижняя граница больше верхней")
    return low, high


def parse_int(text: str, *, minimum: int = 0, maximum: int = 1_000_000) -> int | None:
    if is_clear(text):
        return None
    if not re.fullmatch(r"\s*\d+\s*", text):
        raise InputError("Введите целое число")
    value = int(text)
    if value < minimum or value > maximum:
        raise InputError(f"Число должно быть от {minimum} до {maximum}")
    return value


def parse_permille_range(text: str) -> tuple[int | None, int | None]:
    if is_clear(text):
        return None, None
    low_text, high_text = _split_range(text)
    low = parse_int(low_text, maximum=1000) if low_text else None
    high = parse_int(high_text, maximum=1000) if high_text else None
    if low is None and high is None:
        raise InputError("Укажите хотя бы одну границу")
    if low is not None and high is not None and low > high:
        raise InputError("Нижняя граница больше верхней")
    return low, high


def parse_percent(text: str) -> float | None:
    if is_clear(text):
        return None
    try:
        value = Decimal(text.strip().replace(",", ".").rstrip("%"))
    except InvalidOperation as exc:
        raise InputError("Введите число процентов, например 15") from exc
    if not value.is_finite() or value < 0 or value > 100:
        raise InputError("Процент должен быть от 0 до 100")
    return float(value)


def parse_names(text: str) -> list[str]:
    if is_clear(text):
        return []
    parts = re.split(r"[,;\n]+", text)
    names = [" ".join(p.split()) for p in parts if p.strip()]
    if not names:
        raise InputError("Перечислите названия через запятую")
    if any(len(n) > 128 for n in names):
        raise InputError("Слишком длинное название")
    return names


def parse_period(text: str) -> tuple[int | None, int | None]:
    """'3/24' -> at most 3 purchases per 24 hours."""
    if is_clear(text):
        return None, None
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if not match:
        raise InputError("Формат: «количество/часы», например 3/24")
    count, hours = int(match.group(1)), int(match.group(2))
    if count < 1 or hours < 1 or hours > 24 * 365:
        raise InputError("Количество и часы должны быть положительными")
    return count, hours


def parse_name(text: str) -> str:
    name = " ".join(text.split())
    if not name:
        raise InputError("Название не может быть пустым")
    if len(name) > 64:
        raise InputError("Не длиннее 64 символов")
    return name
