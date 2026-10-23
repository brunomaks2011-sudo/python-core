"""HTTP helpers shared by the MRKT and Gift Wiki clients."""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import aiohttp

USER_AGENT = "GiftSniperBot/1.0 (aiohttp)"


class AsyncRateLimiter:
    """Token bucket limiter. `pause()` blocks all callers, e.g. after HTTP 429 Retry-After."""

    def __init__(self, rate_per_second: float, burst: int | None = None) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate_per_second
        self.capacity = float(burst if burst is not None else max(1, int(rate_per_second)))
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._blocked_until = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                if now < self._blocked_until:
                    await asyncio.sleep(self._blocked_until - now)
                    continue
                self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self.rate)

    def pause(self, seconds: float) -> None:
        self._blocked_until = max(self._blocked_until, time.monotonic() + max(0.0, seconds))


def retry_after_seconds(headers: object, default: float = 5.0, maximum: float = 300.0) -> float:
    value = None
    if hasattr(headers, "get"):
        value = headers.get("Retry-After")
    if not value:
        return default
    try:
        return min(maximum, max(0.0, float(value)))
    except (TypeError, ValueError):
        pass
    try:
        moment = parsedate_to_datetime(str(value))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return min(maximum, max(0.0, (moment - datetime.now(UTC)).total_seconds()))
    except (TypeError, ValueError):
        return default


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 10.0) -> float:
    """Exponential backoff with full jitter."""
    return random.uniform(0, min(cap, base * (2**attempt)))


def make_session(timeout_seconds: float, limit: int = 20) -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(limit=limit, ttl_dns_cache=300, keepalive_timeout=60)
    return aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        trust_env=True,  # honour HTTPS_PROXY if the deployment needs an outbound proxy
    )


def request_not_sent(exc: BaseException) -> bool:
    """True when the error proves the request never reached the server (safe to treat as not executed)."""
    return isinstance(exc, aiohttp.ClientConnectorError | aiohttp.ConnectionTimeoutError)
