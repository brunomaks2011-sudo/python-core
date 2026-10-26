"""Positions of the resale assistant: gifts bought to sell again.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resale_positions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=True),
        sa.Column("run_mode", sa.String(length=16), nullable=False),
        sa.Column("gift_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("collection_name", sa.String(length=128), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("backdrop_name", sa.String(length=128), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("buy_price_nano", sa.BigInteger(), nullable=False),
        sa.Column("target_price_nano", sa.BigInteger(), nullable=True),
        sa.Column("list_price_nano", sa.BigInteger(), nullable=True),
        sa.Column("fee_permille", sa.Integer(), nullable=False),
        sa.Column("expected_profit_nano", sa.BigInteger(), nullable=True),
        sa.Column("sales_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("tries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("resale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sold_price_nano", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["purchase_attempts.id"],
            name=op.f("fk_resale_positions_attempt_id_purchase_attempts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_resale_positions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resale_positions")),
    )
    op.create_index("ix_resale_positions_gift", "resale_positions", ["gift_id"], unique=False)
    op.create_index("ix_resale_positions_status", "resale_positions", ["status"], unique=False)
    op.create_index(
        "ix_resale_positions_user_created", "resale_positions", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_resale_positions_user_created", table_name="resale_positions")
    op.drop_index("ix_resale_positions_status", table_name="resale_positions")
    op.drop_index("ix_resale_positions_gift", table_name="resale_positions")
    op.drop_table("resale_positions")
