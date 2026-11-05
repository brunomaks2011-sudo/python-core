"""Delivery carriers.

Nova Poshta: live city / branch lookup and tracking through the official
JSON API when ``NOVA_POSHTA_API_KEY`` is configured.  Without a key the
checkout falls back to manual input – nothing is faked.

Ukrposhta: manual address input + public tracking link.  The API client
skeleton lives in ``ukrposhta.py`` and is enabled by ``UKRPOSHTA_BEARER_TOKEN``.
"""
from __future__ import annotations

from urllib.parse import quote

from django.conf import settings

from .novaposhta import NovaPoshtaClient, NovaPoshtaError  # noqa: F401


def nova_poshta_enabled() -> bool:
    return bool(settings.NOVA_POSHTA_API_KEY)


def ukrposhta_enabled() -> bool:
    return bool(settings.UKRPOSHTA_BEARER_TOKEN)


def tracking_url(delivery_method: str, number: str) -> str:
    number = (number or "").strip()
    if not number:
        return ""
    if delivery_method.startswith("np_"):
        return f"https://novaposhta.ua/tracking/?cargo_number={quote(number)}"
    if delivery_method == "ukrposhta":
        return f"https://track.ukrposhta.ua/tracking_UA.html?barcode={quote(number)}"
    return ""
