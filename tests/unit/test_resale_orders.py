"""Resale assistant arithmetic, MRKT orders and selling: parsing, requests, outbid detection."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from gift_sniper.domain.enums import FilterKind
from gift_sniper.domain.types import MrktOrder
from gift_sniper.integrations.mrkt import MrktClient, MrktFormatError, MrktHTTPError
from gift_sniper.integrations.mrkt.parsing import order_items, parse_gift, parse_order
from gift_sniper.services.filters import FilterCriteria, ResaleRules, describe_criteria
from gift_sniper.services.orders import Floor, OrderView, same_attributes
from gift_sniper.services.resale import CENT, ResalePlan, buyer_price_for, fee_permille, list_price_for
from tests.factories import TON, make_settings
from tests.fake_server import FakeServer, Reply

API = "/api/v1/"


def order(order_id: str, price: int, **kw: object) -> MrktOrder:
    values: dict[str, object] = {
        "collection_name": "Plush Pepe",
        "model_name": "Onyx",
        "backdrop_name": None,
        "symbol_name": None,
    }
    values.update(kw)
    return MrktOrder(order_id=order_id, price_nano=price, **values)  # type: ignore[arg-type]


class TestFeeArithmetic:
    def test_list_price_leaves_buyers_at_the_value_with_the_fee(self) -> None:
        # buyers pay list × 1.02: 13.10 TON / 1.02 = 12.8431… → 12.84 TON (down to 0.01 TON)
        assert list_price_for(13_100_000_000, fee_permille(2.0)) == 12_840_000_000
        assert buyer_price_for(12_840_000_000, 20) == 13_096_800_000
        assert buyer_price_for(list_price_for(13_100_000_000, 20), 20) <= 13_100_000_000

    def test_rounding_is_always_down_to_a_cent(self) -> None:
        for buyer in (1 * TON, 3_333_333_333, 99_990_000_000):
            price = list_price_for(buyer, 20)
            assert price % CENT == 0 and buyer_price_for(price, 20) <= buyer

    def test_fee_permille(self) -> None:
        assert fee_permille(2.0) == 20 and fee_permille(2.5) == 25 and fee_permille(0) == 0


class TestResalePlan:
    def plan(self, **kw: object) -> ResalePlan:
        values: dict[str, object] = {
            "gift_id": "g1",
            "buy_price_nano": 12 * TON,
            "fee_permille": 20,
            "period_days": 7,
            "min_sales": 3,
            "min_profit_nano": 300_000_000,
            "picture_sales": 4,
            "picture_median_nano": 13_100_000_000,
            "model_sales": 9,
            "model_median_nano": 12_500_000_000,
            "basis": "picture",
            "target_nano": 13_100_000_000,
            "list_price_nano": 12_840_000_000,
            "profit_nano": 840_000_000,
        }
        values.update(kw)
        return ResalePlan(**values)  # type: ignore[arg-type]

    def test_ok_needs_the_profit_and_no_reason(self) -> None:
        assert self.plan().ok
        assert not self.plan(profit_nano=200_000_000).ok
        assert not self.plan(reason="мало продаж").ok

    def test_round_trip_and_new_price(self) -> None:
        plan = self.plan()
        again = ResalePlan.from_dict(plan.to_dict() | {"unknown": 1})
        assert again == plan
        assert ResalePlan.from_dict("broken") is None
        cheaper = plan.at_price(12_500_000_000)
        assert cheaper.profit_nano == 340_000_000 and cheaper.buy_price_nano == 12_500_000_000
        assert plan.sales_count == 4 and self.plan(basis="model").sales_count == 9

    def test_lines_explain_the_decision(self) -> None:
        text = "\n".join(
            self.plan(competitor_nano=13_500_000_000, gift_sales=1, gift_median_nano=11 * TON).lines()
        )
        assert "модель + фон — 4 (медиана 13.1 TON)" in text and "вся модель — 9" in text
        assert "Этот подарок продавался 1 раз(а)" in text and "дешевле всего: 13.5 TON" in text
        assert (
            "Выставить за 12.84 TON" in text and "увидят 13.0968 TON" in text and "комиссией MRKT 2%" in text
        )
        assert "Профит: 0.84 TON" in text

    def test_rules_in_the_filter_summary(self) -> None:
        lines = describe_criteria(FilterKind.REGULAR, FilterCriteria(resale=ResaleRules()))
        assert any("Перекуп: профит от 0.3 TON после комиссии 2%" in line for line in lines)


class TestOrderParsing:
    def test_order_fields_by_the_request_names(self) -> None:
        item = {
            "id": "o1",
            "collectionName": "Plush Pepe",
            "modelName": "Onyx",
            "backdropName": "Black",
            "symbolName": None,
            "priceMaxNanoTONs": 10 * TON,
            "priceMinNanoTONs": 9 * TON,
            "quantity": 2,
            "isMine": True,
        }
        parsed = parse_order(item)
        assert parsed is not None and parsed.order_id == "o1" and parsed.price_nano == 10 * TON
        assert parsed.min_price_nano == 9 * TON and parsed.quantity == 2 and parsed.is_mine is True
        assert parsed.attributes == ("Plush Pepe", "Onyx", "Black", None)

    def test_without_id_or_price_it_is_not_an_order(self) -> None:
        assert parse_order({"collectionName": "Plush Pepe", "priceMaxNanoTONs": TON}) is None
        assert parse_order({"id": "o1"}) is None
        assert parse_order({"id": "o1", "price": 0}) is None
        assert parse_order(["o1"]) is None

    def test_lists_of_orders(self) -> None:
        one = {"orderId": "o2", "priceNanoTONs": TON}
        assert order_items([one]) == [one]
        assert order_items({"orders": [one], "cursor": ""}) == [one]
        assert order_items({"items": []}) == []
        assert order_items(one) == [one]  # orders/top may give the order itself
        assert order_items({"cursor": "x"}) is None
        assert order_items("text") is None

    def test_gift_fee_and_resale_lock_fields(self) -> None:
        gift = parse_gift(
            {
                "id": "a",
                "salePrice": 10_200_000_000,
                "salePriceWithoutFee": 10 * TON,
                "nextResaleDate": "2026-10-27T10:00:00Z",
            }
        )
        assert gift is not None and gift.price_without_fee_nano == 10 * TON
        assert gift.next_resale_at is not None and gift.next_resale_at.day == 27


class TestOrderView:
    def test_outbid_by_a_higher_order_of_someone_else(self) -> None:
        view = OrderView(order("mine", 10 * TON), order("other", 10_500_000_000))
        assert view.outbid and view.next_price_nano == 10_510_000_000
        view.floors = [Floor("модели", 12_300_000_000), Floor("фона", None)]
        text = "\n".join(view.lines())
        assert "Перебили: <b>10.5 TON</b>" in text and "Перебить на 0.01 → <b>10.51 TON</b>" in text
        assert "Флор модели: 12.3 TON — на 1.79 TON выше нового ордера" in text
        assert "Флор фона: нет объявлений" in text
        data = view.to_dict()
        assert data["outbid"] is True and data["next_price_nano"] == 10_510_000_000

    def test_own_or_equal_top_is_not_outbid(self) -> None:
        assert not OrderView(order("mine", 10 * TON), order("mine", 10 * TON)).outbid
        equal = OrderView(order("mine", 10 * TON), order("other", 10 * TON))
        assert not equal.outbid and equal.next_price_nano is None
        assert "Такая же цена у другого ордера" in "\n".join(equal.lines())
        assert not OrderView(order("mine", 10 * TON), None).outbid

    def test_same_attributes_ignores_case_and_spaces(self) -> None:
        assert same_attributes(order("a", TON, model_name="Onyx "), order("b", 2 * TON, model_name="onyx"))
        assert not same_attributes(order("a", TON), order("b", TON, backdrop_name="Black"))


@pytest_asyncio.fixture
async def server() -> AsyncIterator[FakeServer]:
    srv = FakeServer()
    await srv.start()
    yield srv
    await srv.stop()


async def client_for(server: FakeServer) -> MrktClient:
    client = MrktClient(make_settings(mrkt_api_base_url=server.url + "/api/v1"))
    await client.start()
    return client


class TestOrderRequests:
    async def test_my_orders_and_market_orders(self, server: FakeServer) -> None:
        item = {"id": "o1", "collectionName": "Plush Pepe", "priceMaxNanoTONs": 3 * TON}
        server.add("POST", API + "orders/get-my-orders", Reply(body={"orders": [item]}))
        server.add("POST", API + "orders", Reply(body=[item]))
        client = await client_for(server)
        try:
            mine = await client.my_orders()
            market = await client.orders("Plush Pepe", models=["Onyx"])
        finally:
            await client.close()
        assert [o.order_id for o in mine] == ["o1"] and market[0].price_nano == 3 * TON
        sent = server.calls("POST", API + "orders")[0].json
        assert sent["collectionNames"] == ["Plush Pepe"] and sent["modelNames"] == ["Onyx"]
        assert sent["ordering"] == "Price" and sent["lowToHigh"] is False

    async def test_unknown_shape_is_a_format_error(self, server: FakeServer) -> None:
        server.add("POST", API + "orders/get-my-orders", Reply(body={"total": 3}))
        server.add("POST", API + "orders", Reply(body=[{"orderUuid": "x", "amount": 1}]))
        client = await client_for(server)
        try:
            with pytest.raises(MrktFormatError, match="total"):
                await client.my_orders()
            with pytest.raises(MrktFormatError, match="orderUuid"):
                await client.orders("Plush Pepe")
        finally:
            await client.close()

    async def test_top_order(self, server: FakeServer) -> None:
        server.add(
            "POST",
            API + "orders/top",
            Reply(body={"id": "o9", "priceMaxNanoTONs": 5 * TON}),
            Reply(body=None),
        )
        client = await client_for(server)
        try:
            top = await client.top_order("Plush Pepe", "Onyx")
            none = await client.top_order("Plush Pepe", "Onyx")
        finally:
            await client.close()
        assert top is not None and top.order_id == "o9" and none is None
        assert server.calls("POST", API + "orders/top")[0].json == {
            "collectionName": "Plush Pepe",
            "modelName": "Onyx",
            "backdropName": None,
            "symbolName": None,
        }

    async def test_create_and_cancel_are_never_retried(self, server: FakeServer) -> None:
        server.add("POST", API + "orders/create", Reply(status=502, body={}))
        server.add("POST", API + "orders/cancel/o1", Reply(status=503, body={}))
        client = await client_for(server)
        try:
            with pytest.raises(MrktHTTPError):
                await client.create_order(
                    collection="Plush Pepe", model="Onyx", backdrop=None, symbol=None, price_nano=TON
                )
            with pytest.raises(MrktHTTPError):
                await client.cancel_order("o1")
        finally:
            await client.close()
        created = server.calls("POST", API + "orders/create")
        assert len(created) == 1 and created[0].json == {
            "collectionName": "Plush Pepe",
            "modelName": "Onyx",
            "backdropName": None,
            "symbolName": None,
            "priceMinNanoTONs": TON,
            "priceMaxNanoTONs": TON,
            "quantity": 1,
            "isTransferable": False,
        }
        assert len(server.calls("POST", API + "orders/cancel/o1")) == 1

    async def test_list_for_sale_sends_both_documented_payloads_once(self, server: FakeServer) -> None:
        server.add(
            "POST", API + "gifts/sale", Reply(body={"ids": ["a1"], "prices": [TON]}), Reply(status=500)
        )
        client = await client_for(server)
        try:
            assert await client.list_for_sale("a1", TON) == ["a1"]
            with pytest.raises(MrktHTTPError):
                await client.list_for_sale("a1", TON)
        finally:
            await client.close()
        calls = server.calls("POST", API + "gifts/sale")
        assert len(calls) == 2 and calls[0].json == {"ids": ["a1"], "price": TON, "prices": [TON]}
