"""Client for the Gift Wiki API (https://api.giftwiki.tg).

Implements only the documented operation GET /gifts/monochromes ("List gift monochrome metadata"):
* auth: header `X-API-Key` (dev API key with collection:read scope);
* `page` selects a page of a fixed 21-item list; `limit` is accepted only for compatibility;
* `gift_id` / `gift_name` return ALL records of the gift and ignore paging (API key only);
* `collection_id`, `model_name`, `backdrop_name`, `type` (low|medium|high|combo) filter the list;
* 200 -> JSON array of records; 401/403 -> {"error": "..."}.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any
from urllib.parse import urlencode

import aiohttp

from gift_sniper.config import Settings
from gift_sniper.domain.types import MonochromeRecord
from gift_sniper.integrations.http import AsyncRateLimiter, backoff_delay, make_session, retry_after_seconds
from gift_sniper.metrics import EXTERNAL_LATENCY, EXTERNAL_REQUESTS, Timer

log = logging.getLogger(__name__)

SERVICE = "giftwiki"
PATH_MONOCHROMES = "/gifts/monochromes"
PAGE_SIZE = 21  # "the public list is fixed at 21 items"


class GiftWikiError(Exception):
    pass


class GiftWikiAuthError(GiftWikiError):
    """HTTP 401: missing or invalid API key."""


class GiftWikiForbiddenError(GiftWikiError):
    """HTTP 403: e.g. bearer app users cannot use gift_id/gift_name lookups."""


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_monochrome_record(item: Any) -> MonochromeRecord | None:
    if not isinstance(item, dict):
        return None
    record_id = _opt_str(item.get("_id"))
    if not record_id:
        return None
    return MonochromeRecord(
        record_id=record_id,
        gift_id=_opt_str(item.get("gift_id")),
        gift_name=_opt_str(item.get("gift_name")),
        model_name=_opt_str(item.get("model_name")),
        backdrop_name=_opt_str(item.get("backdrop_name")),
        type_raw=_opt_str(item.get("type")),
        center_color=_opt_str(item.get("center_color")),
        edge_color=_opt_str(item.get("edge_color")),
        pattern_color=_opt_str(item.get("pattern_color")),
        text_color=_opt_str(item.get("text_color")),
        photo_url=_opt_str(item.get("photo_url")),
        animation_url=_opt_str(item.get("animation_url")),
        raw=item,
    )


class GiftWikiClient:
    def __init__(self, settings: Settings, session: aiohttp.ClientSession | None = None) -> None:
        self.settings = settings
        self.base_url = settings.giftwiki_api_base_url.rstrip("/")
        self._session = session
        self._own_session = session is None
        self.limiter = AsyncRateLimiter(settings.giftwiki_requests_per_second)
        self.invalid_records = 0

    async def start(self) -> None:
        if self._session is None:
            self._session = make_session(self.settings.giftwiki_request_timeout_seconds, limit=4)

    async def close(self) -> None:
        if self._session is not None and self._own_session:
            await self._session.close()
        self._session = None

    @property
    def configured(self) -> bool:
        return self.settings.giftwiki_configured

    def source_url(self, **params: Any) -> str:
        """Human-readable reference to the API query a record came from (no secrets in it)."""
        query = urlencode({k: v for k, v in params.items() if v is not None})
        return f"{self.base_url}{PATH_MONOCHROMES}" + (f"?{query}" if query else "")

    def _headers(self) -> dict[str, str]:
        if not self.settings.giftwiki_api_key:
            raise GiftWikiAuthError("GIFTWIKI_API_KEY is not set")
        return {"X-API-Key": self.settings.giftwiki_api_key.get_secret_value(), "Accept": "application/json"}

    async def _get_records(
        self, params: list[tuple[str, str]], *, max_retries: int = 4
    ) -> list[MonochromeRecord]:
        if self._session is None:
            raise RuntimeError("GiftWikiClient.start() was not called")
        url = self.base_url + PATH_MONOCHROMES
        attempt = 0
        while True:
            await self.limiter.acquire()
            timer = Timer()
            try:
                async with self._session.get(url, params=params, headers=self._headers()) as resp:
                    status = resp.status
                    body = await resp.text()
                    headers = resp.headers
            except (aiohttp.ClientError, TimeoutError) as exc:
                EXTERNAL_REQUESTS.labels(SERVICE, "monochromes", "network_error").inc()
                if attempt >= max_retries:
                    raise GiftWikiError(f"Gift Wiki unavailable: {type(exc).__name__}: {exc}") from exc
                await asyncio.sleep(backoff_delay(attempt, base=1.0, cap=30.0))
                attempt += 1
                continue
            finally:
                EXTERNAL_LATENCY.labels(SERVICE, "monochromes").observe(timer.elapsed)
            EXTERNAL_REQUESTS.labels(SERVICE, "monochromes", str(status)).inc()

            if status == 200:
                try:
                    data = json.loads(body) if body else []
                except ValueError as exc:
                    raise GiftWikiError("Gift Wiki returned a non-JSON body") from exc
                if not isinstance(data, list):
                    raise GiftWikiError(
                        f"Gift Wiki returned {type(data).__name__}, expected an array of records"
                    )
                records = []
                for item in data:
                    record = parse_monochrome_record(item)
                    if record is None:
                        self.invalid_records += 1
                        log.warning("skipping malformed Gift Wiki record", extra={"item": str(item)[:200]})
                        continue
                    records.append(record)
                return records
            error = _error_message(body)
            if status == 401:
                raise GiftWikiAuthError(f"Gift Wiki 401 Unauthorized: {error}")
            if status == 403:
                raise GiftWikiForbiddenError(f"Gift Wiki 403 Forbidden: {error}")
            if status == 429 or status >= 500:
                if attempt >= max_retries:
                    raise GiftWikiError(f"Gift Wiki HTTP {status}: {error}")
                delay = (
                    retry_after_seconds(headers, default=5.0)
                    if status == 429
                    else backoff_delay(attempt, 1.0, 30.0)
                )
                if status == 429:
                    self.limiter.pause(delay)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise GiftWikiError(f"Gift Wiki HTTP {status}: {error}")

    @staticmethod
    def _type_params(types: Iterable[str] | None) -> list[tuple[str, str]]:
        values = [t for t in (types or []) if t]
        return [("type", ",".join(values))] if values else []

    async def list_monochromes(
        self,
        page: int = 1,
        *,
        types: Iterable[str] | None = None,
        model_name: str | None = None,
        backdrop_name: str | None = None,
        collection_id: str | None = None,
    ) -> list[MonochromeRecord]:
        params: list[tuple[str, str]] = [("page", str(max(1, page)))]
        if model_name:
            params.append(("model_name", model_name))
        if backdrop_name:
            params.append(("backdrop_name", backdrop_name))
        if collection_id:
            params.append(("collection_id", collection_id))
        params += self._type_params(types)
        return await self._get_records(params)

    async def monochromes_for_gift(
        self, *, gift_name: str | None = None, gift_id: str | None = None, types: Iterable[str] | None = None
    ) -> list[MonochromeRecord]:
        """All records of one gift (documented: lookups return all matching records, paging ignored)."""
        if not gift_name and not gift_id:
            raise ValueError("gift_name or gift_id is required")
        params: list[tuple[str, str]] = []
        if gift_id:
            params.append(("gift_id", gift_id))
        if gift_name:
            params.append(("gift_name", gift_name))
        params += self._type_params(types)
        return await self._get_records(params)

    async def iter_all_pages(self, max_pages: int) -> AsyncIterator[tuple[int, list[MonochromeRecord]]]:
        """Walk the paginated list until a short page. Yields (page_number, records)."""
        for page in range(1, max_pages + 1):
            records = await self.list_monochromes(page)
            yield page, records
            if len(records) < PAGE_SIZE:
                return


def _error_message(body: str) -> str:
    try:
        data = json.loads(body)
    except ValueError:
        return body[:200]
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return body[:200]
