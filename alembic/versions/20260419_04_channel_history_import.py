"""Add channel history import table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260419_04"
down_revision = "20260415_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_history_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("raw_text", sa.Text()),
        sa.Column("normalized_text", sa.Text()),
        sa.Column("text_hash", sa.String(length=64)),
        sa.Column("original_published_at", sa.DateTime(timezone=True)),
        sa.Column("imported_by", sa.BigInteger()),
        sa.Column("matched_paste_id", sa.Integer(), sa.ForeignKey("paste_library.id", ondelete="SET NULL")),
        sa.Column("match_kind", sa.String(length=16)),
        sa.Column("match_score", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("channel_id", "source_chat_id", "source_message_id"),
    )
    op.create_index("ix_channel_history_messages_channel_id", "channel_history_messages", ["channel_id"])
    op.create_index("ix_channel_history_messages_source_chat_id", "channel_history_messages", ["source_chat_id"])
    op.create_index("ix_channel_history_messages_source_message_id", "channel_history_messages", ["source_message_id"])
    op.create_index("ix_channel_history_messages_text_hash", "channel_history_messages", ["text_hash"])
    op.create_index("ix_channel_history_messages_normalized_text", "channel_history_messages", ["normalized_text"])
    op.create_index("ix_channel_history_messages_original_published_at", "channel_history_messages", ["original_published_at"])
    op.create_index("ix_channel_history_messages_matched_paste_id", "channel_history_messages", ["matched_paste_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_history_messages_matched_paste_id", table_name="channel_history_messages")
    op.drop_index("ix_channel_history_messages_original_published_at", table_name="channel_history_messages")
    op.drop_index("ix_channel_history_messages_normalized_text", table_name="channel_history_messages")
    op.drop_index("ix_channel_history_messages_text_hash", table_name="channel_history_messages")
    op.drop_index("ix_channel_history_messages_source_message_id", table_name="channel_history_messages")
    op.drop_index("ix_channel_history_messages_source_chat_id", table_name="channel_history_messages")
    op.drop_index("ix_channel_history_messages_channel_id", table_name="channel_history_messages")
    op.drop_table("channel_history_messages")
