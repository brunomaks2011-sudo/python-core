"""Initial schema: users, settings, filters, budgets, Gift Wiki reference, MRKT market data, purchases, logs.

Revision ID: 0001
Revises:
Create Date: 2026-10-23 14:17:05.903328
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_created", "audit_log", ["created_at"], unique=False)
    op.create_table(
        "bot_state",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_bot_state")),
    )
    op.create_table(
        "collection_mappings",
        sa.Column("mrkt_collection_name", sa.String(length=128), nullable=False),
        sa.Column("giftwiki_gift_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("mrkt_collection_name", name=op.f("pk_collection_mappings")),
    )
    op.create_table(
        "error_logs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_error_logs")),
    )
    op.create_index("ix_error_logs_created", "error_logs", ["created_at"], unique=False)
    op.create_table(
        "feed_events",
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("amount_nano", sa.BigInteger(), nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_feed_events")),
    )
    op.create_index("ix_feed_events_received", "feed_events", ["received_at"], unique=False)
    op.create_table(
        "gift_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_name", sa.String(length=128), nullable=False),
        sa.Column("collection_norm", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_norm", sa.String(length=128), nullable=False),
        sa.Column("rarity_permille", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gift_models")),
        sa.UniqueConstraint("collection_norm", "model_norm", name="uq_gift_models_key"),
    )
    op.create_table(
        "gifts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("collection_name", sa.String(length=128), nullable=True),
        sa.Column("collection_title", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("backdrop_name", sa.String(length=128), nullable=True),
        sa.Column("symbol_name", sa.String(length=128), nullable=True),
        sa.Column("model_rarity_permille", sa.Integer(), nullable=True),
        sa.Column("backdrop_rarity_permille", sa.Integer(), nullable=True),
        sa.Column("symbol_rarity_permille", sa.Integer(), nullable=True),
        sa.Column("backdrop_center_color", sa.Integer(), nullable=True),
        sa.Column("backdrop_edge_color", sa.Integer(), nullable=True),
        sa.Column("monochrome_status", sa.String(length=16), server_default="UNKNOWN", nullable=False),
        sa.Column("monochrome_type", sa.String(length=16), nullable=True),
        sa.Column("monochrome_record_id", sa.String(length=64), nullable=True),
        sa.Column("monochrome_reason", sa.Text(), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gifts")),
    )
    op.create_index("ix_gifts_collection_model", "gifts", ["collection_name", "model_name"], unique=False)
    op.create_table(
        "giftwiki_gifts",
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("gift_name", sa.String(length=128), nullable=True),
        sa.Column("name_norm", sa.String(length=128), nullable=False),
        sa.Column("records_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("coverage_complete", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("coverage_source", sa.String(length=32), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("gift_id", name=op.f("pk_giftwiki_gifts")),
    )
    op.create_index(op.f("ix_giftwiki_gifts_name_norm"), "giftwiki_gifts", ["name_norm"], unique=False)
    op.create_table(
        "giftwiki_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_fetched", sa.Integer(), nullable=False),
        sa.Column("records_fetched", sa.Integer(), nullable=False),
        sa.Column("gifts_covered", sa.Integer(), nullable=False),
        sa.Column("records_added", sa.Integer(), nullable=False),
        sa.Column("records_removed", sa.Integer(), nullable=False),
        sa.Column("lookups_done", sa.Integer(), nullable=False),
        sa.Column("lookups_failed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_giftwiki_sync_runs")),
    )
    op.create_table(
        "mrkt_collections",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("floor_price_nano", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_mrkt_collections")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=256), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_purchase", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("per_purchase_limit_nano", sa.BigInteger(), nullable=True),
        sa.Column("daily_limit_nano", sa.BigInteger(), nullable=True),
        sa.Column("total_limit_nano", sa.BigInteger(), nullable=True),
        sa.Column("period_max_count", sa.Integer(), nullable=True),
        sa.Column("period_hours", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_budgets_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
        sa.UniqueConstraint("user_id", "scope", name="uq_budgets_user_scope"),
    )
    op.create_table(
        "filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("autobuy", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "limits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_filters_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_filters")),
    )
    op.create_index("ix_filters_enabled_kind", "filters", ["enabled", "kind"], unique=False)
    op.create_index(op.f("ix_filters_user_id"), "filters", ["user_id"], unique=False)
    op.create_table(
        "giftwiki_attributes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("name_norm", sa.String(length=128), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["gift_id"],
            ["giftwiki_gifts.gift_id"],
            name=op.f("fk_giftwiki_attributes_gift_id_giftwiki_gifts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_giftwiki_attributes")),
        sa.UniqueConstraint("gift_id", "kind", "name_norm", name="uq_giftwiki_attributes_key"),
    )
    op.create_table(
        "giftwiki_monochromes",
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("gift_name", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("model_norm", sa.String(length=128), nullable=False),
        sa.Column("backdrop_name", sa.String(length=128), nullable=True),
        sa.Column("backdrop_norm", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=True),
        sa.Column("center_color", sa.String(length=32), nullable=True),
        sa.Column("edge_color", sa.String(length=32), nullable=True),
        sa.Column("pattern_color", sa.String(length=32), nullable=True),
        sa.Column("text_color", sa.String(length=32), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("animation_url", sa.Text(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["gift_id"],
            ["giftwiki_gifts.gift_id"],
            name=op.f("fk_giftwiki_monochromes_gift_id_giftwiki_gifts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id", name=op.f("pk_giftwiki_monochromes")),
    )
    op.create_index(
        "ix_giftwiki_monochromes_lookup",
        "giftwiki_monochromes",
        ["gift_id", "model_norm", "backdrop_norm"],
        unique=False,
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("price_nano", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("collection_name", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("monochrome_status", sa.String(length=16), server_default="UNKNOWN", nullable=False),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=True),
        sa.Column("detection_latency_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["gift_id"], ["gifts.id"], name=op.f("fk_listings_gift_id_gifts"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_listings")),
    )
    op.create_index("ix_listings_collection_status", "listings", ["collection_name", "status"], unique=False)
    op.create_index("ix_listings_first_seen", "listings", ["first_seen_at"], unique=False)
    op.create_index("ix_listings_status_price", "listings", ["status", "price_nano"], unique=False)
    op.create_index(
        "uq_listings_active_gift",
        "listings",
        ["gift_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedup_key", sa.String(length=256), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("user_id", "dedup_key", name="uq_notifications_user_dedup"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"], unique=False)
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("autobuy_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "monochrome_autobuy_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("purchases_paused", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "notify",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_settings_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_settings")),
    )
    op.create_table(
        "filter_hits",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("filter_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("price_nano", sa.BigInteger(), nullable=True),
        sa.Column("monochrome_status", sa.String(length=16), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["filter_id"], ["filters.id"], name=op.f("fk_filter_hits_filter_id_filters"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name=op.f("fk_filter_hits_listing_id_listings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_filter_hits")),
        sa.UniqueConstraint(
            "filter_id",
            "listing_id",
            "price_nano",
            name="uq_filter_hits_key",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_filter_hits_user_matched", "filter_hits", ["user_id", "matched_at"], unique=False)
    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=True),
        sa.Column("collection_norm", sa.String(length=128), nullable=False),
        sa.Column("model_norm", sa.String(length=128), nullable=False),
        sa.Column("price_nano", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["gift_id"], ["gifts.id"], name=op.f("fk_price_history_gift_id_gifts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name=op.f("fk_price_history_listing_id_listings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_history")),
    )
    op.create_index(
        "ix_price_history_comparable",
        "price_history",
        ["collection_norm", "model_norm", "observed_at"],
        unique=False,
    )
    op.create_index("ix_price_history_gift", "price_history", ["gift_id", "observed_at"], unique=False)
    op.create_table(
        "purchase_attempts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("filter_id", sa.Integer(), nullable=True),
        sa.Column("filter_name", sa.String(length=64), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("run_mode", sa.String(length=16), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=True),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("collection_name", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("backdrop_name", sa.String(length=128), nullable=True),
        sa.Column("symbol_name", sa.String(length=128), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("expected_price_nano", sa.BigInteger(), nullable=False),
        sa.Column("final_price_nano", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("monochrome_status", sa.String(length=16), nullable=True),
        sa.Column("monochrome_type", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("verification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["filter_id"],
            ["filters.id"],
            name=op.f("fk_purchase_attempts_filter_id_filters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name=op.f("fk_purchase_attempts_listing_id_listings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_purchase_attempts_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_attempts")),
    )
    op.create_index("ix_purchase_attempts_status", "purchase_attempts", ["status"], unique=False)
    op.create_index(
        "ix_purchase_attempts_user_created", "purchase_attempts", ["user_id", "created_at"], unique=False
    )
    op.create_index(
        "uq_purchase_attempts_dry_user_gift",
        "purchase_attempts",
        ["user_id", "gift_id"],
        unique=True,
        postgresql_where=sa.text("run_mode = 'dry_run' AND status = 'dry_run'"),
    )
    op.create_index(
        "uq_purchase_attempts_live_gift",
        "purchase_attempts",
        ["gift_id"],
        unique=True,
        postgresql_where=sa.text(
            "run_mode = 'live' AND status IN ('reserved', 'submitted', 'confirmed', 'unknown')"
        ),
    )
    op.create_table(
        "purchases",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("filter_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("collection_name", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("price_nano", sa.BigInteger(), nullable=True),
        sa.Column(
            "confirmed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("confirmation_source", sa.String(length=32), nullable=False),
        sa.Column("mrkt_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["purchase_attempts.id"],
            name=op.f("fk_purchases_attempt_id_purchase_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["filter_id"], ["filters.id"], name=op.f("fk_purchases_filter_id_filters"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_purchases_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchases")),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_purchases_attempt_id")),
    )
    op.create_index(op.f("ix_purchases_user_id"), "purchases", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_purchases_user_id"), table_name="purchases")
    op.drop_table("purchases")
    op.drop_index(
        "uq_purchase_attempts_live_gift",
        table_name="purchase_attempts",
        postgresql_where=sa.text(
            "run_mode = 'live' AND status IN ('reserved', 'submitted', 'confirmed', 'unknown')"
        ),
    )
    op.drop_index(
        "uq_purchase_attempts_dry_user_gift",
        table_name="purchase_attempts",
        postgresql_where=sa.text("run_mode = 'dry_run' AND status = 'dry_run'"),
    )
    op.drop_index("ix_purchase_attempts_user_created", table_name="purchase_attempts")
    op.drop_index("ix_purchase_attempts_status", table_name="purchase_attempts")
    op.drop_table("purchase_attempts")
    op.drop_index("ix_price_history_gift", table_name="price_history")
    op.drop_index("ix_price_history_comparable", table_name="price_history")
    op.drop_table("price_history")
    op.drop_index("ix_filter_hits_user_matched", table_name="filter_hits")
    op.drop_table("filter_hits")
    op.drop_table("user_settings")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(
        "uq_listings_active_gift", table_name="listings", postgresql_where=sa.text("status = 'active'")
    )
    op.drop_index("ix_listings_status_price", table_name="listings")
    op.drop_index("ix_listings_first_seen", table_name="listings")
    op.drop_index("ix_listings_collection_status", table_name="listings")
    op.drop_table("listings")
    op.drop_index("ix_giftwiki_monochromes_lookup", table_name="giftwiki_monochromes")
    op.drop_table("giftwiki_monochromes")
    op.drop_table("giftwiki_attributes")
    op.drop_index(op.f("ix_filters_user_id"), table_name="filters")
    op.drop_index("ix_filters_enabled_kind", table_name="filters")
    op.drop_table("filters")
    op.drop_table("budgets")
    op.drop_table("users")
    op.drop_table("mrkt_collections")
    op.drop_table("giftwiki_sync_runs")
    op.drop_index(op.f("ix_giftwiki_gifts_name_norm"), table_name="giftwiki_gifts")
    op.drop_table("giftwiki_gifts")
    op.drop_index("ix_gifts_collection_model", table_name="gifts")
    op.drop_table("gifts")
    op.drop_table("gift_models")
    op.drop_index("ix_feed_events_received", table_name="feed_events")
    op.drop_table("feed_events")
    op.drop_index("ix_error_logs_created", table_name="error_logs")
    op.drop_table("error_logs")
    op.drop_table("collection_mappings")
    op.drop_table("bot_state")
    op.drop_index("ix_audit_log_created", table_name="audit_log")
    op.drop_table("audit_log")
