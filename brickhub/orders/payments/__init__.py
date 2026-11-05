"""Payment providers.

Cash on delivery (накладений платіж) needs no integration.  Online card
payments go through a provider class; the shop ships LiqPay (PrivatBank),
which is enabled only when LIQPAY_PUBLIC_KEY / LIQPAY_PRIVATE_KEY are set.
Without keys the card option is shown as unavailable and orders are never
marked as paid.  An order becomes "paid" only after a callback whose
signature, amount and currency were verified.
"""
from __future__ import annotations

from .liqpay import LiqPayProvider

PROVIDERS = {"liqpay": LiqPayProvider}


def card_provider():
    """The configured card provider instance, or None."""
    provider = LiqPayProvider()
    return provider if provider.is_configured() else None


def card_payments_enabled() -> bool:
    return card_provider() is not None
