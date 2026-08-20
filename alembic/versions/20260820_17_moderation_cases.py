"""add idempotent moderation cases

Revision ID: 20260820_17
Revises: 20260820_16
Create Date: 2026-08-20 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_17"
down_revision = "20260820_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moderation_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("case_key", sa.String(length=255), nullable=False),
        sa.Column("canonical_submission_id", sa.Integer(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("channel_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("source_user_id", sa.BigInteger(), nullable=True),
        sa.Column("source_username", sa.String(length=255), nullable=True),
        sa.Column("source_first_name", sa.String(length=255), nullable=True),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("media_group_id", sa.String(length=255), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("moderator_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["canonical_submission_id"], ["submissions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_key"),
    )
    op.create_index("ix_moderation_cases_canonical_submission_id", "moderation_cases", ["canonical_submission_id"])
    op.create_index("ix_moderation_cases_channel_id", "moderation_cases", ["channel_id"])
    op.create_index("ix_moderation_cases_source_user_id", "moderation_cases", ["source_user_id"])
    op.create_index("ix_moderation_cases_moderator_id", "moderation_cases", ["moderator_id"])
    op.create_index("ix_moderation_cases_decision", "moderation_cases", ["decision"])
    op.create_index("ix_moderation_cases_decided_at", "moderation_cases", ["decided_at"])
    op.create_index("ix_moderation_cases_finalized_at", "moderation_cases", ["finalized_at"])
    op.create_index("ix_moderation_cases_voided_at", "moderation_cases", ["voided_at"])
    op.create_index(
        "ix_moderation_cases_payable_month",
        "moderation_cases",
        ["finalized_at", "moderator_id", "decision"],
        postgresql_where=sa.text("voided_at IS NULL AND finalized_at IS NOT NULL"),
    )

    op.create_table(
        "moderation_case_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("moderator_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["moderation_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_moderation_case_events_case_id", "moderation_case_events", ["case_id"])
    op.create_index("ix_moderation_case_events_moderator_id", "moderation_case_events", ["moderator_id"])
    op.create_index("ix_moderation_case_events_event_type", "moderation_case_events", ["event_type"])
    op.create_index("ix_moderation_case_events_occurred_at", "moderation_case_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_moderation_case_events_occurred_at", table_name="moderation_case_events")
    op.drop_index("ix_moderation_case_events_event_type", table_name="moderation_case_events")
    op.drop_index("ix_moderation_case_events_moderator_id", table_name="moderation_case_events")
    op.drop_index("ix_moderation_case_events_case_id", table_name="moderation_case_events")
    op.drop_table("moderation_case_events")

    op.drop_index("ix_moderation_cases_payable_month", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_voided_at", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_finalized_at", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_decided_at", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_decision", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_moderator_id", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_source_user_id", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_channel_id", table_name="moderation_cases")
    op.drop_index("ix_moderation_cases_canonical_submission_id", table_name="moderation_cases")
    op.drop_table("moderation_cases")
