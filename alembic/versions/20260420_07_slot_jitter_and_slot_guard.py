"""add slot jitter and publication slot guard

Revision ID: 20260420_07
Revises: 20260420_06
Create Date: 2026-04-20 00:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260420_07"
down_revision = "20260420_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("slot_jitter_minutes", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("publication_log", sa.Column("slot_id", sa.Integer(), nullable=True))
    op.add_column("publication_log", sa.Column("slot_date", sa.Date(), nullable=True))
    op.create_index(op.f("ix_publication_log_slot_id"), "publication_log", ["slot_id"], unique=False)
    op.create_index(op.f("ix_publication_log_slot_date"), "publication_log", ["slot_date"], unique=False)
    op.create_foreign_key(
        op.f("fk_publication_log_slot_id_channel_slots"),
        "publication_log",
        "channel_slots",
        ["slot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_publication_log_channel_slot_day",
        "publication_log",
        ["channel_id", "slot_id", "slot_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_publication_log_channel_slot_day", "publication_log", type_="unique")
    op.drop_constraint(op.f("fk_publication_log_slot_id_channel_slots"), "publication_log", type_="foreignkey")
    op.drop_index(op.f("ix_publication_log_slot_date"), table_name="publication_log")
    op.drop_index(op.f("ix_publication_log_slot_id"), table_name="publication_log")
    op.drop_column("publication_log", "slot_date")
    op.drop_column("publication_log", "slot_id")
    op.drop_column("channels", "slot_jitter_minutes")
