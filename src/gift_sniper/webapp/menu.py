"""Puts the Mini App into the bot's chat menu button.

The address is WEBAPP_URL when set; otherwise it is read from the Cloudflare quick tunnel (docker-compose
service `tunnel`), whose metrics server answers GET /quicktunnel with {"hostname": "<name>.trycloudflare.com"}.
A quick tunnel gets a new address after every restart, so the button is updated whenever it changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import aiohttp
from redis.asyncio import Redis

from gift_sniper.config import Settings

log = logging.getLogger(__name__)

MENU_BUTTON_TEXT = "Снайпер"


def url_key(prefix: str) -> str:
    return f"{prefix}:webapp:url"


async def current_url(redis: Redis, prefix: str) -> str | None:
    value = await redis.get(url_key(prefix))
    return value.decode() if isinstance(value, bytes) else value


async def tunnel_url(http: aiohttp.ClientSession, metrics_url: str) -> str | None:
    async with http.get(
        metrics_url.rstrip("/") + "/quicktunnel", timeout=aiohttp.ClientTimeout(total=5)
    ) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
    hostname = data.get("hostname") if isinstance(data, dict) else None
    return f"https://{hostname}/app/" if hostname else None


async def publish_menu_button(bot: Any, settings: Settings, redis: Redis, stop: asyncio.Event) -> None:
    from aiogram.types import MenuButtonWebApp, WebAppInfo

    if not settings.webapp_url and not settings.webapp_tunnel_metrics_url:
        log.warning("Mini App address is unknown: set WEBAPP_URL or run the `tunnel` service")
        return
    published: str | None = None
    async with aiohttp.ClientSession() as http:
        while not stop.is_set():
            try:
                url = settings.webapp_url or await tunnel_url(http, settings.webapp_tunnel_metrics_url or "")
                if url and url != published:
                    await bot.set_chat_menu_button(
                        menu_button=MenuButtonWebApp(text=MENU_BUTTON_TEXT, web_app=WebAppInfo(url=url))
                    )
                    await redis.set(url_key(settings.redis_prefix), url)
                    published = url
                    log.info("Mini App menu button published", extra={"url": url})
            except Exception as exc:  # the tunnel may still be starting
                log.warning("Mini App address not available yet", extra={"error": str(exc)})
            if published and settings.webapp_url:
                return
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=60 if published else 10)
