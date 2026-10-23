"""Name normalization used to match MRKT and Gift Wiki names.

Only cosmetic differences are removed (case, whitespace, apostrophe/dash variants, accents).
Different words never become equal, so normalization cannot invent a match.
"""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "ʼ": "'", "´": "'"})
_DASHES = str.maketrans({"–": "-", "—": "-", "‑": "-", "−": "-"})
_SPACES = re.compile(r"\s+")


def normalize_name(value: str | None) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.translate(_APOSTROPHES).translate(_DASHES)
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    text = _SPACES.sub(" ", text).strip().casefold()
    return text


def compact_name(value: str | None) -> str:
    """Normalized name without spaces and punctuation ("Plush Pepe" == "PlushPepe")."""
    return re.sub(r"[^0-9a-zа-яё]+", "", normalize_name(value))


def color_candidates(value: object) -> set[int]:
    """All plausible 24-bit RGB readings of a color value.

    The Gift Wiki documentation types colors as plain strings without a format, so the value may be
    '#RRGGBB', 'RRGGBB', '0xRRGGBB', '#AARRGGBB', a decimal string or rgb(). An ambiguous value such as
    '123456' yields both the decimal and the hex reading. An empty set means "cannot be compared".
    """
    if value is None or isinstance(value, bool):
        return set()
    if isinstance(value, int):
        return {value & 0xFFFFFF} if value >= 0 else set()
    if not isinstance(value, str):
        return set()
    text = value.strip().lower()
    if not text:
        return set()
    match = re.fullmatch(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d.]+)?\s*\)", text)
    if match:
        r, g, b = (int(x) for x in match.groups())
        return {(r << 16) | (g << 8) | b} if max(r, g, b) <= 255 else set()
    if text.startswith("#") or text.startswith("0x"):
        digits = text[1:] if text.startswith("#") else text[2:]
        if re.fullmatch(r"[0-9a-f]{6}|[0-9a-f]{8}", digits):
            return {int(digits, 16) & 0xFFFFFF}
        return set()
    result: set[int] = set()
    if re.fullmatch(r"\d+", text) and int(text) <= 0xFFFFFF:
        result.add(int(text))
    if re.fullmatch(r"[0-9a-f]{6}|[0-9a-f]{8}", text):
        result.add(int(text, 16) & 0xFFFFFF)
    return result
