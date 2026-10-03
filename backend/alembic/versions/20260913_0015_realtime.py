"""Durable realtime invalidation outbox.

Revision ID: 20260913_0015
Revises: 20260913_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0015"
down_revision: str | None = "20260913_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "realtime_cursor",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_realtime_cursor_singleton")),
        sa.CheckConstraint("value >= 0", name=op.f("ck_realtime_cursor_value_nonnegative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_realtime_cursor")),
    )
    op.bulk_insert(
        sa.table(
            "realtime_cursor",
            sa.column("id", sa.Integer()),
            sa.column("value", sa.BigInteger()),
        ),
        [{"id": 1, "value": 0}],
    )
    op.create_table(
        "realtime_events",
        sa.Column("sequence", sa.BigInteger(), nullable=True),
        sa.Column("topic", sa.String(length=24), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_id", sa.Uuid(), nullable=True),
        sa.Column("internal", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "topic IN ('tickets','sla','alerts','notifications','devices','access')",
            name=op.f("ck_realtime_events_topic_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            name=op.f("fk_realtime_events_recipient_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_realtime_events")),
        sa.UniqueConstraint("sequence", name=op.f("uq_realtime_events_sequence")),
    )
    op.create_index(op.f("ix_realtime_events_sequence"), "realtime_events", ["sequence"])
    op.create_index(op.f("ix_realtime_events_topic"), "realtime_events", ["topic"])
    op.create_index(op.f("ix_realtime_events_resource_id"), "realtime_events", ["resource_id"])
    op.create_index(op.f("ix_realtime_events_recipient_id"), "realtime_events", ["recipient_id"])
    op.create_index("ix_realtime_events_topic_sequence", "realtime_events", ["topic", "sequence"])
    op.create_index(
        "ix_realtime_events_recipient_sequence",
        "realtime_events",
        ["recipient_id", "sequence"],
    )
    op.create_index("ix_realtime_events_created_at", "realtime_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_realtime_events_created_at", table_name="realtime_events")
    op.drop_index("ix_realtime_events_recipient_sequence", table_name="realtime_events")
    op.drop_index("ix_realtime_events_topic_sequence", table_name="realtime_events")
    op.drop_index(op.f("ix_realtime_events_recipient_id"), table_name="realtime_events")
    op.drop_index(op.f("ix_realtime_events_resource_id"), table_name="realtime_events")
    op.drop_index(op.f("ix_realtime_events_topic"), table_name="realtime_events")
    op.drop_index(op.f("ix_realtime_events_sequence"), table_name="realtime_events")
    op.drop_table("realtime_events")
    op.drop_table("realtime_cursor")
