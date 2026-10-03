from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TicketStatus(StrEnum):
    NEW = "NEW"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_USER = "PENDING_USER"
    PENDING_VENDOR = "PENDING_VENDOR"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ImpactLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TicketPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TicketSource(StrEnum):
    PORTAL = "PORTAL"
    API = "API"
    AUTOMATION = "AUTOMATION"


class TicketType(StrEnum):
    REQUEST = "REQUEST"
    INCIDENT = "INCIDENT"


class CommentVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class TicketCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ticket_categories"
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    __table_args__ = (
        Index("uq_ticket_categories_code_normalized", func.lower(code), unique=True),
        Index("uq_ticket_categories_name_normalized", func.lower(name), unique=True),
    )


class TicketSubcategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ticket_subcategories"
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("ticket_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    __table_args__ = (
        Index(
            "uq_ticket_subcategories_category_code", "category_id", func.lower(code), unique=True
        ),
        Index(
            "uq_ticket_subcategories_category_name", "category_id", func.lower(name), unique=True
        ),
    )


class Ticket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tickets"
    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requester_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ticket_categories.id", ondelete="RESTRICT"), index=True
    )
    subcategory_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ticket_subcategories.id", ondelete="RESTRICT"), index=True
    )
    impact: Mapped[str] = mapped_column(String(16), nullable=False)
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    assignment_team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), index=True
    )
    assigned_technician_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    record_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TicketType.REQUEST, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolution_code: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint("impact IN ('LOW', 'MEDIUM', 'HIGH')", name="impact_valid"),
        CheckConstraint("urgency IN ('LOW', 'MEDIUM', 'HIGH')", name="urgency_valid"),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="priority_valid"),
        CheckConstraint(
            "status IN ('NEW', 'OPEN', 'IN_PROGRESS', 'PENDING_USER', "
            "'PENDING_VENDOR', 'ESCALATED', 'RESOLVED', 'CLOSED', 'CANCELLED')",
            name="status_valid",
        ),
        CheckConstraint("record_type IN ('REQUEST', 'INCIDENT')", name="record_type_valid"),
        CheckConstraint("source IN ('PORTAL', 'API', 'AUTOMATION')", name="source_valid"),
        CheckConstraint(
            "assigned_technician_id IS NULL OR assignment_team_id IS NOT NULL",
            name="technician_requires_team",
        ),
        Index("ix_tickets_status_created_at", "status", "created_at"),
        Index("ix_tickets_team_status", "assignment_team_id", "status"),
    )


class TicketComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ticket_comments"
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    __table_args__ = (
        CheckConstraint("visibility IN ('PUBLIC', 'INTERNAL')", name="visibility_valid"),
        Index("ix_ticket_comments_ticket_created", "ticket_id", "created_at"),
    )


class TicketAttachment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ticket_attachments"
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploader_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_ticket_attachments_ticket_created", "ticket_id", "created_at"),
    )


class TicketEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ticket_events"
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_ticket_events_ticket_created", "ticket_id", "created_at"),)


class TicketAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ticket_assignments"
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    technician_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    assigned_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="interval_valid"),
        Index(
            "uq_ticket_assignments_active",
            "ticket_id",
            unique=True,
            postgresql_where=ended_at.is_(None),
            sqlite_where=ended_at.is_(None),
        ),
    )
