from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.alerts.models import AlertMetric, AlertOperator, AlertSeverity, AlertState

Reason = Annotated[str, Field(min_length=3, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PolicyCreate(StrictModel):
    name: str = Field(min_length=3, max_length=120)
    metric: AlertMetric
    operator: AlertOperator
    threshold: float = Field(ge=0, le=1_000_000)
    severity: AlertSeverity
    enabled: bool = True
    reason: Reason

    @model_validator(mode="after")
    def metric_threshold_is_valid(self) -> "PolicyCreate":
        if (
            self.metric
            in {
                AlertMetric.CPU_PERCENT,
                AlertMetric.MEMORY_PERCENT,
                AlertMetric.DISK_PERCENT,
            }
            and self.threshold > 100
        ):
            raise ValueError("Percentage thresholds cannot exceed 100")
        if self.metric == AlertMetric.DEVICE_OFFLINE and self.threshold != 1:
            raise ValueError("Device offline threshold must be 1")
        return self


class PolicyUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    operator: AlertOperator | None = None
    threshold: float | None = Field(default=None, ge=0, le=1_000_000)
    severity: AlertSeverity | None = None
    enabled: bool | None = None
    reason: Reason


class PolicyResponse(StrictModel):
    id: UUID
    name: str
    metric: str
    operator: str
    threshold: float
    severity: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class PolicyPage(StrictModel):
    items: list[PolicyResponse]
    total: int


class RuleCreate(StrictModel):
    name: str = Field(min_length=3, max_length=120)
    enabled: bool = True
    source: str = Field(default="DEVICE_AGENT", pattern="^DEVICE_AGENT$")
    minimum_severity: AlertSeverity
    create_incident: bool = False
    notify_team: bool = False
    assignment_team_id: UUID | None = None
    reason: Reason

    @model_validator(mode="after")
    def actions_are_valid(self) -> "RuleCreate":
        if not self.create_incident and not self.notify_team:
            raise ValueError("At least one automation action is required")
        if self.assignment_team_id is None:
            raise ValueError("Automation actions require an assignment team")
        return self


class RuleUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    enabled: bool | None = None
    minimum_severity: AlertSeverity | None = None
    create_incident: bool | None = None
    notify_team: bool | None = None
    assignment_team_id: UUID | None = None
    reason: Reason


class RuleResponse(StrictModel):
    id: UUID
    name: str
    enabled: bool
    source: str
    minimum_severity: str
    create_incident: bool
    notify_team: bool
    assignment_team_id: UUID | None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime


class RulePage(StrictModel):
    items: list[RuleResponse]
    total: int


class AlertTransition(StrictModel):
    reason: Reason


class AlertResponse(StrictModel):
    id: UUID
    policy_id: UUID
    agent_id: UUID
    asset_id: UUID
    asset_tag: str
    incident_ticket_id: UUID | None
    incident_reference: str | None
    source: str
    severity: str
    metric: str
    threshold: float
    observed_value: float
    state: str
    triggered_at: datetime
    last_observed_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    suppressed_at: datetime | None


class AlertPage(StrictModel):
    items: list[AlertResponse]
    total: int
    offset: int
    limit: int


class ExecutionResponse(StrictModel):
    id: UUID
    rule_id: UUID
    alert_id: UUID
    incident_ticket_id: UUID | None
    status: str
    notification_count: int
    error_code: str | None
    executed_at: datetime


class ExecutionPage(StrictModel):
    items: list[ExecutionResponse]
    total: int


class PreferenceUpdate(StrictModel):
    in_app_enabled: bool
    minimum_alert_severity: AlertSeverity


class PreferenceResponse(StrictModel):
    in_app_enabled: bool
    minimum_alert_severity: str


class NotificationResponse(StrictModel):
    id: UUID
    alert_id: UUID | None
    ticket_id: UUID | None
    event_type: str
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime


class NotificationPage(StrictModel):
    items: list[NotificationResponse]
    total: int
    unread: int
    offset: int
    limit: int


AlertStateFilter = AlertState | None
