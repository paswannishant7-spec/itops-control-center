"""Configurable alerts, deterministic automation, incidents, and notifications."""

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision = "20260913_0014"
down_revision = "20260913_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("record_type", sa.String(16), server_default="REQUEST", nullable=False),
    )
    op.create_index(op.f("ix_tickets_record_type"), "tickets", ["record_type"])
    op.create_check_constraint(
        op.f("ck_tickets_record_type_valid"),
        "tickets",
        "record_type IN ('REQUEST', 'INCIDENT')",
    )
    op.drop_constraint(op.f("ck_tickets_source_valid"), "tickets", type_="check")
    op.create_check_constraint(
        op.f("ck_tickets_source_valid"),
        "tickets",
        "source IN ('PORTAL', 'API', 'AUTOMATION')",
    )
    op.alter_column("tickets", "record_type", server_default=None)

    op.create_table(
        "alert_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("operator", sa.String(24), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "metric IN ('CPU_PERCENT','MEMORY_PERCENT','DISK_PERCENT',"
            "'DEVICE_OFFLINE','HEARTBEAT_MISSED')",
            name=op.f("ck_alert_policies_metric_valid"),
        ),
        sa.CheckConstraint(
            "operator IN ('GREATER_THAN','AT_LEAST')",
            name=op.f("ck_alert_policies_operator_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('INFO','WARNING','HIGH','CRITICAL')",
            name=op.f("ck_alert_policies_severity_valid"),
        ),
        sa.CheckConstraint("threshold >= 0", name=op.f("ck_alert_policies_threshold_nonnegative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_policies")),
        sa.UniqueConstraint("name", name=op.f("uq_alert_policies_name")),
    )
    op.create_index(op.f("ix_alert_policies_metric"), "alert_policies", ["metric"])
    op.create_index(op.f("ix_alert_policies_severity"), "alert_policies", ["severity"])
    op.create_index(op.f("ix_alert_policies_enabled"), "alert_policies", ["enabled"])

    policy_table = sa.table(
        "alert_policies",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("metric", sa.String()),
        sa.column("operator", sa.String()),
        sa.column("threshold", sa.Float()),
        sa.column("severity", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        policy_table,
        [
            {
                "id": UUID("15000000-0000-4000-8000-000000000001"),
                "name": "Critical CPU utilization",
                "metric": "CPU_PERCENT",
                "operator": "GREATER_THAN",
                "threshold": 90.0,
                "severity": "CRITICAL",
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID("15000000-0000-4000-8000-000000000002"),
                "name": "Critical memory utilization",
                "metric": "MEMORY_PERCENT",
                "operator": "GREATER_THAN",
                "threshold": 90.0,
                "severity": "CRITICAL",
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID("15000000-0000-4000-8000-000000000003"),
                "name": "Critical disk utilization",
                "metric": "DISK_PERCENT",
                "operator": "GREATER_THAN",
                "threshold": 90.0,
                "severity": "CRITICAL",
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID("15000000-0000-4000-8000-000000000004"),
                "name": "Device offline",
                "metric": "DEVICE_OFFLINE",
                "operator": "AT_LEAST",
                "threshold": 1.0,
                "severity": "HIGH",
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": UUID("15000000-0000-4000-8000-000000000005"),
                "name": "Repeated missed heartbeats",
                "metric": "HEARTBEAT_MISSED",
                "operator": "AT_LEAST",
                "threshold": 3.0,
                "severity": "CRITICAL",
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("minimum_severity", sa.String(16), nullable=False),
        sa.Column("create_incident", sa.Boolean(), nullable=False),
        sa.Column("notify_team", sa.Boolean(), nullable=False),
        sa.Column("assignment_team_id", sa.Uuid()),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source IN ('DEVICE_AGENT')", name=op.f("ck_automation_rules_source_valid")
        ),
        sa.CheckConstraint(
            "minimum_severity IN ('INFO','WARNING','HIGH','CRITICAL')",
            name=op.f("ck_automation_rules_minimum_severity_valid"),
        ),
        sa.CheckConstraint(
            "create_incident OR notify_team",
            name=op.f("ck_automation_rules_action_required"),
        ),
        sa.CheckConstraint(
            "(NOT create_incident AND NOT notify_team) OR assignment_team_id IS NOT NULL",
            name=op.f("ck_automation_rules_team_required_for_action"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_team_id"],
            ["teams.id"],
            ondelete="RESTRICT",
            name=op.f("fk_automation_rules_assignment_team_id_teams"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_automation_rules_created_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automation_rules")),
        sa.UniqueConstraint("name", name=op.f("uq_automation_rules_name")),
    )
    op.create_index(op.f("ix_automation_rules_enabled"), "automation_rules", ["enabled"])
    op.create_index(
        op.f("ix_automation_rules_assignment_team_id"),
        "automation_rules",
        ["assignment_team_id"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("incident_ticket_id", sa.Uuid()),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by_id", sa.Uuid()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_id", sa.Uuid()),
        sa.Column("suppressed_at", sa.DateTime(timezone=True)),
        sa.Column("suppressed_by_id", sa.Uuid()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('TRIGGERED','ACKNOWLEDGED','RESOLVED','SUPPRESSED')",
            name=op.f("ck_alerts_state_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('INFO','WARNING','HIGH','CRITICAL')",
            name=op.f("ck_alerts_severity_valid"),
        ),
        sa.CheckConstraint(
            "threshold >= 0 AND observed_value >= 0",
            name=op.f("ck_alerts_values_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["alert_policies.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alerts_policy_id_alert_policies"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["device_agents.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alerts_agent_id_device_agents"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alerts_asset_id_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alerts_incident_ticket_id_tickets"),
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alerts_acknowledged_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alerts_resolved_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["suppressed_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alerts_suppressed_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint("incident_ticket_id", name=op.f("uq_alerts_incident_ticket_id")),
    )
    for column in ("policy_id", "agent_id", "asset_id", "severity", "metric", "state"):
        op.create_index(op.f(f"ix_alerts_{column}"), "alerts", [column])
    op.create_index(
        "uq_alerts_active_condition",
        "alerts",
        ["policy_id", "agent_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('TRIGGERED','ACKNOWLEDGED','SUPPRESSED')"),
    )
    op.create_index("ix_alerts_state_triggered", "alerts", ["state", "triggered_at"])

    op.create_table(
        "automation_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("incident_ticket_id", sa.Uuid()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("notification_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "executed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED','SKIPPED','FAILED')",
            name=op.f("ck_automation_executions_status_valid"),
        ),
        sa.CheckConstraint(
            "notification_count >= 0",
            name=op.f("ck_automation_executions_notification_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["automation_rules.id"],
            ondelete="RESTRICT",
            name=op.f("fk_automation_executions_rule_id_automation_rules"),
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="RESTRICT",
            name=op.f("fk_automation_executions_alert_id_alerts"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_automation_executions_incident_ticket_id_tickets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automation_executions")),
    )
    op.create_index(
        "uq_automation_executions_rule_alert",
        "automation_executions",
        ["rule_id", "alert_id"],
        unique=True,
    )
    op.create_index(op.f("ix_automation_executions_rule_id"), "automation_executions", ["rule_id"])
    op.create_index(
        op.f("ix_automation_executions_alert_id"), "automation_executions", ["alert_id"]
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False),
        sa.Column("minimum_alert_severity", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "minimum_alert_severity IN ('INFO','WARNING','HIGH','CRITICAL')",
            name=op.f("ck_notification_preferences_minimum_alert_severity_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_notification_preferences_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preferences")),
        sa.UniqueConstraint("user_id", name=op.f("uq_notification_preferences_user_id")),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid()),
        sa.Column("ticket_id", sa.Uuid()),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(180), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_notifications_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="RESTRICT",
            name=op.f("fk_notifications_alert_id_alerts"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_notifications_ticket_id_tickets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_notifications_dedupe_key")),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"])
    op.create_index(op.f("ix_notifications_alert_id"), "notifications", ["alert_id"])
    op.create_index(op.f("ix_notifications_ticket_id"), "notifications", ["ticket_id"])
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid()),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "entity_type IN ('ALERT','POLICY','RULE')",
            name=op.f("ck_alert_events_entity_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alert_events_alert_id_alerts"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_alert_events_actor_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_events")),
    )
    op.create_index(op.f("ix_alert_events_entity_id"), "alert_events", ["entity_id"])
    op.create_index(op.f("ix_alert_events_alert_id"), "alert_events", ["alert_id"])
    op.create_index(op.f("ix_alert_events_actor_id"), "alert_events", ["actor_id"])
    op.create_index(
        "ix_alert_events_entity_created",
        "alert_events",
        ["entity_type", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("alert_events")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
    op.drop_table("automation_executions")
    op.drop_table("alerts")
    op.drop_table("automation_rules")
    op.drop_table("alert_policies")
    op.drop_constraint(op.f("ck_tickets_source_valid"), "tickets", type_="check")
    op.create_check_constraint(
        op.f("ck_tickets_source_valid"), "tickets", "source IN ('PORTAL', 'API')"
    )
    op.drop_constraint(op.f("ck_tickets_record_type_valid"), "tickets", type_="check")
    op.drop_index(op.f("ix_tickets_record_type"), table_name="tickets")
    op.drop_column("tickets", "record_type")
