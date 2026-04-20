"""add channel ad blackouts

Revision ID: 20260420_08
Revises: 20260420_07
Create Date: 2026-04-20 17:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_08"
down_revision = "20260420_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_ad_blackouts",
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_ad_blackouts")),
        sa.UniqueConstraint("channel_id", "starts_at", "ends_at", name="uq_channel_ad_blackouts_window"),
    )
    op.create_index(op.f("ix_channel_ad_blackouts_channel_id"), "channel_ad_blackouts", ["channel_id"], unique=False)
    op.create_index(op.f("ix_channel_ad_blackouts_starts_at"), "channel_ad_blackouts", ["starts_at"], unique=False)
    op.create_index(op.f("ix_channel_ad_blackouts_ends_at"), "channel_ad_blackouts", ["ends_at"], unique=False)
    op.create_index(op.f("ix_channel_ad_blackouts_created_by"), "channel_ad_blackouts", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_channel_ad_blackouts_created_by"), table_name="channel_ad_blackouts")
    op.drop_index(op.f("ix_channel_ad_blackouts_ends_at"), table_name="channel_ad_blackouts")
    op.drop_index(op.f("ix_channel_ad_blackouts_starts_at"), table_name="channel_ad_blackouts")
    op.drop_index(op.f("ix_channel_ad_blackouts_channel_id"), table_name="channel_ad_blackouts")
    op.drop_table("channel_ad_blackouts")
