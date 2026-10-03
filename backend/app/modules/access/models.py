from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)


class Permission(TimestampMixin, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True, index=True
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role_code: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), primary_key=True, index=True
    )


class RoleAssignmentEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "role_assignment_events"
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    before_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    after_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
