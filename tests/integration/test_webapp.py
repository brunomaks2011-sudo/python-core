"""Mini App API: access control, collections with monochrome data, rules stored as filters, limits."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from gift_sniper.db.repo import filters as filters_repo
from gift_sniper.db.repo import listings as listings_repo
from gift_sniper.db.repo import users as users_repo
from gift_sniper.domain.types import FeedEvent
from gift_sniper.integrations.mrkt import MrktAttribute
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
    assert {"ok": False, "text": "Общие лимиты: на покупку, на день и всего", "action": "settings"} in me[
        "checklist"
    ]


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
    detail = await (await client.get(PEPE, headers=auth())).json()
    onyx = next(m for m in detail["models"] if m["name"] == "Onyx")
    assert [b["name"] for b in onyx["monochrome_backdrops"]] == ["Black", "Midnight"]
    assert onyx["rarity"] == 1.5
    assert onyx["monochrome_chance"] == pytest.approx(3.0)  # Black 2% + Midnight 1% of Onyx copies
    assert detail["models"][0]["name"] == "Onyx"  # models with monochromes first
    assert detail["monochrome_share"] == pytest.approx(100 / 3) and detail["models_source"] == "mrkt"
    assert {b["name"] for b in detail["backdrops"]} == {"Black", "Midnight", "White"}

    listing = await (await client.get("/api/collections", headers=auth())).json()
    pepe = next(c for c in listing["items"] if c["name"] == "Plush Pepe")
    assert (pepe["monochrome_models"], pepe["known_models"], pepe["monochrome_pairs"]) == (1, 3, 2)
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
