from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.modules.sla.models import SlaState
from app.modules.tickets.models import ImpactLevel, TicketPriority


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MatrixEntry(StrictModel):
    impact: ImpactLevel
    urgency: ImpactLevel
    priority: TicketPriority


class MatrixUpdate(StrictModel):
    priority: TicketPriority


Minute = Annotated[int, Field(ge=0, le=2879)]


class WindowInput(StrictModel):
    weekday: int = Field(ge=0, le=6)
    start_minute: Minute
    end_minute: int = Field(ge=1, le=2880)

    @field_validator("end_minute")
    @classmethod
    def end_after_start(cls, value: int, info: ValidationInfo) -> int:
        start = info.data.get("start_minute")
        if start is not None and value <= start:
            raise ValueError("end_minute must be after start_minute")
        return value


class HolidayInput(StrictModel):
    holiday_date: date
    name: str = Field(min_length=1, max_length=120)


class CalendarWrite(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    timezone: str = Field(min_length=1, max_length=64)
    is_active: bool = True
    is_default: bool = False
    windows: list[WindowInput] = Field(min_length=1, max_length=28)
    holidays: list[HolidayInput] = Field(default_factory=list, max_length=366)


class CalendarResponse(CalendarWrite):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PolicyWrite(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    priority: TicketPriority
    calendar_id: UUID
    response_target_minutes: int = Field(ge=1, le=525_600)
    resolution_target_minutes: int = Field(ge=1, le=2_102_400)
    at_risk_percent: int = Field(default=80, ge=1, le=99)
    is_active: bool = True

    @model_validator(mode="after")
    def targets_are_ordered(self) -> "PolicyWrite":
        if self.resolution_target_minutes < self.response_target_minutes:
            raise ValueError("Resolution target must not be shorter than response target")
        return self


class PolicyResponse(PolicyWrite):
    id: UUID
    created_at: datetime
    updated_at: datetime


class SlaSnapshot(StrictModel):
    instance_id: UUID
    policy_name: str
    calendar_name: str
    calendar_timezone: str
    state: SlaState
    active_target: str
    response_target_seconds: int
    resolution_target_seconds: int
    response_elapsed_seconds: int
    resolution_elapsed_seconds: int
    elapsed_seconds: int
    remaining_seconds: int
    percentage: float
    is_paused: bool
    response_breached_at: datetime | None
    resolution_breached_at: datetime | None
    escalated_at: datetime | None
    last_evaluated_at: datetime | None


class WorkerResult(StrictModel):
    inspected: int
    changed: int
