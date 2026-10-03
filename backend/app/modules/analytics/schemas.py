from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyticsScope(StrictModel):
    audience: Literal["TEAM", "ORGANIZATION"]
    label: str
    window_days: int = Field(ge=7, le=365)
    window_start: datetime
    window_end: datetime


class OperationalSummary(StrictModel):
    open_tickets: int = Field(ge=0)
    assigned_to_me: int = Field(ge=0)
    unassigned_tickets: int = Field(ge=0)
    active_incidents: int = Field(ge=0)
    critical_incidents: int = Field(ge=0)
    sla_at_risk: int = Field(ge=0)
    sla_breached: int = Field(ge=0)
    online_devices: int = Field(ge=0)
    offline_devices: int = Field(ge=0)
    unhealthy_devices: int = Field(ge=0)
    critical_alerts: int = Field(ge=0)


class DurationMetric(StrictModel):
    minutes: float | None = Field(default=None, ge=0)
    sample_size: int = Field(ge=0)


class PercentageMetric(StrictModel):
    percent: float | None = Field(default=None, ge=0, le=100)
    sample_size: int = Field(ge=0)


class PerformanceMetrics(StrictModel):
    mttr: DurationMetric
    mtta: DurationMetric
    sla_compliance: PercentageMetric
    first_contact_resolution_proxy: PercentageMetric
    reopen_rate: PercentageMetric


class VolumePoint(StrictModel):
    period_start: date
    created: int = Field(ge=0)
    resolved: int = Field(ge=0)


class TicketVolume(StrictModel):
    daily: list[VolumePoint]
    weekly: list[VolumePoint]
    monthly: list[VolumePoint]


class BreakdownItem(StrictModel):
    label: str
    count: int = Field(ge=0)


class TechnicianWorkload(StrictModel):
    technician_id: UUID
    technician_name: str
    assigned_open: int = Field(ge=0)
    resolved_in_window: int = Field(ge=0)


class RecurringIssue(StrictModel):
    category: str
    subcategory: str | None
    ticket_count: int = Field(ge=2)


class AssetIncidentFrequency(StrictModel):
    asset_id: UUID
    asset_tag: str
    incident_count: int = Field(ge=1)


class AiAssistanceMetrics(StrictModel):
    reviewed_recommendations: int = Field(ge=0)
    accepted: int = Field(ge=0)
    edited: int = Field(ge=0)
    rejected: int = Field(ge=0)
    regenerated: int = Field(ge=0)
    acceptance_rate: float | None = Field(default=None, ge=0, le=100)
    edit_rate: float | None = Field(default=None, ge=0, le=100)
    rejection_rate: float | None = Field(default=None, ge=0, le=100)
    label: str


class AttentionTicket(StrictModel):
    id: UUID
    reference: str
    title: str
    priority: str
    status: str
    sla_state: str | None
    updated_at: datetime


class AttentionDevice(StrictModel):
    agent_id: UUID
    asset_id: UUID
    asset_tag: str
    hostname: str | None
    status: str
    health_status: str


class AttentionAlert(StrictModel):
    id: UUID
    asset_id: UUID
    asset_tag: str
    severity: str
    metric: str
    state: str
    triggered_at: datetime


class AttentionQueue(StrictModel):
    urgent_tickets: list[AttentionTicket]
    device_health_issues: list[AttentionDevice]
    critical_alerts: list[AttentionAlert]


class DashboardResponse(StrictModel):
    generated_at: datetime
    scope: AnalyticsScope
    summary: OperationalSummary
    performance: PerformanceMetrics
    ticket_volume: TicketVolume
    by_category: list[BreakdownItem]
    by_department: list[BreakdownItem]
    by_priority: list[BreakdownItem]
    technician_workload: list[TechnicianWorkload]
    recurring_issues: list[RecurringIssue]
    asset_incident_frequency: list[AssetIncidentFrequency]
    ai_assistance: AiAssistanceMetrics
    attention: AttentionQueue
