from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    employee_number: Mapped[str | None] = mapped_column(String(64))
    job_title: Mapped[str | None] = mapped_column(String(120))
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=UserStatus.ACTIVE)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DISABLED', 'LOCKED')", name="status_valid"),
        Index("uq_users_email_normalized", func.lower(email), unique=True),
        Index(
            "uq_users_employee_number_normalized",
            func.lower(employee_number),
            unique=True,
        ),
    )


class RefreshSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (Index("ix_refresh_sessions_family_active", "family_id", "revoked_at"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    family_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="RESTRICT")
    )
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))


class PasswordResetToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
