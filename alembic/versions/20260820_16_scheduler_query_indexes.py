"""add scheduler query indexes

Revision ID: 20260820_16
Revises: 20260730_15
Create Date: 2026-08-20 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_16"
down_revision = "20260730_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_paste_usage_paste_channel_used_at",
        "paste_usage",
        ["paste_id", "channel_id", sa.text("used_at DESC")],
    )
    op.create_index(
        "ix_paste_usage_paste_used_at",
        "paste_usage",
        ["paste_id", sa.text("used_at DESC")],
    )
    op.create_index(
        "ix_publication_log_channel_status_scheduled_for",
        "publication_log",
        ["channel_id", "publish_status", sa.text("scheduled_for DESC")],
    )
    op.create_index(
        "ix_publication_log_due_scheduled",
        "publication_log",
        ["scheduled_for"],
        postgresql_where=sa.text("publish_status = 'scheduled'"),
    )
    op.create_index(
        "ix_content_items_channel_status_source_created",
        "content_items",
        ["channel_id", "status", "source_type", "created_at"],
    )
    op.create_index(
        "ix_channel_slots_channel_active_weekday_time",
        "channel_slots",
        ["channel_id", "is_active", "weekday", "slot_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_slots_channel_active_weekday_time", table_name="channel_slots")
    op.drop_index("ix_content_items_channel_status_source_created", table_name="content_items")
    op.drop_index("ix_publication_log_due_scheduled", table_name="publication_log")
    op.drop_index("ix_publication_log_channel_status_scheduled_for", table_name="publication_log")
    op.drop_index("ix_paste_usage_paste_used_at", table_name="paste_usage")
    op.drop_index("ix_paste_usage_paste_channel_used_at", table_name="paste_usage")
