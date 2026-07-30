"""add subscriber based channel setting profiles

Revision ID: 20260730_13
Revises: 20260730_12
Create Date: 2026-07-30 00:10:00.000000
"""

from __future__ import annotations

from datetime import time

from alembic import op
import sqlalchemy as sa


revision = "20260730_13"
down_revision = "20260730_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_setting_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("min_subscribers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_subscribers", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("min_gap_minutes", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("slot_jitter_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("auto_slots_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auto_slots_plan_time", sa.Time(), nullable=False, server_default="23:30"),
        sa.Column("auto_slots_window_start", sa.Time(), nullable=False, server_default="10:00"),
        sa.Column("auto_slots_window_end", sa.Time(), nullable=False, server_default="22:00"),
        sa.Column("auto_slots_replace_manual", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_posts_per_day", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("max_generated_per_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_paste_per_day", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("same_tag_cooldown_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("same_template_cooldown_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("same_paste_cooldown_days", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("min_ready_queue", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("prefer_real_ratio", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("allow_generated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_pastes", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_channel_setting_profiles_slug", "channel_setting_profiles", ["slug"], unique=False)
    op.create_index("ix_channel_setting_profiles_is_active", "channel_setting_profiles", ["is_active"], unique=False)
    op.create_index("ix_channel_setting_profiles_priority", "channel_setting_profiles", ["priority"], unique=False)
    op.create_index(
        "ix_channel_setting_profiles_min_subscribers",
        "channel_setting_profiles",
        ["min_subscribers"],
        unique=False,
    )
    op.create_index(
        "ix_channel_setting_profiles_max_subscribers",
        "channel_setting_profiles",
        ["max_subscribers"],
        unique=False,
    )

    op.add_column("channels", sa.Column("subscriber_count", sa.Integer(), nullable=True))
    op.add_column("channels", sa.Column("subscriber_count_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("channels", sa.Column("settings_profile_id", sa.Integer(), nullable=True))
    op.add_column(
        "channels",
        sa.Column("settings_profile_auto_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("channels", sa.Column("settings_profile_applied_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_channels_settings_profile_id"), "channels", ["settings_profile_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_channels_settings_profile_id_channel_setting_profiles"),
        "channels",
        "channel_setting_profiles",
        ["settings_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    profiles = sa.table(
        "channel_setting_profiles",
        sa.column("slug", sa.String),
        sa.column("title", sa.String),
        sa.column("priority", sa.Integer),
        sa.column("min_subscribers", sa.Integer),
        sa.column("max_subscribers", sa.Integer),
        sa.column("auto_slots_enabled", sa.Boolean),
        sa.column("auto_slots_window_start", sa.Time),
        sa.column("auto_slots_window_end", sa.Time),
        sa.column("max_posts_per_day", sa.Integer),
        sa.column("max_paste_per_day", sa.Integer),
        sa.column("min_ready_queue", sa.Integer),
    )
    op.bulk_insert(
        profiles,
        [
            {
                "slug": "starter",
                "title": "Starter 0-49",
                "priority": 10,
                "min_subscribers": 0,
                "max_subscribers": 49,
                "auto_slots_enabled": True,
                "auto_slots_window_start": time(12, 0),
                "auto_slots_window_end": time(20, 0),
                "max_posts_per_day": 3,
                "max_paste_per_day": 2,
                "min_ready_queue": 2,
            },
            {
                "slug": "growing",
                "title": "Growing 50-999",
                "priority": 20,
                "min_subscribers": 50,
                "max_subscribers": 999,
                "auto_slots_enabled": True,
                "auto_slots_window_start": time(10, 0),
                "auto_slots_window_end": time(22, 0),
                "max_posts_per_day": 6,
                "max_paste_per_day": 3,
                "min_ready_queue": 3,
            },
            {
                "slug": "active",
                "title": "Active 1000-9999",
                "priority": 30,
                "min_subscribers": 1000,
                "max_subscribers": 9999,
                "auto_slots_enabled": True,
                "auto_slots_window_start": time(9, 0),
                "auto_slots_window_end": time(23, 0),
                "max_posts_per_day": 10,
                "max_paste_per_day": 4,
                "min_ready_queue": 5,
            },
            {
                "slug": "large",
                "title": "Large 10000+",
                "priority": 40,
                "min_subscribers": 10000,
                "max_subscribers": None,
                "auto_slots_enabled": True,
                "auto_slots_window_start": time(8, 0),
                "auto_slots_window_end": time(23, 30),
                "max_posts_per_day": 14,
                "max_paste_per_day": 5,
                "min_ready_queue": 7,
            },
        ],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_channels_settings_profile_id_channel_setting_profiles"), "channels", type_="foreignkey")
    op.drop_index(op.f("ix_channels_settings_profile_id"), table_name="channels")
    op.drop_column("channels", "settings_profile_applied_at")
    op.drop_column("channels", "settings_profile_auto_enabled")
    op.drop_column("channels", "settings_profile_id")
    op.drop_column("channels", "subscriber_count_checked_at")
    op.drop_column("channels", "subscriber_count")
    op.drop_index("ix_channel_setting_profiles_max_subscribers", table_name="channel_setting_profiles")
    op.drop_index("ix_channel_setting_profiles_min_subscribers", table_name="channel_setting_profiles")
    op.drop_index("ix_channel_setting_profiles_priority", table_name="channel_setting_profiles")
    op.drop_index("ix_channel_setting_profiles_is_active", table_name="channel_setting_profiles")
    op.drop_index("ix_channel_setting_profiles_slug", table_name="channel_setting_profiles")
    op.drop_table("channel_setting_profiles")
