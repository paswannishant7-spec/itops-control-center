from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SlaState(StrEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class PriorityMatrix(TimestampMixin, Base):
    __tablename__ = "priority_matrix"
    impact: Mapped[str] = mapped_column(String(16), primary_key=True)
    urgency: Mapped[str] = mapped_column(String(16), primary_key=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    __table_args__ = (
        CheckConstraint("impact IN ('LOW', 'MEDIUM', 'HIGH')", name="impact_valid"),
        CheckConstraint("urgency IN ('LOW', 'MEDIUM', 'HIGH')", name="urgency_valid"),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="priority_valid"),
    )


class BusinessCalendar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_calendars"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        Index("uq_business_calendars_name_normalized", func.lower(name), unique=True),
        Index(
            "uq_business_calendars_default",
            "is_default",
            unique=True,
            postgresql_where=is_default.is_(True),
            sqlite_where=is_default.is_(True),
        ),
    )


class BusinessWindow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "business_windows"
    calendar_id: Mapped[UUID] = mapped_column(
        ForeignKey("business_calendars.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="weekday_valid"),
        CheckConstraint("start_minute >= 0 AND start_minute < 1440", name="start_valid"),
        CheckConstraint("end_minute > start_minute AND end_minute <= 2880", name="end_valid"),
        UniqueConstraint(
            "calendar_id",
            "weekday",
            "start_minute",
            "end_minute",
            name="uq_business_windows_window_unique",
        ),
    )


class BusinessHoliday(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "business_holidays"
    calendar_id: Mapped[UUID] = mapped_column(
        ForeignKey("business_calendars.id", ondelete="CASCADE"), nullable=False, index=True
    )
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "calendar_id", "holiday_date", name="uq_business_holidays_calendar_date_unique"
        ),
    )


class SlaPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sla_policies"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    calendar_id: Mapped[UUID] = mapped_column(
        ForeignKey("business_calendars.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    response_target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_target_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    at_risk_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        Index("uq_sla_policies_name_normalized", func.lower(name), unique=True),
        Index(
            "uq_sla_policies_active_priority",
            "priority",
            unique=True,
            postgresql_where=is_active.is_(True),
            sqlite_where=is_active.is_(True),
        ),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="priority_valid"),
        CheckConstraint("response_target_minutes > 0", name="response_target_positive"),
        CheckConstraint("resolution_target_minutes > 0", name="resolution_target_positive"),
        CheckConstraint("at_risk_percent > 0 AND at_risk_percent < 100", name="risk_valid"),
    )


class SlaInstance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sla_instances"
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("sla_policies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    calendar_id: Mapped[UUID] = mapped_column(
        ForeignKey("business_calendars.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    response_target_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_target_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    at_risk_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    response_elapsed_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolution_elapsed_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("ticket_id", name="uq_sla_instances_ticket_id"),
        CheckConstraint(
            "state IN ('ON_TRACK', 'AT_RISK', 'BREACHED', 'PAUSED', 'COMPLETED')",
            name="state_valid",
        ),
        CheckConstraint("response_target_seconds > 0", name="response_target_positive"),
        CheckConstraint("resolution_target_seconds > 0", name="resolution_target_positive"),
        CheckConstraint("at_risk_percent > 0 AND at_risk_percent < 100", name="risk_valid"),
        CheckConstraint(
            "response_elapsed_seconds >= 0 AND resolution_elapsed_seconds >= 0",
            name="elapsed_nonnegative",
        ),
        Index("ix_sla_instances_state_updated", "state", "updated_at"),
    )


class SlaPause(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sla_pauses"
    instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("sla_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="interval_valid"),
        Index(
            "uq_sla_pauses_active",
            "instance_id",
            unique=True,
            postgresql_where=ended_at.is_(None),
            sqlite_where=ended_at.is_(None),
        ),
    )


class SlaEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sla_events"
    instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("sla_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    notification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_sla_events_instance_created", "instance_id", "created_at"),)
