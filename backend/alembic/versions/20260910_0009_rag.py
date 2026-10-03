"""Published knowledge chunks, pgvector embeddings, and troubleshooting outputs."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "20260910_0009"
down_revision = "20260910_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ai_interactions_task_type_valid"), "ai_interactions", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_interactions_task_type_valid"),
        "ai_interactions",
        "task_type IN ('CLASSIFICATION', 'TROUBLESHOOTING')",
    )
    op.drop_constraint(
        op.f("ck_ai_recommendations_output_type_valid"), "ai_recommendations", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ai_recommendations_output_type_valid"),
        "ai_recommendations",
        "output_type IN ('CLASSIFICATION', 'TROUBLESHOOTING')",
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_knowledge_chunks_ordinal_nonnegative")),
        sa.CheckConstraint(
            "character_count > 0", name=op.f("ck_knowledge_chunks_character_count_positive")
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["knowledge_articles.id"],
            ondelete="CASCADE",
            name=op.f("fk_knowledge_chunks_article_id_knowledge_articles"),
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["knowledge_article_versions.id"],
            ondelete="CASCADE",
            name=op.f("fk_knowledge_chunks_version_id_knowledge_article_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "version_id", "ordinal", name=op.f("uq_knowledge_chunks_version_ordinal_unique")
        ),
    )
    op.create_index(op.f("ix_knowledge_chunks_article_id"), "knowledge_chunks", ["article_id"])
    op.create_index(op.f("ix_knowledge_chunks_version_id"), "knowledge_chunks", ["version_id"])
    op.create_index(
        "ix_knowledge_chunks_article_version",
        "knowledge_chunks",
        ["article_id", "version_id"],
    )
    op.create_table(
        "knowledge_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "dimensions = 1536", name=op.f("ck_knowledge_embeddings_dimensions_supported")
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["knowledge_chunks.id"],
            ondelete="CASCADE",
            name=op.f("fk_knowledge_embeddings_chunk_id_knowledge_chunks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_embeddings")),
        sa.UniqueConstraint(
            "chunk_id",
            "provider",
            "model",
            name=op.f("uq_knowledge_embeddings_chunk_provider_model_unique"),
        ),
    )
    op.create_index(op.f("ix_knowledge_embeddings_chunk_id"), "knowledge_embeddings", ["chunk_id"])
    op.create_index(
        "ix_knowledge_embeddings_vector_hnsw",
        "knowledge_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("knowledge_embeddings")
    op.drop_table("knowledge_chunks")
    op.drop_constraint(
        op.f("ck_ai_recommendations_output_type_valid"), "ai_recommendations", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ai_recommendations_output_type_valid"),
        "ai_recommendations",
        "output_type IN ('CLASSIFICATION')",
    )
    op.drop_constraint(op.f("ck_ai_interactions_task_type_valid"), "ai_interactions", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_interactions_task_type_valid"),
        "ai_interactions",
        "task_type IN ('CLASSIFICATION')",
    )
