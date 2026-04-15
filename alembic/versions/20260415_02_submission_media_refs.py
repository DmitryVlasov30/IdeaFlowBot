"""Add submission media reference metadata."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260415_02"
down_revision = "20260413_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("content_type", sa.String(length=32), nullable=False, server_default="text"),
    )
    op.add_column(
        "submissions",
        sa.Column("media_group_id", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_submissions_content_type", "submissions", ["content_type"])
    op.create_index("ix_submissions_media_group_id", "submissions", ["media_group_id"])


def downgrade() -> None:
    op.drop_index("ix_submissions_media_group_id", table_name="submissions")
    op.drop_index("ix_submissions_content_type", table_name="submissions")
    op.drop_column("submissions", "media_group_id")
    op.drop_column("submissions", "content_type")
