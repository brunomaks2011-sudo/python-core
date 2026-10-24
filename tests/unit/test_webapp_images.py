"""Picture URLs for the Mini App (Fragment patterns from github.com/Nxrix/Telegram-Gifts)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from gift_sniper.selfcheck import Report, _check_images
from gift_sniper.webapp.images import absolute_url, collection_thumb, color_hex, gift_image, giftname
from tests.fake_server import FakeServer, Reply


@pytest_asyncio.fixture
async def server() -> AsyncIterator[FakeServer]:
    srv = FakeServer()
    await srv.start()
    yield srv
    await srv.stop()


def test_fragment_urls() -> None:
    assert giftname("Plush Pepe") == "plushpepe"
    assert giftname("Durov's Cap") == "durovscap"
    assert giftname("whatever", slug="JackInTheBox-12") == "jackinthebox"
    assert collection_thumb("plushpepe") == "https://fragment.com/file/gifts/plushpepe/thumb.webp"
    assert gift_image("PlushPepe-12") == "https://nft.fragment.com/gift/plushpepe-12.webp"
    assert gift_image("Plush Pepe #12") is None and gift_image(None) is None


def test_backdrop_colors() -> None:
    assert color_hex(0x5D3A8C) == "#5d3a8c"
    assert color_hex("#ABCDEF") == color_hex("abcdef") == "#abcdef"
    assert color_hex(str(0x5D3A8C)) == "#5d3a8c"
    assert color_hex("purple") is None and color_hex(None) is None and color_hex(-1) is None


def test_gift_wiki_paths_become_absolute() -> None:
    base = "https://api.giftwiki.tg"
    assert absolute_url("/media/pepe.png", base) == "https://api.giftwiki.tg/media/pepe.png"
    assert absolute_url("https://cdn.example/p.png", base) == "https://cdn.example/p.png"
    assert absolute_url("//cdn.example/p.png", base) == "https://cdn.example/p.png"
    assert absolute_url("javascript:alert(1)", base) is None and absolute_url(" ", base) is None


async def test_self_check_opens_the_pictures(server: FakeServer) -> None:
    server.add("GET", "/thumb.webp", Reply(headers={"Content-Type": "image/webp"}))
    server.add("GET", "/missing.webp", Reply(status=404))
    report = Report()
    await _check_images(
        report, [("ok", server.url + "/thumb.webp"), ("missing", server.url + "/missing.webp")]
    )
    assert report.lines[0].startswith("✅ Картинка ok: HTTP 200 image/webp")
    assert report.lines[1].startswith("⚠️ Картинка missing: HTTP 404")
