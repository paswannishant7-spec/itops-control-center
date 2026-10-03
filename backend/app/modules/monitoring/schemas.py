from datetime import datetime
from ipaddress import ip_address
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Reason = Annotated[str, Field(min_length=3, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EnrollmentCreate(StrictModel):
    asset_id: UUID
    expires_in_minutes: int = Field(default=30, ge=5, le=1440)
    reason: Reason


class EnrollmentResponse(StrictModel):
    agent_id: UUID
    device_id: UUID
    enrollment_token: str
    expires_at: datetime


class AgentEnroll(StrictModel):
    enrollment_token: str = Field(min_length=32, max_length=256)
    agent_version: str = Field(min_length=1, max_length=32)


class AgentCredentialResponse(StrictModel):
    agent_id: UUID
    device_id: UUID
    credential: str
    credential_status: str


class HeartbeatCreate(StrictModel):
    observed_at: datetime
    available: bool = True
    hostname: str = Field(min_length=1, max_length=255)
    operating_system: str = Field(min_length=1, max_length=160)
    ip_addresses: list[str] = Field(default_factory=list, max_length=16)
    boot_time: datetime
    collection_errors: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("ip_addresses")
    @classmethod
    def unique_addresses(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            try:
                normalized.append(str(ip_address(item)))
            except ValueError as exc:
                raise ValueError("IP address is invalid") from exc
        return list(dict.fromkeys(normalized))

    @field_validator("collection_errors")
    @classmethod
    def bounded_errors(cls, value: list[str]) -> list[str]:
        return [item[:120] for item in value]


class MetricCreate(StrictModel):
    sampled_at: datetime
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    memory_used_bytes: int = Field(ge=0)
    memory_total_bytes: int = Field(gt=0)
    disk_percent: float = Field(ge=0, le=100)
    disk_used_bytes: int = Field(ge=0)
    disk_total_bytes: int = Field(gt=0)
    network_bytes_sent: int = Field(ge=0)
    network_bytes_received: int = Field(ge=0)

    @model_validator(mode="after")
    def used_does_not_exceed_total(self) -> "MetricCreate":
        if self.memory_used_bytes > self.memory_total_bytes:
            raise ValueError("Memory used cannot exceed total")
        if self.disk_used_bytes > self.disk_total_bytes:
            raise ValueError("Disk used cannot exceed total")
        return self


class IngestResponse(StrictModel):
    accepted: bool
    server_time: datetime
    status: str


class AgentSummary(StrictModel):
    agent_id: UUID
    device_id: UUID
    asset_tag: str
    hostname: str | None
    status: str
    credential_status: str
    credential_prefix: str | None
    last_seen: datetime | None
    last_heartbeat: datetime | None
    missed_heartbeat_count: int
    agent_version: str | None
    enrolled_at: datetime | None


class AgentPage(StrictModel):
    items: list[AgentSummary]
    total: int
    offset: int
    limit: int


class MetricResponse(StrictModel):
    id: UUID
    sampled_at: datetime
    received_at: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    disk_percent: float
    disk_used_bytes: int
    disk_total_bytes: int
    network_bytes_sent: int
    network_bytes_received: int


class MetricPage(StrictModel):
    items: list[MetricResponse]
    total: int
    offset: int
    limit: int


class DisableAgent(StrictModel):
    reason: Reason
