"""add MCP moderation audit actions

Revision ID: 20260827_22
Revises: 20260827_21
Create Date: 2026-08-27 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260827_22"
down_revision = "20260827_21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_moderation_actions",
        sa.Column("request_id", sa.String(length=160), nullable=False),
        sa.Column("batch_id", sa.String(length=120), nullable=False),
        sa.Column("requested_submission_id", sa.BigInteger(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("expected_status", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("resulting_status", sa.String(length=32), nullable=True),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("content_item_id", sa.Integer(), nullable=True),
        sa.Column("legacy_sync_count", sa.Integer(), nullable=False),
        sa.Column("warning_text", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_mcp_moderation_actions_channel_id_channels"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["content_item_id"],
            ["content_items.id"],
            name=op.f("fk_mcp_moderation_actions_content_item_id_content_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_mcp_moderation_actions_submission_id_submissions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_moderation_actions")),
        sa.UniqueConstraint("request_id", name=op.f("uq_mcp_moderation_actions_request_id")),
    )
    op.create_index(op.f("ix_mcp_moderation_actions_batch_id"), "mcp_moderation_actions", ["batch_id"])
    op.create_index(op.f("ix_mcp_moderation_actions_channel_id"), "mcp_moderation_actions", ["channel_id"])
    op.create_index(
        op.f("ix_mcp_moderation_actions_content_item_id"),
        "mcp_moderation_actions",
        ["content_item_id"],
    )
    op.create_index(op.f("ix_mcp_moderation_actions_created_at"), "mcp_moderation_actions", ["created_at"])
    op.create_index(op.f("ix_mcp_moderation_actions_decision"), "mcp_moderation_actions", ["decision"])
    op.create_index(op.f("ix_mcp_moderation_actions_outcome"), "mcp_moderation_actions", ["outcome"])
    op.create_index(
        op.f("ix_mcp_moderation_actions_requested_submission_id"),
        "mcp_moderation_actions",
        ["requested_submission_id"],
    )
    op.create_index(
        op.f("ix_mcp_moderation_actions_submission_id"),
        "mcp_moderation_actions",
        ["submission_id"],
    )
    op.create_index(op.f("ix_mcp_moderation_actions_completed_at"), "mcp_moderation_actions", ["completed_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_mcp_moderation_actions_completed_at"), table_name="mcp_moderation_actions")
    op.drop_index(
        op.f("ix_mcp_moderation_actions_requested_submission_id"),
        table_name="mcp_moderation_actions",
    )
    op.drop_index(op.f("ix_mcp_moderation_actions_submission_id"), table_name="mcp_moderation_actions")
    op.drop_index(op.f("ix_mcp_moderation_actions_outcome"), table_name="mcp_moderation_actions")
    op.drop_index(op.f("ix_mcp_moderation_actions_decision"), table_name="mcp_moderation_actions")
    op.drop_index(op.f("ix_mcp_moderation_actions_created_at"), table_name="mcp_moderation_actions")
    op.drop_index(op.f("ix_mcp_moderation_actions_content_item_id"), table_name="mcp_moderation_actions")
    op.drop_index(op.f("ix_mcp_moderation_actions_channel_id"), table_name="mcp_moderation_actions")
    op.drop_index(op.f("ix_mcp_moderation_actions_batch_id"), table_name="mcp_moderation_actions")
    op.drop_table("mcp_moderation_actions")
