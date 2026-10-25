"""Purchase flow: double-purchase protection, uncertain outcomes, budgets, modes, emergency stop."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from gift_sniper.config import RunMode
from gift_sniper.db.models import PurchaseAttempt
from gift_sniper.db.repo import purchases as purchases_repo
from gift_sniper.domain.enums import BudgetScope, FilterKind, PurchaseMode, PurchaseRunMode, PurchaseStatus
from gift_sniper.integrations.mrkt import BuyOutcome, BuyOutcomeKind, MrktError
from gift_sniper.services.floors import FloorService
from tests.factories import TON, make_listing
from tests.integration.conftest import Env

pytestmark = pytest.mark.db

UID = 1001


async def setup_regular(env: Env, *, price: int = 10 * TON, gift_id: str = "g1", **user_kw: object) -> int:
    await env.add_user(UID, **user_kw)  # type: ignore[arg-type]
    env.mrkt.add(make_listing(gift_id, price_nano=price))
    return await env.add_filter(UID, criteria={"max_price_nano": 50 * TON})


async def statuses(env: Env) -> list[str]:
    return [a.status for a in await env.attempts()]


async def test_floor_priced_monochrome_is_rechecked_against_the_floor(env: Env) -> None:
    await env.add_user(UID)
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    plan = await env.add_filter(
        UID,
        FilterKind.MONOCHROME,
        criteria={"collections": ["Plush Pepe"], "picks": [{"model": "Onyx", "price_rule": "model_floor"}]},
    )
    mono = make_listing("m1", price_nano=8 * TON)  # Onyx on Black: a confirmed monochrome
    env.mrkt.add(mono)
    env.mrkt.market = [mono, make_listing("other", backdrop_name="White", price_nano=9 * TON)]
    request = env.request(UID, "m1", 8 * TON, filter_id=plan, mode=PurchaseMode.MONOCHROME)
    assert (await env.service.execute(request)).status is PurchaseStatus.CONFIRMED

    cheaper = make_listing("m2", number=101, price_nano=8 * TON)
    env.mrkt.add(cheaper)
    env.mrkt.market = [cheaper, make_listing("undercut", backdrop_name="White", price_nano=7 * TON)]
    env.service.floors = FloorService(env.mrkt)  # a fresh look at the market
    request = env.request(UID, "m2", 8 * TON, filter_id=plan, mode=PurchaseMode.MONOCHROME)
    result = await env.service.execute(request)
    assert result.status is PurchaseStatus.CANCELLED and "флор модели" in result.reason
    assert env.mrkt.buy_calls == ["m1"]


async def test_confirmed_purchase_is_recorded_and_notified(env: Env) -> None:
    fid = await setup_regular(env)
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CONFIRMED
    assert env.mrkt.buy_calls == ["g1"]
    attempts = await env.attempts()
    assert [a.status for a in attempts] == ["confirmed"]
    assert attempts[0].final_price_nano == 10 * TON and attempts[0].filter_name == "f"
    assert await env.purchases_count() == 1
    text = env.sender.texts_for(UID)[-1]
    assert "Покупка подтверждена" in text and "Остаток бюджета" in text and "10 TON" in text


async def test_concurrent_requests_for_same_gift_buy_exactly_once(env: Env) -> None:
    fid = await setup_regular(env)
    fid2 = await env.add_filter(UID, name="second", criteria={"collections": ["Plush Pepe"]})
    await env.add_user(2002)
    fid3 = await env.add_filter(2002, name="other user")
    env.mrkt.buy_delay = 0.2  # keep the first purchase in flight while the others arrive
    requests = [
        env.request(UID, "g1", 10 * TON, filter_id=fid),
        env.request(UID, "g1", 10 * TON, filter_id=fid2),
        env.request(UID, "g1", 10 * TON, filter_id=fid),
        env.request(2002, "g1", 10 * TON, filter_id=fid3),
        env.request(2002, "g1", 10 * TON, filter_id=fid3),
    ]
    results = await asyncio.gather(*(env.service.execute(r) for r in requests))
    assert env.mrkt.buy_calls == ["g1"]
    assert sum(1 for r in results if r.status is PurchaseStatus.CONFIRMED) == 1
    assert await env.purchases_count() == 1
    assert (await statuses(env)).count("confirmed") == 1


async def test_sequential_duplicate_after_confirmation_is_skipped(env: Env) -> None:
    fid = await setup_regular(env)
    await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    env.mrkt.add(make_listing("g1", price_nano=10 * TON))  # even if the listing looked available again
    second = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert second.status is None and "уже куплен" in second.reason
    assert env.mrkt.buy_calls == ["g1"]


async def test_database_unique_index_blocks_double_purchase_without_lock(env: Env) -> None:
    await setup_regular(env)

    def attempt(status: str) -> PurchaseAttempt:
        return PurchaseAttempt(
            user_id=UID, mode="regular", run_mode="live", gift_id="g1", expected_price_nano=TON, status=status
        )

    async with env.sessionmaker() as session, session.begin():
        session.add(attempt("confirmed"))
    with pytest.raises(IntegrityError):
        async with env.sessionmaker() as session, session.begin():
            session.add(attempt("reserved"))
    # failed attempts do not block a new one
    async with env.sessionmaker() as session, session.begin():
        session.add(attempt("failed"))


async def test_reserve_reports_duplicate_when_lock_is_bypassed(env: Env) -> None:
    fid = await setup_regular(env)
    listing = make_listing("g1")
    enrichment = await env.enricher.enrich(listing)
    from gift_sniper.db.repo import filters as filters_repo

    async with env.sessionmaker() as session:
        spec = filters_repo.to_spec(await filters_repo.get_filter(session, UID, fid))  # type: ignore[arg-type]
    req = env.request(UID, "g1", 10 * TON, filter_id=fid)
    first, _ = await env.service._reserve(req, PurchaseRunMode.LIVE, spec, listing, enrichment, 10 * TON, 1)
    second, reasons = await env.service._reserve(
        req, PurchaseRunMode.LIVE, spec, listing, enrichment, 10 * TON, 1
    )
    assert first is not None and second is None and reasons == ["duplicate"]


async def test_uncertain_outcome_verified_as_confirmed_is_not_retried(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.buy_outcomes = deque([BuyOutcome(BuyOutcomeKind.UNCERTAIN, "timeout")])
    on_sale = make_listing("g1", price_nano=10 * TON)
    mine = replace(on_sale, is_on_sale=False, is_mine=True)
    env.mrkt.get_scripts["g1"] = deque([on_sale, mine])
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CONFIRMED
    assert env.mrkt.buy_calls == ["g1"]
    attempt = (await env.attempts())[0]
    assert attempt.verification is not None and attempt.verification["outcome"] == "confirmed"


async def test_uncertain_then_verified_not_executed_allows_one_retry(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.buy_outcomes = deque(
        [
            BuyOutcome(BuyOutcomeKind.UNCERTAIN, "502"),
            BuyOutcome(BuyOutcomeKind.CONFIRMED, "ok", price_nano=10 * TON),
        ]
    )
    on_sale = make_listing("g1", price_nano=10 * TON)
    # recheck, verification x2 (still on sale), recheck before the retry
    env.mrkt.get_scripts["g1"] = deque([on_sale, on_sale, on_sale, on_sale])
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CONFIRMED
    assert env.mrkt.buy_calls == ["g1", "g1"]
    attempts = await env.attempts()
    assert [(a.status, a.attempt_no) for a in attempts] == [("failed", 1), ("confirmed", 2)]
    assert await env.purchases_count() == 1


async def test_retry_budget_is_limited(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.buy_outcomes = deque([BuyOutcome(BuyOutcomeKind.UNCERTAIN, "502")] * 5)
    on_sale = make_listing("g1", price_nano=10 * TON)
    env.mrkt.get_scripts["g1"] = deque([on_sale] * 20)
    await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    # PURCHASE_RETRIES_AFTER_VERIFIED_FAILURE=1 -> at most two buy requests in total
    assert env.mrkt.buy_calls == ["g1", "g1"]


async def test_inconclusive_verification_keeps_reservation_and_blocks_retry(env: Env) -> None:
    fid = await setup_regular(env, daily=15 * TON)
    env.mrkt.buy_outcomes = deque([BuyOutcome(BuyOutcomeKind.UNCERTAIN, "disconnect")])
    on_sale = make_listing("g1", price_nano=10 * TON)
    env.mrkt.get_scripts["g1"] = deque([on_sale] + [MrktError("down")] * 10)
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.UNKNOWN
    assert env.mrkt.buy_calls == ["g1"]
    texts = env.sender.texts_for(UID)
    assert any("Покупка не подтверждена" in t and "неизвестен" in t for t in texts)
    assert not any("Покупка подтверждена" in t for t in texts)
    # the money may be spent: it stays reserved in the budget
    async with env.sessionmaker() as session:
        usage = await purchases_repo.usage(
            session, user_id=UID, run_mode=PurchaseRunMode.LIVE, day_start=datetime(2000, 1, 1, tzinfo=UTC)
        )
    assert usage.total_spent == 10 * TON
    # no second buy of the same gift while the outcome is unknown
    env.mrkt.get_scripts.clear()
    again = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert again.status is None and env.mrkt.buy_calls == ["g1"]
    # and the reservation blocks a second gift above the daily limit
    env.mrkt.add(make_listing("g2", price_nano=10 * TON))
    other = await env.service.execute(env.request(UID, "g2", 10 * TON, filter_id=fid))
    assert other.status is PurchaseStatus.CANCELLED and "дневной лимит" in other.reason


async def test_uncertain_then_sold_to_other_is_failed_without_retry(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.buy_outcomes = deque([BuyOutcome(BuyOutcomeKind.UNCERTAIN, "timeout")])
    on_sale = make_listing("g1", price_nano=10 * TON)
    sold = replace(on_sale, is_on_sale=False, is_mine=False)
    env.mrkt.get_scripts["g1"] = deque([on_sale, sold])
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.FAILED and "другой покупатель" in result.reason
    assert env.mrkt.buy_calls == ["g1"]


async def test_rejected_purchase_is_final_and_releases_budget(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.buy_outcomes = deque([BuyOutcome(BuyOutcomeKind.REJECTED, "MRKT отказал (HTTP 400)")])
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.FAILED
    assert env.mrkt.buy_calls == ["g1"]
    async with env.sessionmaker() as session:
        usage = await purchases_repo.usage(
            session, user_id=UID, run_mode=PurchaseRunMode.LIVE, day_start=datetime(2000, 1, 1, tzinfo=UTC)
        )
    assert usage.total_spent == 0
    assert any("не выполнена" in t for t in env.sender.texts_for(UID))


async def test_daily_limit_is_enforced(env: Env) -> None:
    fid = await setup_regular(env, daily=15 * TON)
    env.mrkt.add(make_listing("g2", price_nano=10 * TON))
    assert (await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))).status is (
        PurchaseStatus.CONFIRMED
    )
    second = await env.service.execute(env.request(UID, "g2", 10 * TON, filter_id=fid))
    assert second.status is PurchaseStatus.CANCELLED and "дневной лимит" in second.reason
    assert env.mrkt.buy_calls == ["g1"]


async def test_concurrent_purchases_of_different_gifts_respect_budget(env: Env) -> None:
    fid = await setup_regular(env, total=15 * TON)
    env.mrkt.add(make_listing("g2", price_nano=10 * TON))
    env.mrkt.buy_delay = 0.1
    results = await asyncio.gather(
        env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid)),
        env.service.execute(env.request(UID, "g2", 10 * TON, filter_id=fid)),
    )
    assert sorted(r.status.value for r in results if r.status) == ["cancelled", "confirmed"]
    assert len(env.mrkt.buy_calls) == 1


async def test_user_limits_are_required_for_purchases(env: Env) -> None:
    fid = await setup_regular(env, per_purchase=None, daily=None, total=None)
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CANCELLED and "не заданы лимиты" in result.reason
    assert env.mrkt.buy_calls == []


async def test_filter_quantity_and_per_gift_limits(env: Env) -> None:
    await env.add_user(UID)
    env.mrkt.add(make_listing("g1", price_nano=10 * TON))
    env.mrkt.add(make_listing("g2", price_nano=10 * TON))
    env.mrkt.add(make_listing("g3", price_nano=30 * TON))
    fid = await env.add_filter(UID, limits={"max_count": 1, "max_price_per_gift_nano": 20 * TON})
    assert (await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))).status is (
        PurchaseStatus.CONFIRMED
    )
    assert (await env.service.execute(env.request(UID, "g2", 10 * TON, filter_id=fid))).status is (
        PurchaseStatus.CANCELLED
    )
    fid2 = await env.add_filter(UID, name="g", limits={"max_price_per_gift_nano": 20 * TON})
    assert (await env.service.execute(env.request(UID, "g3", 30 * TON, filter_id=fid2))).status is (
        PurchaseStatus.CANCELLED
    )
    assert env.mrkt.buy_calls == ["g1"]


async def test_monochrome_mode_buys_only_confirmed_monochromes(env: Env) -> None:
    await env.add_user(UID)
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    env.mrkt.add(make_listing("mono", model_name="Onyx", backdrop_name="Black"))
    env.mrkt.add(make_listing("other-backdrop", model_name="Onyx", backdrop_name="Ivory"))
    env.mrkt.add(make_listing("unknown", collection_name="Lunar Snake", collection_title="Lunar Snake"))
    fid = await env.add_filter(UID, FilterKind.MONOCHROME, name="mono")
    req = lambda g: env.request(UID, g, 10 * TON, filter_id=fid, mode=PurchaseMode.MONOCHROME)  # noqa: E731
    assert (await env.service.execute(req("mono"))).status is PurchaseStatus.CONFIRMED
    not_mono = await env.service.execute(req("other-backdrop"))
    assert not_mono.status is PurchaseStatus.CANCELLED and "NOT_MONOCHROME" in not_mono.reason
    unknown = await env.service.execute(req("unknown"))
    assert unknown.status is PurchaseStatus.CANCELLED and "UNKNOWN" in unknown.reason
    assert env.mrkt.buy_calls == ["mono"]
    attempt = (await env.attempts())[0]
    assert (attempt.monochrome_status, attempt.monochrome_type) == ("MONOCHROME", "high")


async def test_monochrome_budget_is_independent_from_regular(env: Env) -> None:
    await env.add_user(UID, total=100 * TON)
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    await env.set_mode_budget(UID, BudgetScope.MONOCHROME, total_limit_nano=5 * TON)
    env.mrkt.add(make_listing("mono", model_name="Onyx", backdrop_name="Black", price_nano=10 * TON))
    env.mrkt.add(make_listing("reg", model_name="Ivory", backdrop_name="White", price_nano=10 * TON))
    mono_fid = await env.add_filter(UID, FilterKind.MONOCHROME, name="mono")
    reg_fid = await env.add_filter(UID, name="reg")
    mono = await env.service.execute(
        env.request(UID, "mono", 10 * TON, filter_id=mono_fid, mode=PurchaseMode.MONOCHROME)
    )
    assert mono.status is PurchaseStatus.CANCELLED and "Режим монохромов" in mono.reason
    reg = await env.service.execute(env.request(UID, "reg", 10 * TON, filter_id=reg_fid))
    assert reg.status is PurchaseStatus.CONFIRMED


async def test_monochrome_mode_respects_overall_user_budget(env: Env) -> None:
    await env.add_user(UID, total=12 * TON)
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    env.mrkt.add(make_listing("reg", model_name="Ivory", backdrop_name="White", price_nano=10 * TON))
    env.mrkt.add(make_listing("mono", model_name="Onyx", backdrop_name="Black", price_nano=10 * TON))
    reg_fid = await env.add_filter(UID, name="reg")
    mono_fid = await env.add_filter(UID, FilterKind.MONOCHROME, name="mono")
    assert (await env.service.execute(env.request(UID, "reg", 10 * TON, filter_id=reg_fid))).status is (
        PurchaseStatus.CONFIRMED
    )
    mono = await env.service.execute(
        env.request(UID, "mono", 10 * TON, filter_id=mono_fid, mode=PurchaseMode.MONOCHROME)
    )
    assert mono.status is PurchaseStatus.CANCELLED and "Общий лимит" in mono.reason


async def test_mode_toggles_are_independent(env: Env) -> None:
    await env.add_user(UID, autobuy=False, mono=True)
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    env.mrkt.add(make_listing("mono", model_name="Onyx", backdrop_name="Black"))
    env.mrkt.add(make_listing("reg", model_name="Ivory", backdrop_name="White"))
    reg_fid = await env.add_filter(UID, name="reg")
    mono_fid = await env.add_filter(UID, FilterKind.MONOCHROME, name="mono")
    reg = await env.service.execute(env.request(UID, "reg", 10 * TON, filter_id=reg_fid))
    assert reg.status is None and "выключена" in reg.reason
    mono = await env.service.execute(
        env.request(UID, "mono", 10 * TON, filter_id=mono_fid, mode=PurchaseMode.MONOCHROME)
    )
    assert mono.status is PurchaseStatus.CONFIRMED


async def test_dry_run_never_sends_buy_and_uses_separate_accounting(env: Env) -> None:
    fid = await setup_regular(env, daily=15 * TON)
    await env.control.set_run_mode(RunMode.DRY_RUN, by_user=None)
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.DRY_RUN
    assert env.mrkt.buy_calls == []
    assert "Тестовый режим" in env.sender.texts_for(UID)[-1]
    async with env.sessionmaker() as session:
        live = await purchases_repo.usage(
            session, user_id=UID, run_mode=PurchaseRunMode.LIVE, day_start=datetime(2000, 1, 1, tzinfo=UTC)
        )
        dry = await purchases_repo.usage(
            session, user_id=UID, run_mode=PurchaseRunMode.DRY_RUN, day_start=datetime(2000, 1, 1, tzinfo=UTC)
        )
    assert live.total_spent == 0 and dry.total_spent == 10 * TON
    # the same gift is not "bought" twice in test mode either
    assert (await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))).status is None


async def test_notify_only_mode_disables_purchases(env: Env) -> None:
    fid = await setup_regular(env)
    await env.control.set_run_mode(RunMode.NOTIFY_ONLY, by_user=None)
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is None and env.mrkt.buy_calls == []


async def test_run_mode_cannot_exceed_environment(env: Env) -> None:
    env.settings.run_mode = RunMode.DRY_RUN
    with pytest.raises(ValueError):
        await env.control.set_run_mode(RunMode.LIVE, by_user=None)


async def test_emergency_stop_blocks_purchases_and_survives_redis_loss(env: Env) -> None:
    fid = await setup_regular(env)
    await env.control.stop_all(by_user=1, reason="test")
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is None and "Аварийная остановка" in result.reason
    assert env.mrkt.buy_calls == []
    await env.redis.flushall()
    await env.control.restore()  # restart: state comes back from PostgreSQL
    assert await env.control.is_stopped()
    await env.control.resume(by_user=1)
    assert (await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))).status is (
        PurchaseStatus.CONFIRMED
    )


async def test_emergency_stop_between_reservation_and_request(env: Env) -> None:
    fid = await setup_regular(env)
    original = env.mrkt.balance_nano

    async def balance_then_stop() -> int | None:
        await env.control.stop_all(by_user=1, reason="pressed during purchase")
        return await original()

    env.mrkt.balance_nano = balance_then_stop  # type: ignore[method-assign]
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CANCELLED
    assert env.mrkt.buy_calls == []


async def test_insufficient_balance_is_not_sent(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.balance = 5 * TON
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.FAILED and "Недостаточно средств" in result.reason
    assert env.mrkt.buy_calls == []


async def test_price_increase_above_filter_cancels(env: Env) -> None:
    await env.add_user(UID)
    env.mrkt.add(make_listing("g1", price_nano=12 * TON))
    fid = await env.add_filter(UID, criteria={"max_price_nano": 10 * TON})
    result = await env.service.execute(env.request(UID, "g1", 9 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CANCELLED and "цена выше" in result.reason
    assert env.mrkt.buy_calls == []


async def test_listing_gone_on_recheck(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.gifts["g1"] = replace(env.mrkt.gifts["g1"], is_on_sale=False)
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CANCELLED and "снято" in result.reason
    assert env.mrkt.buy_calls == []


async def test_manual_purchase_requires_reconfirmation_on_price_increase(env: Env) -> None:
    await env.add_user(UID, autobuy=False, mono=False)
    env.mrkt.add(make_listing("g1", price_nano=11 * TON))
    result = await env.service.execute(
        env.request(UID, "g1", 10 * TON, mode=PurchaseMode.MANUAL, trigger="manual")
    )
    assert result.status is PurchaseStatus.CANCELLED and "Цена выросла" in result.reason
    env.mrkt.add(make_listing("g1", price_nano=10 * TON))
    ok = await env.service.execute(
        env.request(UID, "g1", 10 * TON, mode=PurchaseMode.MANUAL, trigger="manual")
    )
    assert ok.status is PurchaseStatus.CONFIRMED


async def test_users_without_purchase_rights_cannot_buy(env: Env) -> None:
    fid = await setup_regular(env, can_purchase=False)
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is None and env.mrkt.buy_calls == []


async def test_recovery_after_crash(env: Env) -> None:
    await setup_regular(env)
    async with env.sessionmaker() as session, session.begin():
        for gift, status in (("a", "reserved"), ("b", "submitted")):
            session.add(
                PurchaseAttempt(
                    user_id=UID,
                    mode="regular",
                    run_mode="live",
                    gift_id=gift,
                    expected_price_nano=TON,
                    status=status,
                )
            )
    await env.service.recover_on_startup()
    assert await statuses(env) == ["cancelled", "unknown"]


async def test_background_reverification_resolves_unknown(env: Env) -> None:
    await setup_regular(env)
    async with env.sessionmaker() as session, session.begin():
        session.add(
            PurchaseAttempt(
                user_id=UID,
                mode="regular",
                run_mode="live",
                gift_id="g1",
                expected_price_nano=10 * TON,
                status="unknown",
                collection_name="Plush Pepe",
                number=100,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    env.mrkt.gifts["g1"] = replace(env.mrkt.gifts["g1"], is_on_sale=False, is_mine=True)
    resolved = await env.service.reverify_unknown(max_age_hours=10**6)
    assert resolved == 1
    assert await statuses(env) == ["confirmed"]
    assert await env.purchases_count() == 1
    assert env.mrkt.buy_calls == []  # verification never buys


async def test_stale_snapshot_is_refetched_and_price_change_cancels(env: Env) -> None:
    fid = await setup_regular(env)
    env.settings.purchase_max_snapshot_age_seconds = 0.0  # force the pre-send re-check
    on_sale = make_listing("g1", price_nano=10 * TON)
    more_expensive = make_listing("g1", price_nano=11 * TON)
    env.mrkt.get_scripts["g1"] = deque([on_sale, more_expensive])
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.CANCELLED and "Цена изменилась перед отправкой" in result.reason
    assert env.mrkt.buy_calls == []
    # same price on the re-check -> the purchase goes through
    env.mrkt.get_scripts["g1"] = deque([on_sale, on_sale])
    assert (await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))).status is (
        PurchaseStatus.CONFIRMED
    )


async def test_no_retry_when_lock_was_lost(env: Env) -> None:
    fid = await setup_regular(env)
    env.mrkt.buy_outcomes = deque([BuyOutcome(BuyOutcomeKind.UNCERTAIN, "502")])
    on_sale = make_listing("g1", price_nano=10 * TON)
    env.mrkt.get_scripts["g1"] = deque([on_sale] * 10)
    original_verify = env.service.verify

    async def verify_and_lose_lock(listing):
        result = await original_verify(listing)
        await env.redis.delete(f"{env.settings.redis_prefix}:lock:purchase:g1")  # lock expired meanwhile
        return result

    env.service.verify = verify_and_lose_lock  # type: ignore[method-assign]
    result = await env.service.execute(env.request(UID, "g1", 10 * TON, filter_id=fid))
    assert result.status is PurchaseStatus.FAILED
    assert env.mrkt.buy_calls == ["g1"]  # without the lock no second request is sent
    assert any("не выполнена" in t for t in env.sender.texts_for(UID))
