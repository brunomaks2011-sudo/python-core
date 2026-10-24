"""The bot finds the Mini App address (tunnel or WEBAPP_URL) and puts it into its chat menu button."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import fakeredis
import pytest_asyncio

from gift_sniper.webapp.menu import current_url, publish_menu_button
from tests.factories import make_settings
from tests.fake_server import FakeServer, Reply


class FakeBot:
    def __init__(self) -> None:
        self.buttons: list[Any] = []

    async def set_chat_menu_button(self, *, menu_button: Any) -> bool:
        self.buttons.append(menu_button)
        return True


@pytest_asyncio.fixture
async def server() -> AsyncIterator[FakeServer]:
    srv = FakeServer()
    await srv.start()
    yield srv
    await srv.stop()


async def _publish_until(bot: FakeBot, settings: Any, redis: Any, count: int) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(publish_menu_button(bot, settings, redis, stop))
    for _ in range(200):
        if len(bot.buttons) >= count:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, 2)


async def test_quick_tunnel_address_becomes_the_menu_button(server: FakeServer) -> None:
    server.add("GET", "/quicktunnel", Reply(body={"hostname": "abc-def.trycloudflare.com"}))
    redis = fakeredis.aioredis.FakeRedis()
    bot = FakeBot()
    settings = make_settings(webapp_tunnel_metrics_url=server.url)
    await _publish_until(bot, settings, redis, 1)
    assert bot.buttons[0].web_app.url == "https://abc-def.trycloudflare.com/app/"
    assert bot.buttons[0].text == "Снайпер"
    assert await current_url(redis, settings.redis_prefix) == "https://abc-def.trycloudflare.com/app/"


async def test_fixed_address_is_published_once(server: FakeServer) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    bot = FakeBot()
    settings = make_settings(
        webapp_url="https://sniper.example.com/app/", webapp_tunnel_metrics_url=server.url
    )
    await asyncio.wait_for(publish_menu_button(bot, settings, redis, asyncio.Event()), 2)  # returns by itself
    assert [b.web_app.url for b in bot.buttons] == ["https://sniper.example.com/app/"]
    assert server.calls("GET", "/quicktunnel") == []
