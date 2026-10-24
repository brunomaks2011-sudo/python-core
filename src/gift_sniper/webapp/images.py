"""Gift pictures for the Mini App (the viewer's Telegram app loads them directly).

Fragment URL patterns, from the community reference https://github.com/Nxrix/Telegram-Gifts:
  collection thumbnail  https://fragment.com/file/gifts/<giftname>/thumb.webp
  a minted gift         https://nft.fragment.com/gift/<giftname>-<number>.webp
where <giftname> is the collection name in lowercase (t.me/nft/PlushPepe-12 -> plushpepe-12).
A model on a specific backdrop is pictured by Gift Wiki's photo_url of that monochrome record, or by a
gift with exactly that model and backdrop seen on MRKT.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from gift_sniper.domain.types import nft_slug

_NOT_ALNUM = re.compile(r"[^0-9a-z]")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def giftname(collection: str | None, *, slug: str | None = None) -> str | None:
    """Lowercase collection name used in Fragment paths: from a known gift slug, else from the name."""
    known = nft_slug(slug)
    if known:
        return known.rsplit("-", 1)[0].lower()
    name = _NOT_ALNUM.sub("", (collection or "").lower())
    return name or None


def collection_thumb(name: str | None) -> str | None:
    return f"https://fragment.com/file/gifts/{name}/thumb.webp" if name else None


def gift_image(slug: str | None) -> str | None:
    known = nft_slug(slug)
    return f"https://nft.fragment.com/gift/{known.lower()}.webp" if known else None


def absolute_url(url: str | None, base: str) -> str | None:
    """Gift Wiki may give a picture path relative to its API; pages need an absolute http(s) URL."""
    if not url or not url.strip():
        return None
    full = urljoin(base.rstrip("/") + "/", url.strip())
    return full if urlparse(full).scheme in ("http", "https") else None


def color_hex(value: int | str | None) -> str | None:
    """MRKT gives backdrop colors as integers (0xRRGGBB); Gift Wiki as strings."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return f"#{value & 0xFFFFFF:06x}" if value >= 0 else None
    text = str(value).strip()
    match = _HEX.match(text)
    if match:
        return f"#{match.group(1).lower()}"
    if text.isdigit():
        return color_hex(int(text))
    return None
