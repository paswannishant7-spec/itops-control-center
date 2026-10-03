from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AlertMetric(StrEnum):
    CPU_PERCENT = "CPU_PERCENT"
    MEMORY_PERCENT = "MEMORY_PERCENT"
    DISK_PERCENT = "DISK_PERCENT"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    HEARTBEAT_MISSED = "HEARTBEAT_MISSED"


class AlertOperator(StrEnum):
    GREATER_THAN = "GREATER_THAN"
    AT_LEAST = "AT_LEAST"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertState(StrEnum):
    TRIGGERED = "TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class AlertPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alert_policies"
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    metric: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String(24), nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True, index=True)
    __table_args__ = (
        CheckConstraint(
            "metric IN ('CPU_PERCENT','MEMORY_PERCENT','DISK_PERCENT',"
            "'DEVICE_OFFLINE','HEARTBEAT_MISSED')",
            name="metric_valid",
        ),
        CheckConstraint("operator IN ('GREATER_THAN','AT_LEAST')", name="operator_valid"),
        CheckConstraint("severity IN ('INFO','WARNING','HIGH','CRITICAL')", name="severity_valid"),
        CheckConstraint("threshold >= 0", name="threshold_nonnegative"),
    )


class AutomationRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_rules"
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="DEVICE_AGENT")
    minimum_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    create_incident: Mapped[bool] = mapped_column(nullable=False, default=False)
    notify_team: Mapped[bool] = mapped_column(nullable=False, default=False)
    assignment_team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), index=True
    )
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    __table_args__ = (
        CheckConstraint("source IN ('DEVICE_AGENT')", name="source_valid"),
        CheckConstraint(
            "minimum_severity IN ('INFO','WARNING','HIGH','CRITICAL')",
            name="minimum_severity_valid",
        ),
        CheckConstraint("create_incident OR notify_team", name="action_required"),
        CheckConstraint(
            "(NOT create_incident AND NOT notify_team) OR assignment_team_id IS NOT NULL",
            name="team_required_for_action",
        ),
    )


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("alert_policies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("device_agents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    incident_ticket_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), unique=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    threshold: Mapped[float] = mapped_column(nullable=False)
    observed_value: Mapped[float] = mapped_column(nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppressed_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('TRIGGERED','ACKNOWLEDGED','RESOLVED','SUPPRESSED')",
            name="state_valid",
        ),
        CheckConstraint("severity IN ('INFO','WARNING','HIGH','CRITICAL')", name="severity_valid"),
        CheckConstraint("threshold >= 0 AND observed_value >= 0", name="values_nonnegative"),
        Index(
            "uq_alerts_active_condition",
            "policy_id",
            "agent_id",
            unique=True,
            postgresql_where=state.in_(("TRIGGERED", "ACKNOWLEDGED", "SUPPRESSED")),
            sqlite_where=state.in_(("TRIGGERED", "ACKNOWLEDGED", "SUPPRESSED")),
        ),
        Index("ix_alerts_state_triggered", "state", "triggered_at"),
    )


class AutomationExecution(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_executions"
    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    alert_id: Mapped[UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    incident_ticket_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    notification_count: Mapped[int] = mapped_column(nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint("status IN ('SUCCEEDED','SKIPPED','FAILED')", name="status_valid"),
        CheckConstraint("notification_count >= 0", name="notification_count_nonnegative"),
        Index("uq_automation_executions_rule_alert", "rule_id", "alert_id", unique=True),
    )


class NotificationPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    in_app_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    minimum_alert_severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AlertSeverity.WARNING
    )
    __table_args__ = (
        CheckConstraint(
            "minimum_alert_severity IN ('INFO','WARNING','HIGH','CRITICAL')",
            name="minimum_alert_severity_valid",
        ),
    )


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    alert_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="RESTRICT"), index=True
    )
    ticket_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)


class AlertEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "alert_events"
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    alert_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint("entity_type IN ('ALERT','POLICY','RULE')", name="entity_type_valid"),
        Index("ix_alert_events_entity_created", "entity_type", "entity_id", "created_at"),
    )
