"""Redis distributed lock (SET NX PX + compare-and-delete release)."""

from __future__ import annotations

import secrets
from types import TracebackType

from redis.asyncio import Redis

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class RedisLock:
    def __init__(self, redis: Redis, key: str, ttl_seconds: int) -> None:
        self.redis = redis
        self.key = key
        self.ttl_ms = int(ttl_seconds * 1000)
        self.token = secrets.token_hex(16)
        self.acquired = False

    async def acquire(self) -> bool:
        self.acquired = bool(await self.redis.set(self.key, self.token, nx=True, px=self.ttl_ms))
        return self.acquired

    async def release(self) -> None:
        if self.acquired:
            await self.redis.eval(_RELEASE, 1, self.key, self.token)
            self.acquired = False

    async def extend(self, ttl_seconds: int) -> bool:
        if not self.acquired:
            return False
        current = await self.redis.get(self.key)
        if current is None:
            return False
        if (current.decode() if isinstance(current, bytes) else current) != self.token:
            return False
        return bool(await self.redis.pexpire(self.key, int(ttl_seconds * 1000)))

    async def __aenter__(self) -> RedisLock:
        await self.acquire()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.release()
