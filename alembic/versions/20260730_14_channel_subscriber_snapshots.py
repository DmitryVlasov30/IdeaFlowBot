"""add channel subscriber snapshots

Revision ID: 20260730_14
Revises: 20260730_13
Create Date: 2026-07-30 00:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_14"
down_revision = "20260730_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_subscriber_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscriber_count", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        op.f("ix_channel_subscriber_snapshots_channel_id"),
        "channel_subscriber_snapshots",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_subscriber_snapshots_checked_at"),
        "channel_subscriber_snapshots",
        ["checked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_channel_subscriber_snapshots_checked_at"), table_name="channel_subscriber_snapshots")
    op.drop_index(op.f("ix_channel_subscriber_snapshots_channel_id"), table_name="channel_subscriber_snapshots")
    op.drop_table("channel_subscriber_snapshots")
