"""Task queues on Redis Streams (consumer groups, ack, reclaim of stuck messages).

Two streams are used: listing events (monitor -> processors) and purchase requests (processors -> buyers).
Messages survive restarts. A message that keeps failing is moved to a dead-letter stream after
`max_deliveries` attempts. Purchase handlers are idempotent (DB unique indexes + attempt statuses),
so re-delivery never results in a second purchase.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class StreamQueue:
    def __init__(
        self,
        redis: Redis,
        stream: str,
        group: str,
        *,
        maxlen: int = 100_000,
        claim_idle_ms: int = 60_000,
        max_deliveries: int = 5,
    ) -> None:
        self.redis = redis
        self.stream = stream
        self.group = group
        self.maxlen = maxlen
        self.claim_idle_ms = claim_idle_ms
        self.max_deliveries = max_deliveries
        self.consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._group_ready = False

    async def ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    async def publish(self, payload: dict[str, Any]) -> str:
        msg_id = await self.redis.xadd(
            self.stream, {"data": json.dumps(payload, default=str)}, maxlen=self.maxlen, approximate=True
        )
        return msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)

    async def backlog(self) -> int:
        try:
            info = await self.redis.xpending(self.stream, self.group)
        except ResponseError:
            return 0
        if isinstance(info, dict):
            return int(info.get("pending", 0))
        return 0

    @staticmethod
    def _decode(fields: dict[Any, Any]) -> dict[str, Any] | None:
        raw = fields.get(b"data") if b"data" in fields else fields.get("data")
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def _handle(self, msg_id: Any, fields: dict[Any, Any], handler: Handler) -> None:
        payload = self._decode(fields)
        if payload is None:
            log.error("dropping malformed queue message", extra={"stream": self.stream, "id": str(msg_id)})
            await self.redis.xack(self.stream, self.group, msg_id)
            return
        try:
            await handler(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("queue handler failed", extra={"stream": self.stream, "id": str(msg_id)})
            return  # stays pending; reclaimed later
        await self.redis.xack(self.stream, self.group, msg_id)

    async def _reclaim(self, handler: Handler) -> None:
        try:
            result = await self.redis.xautoclaim(
                self.stream,
                self.group,
                self.consumer,
                min_idle_time=self.claim_idle_ms,
                start_id="0-0",
                count=20,
            )
        except ResponseError:
            return
        messages = result[1] if isinstance(result, list | tuple) and len(result) > 1 else []
        for msg_id, fields in messages:
            if not fields:
                continue
            deliveries = await self._delivery_count(msg_id)
            if deliveries > self.max_deliveries:
                await self.redis.xadd(f"{self.stream}:dead", fields, maxlen=10_000, approximate=True)
                await self.redis.xack(self.stream, self.group, msg_id)
                log.error(
                    "message moved to dead-letter stream", extra={"stream": self.stream, "id": str(msg_id)}
                )
                continue
            await self._handle(msg_id, fields, handler)

    async def _delivery_count(self, msg_id: Any) -> int:
        try:
            rows = await self.redis.xpending_range(self.stream, self.group, min=msg_id, max=msg_id, count=1)
        except ResponseError:
            return 0
        if rows:
            row = rows[0]
            return int(row.get("times_delivered", 0)) if isinstance(row, dict) else 0
        return 0

    async def consume(
        self, handler: Handler, *, stop: asyncio.Event, block_ms: int = 1000, count: int = 10
    ) -> None:
        await self.ensure_group()
        last_reclaim = 0.0
        loop = asyncio.get_running_loop()
        while not stop.is_set():
            if loop.time() - last_reclaim > self.claim_idle_ms / 1000:
                await self._reclaim(handler)
                last_reclaim = loop.time()
            try:
                batches: Any = await self.redis.xreadgroup(
                    self.group, self.consumer, {self.stream: ">"}, count=count, block=block_ms
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("xreadgroup failed", extra={"stream": self.stream})
                await asyncio.sleep(1)
                continue
            for _stream, messages in batches or []:
                for msg_id, fields in messages:
                    await self._handle(msg_id, fields, handler)


class MemoryQueue:
    """In-process queue with the same interface (tests, single-process runs without Redis streams)."""

    def __init__(self) -> None:
        self.items: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.published: list[dict[str, Any]] = []

    async def ensure_group(self) -> None:
        return None

    async def publish(self, payload: dict[str, Any]) -> str:
        data = json.loads(json.dumps(payload, default=str))
        self.published.append(data)
        await self.items.put(data)
        return str(len(self.published))

    async def backlog(self) -> int:
        return self.items.qsize()

    async def consume(
        self, handler: Handler, *, stop: asyncio.Event, block_ms: int = 1000, count: int = 10
    ) -> None:
        while not stop.is_set():
            try:
                payload = await asyncio.wait_for(self.items.get(), timeout=block_ms / 1000)
            except TimeoutError:
                continue
            try:
                await handler(payload)
            except Exception:
                log.exception("memory queue handler failed")
