"""Enforce append-only audit records at the database boundary.

Revision ID: 20260913_0016
Revises: 20260913_0015
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260913_0016"
down_revision: str | None = "20260913_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_TABLES = (
    "role_assignment_events",
    "directory_events",
    "ticket_events",
    "sla_events",
    "knowledge_events",
    "asset_events",
    "alert_events",
    "ai_interactions",
    "ai_feedback",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit records are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in AUDIT_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
        )


def downgrade() -> None:
    for table in reversed(AUDIT_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_mutation()")
