from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class RealtimeTopic(StrEnum):
    TICKETS = "tickets"
    SLA = "sla"
    ALERTS = "alerts"
    NOTIFICATIONS = "notifications"
    DEVICES = "devices"
    ACCESS = "access"


class RealtimeEvent(UUIDPrimaryKeyMixin, Base):
    """Content-free transactional signal published after its owning transaction commits."""

    __tablename__ = "realtime_events"
    sequence: Mapped[int | None] = mapped_column(BigInteger, index=True)
    topic: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    resource_id: Mapped[UUID | None] = mapped_column(index=True)
    recipient_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("sequence", name="uq_realtime_events_sequence"),
        CheckConstraint(
            "topic IN ('tickets','sla','alerts','notifications','devices','access')",
            name="topic_valid",
        ),
        Index("ix_realtime_events_topic_sequence", "topic", "sequence"),
        Index("ix_realtime_events_recipient_sequence", "recipient_id", "sequence"),
        Index("ix_realtime_events_created_at", "created_at"),
    )


class RealtimeCursor(Base):
    """Serializes publication so committed events receive a gap-free delivery order."""

    __tablename__ = "realtime_cursor"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("value >= 0", name="value_nonnegative"),
    )
