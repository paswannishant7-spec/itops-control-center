from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssetType(StrEnum):
    LAPTOP = "LAPTOP"
    DESKTOP = "DESKTOP"
    MONITOR = "MONITOR"
    PRINTER = "PRINTER"
    SERVER = "SERVER"
    NETWORK_DEVICE = "NETWORK_DEVICE"
    MOBILE_DEVICE = "MOBILE_DEVICE"


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    IN_REPAIR = "IN_REPAIR"
    LOST = "LOST"
    RETIRED = "RETIRED"
    DISPOSED = "DISPOSED"


class AssetHealthStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    asset_tag: Mapped[str] = mapped_column(String(64), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(128))
    hostname: Mapped[str | None] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    operating_system: Mapped[str | None] = mapped_column(String(160))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    mac_address: Mapped[str | None] = mapped_column(String(17))
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    purchase_date: Mapped[date | None] = mapped_column(Date)
    warranty_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=AssetStatus.ACTIVE)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AssetHealthStatus.UNKNOWN
    )
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('LAPTOP','DESKTOP','MONITOR','PRINTER','SERVER',"
            "'NETWORK_DEVICE','MOBILE_DEVICE')",
            name="asset_type_valid",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','IN_REPAIR','LOST','RETIRED','DISPOSED')",
            name="status_valid",
        ),
        CheckConstraint(
            "health_status IN ('UNKNOWN','HEALTHY','WARNING','CRITICAL','OFFLINE')",
            name="health_status_valid",
        ),
        CheckConstraint(
            "warranty_end IS NULL OR purchase_date IS NULL OR warranty_end >= purchase_date",
            name="warranty_interval_valid",
        ),
        Index("uq_assets_tag_normalized", func.lower(asset_tag), unique=True),
        Index("uq_assets_serial_normalized", func.lower(serial_number), unique=True),
        Index("ix_assets_status_health", "status", "health_status"),
    )


class AssetAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "asset_assignments"
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
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
        CheckConstraint(
            "owner_id IS NOT NULL OR department_id IS NOT NULL OR location_id IS NOT NULL",
            name="target_required",
        ),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="interval_valid"),
        Index(
            "uq_asset_assignments_active",
            "asset_id",
            unique=True,
            postgresql_where=ended_at.is_(None),
            sqlite_where=ended_at.is_(None),
        ),
        Index("ix_asset_assignments_asset_started", "asset_id", "started_at"),
    )


class AssetEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "asset_events"
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_asset_events_asset_created", "asset_id", "created_at"),)
