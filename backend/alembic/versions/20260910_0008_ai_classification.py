"""Privacy-conscious AI classification interactions and recommendations."""

import sqlalchemy as sa

from alembic import op

revision = "20260910_0008"
down_revision = "20260909_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_interactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("input_metadata", sa.JSON(), nullable=False),
        sa.Column("provider_request_id", sa.String(160)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "task_type IN ('CLASSIFICATION')", name=op.f("ck_ai_interactions_task_type_valid")
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'FALLBACK')",
            name=op.f("ck_ai_interactions_status_valid"),
        ),
        sa.CheckConstraint(
            "attempts > 0 AND attempts <= 2", name=op.f("ck_ai_interactions_attempts_valid")
        ),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_ai_interactions_latency_nonnegative")),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_interactions_ticket_id_tickets"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_interactions_actor_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_interactions")),
    )
    op.create_index(op.f("ix_ai_interactions_ticket_id"), "ai_interactions", ["ticket_id"])
    op.create_index(op.f("ix_ai_interactions_actor_id"), "ai_interactions", ["actor_id"])
    op.create_index(op.f("ix_ai_interactions_status"), "ai_interactions", ["status"])
    op.create_index(
        "ix_ai_interactions_ticket_created", "ai_interactions", ["ticket_id", "created_at"]
    )

    op.create_table(
        "ai_recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interaction_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("output_type", sa.String(32), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "output_type IN ('CLASSIFICATION')",
            name=op.f("ck_ai_recommendations_output_type_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('MODEL', 'FALLBACK')", name=op.f("ck_ai_recommendations_source_valid")
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_ai_recommendations_confidence_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["ai_interactions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_recommendations_interaction_id_ai_interactions"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_recommendations_ticket_id_tickets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_recommendations")),
        sa.UniqueConstraint("interaction_id", name=op.f("uq_ai_recommendations_interaction_id")),
    )
    op.create_index(op.f("ix_ai_recommendations_ticket_id"), "ai_recommendations", ["ticket_id"])
    op.create_index(
        "ix_ai_recommendations_ticket_created",
        "ai_recommendations",
        ["ticket_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("ai_recommendations")
    op.drop_table("ai_interactions")
