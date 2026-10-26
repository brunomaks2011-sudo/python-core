"""Lenient parsing of MRKT responses.

Field names come from community documentation (see docs/DATA_SOURCES.md). A missing or malformed value
becomes None. It is never replaced with zero, because "no data" and "0" mean different things.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from gift_sniper.domain.types import FeedEvent, ListingSnapshot, MrktOrder

# MRKT's request validation names feed types as C# enum members (FeedItemType); accept that spelling too
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        seconds = value / 1000 if value > 10**11 else value
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        # .NET may return 7 fractional digits; Python accepts at most 6
        if "." in text:
            head, _, tail = text.partition(".")
            digits = "".join(ch for ch in tail if ch.isdigit())
            rest = tail[len(digits) :]
            text = f"{head}.{digits[:6]}{rest}"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
        return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return None


def parse_gift(data: Any, fetched_at: datetime | None = None) -> ListingSnapshot | None:
    if not isinstance(data, dict):
        return None
    gift_id = _str(data.get("id"))
    if not gift_id:
        return None
    return ListingSnapshot(
        gift_id=gift_id,
        collection_name=_str(data.get("collectionName")),
        collection_title=_str(data.get("collectionTitle")) or _str(data.get("title")),
        name=_str(data.get("name")),
        number=_int(data.get("number")),
        model_name=_str(data.get("modelName")) or _str(data.get("modelTitle")),
        backdrop_name=_str(data.get("backdropName")),
        symbol_name=_str(data.get("symbolName")),
        model_rarity_permille=_int(data.get("modelRarityPerMille")),
        backdrop_rarity_permille=_int(data.get("backdropRarityPerMille")),
        symbol_rarity_permille=_int(data.get("symbolRarityPerMille")),
        price_nano=_int(data.get("salePrice")),
        is_on_sale=_bool(data.get("isOnSale")),
        is_on_auction=_bool(data.get("isOnAuction")),
        is_mine=_bool(data.get("isMine")),
        backdrop_center_color=_int(data.get("backdropColorsCenterColor")),
        backdrop_edge_color=_int(data.get("backdropColorsEdgeColor")),
        backdrop_text_color=_int(data.get("backdropColorsTextColor")),
        backdrop_symbol_color=_int(data.get("backdropColorsSymbolColor")),
        floor_collection_nano=_int(data.get("floorPriceNanoTONsByCollection")),
        floor_model_backdrop_nano=_int(data.get("floorPriceNanoTONsByBackdropModel")),
        price_without_fee_nano=_int(data.get("salePriceWithoutFee")),
        next_resale_at=parse_datetime(data.get("nextResaleDate")),
        fetched_at=fetched_at or datetime.now(UTC),
        raw=data,
    )


def parse_feed_item(data: Any, fetched_at: datetime | None = None) -> FeedEvent | None:
    if not isinstance(data, dict):
        return None
    listing = parse_gift(data.get("gift"), fetched_at)
    event_type = _str(data.get("type"))
    if listing is None or not event_type:
        return None
    amount = _int(data.get("amount"))
    date = parse_datetime(data.get("date"))
    event_id = (
        _str(data.get("id")) or f"{event_type}:{listing.gift_id}:{amount}:{date.isoformat() if date else ''}"
    )
    return FeedEvent(
        event_id=event_id,
        type=_CAMEL_BOUNDARY.sub("_", event_type).lower(),  # "ChangePrice" -> "change_price"
        listing=listing,
        amount_nano=amount,
        date=date,
    )


def _first(item: dict[str, Any], *keys: str) -> Any:
    return next((item[k] for k in keys if item.get(k) is not None), None)


# Orders: tgmrkts documents the requests (orders/create takes priceMinNanoTONs / priceMaxNanoTONs, collectionName,
# modelName, backdropName, symbolName, quantity) but not the responses. An order is read with the names of
# those request fields; one without a recognisable id and price is not an order to the bot.
ORDER_PRICE_KEYS = ("priceMaxNanoTONs", "priceNanoTONs", "price")
ORDER_LIST_KEYS = ("orders", "items", "data", "result")


def parse_order(data: Any) -> MrktOrder | None:
    if not isinstance(data, dict):
        return None
    order_id = _str(_first(data, "id", "orderId"))
    price = _int(_first(data, *ORDER_PRICE_KEYS))
    if not order_id or price is None or price <= 0:
        return None
    return MrktOrder(
        order_id=order_id,
        collection_name=_str(data.get("collectionName")),
        model_name=_str(data.get("modelName")),
        backdrop_name=_str(data.get("backdropName")),
        symbol_name=_str(data.get("symbolName")),
        price_nano=price,
        min_price_nano=_int(data.get("priceMinNanoTONs")),
        quantity=_int(_first(data, "quantity", "count")),
        is_mine=_bool(data.get("isMine")),
        raw=data,
    )


def order_items(data: Any) -> list[Any] | None:
    """The list of orders in a response: a bare list or a list under a common key; None when there is none."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ORDER_LIST_KEYS:
            if isinstance(data.get(key), list):
                return list(data[key])
        if parse_order(data) is not None:  # orders/top may give the order itself
            return [data]
    return None
