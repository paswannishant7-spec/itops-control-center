"""Versioned knowledge articles and publishing workflow."""

import sqlalchemy as sa

from alembic import op

revision = "20260909_0007"
down_revision = "20260909_0006"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "knowledge_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_categories")),
    )
    op.create_index(
        "uq_knowledge_categories_code_normalized",
        "knowledge_categories",
        [sa.literal_column("lower(code)")],
        unique=True,
    )
    op.create_index(
        "uq_knowledge_categories_name_normalized",
        "knowledge_categories",
        [sa.literal_column("lower(name)")],
        unique=True,
    )

    op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("current_version_id", sa.Uuid()),
        sa.Column("published_version_id", sa.Uuid()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'IN_REVIEW', 'PUBLISHED', 'ARCHIVED')",
            name=op.f("ck_knowledge_articles_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["knowledge_categories.id"],
            ondelete="RESTRICT",
            name=op.f("fk_knowledge_articles_category_id_knowledge_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_knowledge_articles_author_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_knowledge_articles_owner_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_articles")),
    )
    for column in ("category_id", "author_id", "owner_id", "status"):
        op.create_index(op.f(f"ix_knowledge_articles_{column}"), "knowledge_articles", [column])
    op.create_index(
        "uq_knowledge_articles_slug_normalized",
        "knowledge_articles",
        [sa.literal_column("lower(slug)")],
        unique=True,
    )
    op.create_index(
        "ix_knowledge_articles_status_updated", "knowledge_articles", ["status", "updated_at"]
    )

    op.create_table(
        "knowledge_article_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.String(500), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_knowledge_article_versions_version_positive")
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["knowledge_articles.id"],
            ondelete="CASCADE",
            name=op.f("fk_knowledge_article_versions_article_id_knowledge_articles"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_knowledge_article_versions_author_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_article_versions")),
        sa.UniqueConstraint(
            "article_id",
            "version",
            name=op.f("uq_knowledge_article_versions_article_version_unique"),
        ),
    )
    op.create_index(
        op.f("ix_knowledge_article_versions_article_id"),
        "knowledge_article_versions",
        ["article_id"],
    )
    op.create_index(
        op.f("ix_knowledge_article_versions_author_id"), "knowledge_article_versions", ["author_id"]
    )
    op.create_index(
        "ix_knowledge_versions_article_created",
        "knowledge_article_versions",
        ["article_id", "created_at"],
    )
    op.create_foreign_key(
        "fk_knowledge_articles_current_version",
        "knowledge_articles",
        "knowledge_article_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_knowledge_articles_published_version",
        "knowledge_articles",
        "knowledge_article_versions",
        ["published_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "knowledge_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["knowledge_articles.id"],
            ondelete="CASCADE",
            name=op.f("fk_knowledge_events_article_id_knowledge_articles"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_knowledge_events_actor_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_events")),
    )
    op.create_index(op.f("ix_knowledge_events_article_id"), "knowledge_events", ["article_id"])
    op.create_index(op.f("ix_knowledge_events_actor_id"), "knowledge_events", ["actor_id"])
    op.create_index(
        "ix_knowledge_events_article_created", "knowledge_events", ["article_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("knowledge_events")
    op.drop_constraint(
        "fk_knowledge_articles_published_version", "knowledge_articles", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_knowledge_articles_current_version", "knowledge_articles", type_="foreignkey"
    )
    op.drop_table("knowledge_article_versions")
    op.drop_table("knowledge_articles")
    op.drop_table("knowledge_categories")
