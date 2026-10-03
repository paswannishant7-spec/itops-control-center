"""Configurable priority matrix, business calendars and SLA lifecycle."""

from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision = "20260909_0006"
down_revision = "20260909_0005"
branch_labels = None
depends_on = None

CALENDAR_ID = UUID("01991fa0-0000-7000-8000-000000000001")
POLICY_IDS = {
    "CRITICAL": UUID("01991fa0-0000-7000-8000-000000000011"),
    "HIGH": UUID("01991fa0-0000-7000-8000-000000000012"),
    "MEDIUM": UUID("01991fa0-0000-7000-8000-000000000013"),
    "LOW": UUID("01991fa0-0000-7000-8000-000000000014"),
}


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
    priority_matrix = op.create_table(
        "priority_matrix",
        sa.Column("impact", sa.String(16), nullable=False),
        sa.Column("urgency", sa.String(16), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "impact IN ('LOW', 'MEDIUM', 'HIGH')", name=op.f("ck_priority_matrix_impact_valid")
        ),
        sa.CheckConstraint(
            "urgency IN ('LOW', 'MEDIUM', 'HIGH')",
            name=op.f("ck_priority_matrix_urgency_valid"),
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_priority_matrix_priority_valid"),
        ),
        sa.PrimaryKeyConstraint("impact", "urgency", name=op.f("pk_priority_matrix")),
    )
    op.bulk_insert(
        priority_matrix,
        [
            {"impact": impact, "urgency": urgency, "priority": priority}
            for impact, urgency, priority in (
                ("LOW", "LOW", "LOW"),
                ("LOW", "MEDIUM", "MEDIUM"),
                ("LOW", "HIGH", "MEDIUM"),
                ("MEDIUM", "LOW", "MEDIUM"),
                ("MEDIUM", "MEDIUM", "MEDIUM"),
                ("MEDIUM", "HIGH", "HIGH"),
                ("HIGH", "LOW", "MEDIUM"),
                ("HIGH", "MEDIUM", "HIGH"),
                ("HIGH", "HIGH", "CRITICAL"),
            )
        ],
    )

    calendars = op.create_table(
        "business_calendars",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_calendars")),
    )
    op.create_index(
        "uq_business_calendars_name_normalized",
        "business_calendars",
        [sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_business_calendars_default",
        "business_calendars",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )
    op.bulk_insert(
        calendars,
        [
            {
                "id": CALENDAR_ID,
                "name": "Default 24x7",
                "timezone": "UTC",
                "is_active": True,
                "is_default": True,
            }
        ],
    )

    windows = op.create_table(
        "business_windows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "weekday >= 0 AND weekday <= 6", name=op.f("ck_business_windows_weekday_valid")
        ),
        sa.CheckConstraint(
            "start_minute >= 0 AND start_minute < 1440",
            name=op.f("ck_business_windows_start_valid"),
        ),
        sa.CheckConstraint(
            "end_minute > start_minute AND end_minute <= 2880",
            name=op.f("ck_business_windows_end_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["business_calendars.id"],
            ondelete="CASCADE",
            name=op.f("fk_business_windows_calendar_id_business_calendars"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_windows")),
        sa.UniqueConstraint(
            "calendar_id",
            "weekday",
            "start_minute",
            "end_minute",
            name=op.f("uq_business_windows_window_unique"),
        ),
    )
    op.create_index(op.f("ix_business_windows_calendar_id"), "business_windows", ["calendar_id"])
    op.bulk_insert(
        windows,
        [
            {
                "id": UUID(f"01991fa0-0000-7000-8000-{weekday + 101:012d}"),
                "calendar_id": CALENDAR_ID,
                "weekday": weekday,
                "start_minute": 0,
                "end_minute": 1440,
            }
            for weekday in range(7)
        ],
    )

    op.create_table(
        "business_holidays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["business_calendars.id"],
            ondelete="CASCADE",
            name=op.f("fk_business_holidays_calendar_id_business_calendars"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_holidays")),
        sa.UniqueConstraint(
            "calendar_id", "holiday_date", name=op.f("uq_business_holidays_calendar_date_unique")
        ),
    )
    op.create_index(op.f("ix_business_holidays_calendar_id"), "business_holidays", ["calendar_id"])

    policies = op.create_table(
        "sla_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("response_target_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_target_minutes", sa.Integer(), nullable=False),
        sa.Column("at_risk_percent", sa.Integer(), server_default="80", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_sla_policies_priority_valid"),
        ),
        sa.CheckConstraint(
            "response_target_minutes > 0", name=op.f("ck_sla_policies_response_target_positive")
        ),
        sa.CheckConstraint(
            "resolution_target_minutes > 0",
            name=op.f("ck_sla_policies_resolution_target_positive"),
        ),
        sa.CheckConstraint(
            "at_risk_percent > 0 AND at_risk_percent < 100",
            name=op.f("ck_sla_policies_risk_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["business_calendars.id"],
            ondelete="RESTRICT",
            name=op.f("fk_sla_policies_calendar_id_business_calendars"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_policies")),
    )
    op.create_index(op.f("ix_sla_policies_priority"), "sla_policies", ["priority"])
    op.create_index(op.f("ix_sla_policies_calendar_id"), "sla_policies", ["calendar_id"])
    op.create_index(
        "uq_sla_policies_name_normalized",
        "sla_policies",
        [sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_sla_policies_active_priority",
        "sla_policies",
        ["priority"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )
    op.bulk_insert(
        policies,
        [
            {
                "id": POLICY_IDS[priority],
                "name": name,
                "priority": priority,
                "calendar_id": CALENDAR_ID,
                "response_target_minutes": response,
                "resolution_target_minutes": resolution,
                "at_risk_percent": 80,
                "is_active": True,
            }
            for priority, name, response, resolution in (
                ("CRITICAL", "P1 Critical", 15, 120),
                ("HIGH", "P2 High", 60, 480),
                ("MEDIUM", "P3 Medium", 240, 1440),
                ("LOW", "P4 Low", 480, 4320),
            )
        ],
    )

    op.create_table(
        "sla_instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("response_target_seconds", sa.Integer(), nullable=False),
        sa.Column("resolution_target_seconds", sa.Integer(), nullable=False),
        sa.Column("at_risk_percent", sa.Integer(), nullable=False),
        sa.Column("response_elapsed_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resolution_elapsed_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("response_completed_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_completed_at", sa.DateTime(timezone=True)),
        sa.Column("response_breached_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_breached_at", sa.DateTime(timezone=True)),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "state IN ('ON_TRACK', 'AT_RISK', 'BREACHED', 'PAUSED', 'COMPLETED')",
            name=op.f("ck_sla_instances_state_valid"),
        ),
        sa.CheckConstraint(
            "response_target_seconds > 0", name=op.f("ck_sla_instances_response_target_positive")
        ),
        sa.CheckConstraint(
            "resolution_target_seconds > 0",
            name=op.f("ck_sla_instances_resolution_target_positive"),
        ),
        sa.CheckConstraint(
            "at_risk_percent > 0 AND at_risk_percent < 100",
            name=op.f("ck_sla_instances_risk_valid"),
        ),
        sa.CheckConstraint(
            "response_elapsed_seconds >= 0 AND resolution_elapsed_seconds >= 0",
            name=op.f("ck_sla_instances_elapsed_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_sla_instances_ticket_id_tickets"),
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["sla_policies.id"],
            ondelete="RESTRICT",
            name=op.f("fk_sla_instances_policy_id_sla_policies"),
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"],
            ["business_calendars.id"],
            ondelete="RESTRICT",
            name=op.f("fk_sla_instances_calendar_id_business_calendars"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_instances")),
        sa.UniqueConstraint("ticket_id", name=op.f("uq_sla_instances_ticket_id")),
    )
    for column in ("ticket_id", "policy_id", "calendar_id", "state"):
        op.create_index(op.f(f"ix_sla_instances_{column}"), "sla_instances", [column])
    op.create_index("ix_sla_instances_state_updated", "sla_instances", ["state", "updated_at"])
    op.execute(
        """
        INSERT INTO sla_instances (
            id, ticket_id, policy_id, calendar_id, state,
            response_target_seconds, resolution_target_seconds, at_risk_percent,
            response_elapsed_seconds, resolution_elapsed_seconds
        )
        SELECT
            gen_random_uuid(), tickets.id, sla_policies.id, sla_policies.calendar_id, 'ON_TRACK',
            sla_policies.response_target_minutes * 60,
            sla_policies.resolution_target_minutes * 60,
            sla_policies.at_risk_percent, 0, 0
        FROM tickets
        JOIN sla_policies
          ON sla_policies.priority = tickets.priority AND sla_policies.is_active IS TRUE
        """
    )

    op.create_table(
        "sla_pauses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name=op.f("ck_sla_pauses_interval_valid")
        ),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["sla_instances.id"],
            ondelete="CASCADE",
            name=op.f("fk_sla_pauses_instance_id_sla_instances"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_pauses")),
    )
    op.create_index(op.f("ix_sla_pauses_instance_id"), "sla_pauses", ["instance_id"])
    op.create_index(
        "uq_sla_pauses_active",
        "sla_pauses",
        ["instance_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "sla_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("notification_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["sla_instances.id"],
            ondelete="CASCADE",
            name=op.f("fk_sla_events_instance_id_sla_instances"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_events")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_sla_events_idempotency_key")),
    )
    op.create_index(op.f("ix_sla_events_instance_id"), "sla_events", ["instance_id"])
    op.create_index("ix_sla_events_instance_created", "sla_events", ["instance_id", "created_at"])


def downgrade() -> None:
    for table in (
        "sla_events",
        "sla_pauses",
        "sla_instances",
        "sla_policies",
        "business_holidays",
        "business_windows",
        "business_calendars",
        "priority_matrix",
    ):
        op.drop_table(table)
