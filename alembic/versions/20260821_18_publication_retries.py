"""add durable publication retries

Revision ID: 20260821_18
Revises: 20260820_17
Create Date: 2026-08-21 01:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260821_18"
down_revision = "20260820_17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "publication_log",
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "publication_log",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "publication_log",
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_publication_log_retry_after", "publication_log", ["retry_after"])
    op.create_index(
        "ix_publication_log_retry_due",
        "publication_log",
        ["retry_after", "scheduled_for"],
        postgresql_where=sa.text("publish_status = 'scheduled'"),
    )


def downgrade() -> None:
    op.drop_index("ix_publication_log_retry_due", table_name="publication_log")
    op.drop_index("ix_publication_log_retry_after", table_name="publication_log")
    op.drop_column("publication_log", "retry_after")
    op.drop_column("publication_log", "last_attempt_at")
    op.drop_column("publication_log", "attempt_count")
