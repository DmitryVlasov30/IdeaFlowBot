"""add global paste tag rules

Revision ID: 20260713_11
Revises: 20260713_10
Create Date: 2026-07-13 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260713_11"
down_revision = "20260713_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    channel_rule_mode = postgresql.ENUM("include", "exclude", name="channel_paste_tag_rule_mode", create_type=False)

    op.create_table(
        "global_paste_tag_rules",
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tag_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", channel_rule_mode, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tag_id", "mode"),
    )
    op.create_index("ix_global_paste_tag_rules_tag_id", "global_paste_tag_rules", ["tag_id"])
    op.create_index("ix_global_paste_tag_rules_mode", "global_paste_tag_rules", ["mode"])
    op.create_index("ix_global_paste_tag_rules_is_active", "global_paste_tag_rules", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_global_paste_tag_rules_is_active", table_name="global_paste_tag_rules")
    op.drop_index("ix_global_paste_tag_rules_mode", table_name="global_paste_tag_rules")
    op.drop_index("ix_global_paste_tag_rules_tag_id", table_name="global_paste_tag_rules")
    op.drop_table("global_paste_tag_rules")
