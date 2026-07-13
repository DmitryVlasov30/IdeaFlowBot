"""add managed tag system

Revision ID: 20260713_10
Revises: 20260421_09
Create Date: 2026-07-13 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260713_10"
down_revision = "20260421_09"
branch_labels = None
depends_on = None


TAG_SEED: dict[str, tuple[str, int, tuple[str, ...]]] = {
    "study": ("Учёба", 10, ("сесс", "экзам", "зачет", "препод", "лекц", "лаба")),
    "relationships": ("Отношения", 20, ("парень", "девуш", "отношен", "любов", "бывш")),
    "dorm": ("Общага", 30, ("общага", "общежит", "коменда")),
    "money": ("Деньги и работа", 40, ("деньг", "стипенд", "работ", "зарплат")),
    "social": ("Социалка", 50, ("друз", "компан", "тусов", "вечерин")),
    "question": ("Вопросы", 60, ("кто", "как", "что делать", "посоветуйте", "подскажите")),
}


def upgrade() -> None:
    tag_match_type = postgresql.ENUM("contains", "word", "regex", name="tag_match_type", create_type=False)
    tag_assignment_source = postgresql.ENUM("auto", "manual", name="tag_assignment_source", create_type=False)
    channel_rule_mode = postgresql.ENUM("include", "exclude", name="channel_paste_tag_rule_mode", create_type=False)
    postgresql.ENUM("contains", "word", "regex", name="tag_match_type").create(op.get_bind(), checkfirst=True)
    postgresql.ENUM("auto", "manual", name="tag_assignment_source").create(op.get_bind(), checkfirst=True)
    postgresql.ENUM("include", "exclude", name="channel_paste_tag_rule_mode").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "tag_definitions",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_tag_definitions_slug", "tag_definitions", ["slug"])
    op.create_index("ix_tag_definitions_is_active", "tag_definitions", ["is_active"])
    op.create_index("ix_tag_definitions_priority", "tag_definitions", ["priority"])

    op.create_table(
        "tag_keywords",
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tag_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("normalized_keyword", sa.String(length=255), nullable=False),
        sa.Column("match_type", tag_match_type, nullable=False, server_default="contains"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tag_id", "keyword", "match_type"),
    )
    op.create_index("ix_tag_keywords_tag_id", "tag_keywords", ["tag_id"])
    op.create_index("ix_tag_keywords_normalized_keyword", "tag_keywords", ["normalized_keyword"])
    op.create_index("ix_tag_keywords_is_active", "tag_keywords", ["is_active"])

    op.create_table(
        "paste_tag_assignments",
        sa.Column("paste_id", sa.Integer(), sa.ForeignKey("paste_library.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tag_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", tag_assignment_source, nullable=False),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.UniqueConstraint("paste_id", "tag_id", "source"),
    )
    op.create_index("ix_paste_tag_assignments_paste_id", "paste_tag_assignments", ["paste_id"])
    op.create_index("ix_paste_tag_assignments_tag_id", "paste_tag_assignments", ["tag_id"])
    op.create_index("ix_paste_tag_assignments_source", "paste_tag_assignments", ["source"])

    op.create_table(
        "channel_paste_tag_rules",
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tag_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", channel_rule_mode, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("channel_id", "tag_id", "mode"),
    )
    op.create_index("ix_channel_paste_tag_rules_channel_id", "channel_paste_tag_rules", ["channel_id"])
    op.create_index("ix_channel_paste_tag_rules_tag_id", "channel_paste_tag_rules", ["tag_id"])
    op.create_index("ix_channel_paste_tag_rules_mode", "channel_paste_tag_rules", ["mode"])
    op.create_index("ix_channel_paste_tag_rules_is_active", "channel_paste_tag_rules", ["is_active"])

    tag_table = sa.table(
        "tag_definitions",
        sa.column("slug", sa.String),
        sa.column("title", sa.String),
        sa.column("priority", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        tag_table,
        [
            {"slug": slug, "title": title, "priority": priority, "is_active": True}
            for slug, (title, priority, _keywords) in TAG_SEED.items()
        ],
    )

    conn = op.get_bind()
    tag_ids = dict(conn.execute(sa.text("SELECT slug, id FROM tag_definitions")).fetchall())
    keyword_table = sa.table(
        "tag_keywords",
        sa.column("tag_id", sa.Integer),
        sa.column("keyword", sa.String),
        sa.column("normalized_keyword", sa.String),
        sa.column("match_type", tag_match_type),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        keyword_table,
        [
            {
                "tag_id": tag_ids[slug],
                "keyword": keyword,
                "normalized_keyword": keyword,
                "match_type": "contains",
                "is_active": True,
            }
            for slug, (_title, _priority, keywords) in TAG_SEED.items()
            for keyword in keywords
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_paste_tag_rules_is_active", table_name="channel_paste_tag_rules")
    op.drop_index("ix_channel_paste_tag_rules_mode", table_name="channel_paste_tag_rules")
    op.drop_index("ix_channel_paste_tag_rules_tag_id", table_name="channel_paste_tag_rules")
    op.drop_index("ix_channel_paste_tag_rules_channel_id", table_name="channel_paste_tag_rules")
    op.drop_table("channel_paste_tag_rules")
    op.drop_index("ix_paste_tag_assignments_source", table_name="paste_tag_assignments")
    op.drop_index("ix_paste_tag_assignments_tag_id", table_name="paste_tag_assignments")
    op.drop_index("ix_paste_tag_assignments_paste_id", table_name="paste_tag_assignments")
    op.drop_table("paste_tag_assignments")
    op.drop_index("ix_tag_keywords_is_active", table_name="tag_keywords")
    op.drop_index("ix_tag_keywords_normalized_keyword", table_name="tag_keywords")
    op.drop_index("ix_tag_keywords_tag_id", table_name="tag_keywords")
    op.drop_table("tag_keywords")
    op.drop_index("ix_tag_definitions_priority", table_name="tag_definitions")
    op.drop_index("ix_tag_definitions_is_active", table_name="tag_definitions")
    op.drop_index("ix_tag_definitions_slug", table_name="tag_definitions")
    op.drop_table("tag_definitions")

    sa.Enum(name="channel_paste_tag_rule_mode").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tag_assignment_source").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tag_match_type").drop(op.get_bind(), checkfirst=True)
