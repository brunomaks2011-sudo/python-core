"""MRKT floors for floor-priced picks: the lowest asking price of a collection, or of one model in it.

A floor is read from MRKT's listings sorted by price (POST gifts/saling) at decision time and cached for a
few seconds. The listing being judged is always left out, so its own price never becomes the floor it is
compared with: "up to the model floor" means "not above the cheapest other copy of the model on sale".
Auction lots and listings without a price are not asking prices and are skipped as well.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Protocol

from gift_sniper.domain.normalize import normalize_name
from gift_sniper.domain.types import Enrichment, ListingSnapshot
from gift_sniper.integrations.mrkt import MrktError
from gift_sniper.integrations.mrkt.client import SalingQuery
from gift_sniper.services.filters import PriceRule

log = logging.getLogger(__name__)

DEPTH = 5  # enough to skip the listing itself and a few auction lots


class _Search(Protocol):
    async def search_listings(
        self, query: SalingQuery, *, priority: bool = False
    ) -> tuple[list[ListingSnapshot], str | None]: ...


class FloorService:
    def __init__(self, mrkt: _Search, *, ttl: float = 20.0) -> None:
        self.mrkt = mrkt
        self.ttl = ttl
        self._cache: dict[tuple[str, str, str], tuple[float, list[tuple[str, int]]]] = {}

    async def cheapest(
        self, collection: str, model: str | None = None, backdrop: str | None = None
    ) -> list[tuple[str, int]] | None:
        """(gift id, price) of the cheapest listings, cheapest first; None when MRKT cannot tell."""
        key = (
            normalize_name(collection),
            normalize_name(model) if model else "",
            normalize_name(backdrop) if backdrop else "",
        )
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self.ttl:
            return cached[1]
        query = SalingQuery(
            collection_names=[collection],
            model_names=[model] if model else [],
            backdrop_names=[backdrop] if backdrop else [],
            ordering="Price",
            count=DEPTH,
        )
        try:
            listings, _ = await self.mrkt.search_listings(query, priority=True)  # a purchase may wait on it
        except MrktError as exc:
            log.warning("MRKT floor lookup failed", extra={"collection": collection, "error": str(exc)})
            return None
        cheapest = sorted(
            (
                (item.gift_id, item.price_nano)
                for item in listings
                if item.price_nano is not None and not item.is_on_auction
            ),
            key=lambda item: item[1],
        )
        self._cache[key] = (time.monotonic(), cheapest)
        return cheapest

    async def lowest(
        self,
        collection: str,
        *,
        model: str | None = None,
        backdrop: str | None = None,
        exclude_gift: str | None = None,
    ) -> int | None:
        """The lowest asking price of a collection, model, backdrop or model on a backdrop; None: no data."""
        cheapest = await self.cheapest(collection, model, backdrop)
        return next((price for gift_id, price in cheapest or [] if gift_id != exclude_gift), None)

    async def floor(self, listing: ListingSnapshot, rule: PriceRule) -> int | None:
        if rule is PriceRule.FIXED or not listing.collection_name:
            return None
        if rule is PriceRule.MODEL_FLOOR and not listing.model_name:
            return None
        model = listing.model_name if rule is PriceRule.MODEL_FLOOR else None
        return await self.lowest(listing.collection_name, model=model, exclude_gift=listing.gift_id)

    async def with_floors(
        self, listing: ListingSnapshot, enrichment: Enrichment, rules: set[PriceRule]
    ) -> Enrichment:
        """The enrichment with the floors these rules need (the others stay as they were)."""
        if not rules:
            return enrichment
        collection = enrichment.collection_floor_nano
        model = enrichment.model_floor_nano
        if PriceRule.COLLECTION_FLOOR in rules:
            collection = await self.floor(listing, PriceRule.COLLECTION_FLOOR)
        if PriceRule.MODEL_FLOOR in rules:
            model = await self.floor(listing, PriceRule.MODEL_FLOOR)
        return replace(enrichment, collection_floor_nano=collection, model_floor_nano=model)
