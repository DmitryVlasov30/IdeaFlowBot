"""add confession paste publisher and content families

Revision ID: 20260827_20
Revises: 20260822_19
Create Date: 2026-08-27 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260827_20"
down_revision = "20260822_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("content_family", sa.String(length=32), server_default="overheard", nullable=False),
    )
    op.create_index(op.f("ix_channels_content_family"), "channels", ["content_family"])

    op.add_column(
        "paste_library",
        sa.Column("content_family", sa.String(length=32), server_default="overheard", nullable=False),
    )
    op.add_column(
        "paste_library",
        sa.Column("delivery_mode", sa.String(length=32), server_default="text", nullable=False),
    )
    op.add_column("paste_library", sa.Column("storage_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("paste_library", sa.Column("storage_message_id", sa.BigInteger(), nullable=True))
    op.add_column("paste_library", sa.Column("storage_content_type", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_paste_library_content_family"), "paste_library", ["content_family"])
    op.create_index(op.f("ix_paste_library_delivery_mode"), "paste_library", ["delivery_mode"])
    op.create_index(op.f("ix_paste_library_storage_chat_id"), "paste_library", ["storage_chat_id"])
    op.create_unique_constraint(
        "uq_paste_library_storage_message",
        "paste_library",
        ["storage_chat_id", "storage_message_id"],
    )

    op.create_table(
        "confession_publishers",
        sa.Column("bot_api_token", sa.Text(), nullable=False),
        sa.Column("bot_user_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_username", sa.String(length=255), nullable=True),
        sa.Column("storage_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("storage_chat_title", sa.String(length=255), nullable=True),
        sa.Column("bind_code", sa.String(length=32), nullable=True),
        sa.Column("bind_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_confession_publishers")),
        sa.UniqueConstraint("bot_api_token", name=op.f("uq_confession_publishers_bot_api_token")),
        sa.UniqueConstraint("bot_user_id", name=op.f("uq_confession_publishers_bot_user_id")),
    )
    op.create_index(op.f("ix_confession_publishers_bind_code"), "confession_publishers", ["bind_code"])
    op.create_index(op.f("ix_confession_publishers_is_active"), "confession_publishers", ["is_active"])
    op.create_index(op.f("ix_confession_publishers_storage_chat_id"), "confession_publishers", ["storage_chat_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_confession_publishers_storage_chat_id"), table_name="confession_publishers")
    op.drop_index(op.f("ix_confession_publishers_is_active"), table_name="confession_publishers")
    op.drop_index(op.f("ix_confession_publishers_bind_code"), table_name="confession_publishers")
    op.drop_table("confession_publishers")

    op.drop_constraint("uq_paste_library_storage_message", "paste_library", type_="unique")
    op.drop_index(op.f("ix_paste_library_storage_chat_id"), table_name="paste_library")
    op.drop_index(op.f("ix_paste_library_delivery_mode"), table_name="paste_library")
    op.drop_index(op.f("ix_paste_library_content_family"), table_name="paste_library")
    op.drop_column("paste_library", "storage_content_type")
    op.drop_column("paste_library", "storage_message_id")
    op.drop_column("paste_library", "storage_chat_id")
    op.drop_column("paste_library", "delivery_mode")
    op.drop_column("paste_library", "content_family")

    op.drop_index(op.f("ix_channels_content_family"), table_name="channels")
    op.drop_column("channels", "content_family")
