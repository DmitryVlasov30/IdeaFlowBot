"""Add submission anonymous moderation flag."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260415_03"
down_revision = "20260415_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("submissions", "is_anonymous")
