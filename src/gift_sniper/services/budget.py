"""Budget and limit checks (pure). Usage figures are computed in the database by the purchase repository.

Spending counts every attempt that may have spent money: reserved, submitted, unknown and confirmed.
An attempt with an unknown outcome keeps its reservation until it is verified as not executed.
Dry-run attempts are accounted separately, so test mode never consumes the real budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gift_sniper.domain.money import format_ton


@dataclass(frozen=True, slots=True)
class Limits:
    per_purchase: int | None = None
    daily: int | None = None
    total: int | None = None
    period_count: int | None = None
    period_hours: int | None = None
    max_count: int | None = None
    per_operation: int | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    total_spent: int = 0
    daily_spent: int = 0
    total_count: int = 0
    period_count: int = 0


@dataclass(slots=True)
class BudgetCheck:
    ok: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScopeState:
    label: str
    limits: Limits
    usage: Usage


def _check_scope(price: int, scope: ScopeState, reasons: list[str]) -> None:
    lim, use, label = scope.limits, scope.usage, scope.label
    if lim.per_purchase is not None and price > lim.per_purchase:
        reasons.append(
            f"{label}: цена {format_ton(price)} больше лимита на покупку {format_ton(lim.per_purchase)}"
        )
    if lim.per_operation is not None and price > lim.per_operation:
        reasons.append(f"{label}: сумма операции больше {format_ton(lim.per_operation)}")
    if lim.daily is not None and use.daily_spent + price > lim.daily:
        reasons.append(f"{label}: дневной лимит {format_ton(lim.daily)} (уже {format_ton(use.daily_spent)})")
    if lim.total is not None and use.total_spent + price > lim.total:
        reasons.append(f"{label}: общий бюджет {format_ton(lim.total)} (уже {format_ton(use.total_spent)})")
    if lim.max_count is not None and use.total_count >= lim.max_count:
        reasons.append(f"{label}: уже куплено {use.total_count} из {lim.max_count}")
    if lim.period_count is not None and lim.period_hours is not None and use.period_count >= lim.period_count:
        reasons.append(f"{label}: лимит {lim.period_count} покупок за {lim.period_hours} ч")


def check_purchase(
    price: int,
    *,
    user: ScopeState,
    mode: ScopeState | None,
    filter_scope: ScopeState | None,
    require_user_limits: bool,
) -> BudgetCheck:
    reasons: list[str] = []
    if price <= 0:
        reasons.append("некорректная цена")
    if require_user_limits:
        missing = [
            name
            for name, value in (
                ("на одну покупку", user.limits.per_purchase),
                ("на день", user.limits.daily),
                ("общий бюджет", user.limits.total),
            )
            if value is None
        ]
        if missing:
            reasons.append("не заданы лимиты пользователя: " + ", ".join(missing))
    for scope in (user, mode, filter_scope):
        if scope is not None:
            _check_scope(price, scope, reasons)
    return BudgetCheck(ok=not reasons, reasons=reasons)


def remaining(scope: ScopeState) -> int | None:
    """Remaining total budget of a scope, None when no total limit is set."""
    if scope.limits.total is None:
        return None
    return max(0, scope.limits.total - scope.usage.total_spent)
