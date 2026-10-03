"""Technician assistant outputs and immutable human feedback."""

import sqlalchemy as sa

from alembic import op

revision = "20260911_0011"
down_revision = "20260910_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_ai_interactions_task_type_valid"), "ai_interactions", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_interactions_task_type_valid"),
        "ai_interactions",
        "task_type IN ('CLASSIFICATION', 'TROUBLESHOOTING', 'RESPONSE_DRAFT', 'SUMMARIZATION')",
    )
    op.drop_constraint(
        op.f("ck_ai_recommendations_output_type_valid"), "ai_recommendations", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ai_recommendations_output_type_valid"),
        "ai_recommendations",
        "output_type IN ('CLASSIFICATION', 'TROUBLESHOOTING', 'RESPONSE_DRAFT', 'SUMMARIZATION')",
    )
    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interaction_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("feedback_text", sa.String(1000)),
        sa.Column("edited_content", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("output_type", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "action IN ('ACCEPTED', 'EDITED', 'REJECTED', 'REGENERATED')",
            name=op.f("ck_ai_feedback_action_valid"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_ai_feedback_confidence_valid"),
        ),
        sa.CheckConstraint(
            "(action = 'EDITED' AND edited_content IS NOT NULL) OR "
            "(action <> 'EDITED' AND edited_content IS NULL)",
            name=op.f("ck_ai_feedback_edited_content_valid"),
        ),
        sa.CheckConstraint(
            "output_type IN ('CLASSIFICATION', 'TROUBLESHOOTING', "
            "'RESPONSE_DRAFT', 'SUMMARIZATION')",
            name=op.f("ck_ai_feedback_output_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["ai_interactions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_feedback_interaction_id_ai_interactions"),
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["ai_recommendations.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_feedback_recommendation_id_ai_recommendations"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_feedback_ticket_id_tickets"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_ai_feedback_actor_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_feedback")),
        sa.UniqueConstraint("recommendation_id", name=op.f("uq_ai_feedback_recommendation_id")),
    )
    op.create_index(op.f("ix_ai_feedback_interaction_id"), "ai_feedback", ["interaction_id"])
    op.create_index(op.f("ix_ai_feedback_ticket_id"), "ai_feedback", ["ticket_id"])
    op.create_index(op.f("ix_ai_feedback_actor_id"), "ai_feedback", ["actor_id"])
    op.create_index(op.f("ix_ai_feedback_action"), "ai_feedback", ["action"])
    op.create_index("ix_ai_feedback_ticket_created", "ai_feedback", ["ticket_id", "created_at"])


def downgrade() -> None:
    op.drop_table("ai_feedback")
    op.drop_constraint(
        op.f("ck_ai_recommendations_output_type_valid"), "ai_recommendations", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_ai_recommendations_output_type_valid"),
        "ai_recommendations",
        "output_type IN ('CLASSIFICATION', 'TROUBLESHOOTING')",
    )
    op.drop_constraint(op.f("ck_ai_interactions_task_type_valid"), "ai_interactions", type_="check")
    op.create_check_constraint(
        op.f("ck_ai_interactions_task_type_valid"),
        "ai_interactions",
        "task_type IN ('CLASSIFICATION', 'TROUBLESHOOTING')",
    )
