"""A programmable local HTTP server for client tests (real sockets, real aiohttp client stack)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web


@dataclass
class Reply:
    status: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0
    disconnect: bool = False


@dataclass
class Recorded:
    method: str
    path: str
    query: list[tuple[str, str]]
    headers: dict[str, str]
    json: Any


class FakeServer:
    def __init__(self) -> None:
        self.replies: dict[tuple[str, str], deque[Reply]] = defaultdict(deque)
        self.requests: list[Recorded] = []
        self._runner: web.AppRunner | None = None
        self.port = 0

    def add(self, method: str, path: str, *replies: Reply) -> None:
        self.replies[(method.upper(), path)].extend(replies)

    def calls(self, method: str, path: str) -> list[Recorded]:
        return [r for r in self.requests if r.method == method.upper() and r.path == path]

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        body: Any = None
        if request.can_read_body:
            raw = await request.read()
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = raw.decode(errors="replace")
        self.requests.append(
            Recorded(request.method, request.path, list(request.query.items()), dict(request.headers), body)
        )
        queue = self.replies.get((request.method, request.path))
        if not queue:
            return web.json_response({"error": "no reply programmed"}, status=599)
        reply = queue.popleft() if len(queue) > 1 else queue[0]
        if reply.delay:
            await asyncio.sleep(reply.delay)
        if reply.disconnect:
            assert request.transport is not None
            request.transport.close()
            return web.Response()
        if reply.body is None:
            return web.Response(status=reply.status, headers=reply.headers)
        text = reply.body if isinstance(reply.body, str) else json.dumps(reply.body)
        return web.Response(
            status=reply.status, text=text, headers=reply.headers, content_type="application/json"
        )

    async def start(self) -> None:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        server = site._server
        assert server is not None
        self.port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
