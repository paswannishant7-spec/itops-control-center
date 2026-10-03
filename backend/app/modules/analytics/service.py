from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from statistics import fmean
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.repository import AnalyticsRepository, AnalyticsTicket
from app.modules.analytics.schemas import (
    AiAssistanceMetrics,
    AnalyticsScope,
    AssetIncidentFrequency,
    AttentionAlert,
    AttentionDevice,
    AttentionQueue,
    AttentionTicket,
    BreakdownItem,
    DashboardResponse,
    DurationMetric,
    OperationalSummary,
    PercentageMetric,
    PerformanceMetrics,
    RecurringIssue,
    TechnicianWorkload,
    TicketVolume,
    VolumePoint,
)
from app.modules.assets.service import AssetService
from app.modules.tickets.service import TicketService

ACTIVE_TICKET_STATES = frozenset(
    {"NEW", "OPEN", "IN_PROGRESS", "PENDING_USER", "PENDING_VENDOR", "ESCALATED"}
)
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


class WorkloadCounter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.open = 0
        self.resolved = 0


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def percent(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100 / denominator, 1) if denominator else None


def duration_minutes(values: list[float]) -> DurationMetric:
    return DurationMetric(
        minutes=round(fmean(values) / 60, 1) if values else None,
        sample_size=len(values),
    )


def day_bucket(value: date) -> date:
    return value


def week_bucket(value: date) -> date:
    return value - timedelta(days=value.weekday())


def month_bucket(value: date) -> date:
    return value.replace(day=1)


def volume_points(
    tickets: list[AnalyticsTicket], start: datetime, end: datetime, bucket: str
) -> list[VolumePoint]:
    bucket_fn = {"day": day_bucket, "week": week_bucket, "month": month_bucket}[bucket]
    counts: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for record in tickets:
        ticket = record.ticket
        created = aware(ticket.created_at)
        if start <= created <= end:
            counts[bucket_fn(created.date())][0] += 1
        if ticket.resolved_at is not None:
            resolved = aware(ticket.resolved_at)
            if start <= resolved <= end:
                counts[bucket_fn(resolved.date())][1] += 1
    cursor = bucket_fn(start.date())
    last = bucket_fn(end.date())
    result: list[VolumePoint] = []
    while cursor <= last:
        created_count, resolved_count = counts[cursor]
        result.append(
            VolumePoint(period_start=cursor, created=created_count, resolved=resolved_count)
        )
        if bucket == "day":
            cursor += timedelta(days=1)
        elif bucket == "week":
            cursor += timedelta(days=7)
        else:
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return result


