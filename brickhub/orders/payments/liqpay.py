"""LiqPay Checkout (API v3).

Protocol: https://www.liqpay.ua/documentation/api/aquiring/checkout/doc
    data      = base64(json(params))
    signature = base64(sha1(private_key + data + private_key))
The same formula verifies the server-to-server callback.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal

from django.conf import settings

CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"


class LiqPayError(Exception):
    pass


class LiqPayProvider:
    code = "liqpay"
    title = "LiqPay (Visa / Mastercard, Apple Pay, Google Pay)"

    def __init__(self, public_key: str | None = None, private_key: str | None = None, sandbox: bool | None = None):
        self.public_key = public_key if public_key is not None else settings.LIQPAY_PUBLIC_KEY
        self.private_key = private_key if private_key is not None else settings.LIQPAY_PRIVATE_KEY
        self.sandbox = settings.LIQPAY_SANDBOX if sandbox is None else sandbox

    def is_configured(self) -> bool:
        return bool(self.public_key and self.private_key)

    # ------------------------------------------------------------------
    def _sign(self, data: str) -> str:
        raw = (self.private_key + data + self.private_key).encode("utf-8")
        return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")  # noqa: S324 - mandated by LiqPay

    def encode(self, params: dict) -> tuple[str, str]:
        data = base64.b64encode(json.dumps(params, ensure_ascii=False).encode("utf-8")).decode("ascii")
        return data, self._sign(data)

    def checkout_form(self, order, result_url: str, server_url: str) -> dict:
        if not self.is_configured():
            raise LiqPayError("LiqPay не налаштовано")
        params = {
            "version": 3,
            "public_key": self.public_key,
            "action": "pay",
            "amount": f"{order.total:.2f}",
            "currency": "UAH",
            "description": f"Замовлення {order.number} — {settings.SHOP['NAME']}",
            "order_id": order.number,
            "result_url": result_url,
            "server_url": server_url,
            "language": "uk",
        }
        if self.sandbox:
            params["sandbox"] = 1
        data, signature = self.encode(params)
        return {"action": CHECKOUT_URL, "data": data, "signature": signature}

    def parse_callback(self, data: str, signature: str) -> dict:
        """Verify and decode a callback. Raises LiqPayError when the signature is wrong."""
        if not self.is_configured():
            raise LiqPayError("LiqPay не налаштовано")
        expected = self._sign(data or "")
        if not hmac.compare_digest(expected, signature or ""):
            raise LiqPayError("Невірний підпис LiqPay")
        try:
            return json.loads(base64.b64decode(data).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise LiqPayError("Пошкоджені дані LiqPay") from exc

    def is_success(self, payload: dict) -> bool:
        status = payload.get("status")
        return status == "success" or (self.sandbox and status == "sandbox")

    @staticmethod
    def amount_matches(payload: dict, order) -> bool:
        try:
            amount = Decimal(str(payload.get("amount")))
        except Exception:
            return False
        return payload.get("currency") == "UAH" and amount == order.total
