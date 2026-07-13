"""update default channel paste policy

Revision ID: 20260421_09
Revises: 20260420_08
Create Date: 2026-04-21 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_09"
down_revision = "20260420_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("channels", "slot_jitter_minutes", server_default=sa.text("30"))
    op.alter_column("channels", "max_paste_per_day", server_default=sa.text("3"))
    op.alter_column("channels", "same_tag_cooldown_hours", server_default=sa.text("0"))
    op.alter_column("channels", "same_template_cooldown_hours", server_default=sa.text("0"))
    op.alter_column("channels", "same_paste_cooldown_days", server_default=sa.text("120"))
    op.alter_column("paste_library", "per_channel_cooldown_days", server_default=sa.text("120"))


def downgrade() -> None:
    op.alter_column("paste_library", "per_channel_cooldown_days", server_default=sa.text("90"))
    op.alter_column("channels", "same_paste_cooldown_days", server_default=sa.text("30"))
    op.alter_column("channels", "same_template_cooldown_hours", server_default=sa.text("72"))
    op.alter_column("channels", "same_tag_cooldown_hours", server_default=sa.text("48"))
    op.alter_column("channels", "max_paste_per_day", server_default=sa.text("2"))
    op.alter_column("channels", "slot_jitter_minutes", server_default=sa.text("0"))
