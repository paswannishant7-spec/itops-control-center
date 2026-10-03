from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"
    UNREGISTERED = "UNREGISTERED"
    DISABLED = "DISABLED"


class CredentialStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class DeviceAgent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "device_agents"
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AgentStatus.UNREGISTERED, index=True
    )
    credential_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CredentialStatus.PENDING
    )
    credential_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    credential_prefix: Mapped[str | None] = mapped_column(String(12))
    enrollment_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    enrollment_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_metric_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    missed_heartbeat_count: Mapped[int] = mapped_column(nullable=False, default=0)
    agent_version: Mapped[str | None] = mapped_column(String(32))
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_device_agents_asset_id"),
        CheckConstraint(
            "status IN ('ONLINE','OFFLINE','DEGRADED','UNREGISTERED','DISABLED')",
            name="status_valid",
        ),
        CheckConstraint(
            "credential_status IN ('PENDING','ACTIVE','REVOKED')",
            name="credential_status_valid",
        ),
        CheckConstraint("missed_heartbeat_count >= 0", name="missed_heartbeat_nonnegative"),
    )


class DeviceHeartbeat(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "device_heartbeats"
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("device_agents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available: Mapped[bool] = mapped_column(nullable=False)
    resulting_status: Mapped[str] = mapped_column(String(16), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    operating_system: Mapped[str] = mapped_column(String(160), nullable=False)
    ip_addresses: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    boot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collection_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        CheckConstraint("resulting_status IN ('ONLINE','DEGRADED')", name="resulting_status_valid"),
        Index("ix_device_heartbeats_agent_received", "agent_id", "received_at"),
    )


class DeviceMetric(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "device_metrics"
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("device_agents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    disk_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network_bytes_sent: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network_bytes_received: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "cpu_percent >= 0 AND cpu_percent <= 100 AND memory_percent >= 0 AND "
            "memory_percent <= 100 AND disk_percent >= 0 AND disk_percent <= 100",
            name="percentages_valid",
        ),
        CheckConstraint(
            "memory_used_bytes >= 0 AND memory_total_bytes > 0 AND "
            "memory_used_bytes <= memory_total_bytes",
            name="memory_values_valid",
        ),
        CheckConstraint(
            "disk_used_bytes >= 0 AND disk_total_bytes > 0 AND disk_used_bytes <= disk_total_bytes",
            name="disk_values_valid",
        ),
        CheckConstraint(
            "network_bytes_sent >= 0 AND network_bytes_received >= 0",
            name="network_values_valid",
        ),
        Index("ix_device_metrics_agent_sampled", "agent_id", "sampled_at"),
    )
