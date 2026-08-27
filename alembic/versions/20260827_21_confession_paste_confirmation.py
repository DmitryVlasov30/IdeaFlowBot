"""add confirmation queue for confession pastes

Revision ID: 20260827_21
Revises: 20260827_20
Create Date: 2026-08-27 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260827_21"
down_revision = "20260827_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "confession_paste_candidates",
        sa.Column("publisher_id", sa.Integer(), nullable=False),
        sa.Column("storage_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("storage_message_id", sa.BigInteger(), nullable=False),
        sa.Column("prompt_message_id", sa.BigInteger(), nullable=True),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("paste_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["paste_id"],
            ["paste_library.id"],
            name=op.f("fk_confession_paste_candidates_paste_id_paste_library"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["publisher_id"],
            ["confession_publishers.id"],
            name=op.f("fk_confession_paste_candidates_publisher_id_confession_publishers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_confession_paste_candidates")),
        sa.UniqueConstraint(
            "storage_chat_id",
            "storage_message_id",
            name="uq_confession_paste_candidates_storage_message",
        ),
    )
    op.create_index(
        op.f("ix_confession_paste_candidates_paste_id"),
        "confession_paste_candidates",
        ["paste_id"],
    )
    op.create_index(
        op.f("ix_confession_paste_candidates_publisher_id"),
        "confession_paste_candidates",
        ["publisher_id"],
    )
    op.create_index(
        op.f("ix_confession_paste_candidates_status"),
        "confession_paste_candidates",
        ["status"],
    )
    op.create_index(
        op.f("ix_confession_paste_candidates_storage_chat_id"),
        "confession_paste_candidates",
        ["storage_chat_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_confession_paste_candidates_storage_chat_id"),
        table_name="confession_paste_candidates",
    )
    op.drop_index(
        op.f("ix_confession_paste_candidates_status"),
        table_name="confession_paste_candidates",
    )
    op.drop_index(
        op.f("ix_confession_paste_candidates_publisher_id"),
        table_name="confession_paste_candidates",
    )
    op.drop_index(
        op.f("ix_confession_paste_candidates_paste_id"),
        table_name="confession_paste_candidates",
    )
    op.drop_table("confession_paste_candidates")
