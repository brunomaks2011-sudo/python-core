"""The three independent monochrome percentages (ТЗ п. 5).

A. Share of monochrome models   = monochrome models / known models of the gift x 100%  (Gift Wiki)
B. Model drop probability        = only if Gift Wiki publishes it (the documented API does not)
C. Share of monochrome listings  = confirmed monochrome listings / matching listings x 100%  (MRKT)

Rules: missing data is never replaced with zero, UNKNOWN is never counted as monochrome,
probabilities are never multiplied, and A is never presented as the probability of getting a monochrome.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from gift_sniper.domain.enums import MonochromeStatus
from gift_sniper.domain.types import Share

NO_DATA = "Нет данных"


def monochrome_model_share(
    monochrome_models: Iterable[str],
    observed_models: Iterable[str],
    *,
    rarity_by_model: Mapping[str, int | None] | None = None,
) -> Share | None:
    """A. Both arguments are normalized model names of one gift.

    `monochrome_models`: models with at least one Gift Wiki monochrome record.
    `observed_models`: models seen in MRKT listings of the collection.
    The documented Gift Wiki API publishes only monochrome records, not the full model list, so the
    denominator is the union of both sets and the result is flagged "по известным моделям".
    Without observed models the denominator would consist of monochrome models only (a fake 100%),
    so None ("Нет данных") is returned instead.
    """
    mono = {m for m in monochrome_models if m}
    observed = {m for m in observed_models if m}
    if not observed:
        return None
    known = observed | mono
    note = "по известным моделям"
    complete = False
    if rarity_by_model is not None:
        rarities = [rarity_by_model.get(m) for m in known]
        if rarities and all(r is not None for r in rarities):
            coverage = sum(r for r in rarities if r is not None)
            note += f"; сумма редкостей известных моделей по MRKT: {coverage}‰ из 1000‰"
            complete = coverage >= 990  # per-mille values are rounded, a full set sums to ~1000
    return Share(numerator=len(mono), denominator=len(known), note=note, complete=complete)


def monochrome_listing_share(statuses: Iterable[MonochromeStatus | str]) -> Share:
    """C. Every matching listing is in the denominator; only confirmed monochromes in the numerator."""
    total = mono = unknown = 0
    for status in statuses:
        total += 1
        value = MonochromeStatus(status)
        if value is MonochromeStatus.MONOCHROME:
            mono += 1
        elif value is MonochromeStatus.UNKNOWN:
            unknown += 1
    return Share(numerator=mono, denominator=total, unknown=unknown)


def format_percent(value: float | None) -> str:
    if value is None:
        return NO_DATA
    text = f"{value:.2f}".rstrip("0").rstrip(".") if value < 10 else f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text}%"


def format_permille(permille: int | None) -> str:
    """Telegram/MRKT rarity is given in per mille; show it as a percentage."""
    if permille is None:
        return NO_DATA
    return format_percent(permille / 10)


def format_model_share(share: Share | None) -> str:
    if share is None or share.percent is None:
        return NO_DATA
    text = f"{share.numerator} из {share.denominator} моделей — {format_percent(share.percent)}"
    if share.note:
        text += f" ({share.note})"
    return text


def format_listing_share(share: Share | None, *, computed_at: datetime | None = None, scope: str = "") -> str:
    if share is None or share.percent is None:
        return NO_DATA
    text = f"{share.numerator} из {share.denominator} объявлений — {format_percent(share.percent)}"
    extras = []
    if share.unknown:
        extras.append(f"статус неизвестен у {share.unknown}")
    if scope:
        extras.append(scope)
    if computed_at is not None:
        extras.append(f"расчёт {computed_at:%Y-%m-%d %H:%M} UTC")
    if extras:
        text += " (" + "; ".join(extras) + ")"
    return text
