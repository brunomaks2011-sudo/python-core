"""PostgreSQL schema (SQLAlchemy 2 ORM). Mirrored by migrations/versions/0001_initial.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Json = dict[str, Any]
NAME = 128


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012
        Json: JSONB,
        list[Any]: JSONB,
        datetime: DateTime(timezone=True),
    }


def _now() -> Any:
    return func.now()


# ---------------------------------------------------------------- users & settings
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # Telegram id
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(256))
    is_admin: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    can_purchase: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_blocked: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=_now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=_now())


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    autobuy_enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    monochrome_autobuy_enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    purchases_paused: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    notify: Mapped[Json] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(server_default=_now(), onupdate=func.now())


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "scope", name="uq_budgets_user_scope"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(16))  # user | regular | monochrome
    per_purchase_limit_nano: Mapped[int | None] = mapped_column(BigInteger)
    daily_limit_nano: Mapped[int | None] = mapped_column(BigInteger)
    total_limit_nano: Mapped[int | None] = mapped_column(BigInteger)
    period_max_count: Mapped[int | None] = mapped_column(Integer)
    period_hours: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(server_default=_now(), onupdate=func.now())


class Filter(Base):
    __tablename__ = "filters"
    __table_args__ = (Index("ix_filters_enabled_kind", "enabled", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # regular | monochrome
    enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    autobuy: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    criteria: Mapped[Json] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    limits: Mapped[Json] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    activated_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=_now())
    updated_at: Mapped[datetime] = mapped_column(server_default=_now(), onupdate=func.now())


# ---------------------------------------------------------------- Gift Wiki reference data
class GiftWikiGift(Base):
    """A Gift Wiki gift (Telegram gift type), the counterpart of a MRKT collection."""

    __tablename__ = "giftwiki_gifts"

    gift_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gift_name: Mapped[str | None] = mapped_column(String(NAME))
    name_norm: Mapped[str] = mapped_column(String(NAME), index=True)
    records_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    coverage_complete: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    coverage_source: Mapped[str | None] = mapped_column(String(32))
    last_synced_at: Mapped[datetime | None] = mapped_column()
    first_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    source_url: Mapped[str | None] = mapped_column(Text)


class GiftWikiMonochrome(Base):
    """Monochrome classification records (GET /gifts/monochromes), kept with provenance."""

    __tablename__ = "giftwiki_monochromes"
    __table_args__ = (Index("ix_giftwiki_monochromes_lookup", "gift_id", "model_norm", "backdrop_norm"),)

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Gift Wiki `_id`
    gift_id: Mapped[str] = mapped_column(String(64), ForeignKey("giftwiki_gifts.gift_id", ondelete="CASCADE"))
    gift_name: Mapped[str | None] = mapped_column(String(NAME))
    model_name: Mapped[str | None] = mapped_column(String(NAME))
    model_norm: Mapped[str] = mapped_column(String(NAME))
    backdrop_name: Mapped[str | None] = mapped_column(String(NAME))
    backdrop_norm: Mapped[str] = mapped_column(String(NAME))
    type: Mapped[str | None] = mapped_column(String(32))
    center_color: Mapped[str | None] = mapped_column(String(32))
    edge_color: Mapped[str | None] = mapped_column(String(32))
    pattern_color: Mapped[str | None] = mapped_column(String(32))
    text_color: Mapped[str | None] = mapped_column(String(32))
    photo_url: Mapped[str | None] = mapped_column(Text)
    animation_url: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[Json] = mapped_column(default=dict)
    source_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(server_default=_now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    removed_at: Mapped[datetime | None] = mapped_column()


class GiftWikiAttribute(Base):
    """Models and backdrops mentioned by Gift Wiki records (with colors for backdrops)."""

    __tablename__ = "giftwiki_attributes"
    __table_args__ = (UniqueConstraint("gift_id", "kind", "name_norm", name="uq_giftwiki_attributes_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    gift_id: Mapped[str] = mapped_column(String(64), ForeignKey("giftwiki_gifts.gift_id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # model | backdrop
    name: Mapped[str] = mapped_column(String(NAME))
    name_norm: Mapped[str] = mapped_column(String(NAME))
    details: Mapped[Json] = mapped_column(default=dict)
    source_url: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=_now())


class GiftWikiSyncRun(Base):
    __tablename__ = "giftwiki_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))  # running | success | partial | failed
    started_at: Mapped[datetime] = mapped_column(server_default=_now())
    finished_at: Mapped[datetime | None] = mapped_column()
    pages_fetched: Mapped[int] = mapped_column(default=0)
    records_fetched: Mapped[int] = mapped_column(default=0)
    gifts_covered: Mapped[int] = mapped_column(default=0)
    records_added: Mapped[int] = mapped_column(default=0)
    records_removed: Mapped[int] = mapped_column(default=0)
    lookups_done: Mapped[int] = mapped_column(default=0)
    lookups_failed: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)


class CollectionMapping(Base):
    """MRKT collection name -> Gift Wiki gift id."""

    __tablename__ = "collection_mappings"

    mrkt_collection_name: Mapped[str] = mapped_column(String(NAME), primary_key=True)
    giftwiki_gift_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # matched | ambiguous | not_found | manual
    method: Mapped[str | None] = mapped_column(String(32))
    candidates: Mapped[list[Any]] = mapped_column(default=list)
    checked_at: Mapped[datetime] = mapped_column(server_default=_now())
    verified_by: Mapped[int | None] = mapped_column(BigInteger)


# ---------------------------------------------------------------- MRKT market data
class MarketCollection(Base):
    __tablename__ = "mrkt_collections"

    name: Mapped[str] = mapped_column(String(NAME), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(NAME))
    floor_price_nano: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(server_default=_now())


class GiftModel(Base):
    """Models observed in MRKT listings (with MRKT rarity), used as known models of a collection."""

    __tablename__ = "gift_models"
    __table_args__ = (UniqueConstraint("collection_norm", "model_norm", name="uq_gift_models_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_name: Mapped[str] = mapped_column(String(NAME))
    collection_norm: Mapped[str] = mapped_column(String(NAME))
    model_name: Mapped[str] = mapped_column(String(NAME))
    model_norm: Mapped[str] = mapped_column(String(NAME))
    rarity_permille: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16), default="mrkt")
    first_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=_now())


class Gift(Base):
    """A collectible gift item seen on MRKT, with its stored monochrome classification."""

    __tablename__ = "gifts"
    __table_args__ = (Index("ix_gifts_collection_model", "collection_name", "model_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # MRKT gift id
    collection_name: Mapped[str | None] = mapped_column(String(NAME))
    collection_title: Mapped[str | None] = mapped_column(String(NAME))
    name: Mapped[str | None] = mapped_column(String(NAME))
    number: Mapped[int | None] = mapped_column(Integer)
    model_name: Mapped[str | None] = mapped_column(String(NAME))
    backdrop_name: Mapped[str | None] = mapped_column(String(NAME))
    symbol_name: Mapped[str | None] = mapped_column(String(NAME))
    model_rarity_permille: Mapped[int | None] = mapped_column(Integer)
    backdrop_rarity_permille: Mapped[int | None] = mapped_column(Integer)
    symbol_rarity_permille: Mapped[int | None] = mapped_column(Integer)
    backdrop_center_color: Mapped[int | None] = mapped_column(Integer)
    backdrop_edge_color: Mapped[int | None] = mapped_column(Integer)
    monochrome_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN", server_default="UNKNOWN")
    monochrome_type: Mapped[str | None] = mapped_column(String(16))
    monochrome_record_id: Mapped[str | None] = mapped_column(String(64))
    monochrome_reason: Mapped[str | None] = mapped_column(Text)
    classified_at: Mapped[datetime | None] = mapped_column()
    first_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    raw: Mapped[Json] = mapped_column(default=dict)


class Listing(Base):
    """A sale listing of a gift. At most one active listing per gift (partial unique index)."""

    __tablename__ = "listings"
    __table_args__ = (
        Index("uq_listings_active_gift", "gift_id", unique=True, postgresql_where=text("status = 'active'")),
        Index("ix_listings_first_seen", "first_seen_at"),
        Index("ix_listings_collection_status", "collection_name", "status"),
        Index("ix_listings_status_price", "status", "price_nano"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    gift_id: Mapped[str] = mapped_column(String(64), ForeignKey("gifts.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))
    price_nano: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8), default="TON")
    collection_name: Mapped[str | None] = mapped_column(String(NAME))
    model_name: Mapped[str | None] = mapped_column(String(NAME))
    monochrome_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN", server_default="UNKNOWN")
    listed_at: Mapped[datetime | None] = mapped_column()
    first_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=_now())
    closed_at: Mapped[datetime | None] = mapped_column()
    close_reason: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16), default="feed")
    source_event_id: Mapped[str | None] = mapped_column(String(128))
    detection_latency_ms: Mapped[int | None] = mapped_column(Integer)


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_comparable", "collection_norm", "model_norm", "observed_at"),
        Index("ix_price_history_gift", "gift_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    gift_id: Mapped[str] = mapped_column(String(64), ForeignKey("gifts.id", ondelete="CASCADE"))
    listing_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("listings.id", ondelete="SET NULL"))
    collection_norm: Mapped[str] = mapped_column(String(NAME))
    model_norm: Mapped[str] = mapped_column(String(NAME))
    price_nano: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(16))
    observed_at: Mapped[datetime] = mapped_column(server_default=_now())


class FeedEventLog(Base):
    """Processed MRKT feed events. The primary key protects against processing an event twice."""

    __tablename__ = "feed_events"
    __table_args__ = (Index("ix_feed_events_received", "received_at"),)

    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    gift_id: Mapped[str] = mapped_column(String(64))
    amount_nano: Mapped[int | None] = mapped_column(BigInteger)
    event_date: Mapped[datetime | None] = mapped_column()
    received_at: Mapped[datetime] = mapped_column(server_default=_now())


class FilterHit(Base):
    __tablename__ = "filter_hits"
    __table_args__ = (
        UniqueConstraint(
            "filter_id",
            "listing_id",
            "price_nano",
            name="uq_filter_hits_key",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_filter_hits_user_matched", "user_id", "matched_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filter_id: Mapped[int] = mapped_column(ForeignKey("filters.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    listing_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("listings.id", ondelete="CASCADE"))
    gift_id: Mapped[str] = mapped_column(String(64))
    price_nano: Mapped[int | None] = mapped_column(BigInteger)
    monochrome_status: Mapped[str] = mapped_column(String(16))
    matched_at: Mapped[datetime] = mapped_column(server_default=_now())


# ---------------------------------------------------------------- purchases
LIVE_ACTIVE_WHERE = "run_mode = 'live' AND status IN ('reserved', 'submitted', 'confirmed', 'unknown')"
DRY_ACTIVE_WHERE = "run_mode = 'dry_run' AND status = 'dry_run'"


class PurchaseAttempt(Base):
    __tablename__ = "purchase_attempts"
    __table_args__ = (
        # One live purchase per MRKT gift: the bot uses a single MRKT account, so two attempts on the
        # same gift (from different filters or users) are always a double purchase.
        Index(
            "uq_purchase_attempts_live_gift", "gift_id", unique=True, postgresql_where=text(LIVE_ACTIVE_WHERE)
        ),
        Index(
            "uq_purchase_attempts_dry_user_gift",
            "user_id",
            "gift_id",
            unique=True,
            postgresql_where=text(DRY_ACTIVE_WHERE),
        ),
        Index("ix_purchase_attempts_user_created", "user_id", "created_at"),
        Index("ix_purchase_attempts_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    filter_id: Mapped[int | None] = mapped_column(ForeignKey("filters.id", ondelete="SET NULL"))
    filter_name: Mapped[str | None] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))  # regular | monochrome | manual
    run_mode: Mapped[str] = mapped_column(String(16))  # live | dry_run
    listing_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("listings.id", ondelete="SET NULL"))
    gift_id: Mapped[str] = mapped_column(String(64))
    collection_name: Mapped[str | None] = mapped_column(String(NAME))
    model_name: Mapped[str | None] = mapped_column(String(NAME))
    backdrop_name: Mapped[str | None] = mapped_column(String(NAME))
    symbol_name: Mapped[str | None] = mapped_column(String(NAME))
    number: Mapped[int | None] = mapped_column(Integer)
    expected_price_nano: Mapped[int] = mapped_column(BigInteger)
    final_price_nano: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text)
    attempt_no: Mapped[int] = mapped_column(default=1)
    monochrome_status: Mapped[str | None] = mapped_column(String(16))
    monochrome_type: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(server_default=_now())
    updated_at: Mapped[datetime] = mapped_column(server_default=_now(), onupdate=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    response: Mapped[Json | None] = mapped_column()
    verification: Mapped[Json | None] = mapped_column()


class Purchase(Base):
    """Confirmed purchases only."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchase_attempts.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filter_id: Mapped[int | None] = mapped_column(ForeignKey("filters.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(16))
    gift_id: Mapped[str] = mapped_column(String(64))
    collection_name: Mapped[str | None] = mapped_column(String(NAME))
    model_name: Mapped[str | None] = mapped_column(String(NAME))
    price_nano: Mapped[int | None] = mapped_column(BigInteger)
    confirmed_at: Mapped[datetime] = mapped_column(server_default=_now())
    confirmation_source: Mapped[str] = mapped_column(String(32))
    mrkt_response: Mapped[Json | None] = mapped_column()


# ---------------------------------------------------------------- notifications & logs
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_notifications_user_dedup"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    dedup_key: Mapped[str] = mapped_column(String(256))
    listing_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(server_default=_now())


class ErrorLog(Base):
    __tablename__ = "error_logs"
    __table_args__ = (Index("ix_error_logs_created", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=_now())
    component: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[Json] = mapped_column(default=dict)


class AuditLog(Base):
    """Operations journal: settings changes, emergency stops, purchases."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_created", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=_now())
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[Json] = mapped_column(default=dict)


class BotState(Base):
    __tablename__ = "bot_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Json] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(server_default=_now(), onupdate=func.now())
