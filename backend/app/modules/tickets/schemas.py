from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.tickets.models import CommentVisibility, ImpactLevel, TicketStatus

Title = Annotated[str, Field(min_length=5, max_length=200)]
Description = Annotated[str, Field(min_length=10, max_length=20_000)]
Reason = Annotated[str, Field(min_length=3, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NamedReference(StrictModel):
    id: UUID
    name: str


class PersonReference(StrictModel):
    id: UUID
    display_name: str
    email: str


class TicketCreate(StrictModel):
    title: Title
    description: Description
    impact: ImpactLevel = ImpactLevel.MEDIUM
    urgency: ImpactLevel = ImpactLevel.MEDIUM
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    asset_id: UUID | None = None


class TicketUpdate(StrictModel):
    title: Title | None = None
    description: Description | None = None
    impact: ImpactLevel | None = None
    urgency: ImpactLevel | None = None
    category_id: UUID | None = None
    subcategory_id: UUID | None = None
    asset_id: UUID | None = None
    reason: Reason

    @model_validator(mode="after")
    def require_change(self) -> "TicketUpdate":
        fields = {
            "title",
            "description",
            "impact",
            "urgency",
            "category_id",
            "subcategory_id",
            "asset_id",
        }
        if not (fields & self.model_fields_set):
            raise ValueError("At least one ticket field must be supplied")
        return self


class TicketTransitionRequest(StrictModel):
    status: TicketStatus
    reason: Reason
    resolution_summary: str | None = Field(default=None, max_length=10_000)
    resolution_code: str | None = Field(default=None, max_length=64)


class TicketAssignmentRequest(StrictModel):
    team_id: UUID
    technician_id: UUID | None = None
    reason: Reason


class TicketCommentCreate(StrictModel):
    body: str = Field(min_length=1, max_length=10_000)
    visibility: CommentVisibility = CommentVisibility.PUBLIC


class TicketSummary(StrictModel):
    id: UUID
    reference: str
    title: str
    requester: PersonReference
    department: NamedReference | None
    location: NamedReference | None
    impact: str
    urgency: str
    priority: str
    sla_state: str | None
    status: str
    assignment_team: NamedReference | None
    assigned_technician: PersonReference | None
    record_type: str
    source: str
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketSummary):
    description: str
    asset_id: UUID | None
    category: NamedReference | None
    subcategory: NamedReference | None
    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    reopened_at: datetime | None
    resolution_summary: str | None
    resolution_code: str | None


class TicketPage(StrictModel):
    items: list[TicketSummary]
    total: int
    offset: int
    limit: int


class TicketCommentResponse(StrictModel):
    id: UUID
    author: PersonReference
    body: str
    visibility: str
    created_at: datetime
    updated_at: datetime


class CommentPage(StrictModel):
    items: list[TicketCommentResponse]
    total: int
    offset: int
    limit: int


class TicketAttachmentResponse(StrictModel):
    id: UUID
    original_name: str
    content_type: str
    size_bytes: int
    uploader: PersonReference
    created_at: datetime


class TicketEventResponse(StrictModel):
    id: UUID
    event_type: str
    actor: PersonReference
    before_state: dict[str, object] | None
    after_state: dict[str, object] | None
    reason: str
    created_at: datetime


class EventPage(StrictModel):
    items: list[TicketEventResponse]
    total: int
    offset: int
    limit: int


class CategoryResponse(StrictModel):
    id: UUID
    code: str
    name: str
    subcategories: list[NamedReference]
