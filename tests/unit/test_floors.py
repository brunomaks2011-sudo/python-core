"""MRKT floors for floor-priced picks: the listing itself and auction lots never set the floor."""

from __future__ import annotations

from gift_sniper.domain.types import ListingSnapshot
from gift_sniper.integrations.mrkt import MrktError
from gift_sniper.integrations.mrkt.client import SalingQuery
from gift_sniper.services.filters import PriceRule
from gift_sniper.services.floors import FloorService
from tests.factories import TON, make_enrichment, make_listing


class Market:
    """gifts/saling stand-in: listings of the queried collection and model, cheapest first."""

    def __init__(self, listings: list[ListingSnapshot], *, down: bool = False) -> None:
        self.listings = listings
        self.down = down
        self.queries: list[SalingQuery] = []

    async def search_listings(self, query: SalingQuery) -> tuple[list[ListingSnapshot], str | None]:
        self.queries.append(query)
        if self.down:
            raise MrktError("MRKT is down")
        found = [
            item
            for item in self.listings
            if item.collection_name in query.collection_names
            and (not query.model_names or item.model_name in query.model_names)
        ]
        return sorted(found, key=lambda item: item.price_nano or 0)[: query.count], None


JUDGED = make_listing("mono", model_name="Onyx", price_nano=5 * TON)
MARKET = [
    JUDGED,  # the cheapest Onyx is the listing being judged itself
    make_listing("other-onyx", model_name="Onyx", price_nano=7 * TON),
    make_listing("auction-onyx", model_name="Onyx", price_nano=TON, is_on_auction=True),
    make_listing("ivory", model_name="Ivory", price_nano=3 * TON),
    make_listing("elsewhere", collection_name="Lol Pop", model_name="Onyx", price_nano=TON),
]


async def test_floors_leave_out_the_listing_itself_and_auctions() -> None:
    floors = FloorService(Market(MARKET))
    assert await floors.floor(JUDGED, PriceRule.MODEL_FLOOR) == 7 * TON
    assert await floors.floor(JUDGED, PriceRule.COLLECTION_FLOOR) == 3 * TON
    enriched = await floors.with_floors(JUDGED, make_enrichment(), {PriceRule.MODEL_FLOOR})
    assert (enriched.model_floor_nano, enriched.collection_floor_nano) == (7 * TON, None)
    assert await floors.with_floors(JUDGED, make_enrichment(), set()) == make_enrichment()


async def test_no_other_listing_or_no_answer_means_no_floor() -> None:
    alone = FloorService(Market([JUDGED]))
    assert await alone.floor(JUDGED, PriceRule.MODEL_FLOOR) is None
    down = FloorService(Market(MARKET, down=True))
    assert await down.floor(JUDGED, PriceRule.COLLECTION_FLOOR) is None


async def test_floors_are_cached_for_a_few_seconds() -> None:
    market = Market(MARKET)
    floors = FloorService(market)
    await floors.floor(JUDGED, PriceRule.MODEL_FLOOR)
    other = make_listing("next-mono", model_name="Onyx", price_nano=6 * TON)
    assert await floors.floor(other, PriceRule.MODEL_FLOOR) == 5 * TON  # the first listing is "other" now
    assert len(market.queries) == 1
    query = market.queries[0]
    assert (query.collection_names, query.model_names, query.ordering, query.low_to_high) == (
        ["Plush Pepe"],
        ["Onyx"],
        "Price",
        True,
    )
    fresh = FloorService(market, ttl=0)
    await fresh.floor(JUDGED, PriceRule.MODEL_FLOOR)
    await fresh.floor(JUDGED, PriceRule.MODEL_FLOOR)
    assert len(market.queries) == 3