def breakdown(counter: Counter[str], limit: int = 8) -> list[BreakdownItem]:
    return [BreakdownItem(label=label, count=count) for label, count in counter.most_common(limit)]


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AnalyticsRepository(session)

    async def dashboard(
        self, actor_id: UUID, window_days: int, now: datetime | None = None
    ) -> DashboardResponse:
        end = aware(now or datetime.now(UTC))
        start = datetime.combine(end.date() - timedelta(days=window_days - 1), time.min, tzinfo=UTC)
        ticket_access = await TicketService(self.session).access(actor_id, "analytics:view")
        asset_access = await AssetService(self.session).access(actor_id, "analytics:view")
        tickets = await self.repository.tickets(ticket_access, start)
        devices = await self.repository.devices(asset_access)
        alerts = await self.repository.alerts(asset_access)
        feedback = await self.repository.feedback_actions(ticket_access, start)

        active = [record for record in tickets if record.ticket.status in ACTIVE_TICKET_STATES]
        resolved = [
            record
            for record in tickets
            if record.ticket.resolved_at is not None
            and start <= aware(record.ticket.resolved_at) <= end
        ]
        responded = [
            record
            for record in tickets
            if record.ticket.first_response_at is not None
            and start <= aware(record.ticket.first_response_at) <= end
        ]
        sla_completed = [
            record.sla
            for record in tickets
            if record.sla is not None
            and record.sla.resolution_completed_at is not None
            and start <= aware(record.sla.resolution_completed_at) <= end
        ]
        sla_compliant = sum(
            value.resolution_breached_at is None
            and value.resolution_elapsed_seconds <= value.resolution_target_seconds
            for value in sla_completed
        )

        created_in_window = [
            record for record in tickets if start <= aware(record.ticket.created_at) <= end
        ]
        category_counts = Counter(
            record.category_name or "Uncategorised" for record in created_in_window
        )
        department_counts = Counter(
            record.department_name or "No department" for record in created_in_window
        )
        priority_counts = Counter(record.ticket.priority for record in created_in_window)

        workload: dict[UUID, WorkloadCounter] = {}
        for record in active + resolved:
            technician_id = record.ticket.assigned_technician_id
            if technician_id is None or record.technician_name is None:
                continue
            item = workload.setdefault(technician_id, WorkloadCounter(record.technician_name))
            if record in active:
                item.open += 1
            if record in resolved:
                item.resolved += 1

        recurrence = Counter(
            (record.category_name or "Uncategorised", record.subcategory_name)
            for record in created_in_window
        )
        asset_incidents: Counter[tuple[UUID, str]] = Counter()
        for record in created_in_window:
            if (
                record.ticket.record_type == "INCIDENT"
                and record.ticket.asset_id is not None
                and record.asset_tag is not None
            ):
                asset_incidents[(record.ticket.asset_id, record.asset_tag)] += 1
        action_counts = Counter(feedback)
        reviewed = sum(action_counts[action] for action in ("ACCEPTED", "EDITED", "REJECTED"))

        urgent = sorted(
            active,
            key=lambda record: (
                PRIORITY_ORDER.get(record.ticket.priority, 9),
                0 if record.sla and record.sla.state == "BREACHED" else 1,
                -aware(record.ticket.updated_at).timestamp(),
            ),
        )[:6]
        issue_devices = sorted(
            [value for value in devices if value.agent.status in {"OFFLINE", "DEGRADED"}],
            key=lambda value: (0 if value.agent.status == "OFFLINE" else 1, value.asset.asset_tag),
        )[:6]
        all_critical_alerts = [value for value in alerts if value.alert.severity == "CRITICAL"]
        critical_alerts = sorted(
            all_critical_alerts,
            key=lambda value: aware(value.alert.triggered_at),
            reverse=True,
        )[:6]

        organization = (
            "ticket:view_all" in ticket_access.permissions
            and "asset:view_all" in asset_access.permissions
        )
        return DashboardResponse(
            generated_at=end,
            scope=AnalyticsScope(
                audience="ORGANIZATION" if organization else "TEAM",
                label=(
                    "Organization-wide operations" if organization else "My teams and assignments"
                ),
                window_days=window_days,
                window_start=start,
                window_end=end,
            ),
            summary=OperationalSummary(
                open_tickets=len(active),
                assigned_to_me=sum(
                    record.ticket.assigned_technician_id == actor_id for record in active
                ),
                unassigned_tickets=sum(
                    record.ticket.assigned_technician_id is None for record in active
                ),
                active_incidents=sum(record.ticket.record_type == "INCIDENT" for record in active),
                critical_incidents=sum(
                    record.ticket.record_type == "INCIDENT" and record.ticket.priority == "CRITICAL"
                    for record in active
                ),
                sla_at_risk=sum(
                    record.sla is not None and record.sla.state == "AT_RISK" for record in active
                ),
                sla_breached=sum(
                    record.sla is not None and record.sla.state == "BREACHED" for record in active
                ),
                online_devices=sum(value.agent.status == "ONLINE" for value in devices),
                offline_devices=sum(value.agent.status == "OFFLINE" for value in devices),
                unhealthy_devices=sum(
                    value.agent.status in {"OFFLINE", "DEGRADED"} for value in devices
                ),
                critical_alerts=len(all_critical_alerts),
            ),
            performance=PerformanceMetrics(
                mttr=duration_minutes(
                    [
                        (
                            aware(record.ticket.resolved_at) - aware(record.ticket.created_at)
                        ).total_seconds()
                        for record in resolved
                        if record.ticket.resolved_at is not None
                        and aware(record.ticket.resolved_at) >= aware(record.ticket.created_at)
                    ]
                ),
                mtta=duration_minutes(
                    [
                        (
                            aware(record.ticket.first_response_at) - aware(record.ticket.created_at)
                        ).total_seconds()
                        for record in responded
                        if record.ticket.first_response_at is not None
                        and aware(record.ticket.first_response_at)
                        >= aware(record.ticket.created_at)
                    ]
                ),
                sla_compliance=PercentageMetric(
                    percent=percent(sla_compliant, len(sla_completed)),
                    sample_size=len(sla_completed),
                ),
                first_contact_resolution_proxy=PercentageMetric(
                    percent=percent(
                        sum(record.ticket.reopened_at is None for record in resolved), len(resolved)
                    ),
                    sample_size=len(resolved),
                ),
                reopen_rate=PercentageMetric(
                    percent=percent(
                        sum(record.ticket.reopened_at is not None for record in resolved),
                        len(resolved),
                    ),
                    sample_size=len(resolved),
                ),
            ),
            ticket_volume=TicketVolume(
                daily=volume_points(tickets, start, end, "day"),
                weekly=volume_points(tickets, start, end, "week"),
                monthly=volume_points(tickets, start, end, "month"),
            ),
            by_category=breakdown(category_counts),
            by_department=breakdown(department_counts),
            by_priority=breakdown(priority_counts, 4),
            technician_workload=[
                TechnicianWorkload(
                    technician_id=technician_id,
                    technician_name=values.name,
                    assigned_open=values.open,
                    resolved_in_window=values.resolved,
                )
                for technician_id, values in sorted(
                    workload.items(),
                    key=lambda item: (-item[1].open, -item[1].resolved, str(item[0])),
                )
            ],
            recurring_issues=[
                RecurringIssue(category=key[0], subcategory=key[1], ticket_count=count)
                for key, count in recurrence.most_common(6)
                if count >= 2
            ],
            asset_incident_frequency=[
                AssetIncidentFrequency(asset_id=key[0], asset_tag=key[1], incident_count=count)
                for key, count in asset_incidents.most_common(6)
            ],
            ai_assistance=AiAssistanceMetrics(
                reviewed_recommendations=reviewed,
                accepted=action_counts["ACCEPTED"],
                edited=action_counts["EDITED"],
                rejected=action_counts["REJECTED"],
                regenerated=action_counts["REGENERATED"],
                acceptance_rate=percent(action_counts["ACCEPTED"], reviewed),
                edit_rate=percent(action_counts["EDITED"], reviewed),
                rejection_rate=percent(action_counts["REJECTED"], reviewed),
                label="Operational review rates; not a scientific AI accuracy measure.",
            ),
            attention=AttentionQueue(
                urgent_tickets=[
                    AttentionTicket(
                        id=record.ticket.id,
                        reference=record.ticket.reference,
                        title=record.ticket.title,
                        priority=record.ticket.priority,
                        status=record.ticket.status,
                        sla_state=record.sla.state if record.sla else None,
                        updated_at=record.ticket.updated_at,
                    )
                    for record in urgent
                ],
                device_health_issues=[
                    AttentionDevice(
                        agent_id=value.agent.id,
                        asset_id=value.asset.id,
                        asset_tag=value.asset.asset_tag,
                        hostname=value.asset.hostname,
                        status=value.agent.status,
                        health_status=value.asset.health_status,
                    )
                    for value in issue_devices
                ],
                critical_alerts=[
                    AttentionAlert(
                        id=value.alert.id,
                        asset_id=value.asset.id,
                        asset_tag=value.asset.asset_tag,
                        severity=value.alert.severity,
                        metric=value.alert.metric,
                        state=value.alert.state,
                        triggered_at=value.alert.triggered_at,
                    )
                    for value in critical_alerts
                ],
            ),
        )
