"""Per-user notification preferences (stored as JSONB in user_settings.notify)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NotificationSettings(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    all_listings: bool = False  # every new listing (within price range / collections below)
    matching_only: bool = True  # listings that match the user's enabled filters
    monochrome: bool = True  # confirmed monochromes, even without a matching filter
    price_drops: bool = False
    purchases: bool = True
    errors: bool = True
    min_price_nano: int | None = None
    max_price_nano: int | None = None
    collections: list[str] = Field(default_factory=list)
    min_monochrome_share_percent: float | None = None
    max_per_minute: int = 20
    no_repeats: bool = True
    price_drop_min_percent: float = 5.0
