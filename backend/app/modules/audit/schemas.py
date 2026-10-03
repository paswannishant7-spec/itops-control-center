from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditSource(StrEnum):
    ACCESS = "ACCESS"
    DIRECTORY = "DIRECTORY"
    TICKET = "TICKET"
    SLA = "SLA"
    KNOWLEDGE = "KNOWLEDGE"
    ASSET = "ASSET"
    ALERT = "ALERT"
    AI = "AI"


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source: AuditSource
    action: str
    entity_type: str
    entity_id: UUID
    actor_id: UUID | None
    before_state: dict[str, object] | None
    after_state: dict[str, object] | None
    reason: str
    request_id: str | None
    created_at: datetime


class AuditEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuditEventResponse]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
