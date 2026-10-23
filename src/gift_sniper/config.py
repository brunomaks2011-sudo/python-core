"""Application settings loaded from environment variables (never from source code)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class RunMode(StrEnum):
    """Global safety mode.

    notify_only: only notifications, the purchase module is fully disabled.
    dry_run:     test mode, the bot shows what it *would* buy, no buy requests are sent.
    live:        real purchases through MRKT.
    """

    NOTIFY_ONLY = "notify_only"
    DRY_RUN = "dry_run"
    LIVE = "live"

    @property
    def rank(self) -> int:
        return {RunMode.NOTIFY_ONLY: 0, RunMode.DRY_RUN: 1, RunMode.LIVE: 2}[self]


class AbsentPairPolicy(StrEnum):
    NOT_MONOCHROME = "not_monochrome"
    UNKNOWN = "unknown"


class MonitorSource(StrEnum):
    FEED = "feed"
    SALING = "saling"


def _split_ints(value: Any) -> list[int]:
    if value is None or value == "":
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, list | tuple | set):
        return [int(v) for v in value]
    return [int(part) for part in str(value).replace(";", ",").split(",") if part.strip()]


IntList = Annotated[list[int], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram bot -----------------------------------------------------------------
    telegram_bot_token: SecretStr | None = None
    admin_user_ids: IntList = Field(default_factory=list)
    allowed_user_ids: IntList = Field(default_factory=list)
    purchase_user_ids: IntList = Field(default_factory=list)

    # --- Safety ---------------------------------------------------------------------------
    run_mode: RunMode = RunMode.DRY_RUN
    timezone: str = "UTC"

    # --- Storage ----------------------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://sniper:sniper@localhost:5432/sniper"
    redis_url: str = "redis://localhost:6379/0"
    redis_prefix: str = "sniper"

    # --- MRKT (unofficial Mini App API, see docs/DATA_SOURCES.md) ---------------------
    mrkt_api_base_url: str = "https://api.tgmrkt.io/api/v1"
    mrkt_access_token: SecretStr | None = None
    mrkt_init_data: SecretStr | None = None
    mrkt_auth_header_format: str = "raw"  # raw | bearer
    mrkt_referer: str = "https://cdn.tgmrkt.io/"
    mrkt_requests_per_second: float = 2.0
    mrkt_priority_requests_per_second: float = 2.0
    mrkt_request_timeout_seconds: float = 10.0
    mrkt_buy_timeout_seconds: float = 15.0
    mrkt_monitor_enabled: bool = True
    mrkt_monitor_source: MonitorSource = MonitorSource.FEED
    mrkt_feed_poll_interval_seconds: float = 2.0
    mrkt_feed_page_size: int = 20
    mrkt_feed_max_pages: int = 5
    mrkt_app_url: str = "https://t.me/mrkt/app"
    mrkt_listing_url_template: str = ""

    # --- Gift Wiki ----------------------------------------------------------------------
    giftwiki_api_base_url: str = "https://api.giftwiki.tg"
    giftwiki_api_key: SecretStr | None = None
    giftwiki_requests_per_second: float = 1.0
    giftwiki_request_timeout_seconds: float = 20.0
    giftwiki_sync_interval_minutes: int = 360
    giftwiki_max_pages: int = 2000
    giftwiki_per_gift_lookup: bool = True
    giftwiki_stale_after_hours: float = 24.0
    giftwiki_public_url: str = "https://t.me/giftwiki"

    # --- Monochrome classification ------------------------------------------------------
    monochrome_absent_pair_policy: AbsentPairPolicy = AbsentPairPolicy.NOT_MONOCHROME
    monochrome_autobuy_max_data_age_hours: float = 72.0
    monochrome_color_check: bool = True

    # --- Purchases ----------------------------------------------------------------------
    purchase_lock_ttl_seconds: int = 120
    purchase_max_snapshot_age_seconds: float = 5.0
    purchase_verify_attempts: int = 5
    purchase_verify_delay_seconds: float = 2.0
    purchase_retries_after_verified_failure: int = 1
    purchase_check_balance: bool = True
    purchase_workers: int = 2
    processor_workers: int = 2

    # --- Discount methodology -----------------------------------------------------------
    discount_window_days: int = 7
    discount_min_samples: int = 5

    # --- Notifications --------------------------------------------------------------------
    notify_default_max_per_minute: int = 20
    telegram_global_messages_per_second: float = 25.0
    bot_flood_max_events: int = 15
    bot_flood_window_seconds: float = 5.0

    # --- Observability ------------------------------------------------------------------
    metrics_port: int = 9100
    metrics_host: str = "0.0.0.0"
    log_level: str = "INFO"
    log_format: str = "json"  # json | text

    @field_validator("admin_user_ids", "allowed_user_ids", "purchase_user_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: Any) -> list[int]:
        return _split_ints(value)

    @field_validator(
        "telegram_bot_token", "mrkt_access_token", "mrkt_init_data", "giftwiki_api_key", mode="before"
    )
    @classmethod
    def _empty_secret(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("mrkt_auth_header_format")
    @classmethod
    def _check_auth_format(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"raw", "bearer"}:
            raise ValueError("MRKT_AUTH_HEADER_FORMAT must be 'raw' or 'bearer'")
        return value

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, value: str) -> str:
        ZoneInfo(value)  # raises for unknown zones
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def is_allowed(self, user_id: int) -> bool:
        return self.is_admin(user_id) or user_id in self.allowed_user_ids

    def can_purchase(self, user_id: int) -> bool:
        if self.purchase_user_ids:
            return user_id in self.purchase_user_ids
        return self.is_admin(user_id)

    @property
    def mrkt_configured(self) -> bool:
        return bool(self.mrkt_access_token or self.mrkt_init_data)

    @property
    def giftwiki_configured(self) -> bool:
        return self.giftwiki_api_key is not None and bool(self.giftwiki_api_key.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
