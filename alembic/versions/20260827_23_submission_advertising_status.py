"""add advertising submission status

Revision ID: 20260827_23
Revises: 20260827_22
Create Date: 2026-08-27 20:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260827_23"
down_revision = "20260827_22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE submission_status ADD VALUE IF NOT EXISTS 'advertising'")


def downgrade() -> None:
    op.execute(
        "UPDATE submissions SET status = 'hold' "
        "WHERE status::text = 'advertising'"
    )
    op.execute("ALTER TABLE submissions ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE submission_status RENAME TO submission_status_old")
    op.execute(
        "CREATE TYPE submission_status AS ENUM ("
        "'new', "
        "'approved_as_source', "
        "'paste_candidate', "
        "'content_created', "
        "'rejected', "
        "'hold'"
        ")"
    )
    op.execute(
        "ALTER TABLE submissions ALTER COLUMN status TYPE submission_status "
        "USING status::text::submission_status"
    )
    op.execute(
        "ALTER TABLE submissions ALTER COLUMN status "
        "SET DEFAULT 'new'::submission_status"
    )
    op.execute("DROP TYPE submission_status_old")
