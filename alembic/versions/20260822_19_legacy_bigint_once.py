"""migrate legacy integer columns once

Revision ID: 20260822_19
Revises: 20260821_18
Create Date: 2026-08-22 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260822_19"
down_revision = "20260821_18"
branch_labels = None
depends_on = None


LEGACY_BIGINT_COLUMNS = {
    "admin_actions_data": ["message_id", "chat_id", "admin_id", "timestamp"],
    "advertising": ["channel_id", "post_id", "time"],
    "anonym_message": ["message_id", "chat_id"],
    "banned_user": ["id_user", "id_channel", "bot_id"],
    "bots_data": ["channel_id"],
    "bot_admins": ["user_id"],
    "chat_admins": ["bot_id", "chat_id"],
    "delayed_posts": ["bot_id", "time_seconds", "message_id", "sender_id"],
    "sender_info": [
        "user_id",
        "channel_id",
        "message_id",
        "chat_id",
        "preview_file_size",
        "review_chat_id",
        "review_message_id",
        "timestamp",
    ],
    "service_message": ["bot_id"],
    "users": ["user_id"],
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name, column_names in LEGACY_BIGINT_COLUMNS.items():
        for column_name in column_names:
            op.execute(
                sa.text(
                    f'''
                    DO $legacy_bigint$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = current_schema()
                              AND table_name = '{table_name}'
                              AND column_name = '{column_name}'
                              AND udt_name <> 'int8'
                        ) THEN
                            ALTER TABLE "{table_name}"
                            ALTER COLUMN "{column_name}" TYPE BIGINT
                            USING NULLIF("{column_name}"::text, '')::bigint;
                        END IF;
                    END
                    $legacy_bigint$;
                    '''
                )
            )


def downgrade() -> None:
    # BIGINT values cannot safely be narrowed back to INTEGER.
    pass
