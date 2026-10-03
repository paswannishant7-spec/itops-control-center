"""Semantic ticket representations and pgvector similarity index."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "20260910_0010"
down_revision = "20260910_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("representation_hash", sa.String(64), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "dimensions = 1536", name=op.f("ck_ticket_embeddings_dimensions_supported")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="CASCADE",
            name=op.f("fk_ticket_embeddings_ticket_id_tickets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_embeddings")),
        sa.UniqueConstraint(
            "ticket_id",
            "provider",
            "model",
            name=op.f("uq_ticket_embeddings_ticket_provider_model_unique"),
        ),
    )
    op.create_index(op.f("ix_ticket_embeddings_ticket_id"), "ticket_embeddings", ["ticket_id"])
    op.create_index(
        "ix_ticket_embeddings_vector_hnsw",
        "ticket_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("ticket_embeddings")
