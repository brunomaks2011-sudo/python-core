"""Budget and limit checks."""

from __future__ import annotations

from gift_sniper.services.budget import Limits, ScopeState, Usage, check_purchase, remaining
from tests.factories import TON

USER_LIMITS = Limits(per_purchase=20 * TON, daily=50 * TON, total=100 * TON)


def state(limits: Limits = USER_LIMITS, **usage: int) -> ScopeState:
    return ScopeState("scope", limits, Usage(**usage))


def test_within_all_limits() -> None:
    assert check_purchase(10 * TON, user=state(), mode=None, filter_scope=None, require_user_limits=True).ok


def test_user_limits_are_mandatory() -> None:
    result = check_purchase(
        1 * TON, user=state(Limits()), mode=None, filter_scope=None, require_user_limits=True
    )
    assert not result.ok
    assert "не заданы лимиты" in result.reasons[0]


def test_per_purchase_daily_total() -> None:
    assert not check_purchase(
        21 * TON, user=state(), mode=None, filter_scope=None, require_user_limits=True
    ).ok
    assert not check_purchase(
        10 * TON,
        user=state(daily_spent=45 * TON, total_spent=45 * TON),
        mode=None,
        filter_scope=None,
        require_user_limits=True,
    ).ok
    assert not check_purchase(
        10 * TON,
        user=state(daily_spent=0, total_spent=95 * TON),
        mode=None,
        filter_scope=None,
        require_user_limits=True,
    ).ok
    # exactly at the limit is allowed
    assert check_purchase(
        10 * TON,
        user=state(daily_spent=40 * TON, total_spent=90 * TON),
        mode=None,
        filter_scope=None,
        require_user_limits=True,
    ).ok


def test_mode_budget_is_independent_but_user_budget_still_applies() -> None:
    mono = ScopeState("mono", Limits(total=30 * TON), Usage(total_spent=25 * TON))
    blocked = check_purchase(10 * TON, user=state(), mode=mono, filter_scope=None, require_user_limits=True)
    assert not blocked.ok
    regular = ScopeState("regular", Limits(total=30 * TON), Usage(total_spent=0))
    # the regular mode has its own budget left, but the overall user budget is exhausted
    user_exhausted = state(total_spent=95 * TON)
    assert not check_purchase(
        10 * TON, user=user_exhausted, mode=regular, filter_scope=None, require_user_limits=True
    ).ok
    assert check_purchase(
        10 * TON, user=state(), mode=regular, filter_scope=None, require_user_limits=True
    ).ok


def test_filter_limits_count_and_period() -> None:
    f = ScopeState(
        "f", Limits(max_count=2, per_purchase=15 * TON, per_operation=12 * TON), Usage(total_count=2)
    )
    result = check_purchase(10 * TON, user=state(), mode=None, filter_scope=f, require_user_limits=True)
    assert not result.ok and "уже куплено 2 из 2" in result.reasons[0]
    per_op = ScopeState("f", Limits(per_operation=5 * TON), Usage())
    assert not check_purchase(
        10 * TON, user=state(), mode=None, filter_scope=per_op, require_user_limits=True
    ).ok
    period = ScopeState("m", Limits(period_count=3, period_hours=24), Usage(period_count=3))
    assert not check_purchase(
        1 * TON, user=state(), mode=period, filter_scope=None, require_user_limits=True
    ).ok


def test_invalid_price() -> None:
    assert not check_purchase(0, user=state(), mode=None, filter_scope=None, require_user_limits=True).ok


def test_remaining() -> None:
    assert remaining(state(total_spent=30 * TON)) == 70 * TON
    assert remaining(state(Limits(), total_spent=5)) is None
    assert remaining(state(total_spent=150 * TON)) == 0
