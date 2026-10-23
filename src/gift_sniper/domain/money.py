"""TON amounts. MRKT reports prices in nanoTON (1 TON = 10^9 nanoTON); we keep integers end to end."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

NANO_PER_TON = 1_000_000_000
MAX_TON_INPUT = Decimal("10000000")  # sanity bound for user input


class MoneyParseError(ValueError):
    pass


def ton_to_nano(value: str | Decimal | int | float) -> int:
    """Parse a TON amount entered by a user (e.g. "1.5", "2,25") into nanoTON."""
    if isinstance(value, float):
        value = repr(value)
    text = str(value).strip().replace(",", ".").replace(" ", "")
    if text.lower().endswith("ton"):
        text = text[:-3]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyParseError(f"Не удалось распознать сумму: {value!r}") from exc
    if not amount.is_finite():
        raise MoneyParseError("Сумма должна быть числом")
    if amount < 0:
        raise MoneyParseError("Сумма не может быть отрицательной")
    if amount > MAX_TON_INPUT:
        raise MoneyParseError("Слишком большая сумма")
    nano = amount * NANO_PER_TON
    if nano != nano.to_integral_value():
        raise MoneyParseError("Слишком много знаков после запятой (максимум 9)")
    return int(nano)


def nano_to_ton(nano: int) -> Decimal:
    return Decimal(nano) / NANO_PER_TON


def format_ton(nano: int | None, *, none: str = "Нет данных") -> str:
    if nano is None:
        return none
    ton = nano_to_ton(nano)
    text = f"{ton:.9f}".rstrip("0").rstrip(".")
    return f"{text} TON"
