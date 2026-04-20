"""add notification subscriptions

Revision ID: 20260419_05
Revises: 20260419_04
Create Date: 2026-04-19 22:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260419_05"
down_revision = "20260419_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_subscriptions",
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_subscriptions")),
        sa.UniqueConstraint("channel_id", "user_id", name="uq_notification_subscriptions_channel_id_user_id"),
    )
    op.create_index(op.f("ix_notification_subscriptions_channel_id"), "notification_subscriptions", ["channel_id"], unique=False)
    op.create_index(op.f("ix_notification_subscriptions_user_id"), "notification_subscriptions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_subscriptions_user_id"), table_name="notification_subscriptions")
    op.drop_index(op.f("ix_notification_subscriptions_channel_id"), table_name="notification_subscriptions")
    op.drop_table("notification_subscriptions")
