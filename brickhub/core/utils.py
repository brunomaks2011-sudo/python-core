"""Small helpers shared by all apps."""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from django.utils.text import slugify

# Official Ukrainian transliteration (КМУ №55, 2010) – used for URL slugs.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh",
    "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "'": "", "’": "", "ʼ": "",
    "ы": "y", "э": "e", "ё": "io", "ъ": "",
}
_TRANSLIT_START = {"є": "ye", "ї": "yi", "й": "y", "ю": "yu", "я": "ya"}


def transliterate(text: str) -> str:
    out = []
    prev_is_letter = False
    for ch in text:
        low = ch.lower()
        if low in _TRANSLIT:
            rep = _TRANSLIT_START.get(low) if not prev_is_letter and low in _TRANSLIT_START else _TRANSLIT[low]
            if ch.isupper() and rep:
                rep = rep[0].upper() + rep[1:]
            out.append(rep)
            prev_is_letter = True
        else:
            out.append(ch)
            prev_is_letter = ch.isalpha()
    return "".join(out)


def make_slug(*parts: str, max_length: int = 200) -> str:
    text = " ".join(p for p in parts if p)
    text = text.replace("×", "x").replace("°", "")
    slug = slugify(transliterate(text))
    return slug[:max_length].strip("-") or "item"


def money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_uah(value, show_currency: bool = True) -> str:
    """1299 -> '1 299 ₴', 2.5 -> '2,50 ₴' (narrow no-break space as thousands separator)."""
    if value is None or value == "":
        return ""
    amount = money(value)
    whole, frac = divmod(abs(amount), 1)
    whole_str = f"{int(whole):,}".replace(",", "\u202f")
    text = whole_str if frac == 0 else f"{whole_str},{int((frac * 100).to_integral_value()):02d}"
    if amount < 0:
        text = "−" + text
    return f"{text}\u00a0₴" if show_currency else text


def plural_uk(n: int, one: str, few: str, many: str) -> str:
    """Ukrainian plural form: 1 деталь, 2 деталі, 5 деталей."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


_PHONE_RE = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    """Normalise a Ukrainian phone number to +380XXXXXXXXX (or return '' if invalid)."""
    digits = _PHONE_RE.sub("", raw or "")
    if digits.startswith("380") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("80") and len(digits) == 11:
        return "+3" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+38" + digits
    return ""


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
