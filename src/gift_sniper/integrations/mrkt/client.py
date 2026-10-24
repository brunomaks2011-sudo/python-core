"""Client for the MRKT Mini App API (https://api.tgmrkt.io/api/v1).

There is no official public MRKT API. Only endpoints described consistently by community
documentation are used (boostNT/MRKT-API, aiofake/tgmrkt, amrkt); see docs/DATA_SOURCES.md.

Safety rules implemented here:
* idempotent requests (reads) are retried on 429/5xx/network errors with backoff;
* `buy` is NEVER retried automatically. Its outcome is classified as CONFIRMED, REJECTED
  (the request provably did not execute) or UNCERTAIN (must be verified before any retry).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import quote

import aiohttp

from gift_sniper.config import Settings
from gift_sniper.domain.types import FeedEvent, ListingSnapshot
from gift_sniper.integrations.http import (
    AsyncRateLimiter,
    backoff_delay,
    make_session,
    request_not_sent,
    retry_after_seconds,
)
from gift_sniper.integrations.mrkt.parsing import _int, parse_feed_item, parse_gift
from gift_sniper.metrics import EXTERNAL_LATENCY, EXTERNAL_REQUESTS, Timer

log = logging.getLogger(__name__)


def _first(item: dict[str, Any], *keys: str) -> Any:
    """Value of the first key that is present and not null."""
    return next((item[k] for k in keys if item.get(k) is not None), None)


SERVICE = "mrkt"
MAX_PAGE_SIZE = 20  # documented limit of gifts/saling


class MrktError(Exception):
    pass


class MrktAuthError(MrktError):
    pass


class MrktHTTPError(MrktError):
    def __init__(self, status: int, body: str, endpoint: str) -> None:
        super().__init__(f"MRKT {endpoint} HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body
        self.endpoint = endpoint


class MrktUnavailable(MrktError):
    pass


class BuyOutcomeKind(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"  # definitely not executed
    UNCERTAIN = "uncertain"  # may or may not have been executed


@dataclass(slots=True)
class BuyOutcome:
    kind: BuyOutcomeKind
    reason: str
    price_nano: int | None = None
    http_status: int | None = None
    response: Any = None
    purchased: ListingSnapshot | None = None


@dataclass(slots=True)
class SalingQuery:
    collection_names: list[str] = field(default_factory=list)
    model_names: list[str] = field(default_factory=list)
    backdrop_names: list[str] = field(default_factory=list)
    symbol_names: list[str] = field(default_factory=list)
    ordering: str = "Price"  # Price | ModelRarity | BackgroundRarity | SymbolRarity | None (listing time)
    low_to_high: bool = True
    count: int = MAX_PAGE_SIZE
    cursor: str = ""

    def payload(self) -> dict[str, Any]:
        # Price bounds are intentionally not sent: their unit is not documented consistently,
        # prices are filtered locally instead.
        return {
            "collectionNames": self.collection_names,
            "modelNames": self.model_names,
            "backdropNames": self.backdrop_names,
            "symbolNames": self.symbol_names,
            "ordering": self.ordering,
            "lowToHigh": self.low_to_high,
            "count": min(MAX_PAGE_SIZE, max(1, self.count)),
            "cursor": self.cursor,
        }


@dataclass(slots=True)
class MrktCollection:
    name: str
    title: str | None
    floor_price_nano: int | None


@dataclass(frozen=True, slots=True)
class MrktAttribute:
    """A model or backdrop of a collection as listed by MRKT (POST gifts/models | gifts/backdrops)."""

    name: str
    rarity_permille: int | None = None
    floor_price_nano: int | None = None


class MrktClient:
    def __init__(self, settings: Settings, session: aiohttp.ClientSession | None = None) -> None:
        self.settings = settings
        self.base_url = settings.mrkt_api_base_url.rstrip("/") + "/"
        self._session = session
        self._own_session = session is None
        self._token: str | None = (
            settings.mrkt_access_token.get_secret_value() if settings.mrkt_access_token else None
        )
        self._auth_lock = asyncio.Lock()
        self._last_auth_attempt: float | None = None
        self.limiter = AsyncRateLimiter(settings.mrkt_requests_per_second)
        self.priority_limiter = AsyncRateLimiter(settings.mrkt_priority_requests_per_second)
        self.last_auth_error: str | None = None

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if self._session is None:
            self._session = make_session(self.settings.mrkt_request_timeout_seconds)

    async def close(self) -> None:
        if self._session is not None and self._own_session:
            await self._session.close()
        self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("MrktClient.start() was not called")
        return self._session

    @property
    def configured(self) -> bool:
        return bool(self._token or self.can_reauthenticate)

    @property
    def can_reauthenticate(self) -> bool:
        """A new token can be obtained without the operator: initData or a saved Telegram session."""
        return bool(self.settings.mrkt_init_data or self.settings.mrkt_session_available)

    @property
    def token(self) -> str | None:
        return self._token

    # ------------------------------------------------------------------ auth
    def _auth_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Referer": self.settings.mrkt_referer,
            "Origin": self.settings.mrkt_referer.rstrip("/"),
        }
        if self._token:
            value = self._token if self.settings.mrkt_auth_header_format == "raw" else f"Bearer {self._token}"
            headers["Authorization"] = value
        return headers

    async def _obtain_init_data(self) -> str:
        if self.settings.mrkt_init_data:
            return self.settings.mrkt_init_data.get_secret_value()
        if self.settings.mrkt_session_available:
            from gift_sniper.integrations.mrkt.telegram_auth import fetch_init_data

            assert self.settings.telegram_api_id and self.settings.telegram_api_hash
            try:
                return await fetch_init_data(
                    api_id=self.settings.telegram_api_id,
                    api_hash=self.settings.telegram_api_hash.get_secret_value(),
                    session_path=self.settings.mrkt_telegram_session,
                    interactive=False,
                )
            except Exception as exc:  # Telegram RPC/network errors, revoked session, ...
                raise MrktAuthError(f"Не удалось открыть MRKT через Telegram-сессию: {exc}") from exc
        raise MrktAuthError(
            "Нет токена MRKT: задайте MRKT_ACCESS_TOKEN или выполните `python -m gift_sniper mrkt-login`"
        )

    async def obtain_token(self) -> str:
        """Force a new token (used by `mrkt-login`)."""
        self._last_auth_attempt = None
        await self._authenticate(stale_token=self._token)
        assert self._token is not None
        return self._token

    async def _authenticate(self, stale_token: str | None = None) -> None:
        async with self._auth_lock:
            if self._token and self._token != stale_token:
                return  # another task has already refreshed the token
            now = time.monotonic()
            cooldown = self.settings.mrkt_auth_cooldown_seconds
            if self._last_auth_attempt is not None and now - self._last_auth_attempt < cooldown:
                wait = cooldown - (now - self._last_auth_attempt)
                raise MrktAuthError(f"Повторная авторизация MRKT возможна через {wait:.0f} с")
            self._last_auth_attempt = now
            init_data = await self._obtain_init_data()
            timer = Timer()
            try:
                async with self.session.post(
                    self.base_url + "auth",
                    json={"data": init_data},
                    headers={"Content-Type": "application/json", "Referer": self.settings.mrkt_referer},
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        EXTERNAL_REQUESTS.labels(SERVICE, "auth", str(resp.status)).inc()
                        raise MrktAuthError(f"MRKT auth failed: HTTP {resp.status}")
                    data = await resp.json(content_type=None)
            finally:
                EXTERNAL_LATENCY.labels(SERVICE, "auth").observe(timer.elapsed)
            token = data.get("token") if isinstance(data, dict) else None
            if not token:
                raise MrktAuthError(f"MRKT auth response has no token: {text[:120]}")
            EXTERNAL_REQUESTS.labels(SERVICE, "auth", "ok").inc()
            self._token = str(token)
            self.last_auth_error = None

    async def _ensure_token(self) -> None:
        if not self._token:
            await self._authenticate()

    # ------------------------------------------------------------------ transport
    async def _request(
        self,
        method: str,
        path: str,
        *,
        endpoint: str,
        payload: Any = None,
        priority: bool = False,
        max_retries: int = 3,
        allow_404: bool = False,
    ) -> Any:
        """Idempotent request with retries. Not used for purchases."""
        await self._ensure_token()
        reauthenticated = False
        attempt = 0
        while True:
            await (self.priority_limiter if priority else self.limiter).acquire()
            timer = Timer()
            used_token = self._token
            try:
                async with self.session.request(
                    method, self.base_url + path, json=payload, headers=self._auth_headers()
                ) as resp:
                    body = await resp.text()
                    status = resp.status
                    headers = resp.headers
            except (aiohttp.ClientError, TimeoutError) as exc:
                EXTERNAL_REQUESTS.labels(SERVICE, endpoint, "network_error").inc()
                if attempt >= max_retries:
                    raise MrktUnavailable(f"MRKT {endpoint}: {type(exc).__name__}: {exc}") from exc
                await asyncio.sleep(backoff_delay(attempt))
                attempt += 1
                continue
            finally:
                EXTERNAL_LATENCY.labels(SERVICE, endpoint).observe(timer.elapsed)

            EXTERNAL_REQUESTS.labels(SERVICE, endpoint, str(status)).inc()
            if status == 401:
                if not reauthenticated and self.can_reauthenticate:
                    await self._authenticate(stale_token=used_token)
                    reauthenticated = True
                    continue
                self.last_auth_error = f"HTTP 401 on {endpoint}"
                raise MrktAuthError(
                    "MRKT отклонил токен (HTTP 401): обновите MRKT_ACCESS_TOKEN или выполните mrkt-login"
                )
            if status == 404 and allow_404:
                return None
            if status == 429 or status >= 500:
                delay = retry_after_seconds(headers) if status == 429 else backoff_delay(attempt)
                if status == 429:
                    self.limiter.pause(delay)
                    self.priority_limiter.pause(delay)
                if attempt >= max_retries:
                    raise MrktHTTPError(status, body, endpoint)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            if status >= 400:
                raise MrktHTTPError(status, body, endpoint)
            if not body:
                return None
            try:
                return json.loads(body)
            except ValueError as exc:
                raise MrktError(f"MRKT {endpoint}: response is not JSON") from exc

    # ------------------------------------------------------------------ reads
    async def search_listings(self, query: SalingQuery) -> tuple[list[ListingSnapshot], str | None]:
        data = await self._request("POST", "gifts/saling", endpoint="gifts/saling", payload=query.payload())
        fetched_at = datetime.now(UTC)
        gifts = data.get("gifts") if isinstance(data, dict) else None
        listings = [g for g in (parse_gift(item, fetched_at) for item in (gifts or [])) if g is not None]
        cursor = data.get("cursor") if isinstance(data, dict) else None
        return listings, (str(cursor) if cursor else None)

    async def feed(self, *, count: int = 20, cursor: str = "") -> tuple[list[FeedEvent], str | None]:
        """Latest market events of every type; callers keep the types they need.

        MRKT rejects "change_price" as a `type` filter (HTTP 400, FeedItemType) although the community
        clients document it and MRKT reports that type in feed items, so no server-side type filter is sent.
        """
        payload = {
            "count": count,
            "cursor": cursor,
            "collectionNames": [],
            "modelNames": [],
            "backdropNames": [],
            "type": [],
            "ordering": "Latest",
            "lowToHigh": False,
        }
        data = await self._request("POST", "feed", endpoint="feed", payload=payload)
        fetched_at = datetime.now(UTC)
        items = data.get("items") if isinstance(data, dict) else data if isinstance(data, list) else None
        events = [e for e in (parse_feed_item(item, fetched_at) for item in (items or [])) if e is not None]
        next_cursor = data.get("cursor") if isinstance(data, dict) else None
        return events, (str(next_cursor) if next_cursor else None)

    async def get_gift(self, gift_id: str, *, priority: bool = True) -> ListingSnapshot | None:
        data = await self._request(
            "GET",
            f"gifts/gift/{quote(gift_id, safe='')}",
            endpoint="gifts/gift",
            priority=priority,
            max_retries=1,
            allow_404=True,
        )
        return parse_gift(data, datetime.now(UTC)) if data is not None else None

    async def find_in_inventory(self, collection_name: str, number: int) -> list[ListingSnapshot]:
        payload = {
            "count": 20,
            "cursor": "",
            "collectionNames": [collection_name],
            "modelNames": [],
            "backdropNames": [],
            "symbolNames": [],
            "number": number,
            "ordering": "None",
            "lowToHigh": False,
        }
        data = await self._request(
            "POST", "gifts", endpoint="gifts/inventory", payload=payload, priority=True
        )
        gifts = data.get("gifts") if isinstance(data, dict) else None
        fetched_at = datetime.now(UTC)
        return [g for g in (parse_gift(item, fetched_at) for item in (gifts or [])) if g is not None]

    async def balance_nano(self) -> int | None:
        data = await self._request("GET", "balance", endpoint="balance", priority=True, max_retries=1)
        if isinstance(data, dict):
            nested = data.get("balance")
            source = nested if isinstance(nested, dict) else data
            return _int(source.get("hard"))
        return None

    async def collections(self) -> list[MrktCollection]:
        data = await self._request("GET", "gifts/collections", endpoint="gifts/collections")
        result: list[MrktCollection] = []
        for item in data or []:
            if isinstance(item, dict) and item.get("name"):
                result.append(
                    MrktCollection(
                        name=str(item["name"]),
                        title=str(item["title"]) if item.get("title") else None,
                        floor_price_nano=_int(item.get("floorPriceNanoTons")),
                    )
                )
        return result

    async def collection_attributes(self, kind: str, collection_name: str) -> list[MrktAttribute]:
        """Models (kind="model") or backdrops (kind="backdrop") of a collection.

        The request comes from tgmrkts (`POST gifts/models | gifts/backdrops {"collections": [...]}`), which does
        not document the response fields. Items are read with the field names MRKT uses in gift objects
        (`modelName`, `modelRarityPerMille`, ...) and collections (`floorPriceNanoTons`); anything else gives an
        empty list, and callers fall back to what the monitor has observed.
        """
        if kind not in ("model", "backdrop"):
            raise ValueError(f"unknown attribute kind: {kind}")
        endpoint = f"gifts/{kind}s"
        data = await self._request(
            "POST", endpoint, endpoint=endpoint, payload={"collections": [collection_name]}, max_retries=1
        )
        items = data.get(f"{kind}s") if isinstance(data, dict) else data
        result: list[MrktAttribute] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            name = _first(item, f"{kind}Name", "name")
            if name is None or not str(name).strip():
                continue
            result.append(
                MrktAttribute(
                    name=str(name).strip(),
                    rarity_permille=_int(_first(item, f"{kind}RarityPerMille", "rarityPerMille")),
                    floor_price_nano=_int(_first(item, "floorPriceNanoTons", "floorPriceNanoTONs")),
                )
            )
        if not result and data:
            sample = items[0] if isinstance(items, list) and items else data
            keys = sorted(sample)[:20] if isinstance(sample, dict) else type(sample).__name__
            log.warning("MRKT %s: unrecognized response shape", endpoint, extra={"keys": keys})
        return result

    async def me(self) -> dict[str, Any] | None:
        data = await self._request("GET", "me", endpoint="me", max_retries=1)
        return data if isinstance(data, dict) else None

    # ------------------------------------------------------------------ purchase
    async def buy(self, gift_id: str) -> BuyOutcome:
        """Single purchase request. Never retried here; the caller verifies uncertain outcomes."""
        try:
            await self._ensure_token()
        except MrktAuthError as exc:
            return BuyOutcome(BuyOutcomeKind.REJECTED, f"Нет авторизации MRKT: {exc}")
        await self.priority_limiter.acquire()
        timer = Timer()
        try:
            async with self.session.post(
                self.base_url + "gifts/buy",
                json={"ids": [gift_id]},
                headers=self._auth_headers(),
                timeout=aiohttp.ClientTimeout(total=self.settings.mrkt_buy_timeout_seconds),
            ) as resp:
                status = resp.status
                body = await resp.text()
        except Exception as exc:
            EXTERNAL_LATENCY.labels(SERVICE, "gifts/buy").observe(timer.elapsed)
            if request_not_sent(exc):
                EXTERNAL_REQUESTS.labels(SERVICE, "gifts/buy", "not_sent").inc()
                return BuyOutcome(
                    BuyOutcomeKind.REJECTED, f"Соединение не установлено, запрос не отправлен: {exc}"
                )
            EXTERNAL_REQUESTS.labels(SERVICE, "gifts/buy", "uncertain").inc()
            return BuyOutcome(
                BuyOutcomeKind.UNCERTAIN,
                f"Сетевая ошибка после отправки запроса: {type(exc).__name__}: {exc}",
            )
        EXTERNAL_LATENCY.labels(SERVICE, "gifts/buy").observe(timer.elapsed)
        EXTERNAL_REQUESTS.labels(SERVICE, "gifts/buy", str(status)).inc()
        return classify_buy_response(gift_id, status, body)


def classify_buy_response(gift_id: str, status: int, body: str) -> BuyOutcome:
    parsed: Any = None
    if body:
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
    short = body[:300] if body else ""
    if 200 <= status < 300:
        entries = parsed if isinstance(parsed, list) else None
        if not entries:
            return BuyOutcome(
                BuyOutcomeKind.UNCERTAIN,
                "MRKT ответил успехом, но без данных о покупке",
                http_status=status,
                response=parsed if parsed is not None else short,
            )
        chosen: dict[str, Any] | None = None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            user_gift = parse_gift(entry.get("userGift"))
            if user_gift is not None and user_gift.gift_id == gift_id:
                chosen = entry
                break
            chosen = chosen or entry
        if chosen is None:
            return BuyOutcome(
                BuyOutcomeKind.UNCERTAIN, "Ответ MRKT не распознан", http_status=status, response=parsed
            )
        purchased = parse_gift(chosen.get("userGift"))
        return BuyOutcome(
            BuyOutcomeKind.CONFIRMED,
            "MRKT подтвердил покупку",
            price_nano=_int(chosen.get("price")),
            http_status=status,
            response=parsed,
            purchased=purchased,
        )
    if status in (408, 425) or status >= 500:
        return BuyOutcome(
            BuyOutcomeKind.UNCERTAIN,
            f"MRKT вернул HTTP {status}",
            http_status=status,
            response=parsed or short,
        )
    if status == 401:
        return BuyOutcome(
            BuyOutcomeKind.REJECTED,
            "MRKT отклонил токен (HTTP 401)",
            http_status=status,
            response=parsed or short,
        )
    if status == 429:
        return BuyOutcome(
            BuyOutcomeKind.REJECTED, "MRKT ограничил частоту запросов (HTTP 429)", http_status=status
        )
    message = None
    if isinstance(parsed, dict):
        message = parsed.get("message") or parsed.get("error") or parsed.get("title")
    return BuyOutcome(
        BuyOutcomeKind.REJECTED,
        f"MRKT отказал (HTTP {status}){': ' + str(message) if message else ''}",
        http_status=status,
        response=parsed or short,
    )
