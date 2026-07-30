"""add minimum auto slots per day

Revision ID: 20260730_15
Revises: 20260730_14
Create Date: 2026-07-30 02:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_15"
down_revision = "20260730_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("min_slots_per_day", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "channel_setting_profiles",
        sa.Column("min_slots_per_day", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("UPDATE channel_setting_profiles SET min_slots_per_day = 2 WHERE slug = 'starter'")
    op.execute("UPDATE channel_setting_profiles SET min_slots_per_day = 3 WHERE slug = 'growing'")
    op.execute("UPDATE channel_setting_profiles SET min_slots_per_day = 4 WHERE slug = 'active'")
    op.execute("UPDATE channel_setting_profiles SET min_slots_per_day = 5 WHERE slug = 'large'")


def downgrade() -> None:
    op.drop_column("channel_setting_profiles", "min_slots_per_day")
    op.drop_column("channels", "min_slots_per_day")
