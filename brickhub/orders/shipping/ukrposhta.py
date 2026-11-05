"""Ukrposhta integration point.

Ukrposhta issues separate bearer tokens for its APIs (address classifier,
shipments, status tracking).  The shop currently needs only tracking, which is
enabled when ``UKRPOSHTA_BEARER_TOKEN`` is set.  Shipment creation can be added
in ``UkrposhtaClient.create_shipment`` when the shop signs a contract.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("brickhub")

TRACKING_URL = "https://www.ukrposhta.ua/status-tracking/0.0.1/statuses/last"


class UkrposhtaError(Exception):
    pass


class UkrposhtaClient:
    timeout = 8

    def __init__(self, token: str | None = None):
        self.token = token if token is not None else settings.UKRPOSHTA_BEARER_TOKEN

    def track(self, barcode: str) -> dict | None:
        if not self.token:
            raise UkrposhtaError("Інтеграцію з Укрпоштою не налаштовано")
        query = urllib.parse.urlencode({"barcode": barcode, "lang": "UA"})
        req = urllib.request.Request(f"{TRACKING_URL}?{query}", headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - fixed https URL
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            logger.warning("Ukrposhta API error: %s", exc)
            raise UkrposhtaError("Сервіс Укрпошти тимчасово недоступний") from exc
        if not isinstance(data, dict):
            return None
        return {"status": data.get("eventName", ""), "date": data.get("date", ""), "place": data.get("name", "")}

    def create_shipment(self, order):  # pragma: no cover - requires a contract with Ukrposhta
        raise NotImplementedError("Створення відправлень Укрпошти потребує договору та токена eCom API")
