"""MRKT and Gift Wiki HTTP clients against a local server returning documentation-shaped responses."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from gift_sniper.integrations.giftwiki import (
    GiftWikiAuthError,
    GiftWikiClient,
    GiftWikiError,
    GiftWikiForbiddenError,
)
from gift_sniper.integrations.mrkt import BuyOutcomeKind, MrktAuthError, MrktClient, SalingQuery
from gift_sniper.integrations.mrkt.client import classify_buy_response
from gift_sniper.integrations.mrkt.parsing import parse_datetime, parse_feed_item, parse_gift
from tests.factories import TON, make_settings
from tests.fake_server import FakeServer, Reply

API = "/api/v1/"
GW = "/gifts/monochromes"

GIFT = {
    "id": "a1b2",
    "name": "PlushPepe-42",
    "number": 42,
    "collectionName": "Plush Pepe",
    "collectionTitle": "Plush Pepe",
    "modelName": "Onyx",
    "modelRarityPerMille": 15,
    "backdropName": "Black",
    "backdropRarityPerMille": 20,
    "symbolName": "Star",
    "symbolRarityPerMille": 4,
    "salePrice": 12 * TON,
    "isOnSale": True,
    "isMine": False,
    "backdropColorsCenterColor": 0,
}


def gw_record(
    i: int, gift: str = "Plush Pepe", model: str = "Onyx", backdrop: str = "Black", kind: str = "high"
):
    return {
        "_id": f"id{i}",
        "gift_id": "g-pepe",
        "gift_name": gift,
        "model_name": model,
        "backdrop_name": backdrop,
        "type": kind,
        "center_color": "#000000",
        "edge_color": "#000000",
        "pattern_color": "#111111",
        "text_color": "#ffffff",
        "photo_url": "https://x/1.png",
        "animation_url": "https://x/1.json",
        "future_field": 1,
    }


@pytest_asyncio.fixture
async def server() -> AsyncIterator[FakeServer]:
    srv = FakeServer()
    await srv.start()
    yield srv
    await srv.stop()


async def mrkt_client(server: FakeServer, **overrides: object) -> MrktClient:
    client = MrktClient(make_settings(mrkt_api_base_url=server.url + "/api/v1", **overrides))
    await client.start()
    return client


class TestMrktParsing:
    def test_gift_fields_and_missing_values_stay_none(self) -> None:
        gift = parse_gift(GIFT)
        assert gift is not None
        assert gift.price_nano == 12 * TON and gift.model_rarity_permille == 15
        assert gift.telegram_slug == "PlushPepe-42"
        sparse = parse_gift({"id": "x"})
        assert sparse is not None
        assert (
            sparse.price_nano is None and sparse.model_rarity_permille is None and sparse.is_on_sale is None
        )

    def test_invalid_gift(self) -> None:
        assert parse_gift({"name": "no id"}) is None
        assert parse_gift("junk") is None

    def test_feed_item(self) -> None:
        event = parse_feed_item(
            {
                "type": "listing",
                "id": "ev1",
                "gift": GIFT,
                "amount": 11 * TON,
                "date": "2026-10-23T10:00:00.1234567Z",
            }
        )
        assert event is not None
        assert (event.event_id, event.type, event.amount_nano) == ("ev1", "listing", 11 * TON)
        assert event.date is not None and event.date.microsecond == 123456

    def test_datetime_variants(self) -> None:
        assert parse_datetime("2026-10-23T10:00:00") is not None
        assert parse_datetime(1_760_000_000_000) is not None
        assert parse_datetime("garbage") is None


class TestBuyClassification:
    def test_confirmed(self) -> None:
        out = classify_buy_response("a1b2", 200, '[{"userGift": {"id": "a1b2"}, "price": 12000000000}]')
        assert out.kind is BuyOutcomeKind.CONFIRMED and out.price_nano == 12 * TON

    def test_success_without_data_is_uncertain(self) -> None:
        assert classify_buy_response("a1b2", 200, "[]").kind is BuyOutcomeKind.UNCERTAIN
        assert classify_buy_response("a1b2", 200, "").kind is BuyOutcomeKind.UNCERTAIN

    def test_server_errors_are_uncertain(self) -> None:
        for status in (500, 502, 503, 504, 408):
            assert classify_buy_response("a1b2", status, "oops").kind is BuyOutcomeKind.UNCERTAIN

    def test_client_errors_are_definite(self) -> None:
        out = classify_buy_response("a1b2", 400, '{"message": "Gift is not for sale"}')
        assert out.kind is BuyOutcomeKind.REJECTED and "not for sale" in out.reason
        assert classify_buy_response("a1b2", 401, "").kind is BuyOutcomeKind.REJECTED
        assert classify_buy_response("a1b2", 429, "").kind is BuyOutcomeKind.REJECTED


class TestMrktClient:
    async def test_saling_request_and_headers(self, server: FakeServer) -> None:
        server.add("POST", API + "gifts/saling", Reply(body={"gifts": [GIFT], "cursor": "c2"}))
        client = await mrkt_client(server)
        try:
            listings, cursor = await client.search_listings(SalingQuery(collection_names=["Plush Pepe"]))
        finally:
            await client.close()
        assert cursor == "c2" and listings[0].gift_id == "a1b2"
        call = server.calls("POST", API + "gifts/saling")[0]
        assert call.headers["Authorization"] == "test-token"
        assert call.headers["Referer"] == "https://cdn.tgmrkt.io/"
        assert call.json["collectionNames"] == ["Plush Pepe"] and call.json["count"] == 20
        assert "minPrice" not in call.json  # unit is not documented consistently -> prices filtered locally

    async def test_bearer_format(self, server: FakeServer) -> None:
        server.add("GET", API + "balance", Reply(body={"hard": 5 * TON}))
        client = await mrkt_client(server, mrkt_auth_header_format="bearer")
        try:
            assert await client.balance_nano() == 5 * TON
        finally:
            await client.close()
        assert server.calls("GET", API + "balance")[0].headers["Authorization"] == "Bearer test-token"

    async def test_retry_on_429_then_success(self, server: FakeServer) -> None:
        server.add(
            "POST",
            API + "feed",
            Reply(status=429, headers={"Retry-After": "0"}),
            Reply(body={"items": [{"type": "listing", "id": "e1", "gift": GIFT, "amount": 1}]}),
        )
        client = await mrkt_client(server)
        try:
            events, _ = await client.feed()
        finally:
            await client.close()
        assert [e.event_id for e in events] == ["e1"]
        calls = server.calls("POST", API + "feed")
        assert len(calls) == 2
        # MRKT answers HTTP 400 to a "change_price" type filter: every type is requested
        assert calls[-1].json["type"] == []

    async def test_feed_type_names_are_normalized(self, server: FakeServer) -> None:
        items = [
            {"type": "change_price", "id": "e1", "gift": GIFT, "amount": 1},
            {"type": "ChangePrice", "id": "e2", "gift": GIFT, "amount": 1},
            {"type": "Listing", "id": "e3", "gift": GIFT, "amount": 1},
        ]
        server.add("POST", API + "feed", Reply(body={"items": items}))
        client = await mrkt_client(server)
        try:
            events, _ = await client.feed()
        finally:
            await client.close()
        assert [e.type for e in events] == ["change_price", "change_price", "listing"]

    async def test_401_raises_auth_error(self, server: FakeServer) -> None:
        server.add("GET", API + "me", Reply(status=401))
        client = await mrkt_client(server)
        try:
            with pytest.raises(MrktAuthError):
                await client.me()
        finally:
            await client.close()

    async def test_get_gift_404_is_none(self, server: FakeServer) -> None:
        server.add("GET", API + "gifts/gift/a1b2", Reply(status=404))
        client = await mrkt_client(server)
        try:
            assert await client.get_gift("a1b2") is None
        finally:
            await client.close()

    async def test_buy_is_never_retried_on_server_error(self, server: FakeServer) -> None:
        server.add("POST", API + "gifts/buy", Reply(status=502, body={"error": "bad gateway"}))
        client = await mrkt_client(server)
        try:
            out = await client.buy("a1b2")
        finally:
            await client.close()
        assert out.kind is BuyOutcomeKind.UNCERTAIN
        calls = server.calls("POST", API + "gifts/buy")
        assert len(calls) == 1 and calls[0].json == {"ids": ["a1b2"]}

    async def test_buy_confirmed(self, server: FakeServer) -> None:
        server.add("POST", API + "gifts/buy", Reply(body=[{"userGift": GIFT, "price": 12 * TON}]))
        client = await mrkt_client(server)
        try:
            out = await client.buy("a1b2")
        finally:
            await client.close()
        assert out.kind is BuyOutcomeKind.CONFIRMED and out.price_nano == 12 * TON

    async def test_buy_timeout_is_uncertain(self, server: FakeServer) -> None:
        server.add("POST", API + "gifts/buy", Reply(body=[], delay=1.0))
        client = await mrkt_client(server, mrkt_buy_timeout_seconds=0.2)
        try:
            out = await client.buy("a1b2")
        finally:
            await client.close()
        assert out.kind is BuyOutcomeKind.UNCERTAIN

    async def test_buy_server_disconnect_is_uncertain(self, server: FakeServer) -> None:
        server.add("POST", API + "gifts/buy", Reply(disconnect=True))
        client = await mrkt_client(server)
        try:
            out = await client.buy("a1b2")
        finally:
            await client.close()
        assert out.kind is BuyOutcomeKind.UNCERTAIN

    async def test_buy_connection_refused_is_definitely_not_sent(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        client = MrktClient(make_settings(mrkt_api_base_url=f"http://127.0.0.1:{port}/api/v1"))
        await client.start()
        try:
            out = await client.buy("a1b2")
        finally:
            await client.close()
        assert out.kind is BuyOutcomeKind.REJECTED and "не отправлен" in out.reason

    async def test_auth_via_init_data(self, server: FakeServer) -> None:
        server.add("POST", API + "auth", Reply(body={"token": "fresh"}))
        server.add("GET", API + "me", Reply(body={"id": 1}))
        client = await mrkt_client(server, mrkt_access_token=None, mrkt_init_data="query_id=1&user=2")
        try:
            assert await client.me() == {"id": 1}
        finally:
            await client.close()
        assert server.calls("POST", API + "auth")[0].json == {"data": "query_id=1&user=2"}
        assert server.calls("GET", API + "me")[0].headers["Authorization"] == "fresh"


async def gw_client(server: FakeServer) -> GiftWikiClient:
    client = GiftWikiClient(make_settings(giftwiki_api_base_url=server.url))
    await client.start()
    return client


class TestGiftWikiClient:
    async def test_api_key_header_and_record_parsing(self, server: FakeServer) -> None:
        server.add("GET", GW, Reply(body=[gw_record(1)]))
        client = await gw_client(server)
        try:
            records = await client.list_monochromes(1)
        finally:
            await client.close()
        call = server.calls("GET", GW)[0]
        assert call.headers["X-API-Key"] == "gw-key"
        assert ("page", "1") in call.query
        rec = records[0]
        assert (rec.record_id, rec.gift_name, rec.model_name, rec.backdrop_name, rec.type_raw) == (
            "id1",
            "Plush Pepe",
            "Onyx",
            "Black",
            "high",
        )
        assert rec.raw["future_field"] == 1  # undocumented fields are kept, not interpreted

    async def test_pagination_stops_on_short_page(self, server: FakeServer) -> None:
        server.add(
            "GET",
            GW,
            Reply(body=[gw_record(i) for i in range(21)]),
            Reply(body=[gw_record(100 + i) for i in range(3)]),
        )
        client = await gw_client(server)
        try:
            pages = [(p, len(r)) async for p, r in client.iter_all_pages(max_pages=10)]
        finally:
            await client.close()
        assert pages == [(1, 21), (2, 3)]
        assert [dict(c.query)["page"] for c in server.calls("GET", GW)] == ["1", "2"]

    async def test_gift_lookup_sends_gift_name_without_page(self, server: FakeServer) -> None:
        server.add("GET", GW, Reply(body=[gw_record(1), gw_record(2, backdrop="Gray", kind="low")]))
        client = await gw_client(server)
        try:
            records = await client.monochromes_for_gift(gift_name="Plush Pepe", types=["high", "low"])
        finally:
            await client.close()
        query = server.calls("GET", GW)[0].query
        assert ("gift_name", "Plush Pepe") in query and ("type", "high,low") in query
        assert not any(k == "page" for k, _ in query)
        assert len(records) == 2

    async def test_errors(self, server: FakeServer) -> None:
        client = await gw_client(server)
        try:
            server.add("GET", GW, Reply(status=401, body={"error": "bad key"}))
            with pytest.raises(GiftWikiAuthError, match="bad key"):
                await client.list_monochromes(1)
            server.replies.clear()
            server.add("GET", GW, Reply(status=403, body={"error": "Bearer app users cannot use lookups"}))
            with pytest.raises(GiftWikiForbiddenError):
                await client.monochromes_for_gift(gift_name="x")
            server.replies.clear()
            server.add("GET", GW, Reply(body={"not": "a list"}))
            with pytest.raises(GiftWikiError):
                await client.list_monochromes(1)
        finally:
            await client.close()

    async def test_malformed_records_skipped(self, server: FakeServer) -> None:
        server.add("GET", GW, Reply(body=[gw_record(1), {"gift_name": "no id"}, "junk"]))
        client = await gw_client(server)
        try:
            records = await client.list_monochromes(1)
        finally:
            await client.close()
        assert [r.record_id for r in records] == ["id1"]
        assert client.invalid_records == 2

    async def test_429_retry(self, server: FakeServer) -> None:
        server.add("GET", GW, Reply(status=429, headers={"Retry-After": "0"}), Reply(body=[gw_record(1)]))
        client = await gw_client(server)
        try:
            assert len(await client.list_monochromes(1)) == 1
        finally:
            await client.close()

    async def test_missing_key_is_auth_error(self, server: FakeServer) -> None:
        client = GiftWikiClient(make_settings(giftwiki_api_base_url=server.url, giftwiki_api_key=None))
        await client.start()
        try:
            with pytest.raises(GiftWikiAuthError):
                await client.list_monochromes(1)
        finally:
            await client.close()
