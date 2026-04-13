"""Create editorial pipeline schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260413_01"
down_revision = None
branch_labels = None
depends_on = None


submission_status = sa.Enum(
    "new",
    "approved_as_source",
    "paste_candidate",
    "content_created",
    "rejected",
    "hold",
    name="submission_status",
)
content_source_type = sa.Enum(
    "submission",
    "generated",
    "paste",
    "editorial",
    name="content_source_type",
)
content_item_status = sa.Enum(
    "draft",
    "pending_review",
    "approved",
    "scheduled",
    "published",
    "rejected",
    "hold",
    name="content_item_status",
)
review_decision = sa.Enum(
    "approve",
    "reject",
    "hold",
    "edit_and_approve",
    "save_as_paste",
    "approve_as_source",
    name="review_decision",
)
publication_status = sa.Enum(
    "scheduled",
    "sent",
    "failed",
    "cancelled",
    name="publication_status",
)
generation_status = sa.Enum(
    "pending",
    "completed",
    "failed",
    "disabled",
    name="generation_status",
)
paste_status = sa.Enum(
    "draft",
    "active",
    "archived",
    name="paste_status",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    submission_status.create(op.get_bind(), checkfirst=True)
    content_source_type.create(op.get_bind(), checkfirst=True)
    content_item_status.create(op.get_bind(), checkfirst=True)
    review_decision.create(op.get_bind(), checkfirst=True)
    publication_status.create(op.get_bind(), checkfirst=True)
    generation_status.create(op.get_bind(), checkfirst=True)
    paste_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_channel_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255)),
        sa.Column("short_code", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("min_gap_minutes", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("max_posts_per_day", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("max_generated_per_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_paste_per_day", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("same_tag_cooldown_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("same_template_cooldown_hours", sa.Integer(), nullable=False, server_default="72"),
        sa.Column("same_paste_cooldown_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("min_ready_queue", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("prefer_real_ratio", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("allow_generated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_pastes", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tg_channel_id"),
        sa.UniqueConstraint("short_code"),
    )
    op.create_index("ix_channels_tg_channel_id", "channels", ["tg_channel_id"])

    op.create_table(
        "channel_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("slot_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("channel_id", "weekday", "slot_time"),
    )
    op.create_index("ix_channel_slots_channel_id", "channel_slots", ["channel_id"])
    op.create_index("ix_channel_slots_weekday", "channel_slots", ["weekday"])

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legacy_source", sa.String(length=64), nullable=False, server_default="sender_info"),
        sa.Column("legacy_row_id", sa.Integer()),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_user_id", sa.BigInteger()),
        sa.Column("source_message_id", sa.BigInteger()),
        sa.Column("source_chat_id", sa.BigInteger()),
        sa.Column("bot_username", sa.String(length=255)),
        sa.Column("username", sa.String(length=255)),
        sa.Column("first_name", sa.String(length=255)),
        sa.Column("raw_text", sa.Text()),
        sa.Column("cleaned_text", sa.Text()),
        sa.Column("normalized_text", sa.Text()),
        sa.Column("text_hash", sa.String(length=64)),
        sa.Column("detected_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("language_code", sa.String(length=16)),
        sa.Column("is_candidate_for_generation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_candidate_for_paste", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", submission_status, nullable=False, server_default="new"),
        sa.Column("moderator_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("legacy_source", "legacy_row_id"),
    )
    op.create_index("ix_submissions_channel_id", "submissions", ["channel_id"])
    op.create_index("ix_submissions_created_at", "submissions", ["created_at"])
    op.create_index("ix_submissions_status", "submissions", ["status"])
    op.create_index("ix_submissions_text_hash", "submissions", ["text_hash"])
    op.execute(
        "CREATE INDEX ix_submissions_normalized_text_trgm "
        "ON submissions USING gin (normalized_text gin_trgm_ops)"
    )

    op.create_table(
        "generation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", generation_status, nullable=False, server_default="pending"),
        sa.Column("error_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_generation_runs_channel_id", "generation_runs", ["channel_id"])
    op.create_index("ix_generation_runs_status", "generation_runs", ["status"])

    op.create_table(
        "paste_library",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("source_submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="SET NULL")),
        sa.Column("source_content_item_id", sa.Integer()),
        sa.Column("source_channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="SET NULL")),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("primary_tag", sa.String(length=64)),
        sa.Column("status", paste_status, nullable=False, server_default="active"),
        sa.Column("global_cooldown_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("per_channel_cooldown_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("allow_all_channels", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_channel_activity_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_paste_library_text_hash", "paste_library", ["text_hash"])
    op.create_index("ix_paste_library_status", "paste_library", ["status"])
    op.create_index("ix_paste_library_primary_tag", "paste_library", ["primary_tag"])
    op.execute(
        "CREATE INDEX ix_paste_library_normalized_text_trgm "
        "ON paste_library USING gin (normalized_text gin_trgm_ops)"
    )

    op.create_table(
        "content_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", content_source_type, nullable=False),
        sa.Column("origin_submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="SET NULL")),
        sa.Column("origin_paste_id", sa.Integer(), sa.ForeignKey("paste_library.id", ondelete="SET NULL")),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("primary_tag", sa.String(length=64)),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("template_key", sa.String(length=64)),
        sa.Column("tone_key", sa.String(length=64)),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", content_item_status, nullable=False, server_default="pending_review"),
        sa.Column("publish_after", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("generation_run_id", sa.Integer(), sa.ForeignKey("generation_runs.id", ondelete="SET NULL")),
        sa.Column("scheduled_for", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_content_items_channel_id", "content_items", ["channel_id"])
    op.create_index("ix_content_items_source_type", "content_items", ["source_type"])
    op.create_index("ix_content_items_status", "content_items", ["status"])
    op.create_index("ix_content_items_primary_tag", "content_items", ["primary_tag"])
    op.create_index("ix_content_items_template_key", "content_items", ["template_key"])
    op.create_index("ix_content_items_text_hash", "content_items", ["text_hash"])
    op.create_index("ix_content_items_scheduled_for", "content_items", ["scheduled_for"])
    op.execute(
        "CREATE INDEX ix_content_items_normalized_text_trgm "
        "ON content_items USING gin (normalized_text gin_trgm_ops)"
    )

    op.create_table(
        "content_item_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="source"),
    )
    op.create_index("ix_content_item_sources_content_item_id", "content_item_sources", ["content_item_id"])
    op.create_index("ix_content_item_sources_submission_id", "content_item_sources", ["submission_id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", review_decision, nullable=False),
        sa.Column("review_note", sa.Text()),
        sa.Column("edited_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_content_item_id", "reviews", ["content_item_id"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])
    op.create_index("ix_reviews_decision", "reviews", ["decision"])

    op.create_table(
        "publication_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("telegram_message_id", sa.BigInteger()),
        sa.Column("publish_status", publication_status, nullable=False, server_default="scheduled"),
        sa.Column("error_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publication_log_channel_id", "publication_log", ["channel_id"])
    op.create_index("ix_publication_log_content_item_id", "publication_log", ["content_item_id"])
    op.create_index("ix_publication_log_scheduled_for", "publication_log", ["scheduled_for"])
    op.create_index("ix_publication_log_published_at", "publication_log", ["published_at"])
    op.create_index("ix_publication_log_publish_status", "publication_log", ["publish_status"])

    op.create_table(
        "paste_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paste_id", sa.Integer(), sa.ForeignKey("paste_library.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_paste_usage_paste_id", "paste_usage", ["paste_id"])
    op.create_index("ix_paste_usage_channel_id", "paste_usage", ["channel_id"])
    op.create_index("ix_paste_usage_content_item_id", "paste_usage", ["content_item_id"])

    op.create_table(
        "paste_channel_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paste_id", sa.Integer(), sa.ForeignKey("paste_library.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("paste_id", "channel_id"),
    )
    op.create_index("ix_paste_channel_rules_paste_id", "paste_channel_rules", ["paste_id"])
    op.create_index("ix_paste_channel_rules_channel_id", "paste_channel_rules", ["channel_id"])

    op.create_foreign_key(
        "fk_paste_library_source_content_item_id_content_items",
        "paste_library",
        "content_items",
        ["source_content_item_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_content_items_unique_active_hash",
        "content_items",
        ["channel_id", "text_hash"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending_review', 'approved', 'scheduled', 'published')"),
    )


def downgrade() -> None:
    op.drop_index("ix_content_items_unique_active_hash", table_name="content_items")
    op.drop_constraint("fk_paste_library_source_content_item_id_content_items", "paste_library", type_="foreignkey")
    op.drop_index("ix_paste_channel_rules_channel_id", table_name="paste_channel_rules")
    op.drop_index("ix_paste_channel_rules_paste_id", table_name="paste_channel_rules")
    op.drop_table("paste_channel_rules")
    op.drop_index("ix_paste_usage_content_item_id", table_name="paste_usage")
    op.drop_index("ix_paste_usage_channel_id", table_name="paste_usage")
    op.drop_index("ix_paste_usage_paste_id", table_name="paste_usage")
    op.drop_table("paste_usage")
    op.drop_index("ix_publication_log_publish_status", table_name="publication_log")
    op.drop_index("ix_publication_log_published_at", table_name="publication_log")
    op.drop_index("ix_publication_log_scheduled_for", table_name="publication_log")
    op.drop_index("ix_publication_log_content_item_id", table_name="publication_log")
    op.drop_index("ix_publication_log_channel_id", table_name="publication_log")
    op.drop_table("publication_log")
    op.drop_index("ix_reviews_decision", table_name="reviews")
    op.drop_index("ix_reviews_reviewer_id", table_name="reviews")
    op.drop_index("ix_reviews_content_item_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_content_item_sources_submission_id", table_name="content_item_sources")
    op.drop_index("ix_content_item_sources_content_item_id", table_name="content_item_sources")
    op.drop_table("content_item_sources")
    op.execute("DROP INDEX IF EXISTS ix_content_items_normalized_text_trgm")
    op.drop_index("ix_content_items_scheduled_for", table_name="content_items")
    op.drop_index("ix_content_items_text_hash", table_name="content_items")
    op.drop_index("ix_content_items_template_key", table_name="content_items")
    op.drop_index("ix_content_items_primary_tag", table_name="content_items")
    op.drop_index("ix_content_items_status", table_name="content_items")
    op.drop_index("ix_content_items_source_type", table_name="content_items")
    op.drop_index("ix_content_items_channel_id", table_name="content_items")
    op.drop_table("content_items")
    op.execute("DROP INDEX IF EXISTS ix_paste_library_normalized_text_trgm")
    op.drop_index("ix_paste_library_primary_tag", table_name="paste_library")
    op.drop_index("ix_paste_library_status", table_name="paste_library")
    op.drop_index("ix_paste_library_text_hash", table_name="paste_library")
    op.drop_table("paste_library")
    op.drop_index("ix_generation_runs_status", table_name="generation_runs")
    op.drop_index("ix_generation_runs_channel_id", table_name="generation_runs")
    op.drop_table("generation_runs")
    op.execute("DROP INDEX IF EXISTS ix_submissions_normalized_text_trgm")
    op.drop_index("ix_submissions_text_hash", table_name="submissions")
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_index("ix_submissions_created_at", table_name="submissions")
    op.drop_index("ix_submissions_channel_id", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index("ix_channel_slots_weekday", table_name="channel_slots")
    op.drop_index("ix_channel_slots_channel_id", table_name="channel_slots")
    op.drop_table("channel_slots")
    op.drop_index("ix_channels_tg_channel_id", table_name="channels")
    op.drop_table("channels")

    paste_status.drop(op.get_bind(), checkfirst=True)
    generation_status.drop(op.get_bind(), checkfirst=True)
    publication_status.drop(op.get_bind(), checkfirst=True)
    review_decision.drop(op.get_bind(), checkfirst=True)
    content_item_status.drop(op.get_bind(), checkfirst=True)
    content_source_type.drop(op.get_bind(), checkfirst=True)
    submission_status.drop(op.get_bind(), checkfirst=True)

