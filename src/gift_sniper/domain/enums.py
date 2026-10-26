from __future__ import annotations

from enum import StrEnum


class MonochromeStatus(StrEnum):
    MONOCHROME = "MONOCHROME"  # confirmed by a Gift Wiki record for this gift + model + backdrop
    NOT_MONOCHROME = "NOT_MONOCHROME"  # the complete Gift Wiki list for the gift does not contain the pair
    UNKNOWN = "UNKNOWN"  # not enough data for a reliable classification


class GiftWikiMonochromeType(StrEnum):
    """Classification levels documented by Gift Wiki (sorted by Gift Wiki in this order)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    COMBO = "combo"

    @classmethod
    def parse(cls, value: object) -> GiftWikiMonochromeType | None:
        if not isinstance(value, str):
            return None
        try:
            return cls(value.strip().lower())
        except ValueError:
            return None

    @property
    def priority(self) -> int:
        return _TYPE_ORDER.index(self)


_TYPE_ORDER = [
    GiftWikiMonochromeType.HIGH,
    GiftWikiMonochromeType.MEDIUM,
    GiftWikiMonochromeType.LOW,
    GiftWikiMonochromeType.COMBO,
]


class FilterKind(StrEnum):
    REGULAR = "regular"
    MONOCHROME = "monochrome"


class PurchaseMode(StrEnum):
    REGULAR = "regular"
    MONOCHROME = "monochrome"
    MANUAL = "manual"
    RESALE = "resale"  # the resale assistant: bought to be sold again


class ResaleStatus(StrEnum):
    BOUGHT = "bought"  # bought, not listed yet
    WAITING = "waiting"  # MRKT allows listing it later (nextResaleDate)
    LISTED = "listed"  # on sale on MRKT
    FAILED = "failed"  # listing failed, tried again later
    SOLD = "sold"  # MRKT reported the sale
    DRY_RUN = "dry_run"  # test mode: would have been bought and listed


class PurchaseRunMode(StrEnum):
    LIVE = "live"
    DRY_RUN = "dry_run"


class PurchaseStatus(StrEnum):
    RESERVED = "reserved"  # budget reserved, request not sent yet
    SUBMITTED = "submitted"  # request is being sent / was sent, response not processed yet
    CONFIRMED = "confirmed"  # MRKT confirmed the purchase
    FAILED = "failed"  # definitely not executed (MRKT refused, or verified as not executed)
    UNKNOWN = "unknown"  # outcome unknown, waiting for verification; budget stays reserved
    DRY_RUN = "dry_run"  # test mode: would have been bought
    CANCELLED = "cancelled"  # not sent by our decision (re-check failed, limits, emergency stop)


# Statuses that consume budget (live mode): money may be or is spent.
BUDGET_CONSUMING_STATUSES = (
    PurchaseStatus.RESERVED,
    PurchaseStatus.SUBMITTED,
    PurchaseStatus.CONFIRMED,
    PurchaseStatus.UNKNOWN,
)
# Statuses that block a new live attempt for the same MRKT gift.
ACTIVE_LIVE_STATUSES = BUDGET_CONSUMING_STATUSES


class ListingStatus(StrEnum):
    ACTIVE = "active"
    SOLD = "sold"
    REMOVED = "removed"
    UNKNOWN = "unknown"


class BudgetScope(StrEnum):
    USER = "user"
    REGULAR = "regular"
    MONOCHROME = "monochrome"


class FeedEventType(StrEnum):
    LISTING = "listing"
    CHANGE_PRICE = "change_price"
    SALE = "sale"
    UNLISTING = "unlisting"
    RETURN = "return"
    UPLOAD = "upload"
    OBSERVED = "observed"  # synthetic: listing found by polling gifts/saling
