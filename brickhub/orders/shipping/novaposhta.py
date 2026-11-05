"""Thin client for the Nova Poshta JSON API v2.0.

Docs: https://developers.novaposhta.ua/
Only read-only reference methods are used here (settlements, branches,
tracking).  Creating waybills (InternetDocument.save) can be added later in
``create_waybill``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("brickhub")


class NovaPoshtaError(Exception):
    pass


class NovaPoshtaClient:
    timeout = 8

    def __init__(self, api_key: str | None = None, url: str | None = None):
        self.api_key = api_key if api_key is not None else settings.NOVA_POSHTA_API_KEY
        self.url = url or settings.NOVA_POSHTA_API_URL

    # ------------------------------------------------------------------
    def call(self, model: str, method: str, props: dict, cache_seconds: int = 0):
        payload = {"apiKey": self.api_key, "modelName": model, "calledMethod": method, "methodProperties": props}
        key = None
        if cache_seconds:
            digest = hashlib.sha256(json.dumps([model, method, props], sort_keys=True).encode()).hexdigest()
            key = f"np:{digest}"
            hit = cache.get(key)
            if hit is not None:
                return hit
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - fixed https URL
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            logger.warning("Nova Poshta API error: %s", exc)
            raise NovaPoshtaError("Сервіс Нової пошти тимчасово недоступний") from exc
        if not body.get("success"):
            errors = body.get("errors") or body.get("errorCodes") or ["невідома помилка"]
            raise NovaPoshtaError("; ".join(map(str, errors)))
        data = body.get("data") or []
        if key:
            cache.set(key, data, cache_seconds)
        return data

    # ------------------------------------------------------------------
    def search_cities(self, query: str, limit: int = 15) -> list[dict]:
        query = (query or "").strip()
        if len(query) < 2:
            return []
        data = self.call("Address", "searchSettlements",
                         {"CityName": query, "Limit": str(limit), "Page": "1"}, cache_seconds=86400)
        addresses = data[0].get("Addresses", []) if data else []
        out = []
        for a in addresses:
            city_ref = a.get("DeliveryCity") or ""
            if not city_ref:
                continue
            out.append({
                "ref": city_ref,
                "name": a.get("MainDescription", ""),
                "label": a.get("Present") or a.get("MainDescription", ""),
                "warehouses": int(a.get("Warehouses") or 0),
            })
        return out

    def warehouses(self, city_ref: str, query: str = "", kind: str = "branch", limit: int = 50) -> list[dict]:
        if not city_ref:
            return []
        props = {"CityRef": city_ref, "Page": "1", "Limit": str(limit), "Language": "UA"}
        if query:
            props["FindByString"] = query
        data = self.call("Address", "getWarehouses", props, cache_seconds=3600 * 6)
        out = []
        for w in data:
            category = (w.get("CategoryOfWarehouse") or "").lower()
            description = w.get("Description", "")
            is_postomat = category == "postomat" or "поштомат" in description.lower()
            if kind == "postomat" and not is_postomat:
                continue
            if kind == "branch" and is_postomat:
                continue
            out.append({"ref": w.get("Ref", ""), "number": w.get("Number", ""), "label": description,
                        "postomat": is_postomat})
        return out

    def track(self, number: str, phone: str = "") -> dict | None:
        docs = [{"DocumentNumber": number, "Phone": phone.lstrip("+")}]
        data = self.call("TrackingDocument", "getStatusDocuments", {"Documents": docs}, cache_seconds=600)
        if not data:
            return None
        d = data[0]
        return {
            "status": d.get("Status", ""),
            "code": d.get("StatusCode", ""),
            "warehouse": d.get("WarehouseRecipient", ""),
            "scheduled": d.get("ScheduledDeliveryDate", ""),
            "delivered": d.get("RecipientDateTime", ""),
        }
