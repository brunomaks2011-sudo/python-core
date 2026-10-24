"""Gift titles in bot messages link to the gift in Telegram when MRKT gives its slug."""

from __future__ import annotations

from gift_sniper.services import texts
from tests.factories import make_listing


def test_gift_title_links_to_the_telegram_gift_page() -> None:
    listing = make_listing("g1", name="PlushPepe-100", number=100)
    assert texts.gift_link(listing) == '<a href="https://t.me/nft/PlushPepe-100">Plush Pepe #100</a>'


def test_gift_title_without_a_slug_stays_plain_text() -> None:
    listing = make_listing("g1", name="not a slug", number=7, collection_title="<Pepe>")
    assert texts.gift_link(listing) == "&lt;Pepe&gt; #7"
    assert texts.nft_url(None) is None
