from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DirectoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class TeamMemberRole(StrEnum):
    MEMBER = "MEMBER"
    LEAD = "LEAD"


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "departments"
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DirectoryStatus.ACTIVE)
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_valid"),
        Index("uq_departments_code_normalized", func.lower(code), unique=True),
        Index("uq_departments_name_normalized", func.lower(name), unique=True),
    )


class Location(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "locations"
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DirectoryStatus.ACTIVE)
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_valid"),
        Index("uq_locations_code_normalized", func.lower(code), unique=True),
        Index("uq_locations_name_normalized", func.lower(name), unique=True),
    )


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DirectoryStatus.ACTIVE)
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_valid"),
        Index("uq_teams_code_normalized", func.lower(code), unique=True),
        Index("uq_teams_name_normalized", func.lower(name), unique=True),
    )


class TeamMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "team_members"
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    member_role: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TeamMemberRole.MEMBER
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("member_role IN ('MEMBER', 'LEAD')", name="member_role_valid"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="interval_valid"),
        Index(
            "uq_team_members_active",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=ended_at.is_(None),
            sqlite_where=ended_at.is_(None),
        ),
    )


class DirectoryEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only application audit for Phase 5 directory administration."""

    __tablename__ = "directory_events"
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    __table_args__ = (
        Index("ix_directory_events_entity", "entity_type", "entity_id", "created_at"),
    )
