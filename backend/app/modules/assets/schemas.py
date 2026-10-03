import re
from datetime import date, datetime
from ipaddress import ip_address
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.assets.models import AssetHealthStatus, AssetStatus, AssetType

Reason = Annotated[str, Field(min_length=3, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AssetCreate(StrictModel):
    asset_tag: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    serial_number: str | None = Field(default=None, min_length=1, max_length=128)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: AssetType
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    operating_system: str | None = Field(default=None, max_length=160)
    ip_address: str | None = Field(default=None, max_length=45)
    mac_address: str | None = Field(default=None, max_length=17)
    owner_id: UUID | None = None
    department_id: UUID | None = None
    location_id: UUID | None = None
    purchase_date: date | None = None
    warranty_end: date | None = None
    status: AssetStatus = AssetStatus.ACTIVE
    health_status: AssetHealthStatus = AssetHealthStatus.UNKNOWN
    reason: Reason

    @field_validator("asset_tag", mode="before")
    @classmethod
    def normalize_tag(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("ip_address")
    @classmethod
    def valid_ip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError("IP address is invalid") from exc

    @field_validator("mac_address")
    @classmethod
    def valid_mac(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.replace("-", ":").upper()
        if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", normalized):
            raise ValueError("MAC address is invalid")
        return normalized

    @model_validator(mode="after")
    def valid_dates(self) -> "AssetCreate":
        if self.purchase_date and self.warranty_end and self.warranty_end < self.purchase_date:
            raise ValueError("Warranty end cannot precede purchase date")
        return self


class AssetUpdate(StrictModel):
    asset_tag: str | None = Field(default=None, min_length=1, max_length=64)
    serial_number: str | None = Field(default=None, min_length=1, max_length=128)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: AssetType | None = None
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    operating_system: str | None = Field(default=None, max_length=160)
    ip_address: str | None = Field(default=None, max_length=45)
    mac_address: str | None = Field(default=None, max_length=17)
    purchase_date: date | None = None
    warranty_end: date | None = None
    status: AssetStatus | None = None
    health_status: AssetHealthStatus | None = None
    reason: Reason

    @field_validator("asset_tag", mode="before")
    @classmethod
    def normalize_tag(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("ip_address")
    @classmethod
    def valid_ip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError("IP address is invalid") from exc

    @field_validator("mac_address")
    @classmethod
    def valid_mac(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.replace("-", ":").upper()
        if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", normalized):
            raise ValueError("MAC address is invalid")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "AssetUpdate":
        if not (set(type(self).model_fields) - {"reason"}) & self.model_fields_set:
            raise ValueError("At least one asset field must be supplied")
        if self.status in {AssetStatus.RETIRED, AssetStatus.DISPOSED}:
            raise ValueError("Use the retirement endpoint for terminal status")
        return self


class AssetAssignmentCreate(StrictModel):
    owner_id: UUID | None = None
    department_id: UUID | None = None
    location_id: UUID | None = None
    clear: bool = False
    reason: Reason

    @model_validator(mode="after")
    def target_or_clear(self) -> "AssetAssignmentCreate":
        supplied = any((self.owner_id, self.department_id, self.location_id))
        if self.clear == supplied:
            raise ValueError("Provide an assignment target or set clear=true")
        return self


class AssetRetire(StrictModel):
    reason: Reason


class ReferenceSummary(StrictModel):
    id: UUID
    code: str
    name: str


class OwnerSummary(StrictModel):
    id: UUID
    display_name: str
    email: str


class AssetResponse(StrictModel):
    id: UUID
    asset_tag: str
    serial_number: str | None
    hostname: str | None
    asset_type: str
    manufacturer: str | None
    model: str | None
    operating_system: str | None
    ip_address: str | None
    mac_address: str | None
    owner: OwnerSummary | None
    department: ReferenceSummary | None
    location: ReferenceSummary | None
    purchase_date: date | None
    warranty_end: date | None
    status: str
    last_seen: datetime | None
    health_status: str
    created_at: datetime
    updated_at: datetime


class AssetPage(StrictModel):
    items: list[AssetResponse]
    total: int
    offset: int
    limit: int


class AssignmentResponse(StrictModel):
    id: UUID
    owner: OwnerSummary | None
    department: ReferenceSummary | None
    location: ReferenceSummary | None
    assigned_by: OwnerSummary
    reason: str
    started_at: datetime
    ended_at: datetime | None


class AssetEventResponse(StrictModel):
    id: UUID
    action: str
    actor: OwnerSummary
    before_state: dict[str, object] | None
    after_state: dict[str, object] | None
    reason: str
    created_at: datetime


class AssetHistoryResponse(StrictModel):
    assignments: list[AssignmentResponse]
    events: list[AssetEventResponse]


class AssetTicketSummary(StrictModel):
    id: UUID
    reference: str
    title: str
    status: str
    priority: str
    updated_at: datetime
