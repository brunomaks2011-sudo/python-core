"""Mini App API: access control, collections with monochrome data, rules stored as filters, limits."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from gift_sniper.config import RunMode
from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import giftwiki as giftwiki_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.types import FeedEvent, MonochromeRecord
from gift_sniper.integrations.mrkt import MrktAttribute
from gift_sniper.services.enrichment import ReferenceStore
from gift_sniper.services.processor import ListingProcessor
from gift_sniper.services.queue import MemoryQueue
from gift_sniper.webapp.api import MiniAppApi
from gift_sniper.webapp.server import create_app
from tests.factories import TON, make_listing, make_settings
from tests.integration.conftest import Env
from tests.unit.test_webapp_auth import TOKEN, make_init_data

pytestmark = pytest.mark.db

ADMIN = 1  # make_settings() -> ADMIN_USER_IDS=[1]
PEPE = "/api/collections/Plush%20Pepe"


def auth(user_id: int = ADMIN) -> dict[str, str]:
    return {"Authorization": "tma " + make_init_data(TOKEN, user_id)}


@pytest_asyncio.fixture
async def client(env: Env) -> AsyncIterator[TestClient]:  # type: ignore[type-arg]
    async with env.sessionmaker() as session, session.begin():
        await listings_repo.upsert_collections(
            session, [("Plush Pepe", "Plush Pepe", 5 * TON), ("Lol Pop", "Lol Pop", 2 * TON)]
        )
    api = MiniAppApi(
        env.settings,
        env.sessionmaker,
        env.redis,
        env.mrkt,  # type: ignore[arg-type]
        env.store,
        env.filter_cache,
        env.service,
        env.control,
    )
    client = TestClient(TestServer(create_app(api, make_settings(telegram_bot_token=TOKEN))))
    await client.start_server()
    yield client
    await client.close()


async def test_only_signed_requests_from_allowed_users(client: TestClient) -> None:  # type: ignore[type-arg]
    assert (await client.get("/api/me")).status == 401
    stranger = await client.get("/api/me", headers=auth(666))
    assert stranger.status == 403 and "666" in (await stranger.json())["error"]
    page = await client.get("/app/")
    assert page.status == 200 and "Снайпер" in await page.text()
    me = await (await client.get("/api/me", headers=auth())).json()
    assert me["is_admin"] and not me["ready"]
    assert {
        "id": "limits",
        "ok": False,
        "text": "Общие лимиты: на покупку, на день и всего",
        "action": "settings",
    } in me["checklist"]


async def test_collection_shows_models_monochrome_backdrops_and_chance(
    client: TestClient,  # type: ignore[type-arg]
    env: Env,
) -> None:
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high"), ("Onyx", "Midnight", "low")])
    env.mrkt.attributes[("model", "Plush Pepe")] = [
        MrktAttribute("Onyx", 15),
        MrktAttribute("Ivory", 20),
        MrktAttribute("Gold", 5),
    ]
    env.mrkt.attributes[("backdrop", "Plush Pepe")] = [
        MrktAttribute("Black", 20),
        MrktAttribute("Midnight", 10),
        MrktAttribute("White", 30),
    ]
    async with env.sessionmaker() as session, session.begin():  # a gift MRKT showed: Onyx on Black
        await listings_repo.upsert_gift(
            session, make_listing("g7", name="PlushPepe-77", backdrop_center_color=0x112233)
        )
    detail = await (await client.get(PEPE, headers=auth())).json()
    onyx = next(m for m in detail["models"] if m["name"] == "Onyx")
    black, midnight = onyx["pairs"]
    assert (black["backdrop"], black["type"], black["rarity"]) == ("Black", "high", 2.0)
    assert black["image"] == "https://nft.fragment.com/gift/plushpepe-77.webp"  # the gift seen on MRKT
    assert black["center"] == "#112233" and black["price"] is None
    assert (midnight["backdrop"], midnight["type"], midnight["image"]) == ("Midnight", "low", None)
    assert onyx["rarity"] == 1.5 and onyx["image"] == black["image"]
    assert onyx["monochrome_chance"] == pytest.approx(3.0)  # Black 2% + Midnight 1% of Onyx copies
    assert detail["models"][0]["name"] == "Onyx"  # models with monochromes first
    assert detail["monochrome_share"] == pytest.approx(100 / 3) and detail["models_source"] == "mrkt"
    assert detail["image"] == "https://fragment.com/file/gifts/plushpepe/thumb.webp"

    listing = await (await client.get("/api/collections", headers=auth())).json()
    pepe = next(c for c in listing["items"] if c["name"] == "Plush Pepe")
    assert (pepe["monochrome_models"], pepe["known_models"], pepe["monochrome_pairs"]) == (1, 3, 2)
    assert pepe["image"] == "https://fragment.com/file/gifts/plushpepe/thumb.webp"
    await client.get(PEPE, headers=auth())
    assert env.mrkt.attribute_calls.count(("model", "Plush Pepe")) == 1  # cached in Redis
    assert (await client.get("/api/collections/Nope", headers=auth())).status == 404


async def test_rule_from_the_mini_app_buys_through_the_regular_pipeline(
    client: TestClient,  # type: ignore[type-arg]
    env: Env,
) -> None:
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    rule = {"collection": "Plush Pepe", "model": "Onyx", "backdrop_mode": "monochrome", "autobuy": True}
    no_price = await client.post("/api/rules", headers=auth(), json=rule)
    assert no_price.status == 400 and "цену" in (await no_price.json())["error"]
    created = await client.post("/api/rules", headers=auth(), json={**rule, "max_price_ton": "12"})
    assert created.status == 201
    view = await created.json()
    assert (view["kind"], view["autobuy"], view["max_price"], view["model"]) == (
        "monochrome",
        True,
        12,
        "Onyx",
    )
    async with env.sessionmaker() as session:
        row = await filters_repo.get_filter(session, ADMIN, view["id"])
        prefs = await users_repo.get_settings(session, ADMIN)
    assert row is not None and row.enabled
    spec = filters_repo.to_spec(row)
    assert (spec.criteria.collections, spec.criteria.models, spec.criteria.max_price_nano) == (
        ["Plush Pepe"],
        ["Onyx"],
        12 * TON,
    )
    assert prefs.monochrome_autobuy_enabled  # the rule's switch also turns its mode on

    saved = await client.put(
        "/api/settings",
        headers=auth(),
        json={"per_purchase_ton": "20", "daily_ton": "50", "total_ton": "100"},
    )
    assert (await saved.json())["limits"] == {"per_purchase": 20, "daily": 50, "total": 100}

    queue = MemoryQueue()
    processor = ListingProcessor(
        env.settings, env.sessionmaker, env.enricher, env.filter_cache, env.notifier, queue
    )
    listing = make_listing("g1", price_nano=10 * TON)  # Plush Pepe, Onyx on Black
    event = FeedEvent("e1", "listing", listing, 10 * TON, datetime.now(UTC) - timedelta(seconds=1))
    report = await processor.process(event, detected_at=datetime.now(UTC))
    assert report.matched_filters == [view["id"]]
    assert [(p["filter_id"], p["mode"]) for p in queue.published] == [(view["id"], "monochrome")]


async def test_rules_switches_edit_and_delete(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    created = await client.post(
        "/api/rules",
        headers=auth(),
        json={
            "collection": "Lol Pop",
            "backdrop_mode": "selected",
            "backdrops": ["Black"],
            "max_price_ton": 3,
        },
    )
    rule_id = (await created.json())["id"]
    off = await (await client.patch(f"/api/rules/{rule_id}", headers=auth(), json={"enabled": False})).json()
    assert off["enabled"] is False
    edited = await client.put(
        f"/api/rules/{rule_id}",
        headers=auth(),
        json={"collection": "Lol Pop", "model": "Candy", "backdrop_mode": "any", "max_price_ton": "4.5"},
    )
    view = await edited.json()
    assert (view["model"], view["backdrop_mode"], view["backdrops"], view["max_price"]) == (
        "Candy",
        "any",
        [],
        4.5,
    )
    assert len((await (await client.get("/api/rules", headers=auth())).json())["items"]) == 1
    selected_empty = await client.put(
        f"/api/rules/{rule_id}", headers=auth(), json={"collection": "Lol Pop", "backdrop_mode": "selected"}
    )
    assert selected_empty.status == 400
    other_user = await client.delete(f"/api/rules/{rule_id}", headers=auth(2))
    assert other_user.status == 403  # user 2 is not allowed in the bot at all
    assert (await client.delete(f"/api/rules/{rule_id}", headers=auth())).status == 200
    assert (await (await client.get("/api/rules", headers=auth())).json())["items"] == []


async def test_emergency_stop_from_the_mini_app(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    stopped = await (await client.post("/api/stop", headers=auth())).json()
    assert stopped["stopped"] and await env.control.is_stopped()
    resumed = await (await client.post("/api/resume", headers=auth())).json()
    assert not resumed["stopped"]


async def test_price_range_from_and_to(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])
    body = {
        "model": "Onyx",
        "any_price_ton": "10",
        "any_min_ton": "4",
        "pairs": [{"backdrop": "Black", "price_ton": "9", "min_ton": "6,5"}],
    }
    saved = await (await client.put(PEPE + "/picks", headers=auth(), json=body)).json()
    onyx = next(m for m in saved["models"] if m["name"] == "Onyx")
    assert (onyx["any_min"], onyx["any"]) == (4, 10)
    assert (onyx["pairs"][0]["min"], onyx["pairs"][0]["price"]) == (6.5, 9)
    cards = (await (await client.get("/api/rules", headers=auth())).json())["items"]
    labels = [label for card in cards for label in card["picks"]]
    assert "Onyx · любой фон от 4 TON до 10 TON" in labels and "Onyx · Black от 6.5 TON до 9 TON" in labels
    upside = await client.put(PEPE + "/picks", headers=auth(), json={**body, "any_min_ton": "11"})
    assert upside.status == 400 and "«От» больше «до»" in (await upside.json())["error"]

    await client.put(
        "/api/settings",
        headers=auth(),
        json={"per_purchase_ton": "20", "daily_ton": "50", "total_ton": "100"},
    )
    queue = MemoryQueue()
    processor = ListingProcessor(
        env.settings, env.sessionmaker, env.enricher, env.filter_cache, env.notifier, queue
    )

    async def offer(event_id: str, price: int, **kw: str) -> list[int]:
        listing = make_listing(event_id, price_nano=price, **kw)  # type: ignore[arg-type]
        event = FeedEvent(event_id, "listing", listing, price, datetime.now(UTC) - timedelta(seconds=1))
        return (await processor.process(event, detected_at=datetime.now(UTC))).matched_filters

    regular = next(c["id"] for c in cards if c["kind"] == "regular")
    mono = next(c["id"] for c in cards if c["kind"] == "monochrome")
    assert await offer("a", 5 * TON, backdrop_name="White") == [regular]  # any backdrop: 4 … 10
    assert await offer("b", 3 * TON, backdrop_name="White") == []  # cheaper than "от"
    assert mono in await offer("c", 7 * TON)  # Onyx on Black: 6.5 … 9
    assert await offer("d", 6 * TON) == [regular]  # below the pair's "от", still within "любой фон"


async def test_monochromes_up_to_a_floor_from_the_mini_app(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high"), ("Onyx", "Midnight", "low")])
    body = {
        "model": "Onyx",
        "monochrome_rule": "model_floor",
        "pairs": [{"backdrop": "Black", "rule": "collection_floor"}],
    }
    saved = await (await client.put(PEPE + "/picks", headers=auth(), json=body)).json()
    onyx = next(m for m in saved["models"] if m["name"] == "Onyx")
    assert (onyx["monochrome"], onyx["monochrome_rule"], onyx["taken"]) == (None, "model_floor", 2)
    assert [(p["backdrop"], p["price"], p["rule"]) for p in onyx["pairs"]] == [
        ("Black", None, "collection_floor"),
        ("Midnight", None, None),
    ]
    whole = await (
        await client.put(PEPE + "/picks", headers=auth(), json={"monochrome_rule": "collection_floor"})
    ).json()
    assert whole["whole"] == {
        "any": None,
        "any_min": None,
        "monochrome": None,
        "monochrome_min": None,
        "monochrome_rule": "collection_floor",
    }

    cards = (await (await client.get("/api/rules", headers=auth())).json())["items"]
    mono = next(r for r in cards if r["kind"] == "monochrome")
    assert {"model": "Onyx", "backdrops": [], "price": None, "min": None, "rule": "model_floor"} in mono[
        "pick_items"
    ]
    assert "Onyx · все монохромные фоны ≤ флор модели" in mono["picks"]
    async with env.sessionmaker() as session:
        row = await filters_repo.get_filter(session, ADMIN, mono["id"])
    assert row is not None
    rules = {p.price_rule.value for p in filters_repo.to_spec(row).criteria.picks}
    assert rules == {"model_floor", "collection_floor"}
    unknown = await client.put(
        PEPE + "/picks", headers=auth(), json={"model": "Onyx", "monochrome_rule": "cheapest"}
    )
    assert unknown.status == 400


async def test_every_monochrome_up_to_the_floor_in_one_tap(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high")])  # Lol Pop has no monochrome data
    pair = {"model": "Onyx", "pairs": [{"backdrop": "Black", "price_ton": "9"}]}
    await client.put(PEPE + "/picks", headers=auth(), json=pair)

    on = await (
        await client.put("/api/monochromes", headers=auth(), json={"rule": "collection_floor"})
    ).json()
    assert on == {"changed": 1, "collections": 1, "error": None}
    listing = {
        c["name"]: c for c in (await (await client.get("/api/collections", headers=auth())).json())["items"]
    }
    assert (listing["Plush Pepe"]["monochrome_floor"], listing["Lol Pop"]["monochrome_floor"]) == (
        "collection_floor",
        None,
    )
    detail = await (await client.get(PEPE, headers=auth())).json()
    assert detail["whole"]["monochrome_rule"] == "collection_floor"
    onyx = next(m for m in detail["models"] if m["name"] == "Onyx")
    assert [(p["backdrop"], p["price"]) for p in onyx["pairs"]] == [("Black", 9)]  # chosen one by one: kept
    again = await (
        await client.put("/api/monochromes", headers=auth(), json={"rule": "collection_floor"})
    ).json()
    assert again["changed"] == 0

    off = await (await client.put("/api/monochromes", headers=auth(), json={"rule": None})).json()
    assert off["changed"] == 1
    detail = await (await client.get(PEPE, headers=auth())).json()
    assert detail["whole"]["monochrome_rule"] is None and detail["taken"] == 1
    assert (await client.put("/api/monochromes", headers=auth(), json={"rule": "fixed"})).status == 400


async def test_notification_switches_and_what_blocks_buying(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    me = await (await client.get("/api/me", headers=auth())).json()
    assert me["notify"] == {
        "purchases": True,
        "errors": True,
        "matching_only": True,
        "monochrome": True,
        "all_listings": False,
        "price_drops": False,
    }
    body = {"notify": {"monochrome": False, "matching_only": False}}
    saved = await (await client.put("/api/settings", headers=auth(), json=body)).json()
    assert (
        saved["notify"]["monochrome"],
        saved["notify"]["matching_only"],
        saved["notify"]["purchases"],
    ) == (
        False,
        False,
        True,
    )
    async with env.sessionmaker() as session:
        prefs = await users_repo.get_settings(session, ADMIN)
    assert prefs.notify["monochrome"] is False  # where the notifier reads it
    unknown = await client.put("/api/settings", headers=auth(), json={"notify": {"sms": True}})
    assert unknown.status == 400

    # a buying rule whose autobuy switch is off, and a pause: both are named, with the switch to turn on
    await env.add_filter(
        ADMIN, name="pepe", criteria={"collections": ["Plush Pepe"], "max_price_nano": 5 * TON}
    )
    await client.put(
        "/api/settings", headers=auth(), json={"autobuy_enabled": False, "purchases_paused": True}
    )
    me = await (await client.get("/api/me", headers=auth())).json()
    assert me["modes_missing"] == ["autobuy_enabled"]
    assert {"modes", "paused"} <= {c["id"] for c in me["checklist"] if not c["ok"]}
    fixed = await client.put(
        "/api/settings", headers=auth(), json={"autobuy_enabled": True, "purchases_paused": False}
    )
    assert (await fixed.json())["modes_missing"] == []


async def test_reaction_speed_from_the_mini_app(
    client: TestClient,  # type: ignore[type-arg]
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    me = await (await client.get("/api/me", headers=auth())).json()
    assert me["poll_interval"] == env.settings.mrkt_feed_poll_interval_seconds
    fast = await (await client.put("/api/speed", headers=auth(), json={"interval": 0.5})).json()
    assert fast["poll_interval"] == 0.5 and await env.control.poll_interval() == 0.5
    assert (await client.put("/api/speed", headers=auth(), json={"interval": 0.01})).status == 400
    assert (await client.put("/api/speed", headers=auth(), json={})).status == 400
    monkeypatch.setattr(env.settings, "allowed_user_ids", [7])
    assert (await client.put("/api/speed", headers=auth(7), json={"interval": 1})).status == 403


async def test_run_mode_switch_goes_up_to_run_mode_from_env(
    client: TestClient,  # type: ignore[type-arg]
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lowered = await (await client.put("/api/mode", headers=auth(), json={"mode": "dry_run"})).json()
    assert (lowered["run_mode"], lowered["max_run_mode"]) == ("dry_run", "live")
    assert await env.control.run_mode() is RunMode.DRY_RUN
    raised = await (await client.put("/api/mode", headers=auth(), json={"mode": "live"})).json()
    assert raised["run_mode"] == "live" and await env.control.run_mode() is RunMode.LIVE
    assert (await client.put("/api/mode", headers=auth(), json={"mode": "turbo"})).status == 400

    monkeypatch.setattr(env.settings, "run_mode", RunMode.DRY_RUN)  # RUN_MODE=dry_run in .env
    above = await client.put("/api/mode", headers=auth(), json={"mode": "live"})
    assert above.status == 400 and "live.cmd" in (await above.json())["error"]
    assert await env.control.run_mode() is RunMode.DRY_RUN  # never above RUN_MODE

    monkeypatch.setattr(env.settings, "allowed_user_ids", [7])
    viewer = await client.put("/api/mode", headers=auth(7), json={"mode": "notify_only"})
    assert viewer.status == 403 and "администратор" in (await viewer.json())["error"]


async def test_pairs_picked_with_their_own_prices(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    await env.add_giftwiki("Plush Pepe", [("Onyx", "Black", "high"), ("Onyx", "Midnight", "low")])
    picks = {
        "model": "Onyx",
        "any_price_ton": "3",
        "monochrome_price_ton": "7",
        "pairs": [{"backdrop": "Black", "price_ton": "9"}],
        "autobuy": True,
    }
    no_price = await client.put(
        PEPE + "/picks", headers=auth(), json={"model": "Onyx", "pairs": [{"backdrop": "Black"}]}
    )
    assert no_price.status == 400 and "Black" in (await no_price.json())["error"]
    saved = await (await client.put(PEPE + "/picks", headers=auth(), json=picks)).json()
    onyx = next(m for m in saved["models"] if m["name"] == "Onyx")
    assert (onyx["any"], onyx["monochrome"], onyx["taken"]) == (3, 7, 3)
    assert [(p["backdrop"], p["price"]) for p in onyx["pairs"]] == [("Black", 9), ("Midnight", None)]
    whole = await client.put(PEPE + "/picks", headers=auth(), json={"monochrome_price_ton": "4"})
    assert (await whole.json())["whole"] == {
        "any": None,
        "any_min": None,
        "monochrome": 4,
        "monochrome_min": None,
        "monochrome_rule": None,
    }
    listing = (await (await client.get("/api/collections", headers=auth())).json())["items"]
    pepe = next(c for c in listing if c["name"] == "Plush Pepe")
    assert (pepe["taken"], pepe["autobuy"]) == (4, True)
    assert next(c for c in listing if c["name"] == "Lol Pop")["autobuy"] is None  # nothing taken there
    cards = {r["kind"]: r for r in (await (await client.get("/api/rules", headers=auth())).json())["items"]}
    mono_card = cards["monochrome"]
    assert mono_card["image"] == "https://fragment.com/file/gifts/plushpepe/thumb.webp"
    assert {"model": "Onyx", "backdrops": ["Black"], "price": 9, "min": None, "rule": "fixed"} in mono_card[
        "pick_items"
    ]
    assert "Onyx · все монохромные фоны ≤ 7 TON" in mono_card["picks"]  # not "любой фон" in a monochrome plan
    assert cards["regular"]["picks"] == ["Onyx · любой фон ≤ 3 TON"]

    async with env.sessionmaker() as session:
        rows = await filters_repo.list_filters(session, ADMIN)
        prefs = await users_repo.get_settings(session, ADMIN)
    assert sorted(r.name for r in rows) == ["📱 Plush Pepe", "📱 Plush Pepe · монохромы"]
    assert all(r.enabled and r.autobuy for r in rows) and prefs.monochrome_autobuy_enabled
    assert filters_repo.without_plans(rows) == ([], 2)  # the chat menus do not list them

    await client.put(
        "/api/settings",
        headers=auth(),
        json={"per_purchase_ton": "20", "daily_ton": "50", "total_ton": "100"},
    )
    queue = MemoryQueue()
    processor = ListingProcessor(
        env.settings, env.sessionmaker, env.enricher, env.filter_cache, env.notifier, queue
    )

    async def offer(event_id: str, price: int, **kw: str) -> list[int]:
        listing = make_listing(event_id, price_nano=price, **kw)  # type: ignore[arg-type]
        event = FeedEvent(event_id, "listing", listing, price, datetime.now(UTC) - timedelta(seconds=1))
        return (await processor.process(event, detected_at=datetime.now(UTC))).matched_filters

    mono_plan = next(r.id for r in rows if r.kind == "monochrome")
    assert await offer("a", 8 * TON) == [mono_plan]  # Onyx on Black: the pair's own price 9 TON
    assert await offer("b", int(9.5 * TON)) == []
    assert await offer("c", 6 * TON, backdrop_name="Midnight") == [mono_plan]  # every Onyx monochrome: 7
    assert await offer("d", 8 * TON, backdrop_name="Midnight") == []

    cleared = await (await client.put(PEPE + "/picks", headers=auth(), json={"model": "Onyx"})).json()
    assert next(m for m in cleared["models"] if m["name"] == "Onyx")["taken"] == 0
    await client.put(PEPE + "/picks", headers=auth(), json={})  # nothing left for the whole collection
    async with env.sessionmaker() as session:
        assert await filters_repo.list_filters(session, ADMIN) == []


async def test_data_synced_by_another_process_shows_up(client: TestClient, env: Env) -> None:  # type: ignore[type-arg]
    """`sync-giftwiki` runs in its own container: it stores records and bumps the version in Redis."""
    now = datetime.now(UTC)
    record = MonochromeRecord(
        record_id="r1",
        gift_id="gw-1",
        gift_name="Plush Pepe",
        model_name="Onyx",
        backdrop_name="Black",
        type_raw="high",
        raw={},
    )
    async with env.sessionmaker() as session, session.begin():
        await giftwiki_repo.upsert_gift(
            session,
            "gw-1",
            "Plush Pepe",
            records_count=1,
            complete=True,
            coverage_source="gift_lookup",
            synced_at=now,
            source_url="test",
        )
        await giftwiki_repo.upsert_records(session, "gw-1", [record], seen_at=now, source_url="test")
        run = await giftwiki_repo.start_run(session, "manual")
        run.status, run.finished_at = "success", now
    await ReferenceStore(env.sessionmaker, env.redis, env.settings.redis_prefix).bump()  # the other process
    listing = await (await client.get("/api/collections", headers=auth())).json()
    assert next(c for c in listing["items"] if c["name"] == "Plush Pepe")["monochrome_pairs"] == 1
