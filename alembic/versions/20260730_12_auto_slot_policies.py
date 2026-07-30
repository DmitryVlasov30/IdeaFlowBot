"""add automatic slot policies

Revision ID: 20260730_12
Revises: 20260713_11
Create Date: 2026-07-30 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_12"
down_revision = "20260713_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("auto_slots_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "channels",
        sa.Column("auto_slots_plan_time", sa.Time(), server_default="23:30", nullable=False),
    )
    op.add_column(
        "channels",
        sa.Column("auto_slots_window_start", sa.Time(), server_default="10:00", nullable=False),
    )
    op.add_column(
        "channels",
        sa.Column("auto_slots_window_end", sa.Time(), server_default="22:00", nullable=False),
    )
    op.add_column(
        "channels",
        sa.Column("auto_slots_replace_manual", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("channels", sa.Column("auto_slots_last_planned_for", sa.Date(), nullable=True))
    op.add_column(
        "channel_slots",
        sa.Column("is_auto_managed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("channel_slots", "is_auto_managed")
    op.drop_column("channels", "auto_slots_last_planned_for")
    op.drop_column("channels", "auto_slots_replace_manual")
    op.drop_column("channels", "auto_slots_window_end")
    op.drop_column("channels", "auto_slots_window_start")
    op.drop_column("channels", "auto_slots_plan_time")
    op.drop_column("channels", "auto_slots_enabled")
