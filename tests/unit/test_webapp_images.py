"""Picture URLs for the Mini App (Fragment patterns from github.com/Nxrix/Telegram-Gifts)."""

from __future__ import annotations

from gift_sniper.webapp.images import collection_thumb, color_hex, gift_image, giftname


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
