from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.repository import AccessRepository
from app.modules.alerts.models import (
    Alert,
    AlertEvent,
    AlertMetric,
    AlertOperator,
    AlertPolicy,
    AlertSeverity,
    AlertState,
    AutomationExecution,
    AutomationRule,
    ExecutionStatus,
    Notification,
    NotificationPreference,
)
from app.modules.alerts.repository import AlertRecord, AlertRepository
from app.modules.alerts.schemas import PolicyCreate, PolicyUpdate, RuleCreate, RuleUpdate
from app.modules.assets.models import Asset
from app.modules.assets.service import AssetService
from app.modules.monitoring.models import DeviceAgent, DeviceMetric
from app.modules.sla.service import SlaService
from app.modules.tickets.models import (
    ImpactLevel,
    Ticket,
    TicketAssignment,
    TicketEvent,
    TicketSource,
    TicketStatus,
    TicketType,
)

SEVERITY_RANK = {
    AlertSeverity.INFO: 0,
    AlertSeverity.WARNING: 1,
    AlertSeverity.HIGH: 2,
    AlertSeverity.CRITICAL: 3,
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def policy_state(value: AlertPolicy) -> dict[str, object]:
    return {
        "name": value.name,
        "metric": value.metric,
        "operator": value.operator,
        "threshold": value.threshold,
        "severity": value.severity,
        "enabled": value.enabled,
    }


def rule_state(value: AutomationRule) -> dict[str, object]:
    return {
        "name": value.name,
        "enabled": value.enabled,
        "source": value.source,
        "minimum_severity": value.minimum_severity,
        "create_incident": value.create_incident,
        "notify_team": value.notify_team,
        "assignment_team_id": str(value.assignment_team_id) if value.assignment_team_id else None,
    }


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AlertRepository(session)

    async def _require(self, actor_id: UUID, permission: str) -> None:
        _, grants = await AccessRepository(self.session).grants(actor_id)
        if permission not in grants:
            raise HTTPException(403, "Permission denied")

    async def _commit(self, detail: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, detail) from None

    def _event(
        self,
        entity_type: str,
        entity_id: UUID,
        action: str,
        reason: str,
        request_id: str,
        *,
        actor_id: UUID | None = None,
        alert_id: UUID | None = None,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
    ) -> None:
        self.session.add(
            AlertEvent(
                entity_type=entity_type,
                entity_id=entity_id,
                alert_id=alert_id,
                actor_id=actor_id,
                action=action,
                before_state=before,
                after_state=after,
                reason=reason,
                request_id=request_id[:128],
                created_at=utc_now(),
            )
        )

    @staticmethod
    def _valid_policy(metric: str, threshold: float) -> None:
        if (
            metric
            in {
                AlertMetric.CPU_PERCENT,
                AlertMetric.MEMORY_PERCENT,
                AlertMetric.DISK_PERCENT,
            }
            and threshold > 100
        ):
            raise HTTPException(422, "Percentage thresholds cannot exceed 100")
        if metric == AlertMetric.DEVICE_OFFLINE and threshold != 1:
            raise HTTPException(422, "Device offline threshold must be 1")

    async def policies(self, actor_id: UUID) -> list[AlertPolicy]:
        await self._require(actor_id, "alert:view")
        return await self.repository.policies()

    async def create_policy(
        self, actor_id: UUID, payload: PolicyCreate, request_id: str
    ) -> AlertPolicy:
        await self._require(actor_id, "alert:manage")
        policy = AlertPolicy(id=uuid4(), **payload.model_dump(exclude={"reason"}))
        self.session.add(policy)
        self._event(
            "POLICY",
            policy.id,
            "alert_policy.created",
            payload.reason,
            request_id,
            actor_id=actor_id,
            after=policy_state(policy),
        )
        await self._commit("Alert policy name already exists")
        return policy

    async def update_policy(
        self, actor_id: UUID, policy_id: UUID, payload: PolicyUpdate, request_id: str
    ) -> AlertPolicy:
        await self._require(actor_id, "alert:manage")
        policy = await self.repository.policy(policy_id, lock=True)
        if policy is None:
            raise HTTPException(404, "Alert policy not found")
        before = policy_state(policy)
        values = payload.model_dump(exclude={"reason"}, exclude_unset=True)
        threshold = float(values.get("threshold", policy.threshold))
        self._valid_policy(policy.metric, threshold)
        for key, value in values.items():
            setattr(policy, key, value)
        self._event(
            "POLICY",
            policy.id,
            "alert_policy.updated",
            payload.reason,
            request_id,
            actor_id=actor_id,
            before=before,
            after=policy_state(policy),
        )
        if not policy.enabled:
            now = utc_now()
            for alert in await self.repository.active_alerts_for_policy(policy.id):
                self._resolve(alert, now, "Policy disabled", "policy-disabled")
        await self._commit("Alert policy update conflicts with existing configuration")
        await self.session.refresh(policy)
        return policy

    async def rules(self, actor_id: UUID) -> list[AutomationRule]:
        await self._require(actor_id, "alert:manage")
        return await self.repository.rules()

    async def _validate_rule(
        self, rule: RuleCreate | RuleUpdate, current: AutomationRule | None
    ) -> None:
        team_id = rule.assignment_team_id
        create_incident = getattr(rule, "create_incident", None)
        notify_team = getattr(rule, "notify_team", None)
        if current:
            team_id = (
                team_id
                if "assignment_team_id" in rule.model_fields_set
                else current.assignment_team_id
            )
            create_incident = (
                create_incident
                if "create_incident" in rule.model_fields_set
                else current.create_incident
            )
            notify_team = (
                notify_team if "notify_team" in rule.model_fields_set else current.notify_team
            )
        if not create_incident and not notify_team:
            raise HTTPException(422, "At least one automation action is required")
        if team_id is None or await self.repository.team(team_id) is None:
            raise HTTPException(422, "Automation requires an active assignment team")

    async def create_rule(
        self, actor_id: UUID, payload: RuleCreate, request_id: str
    ) -> AutomationRule:
        await self._require(actor_id, "alert:manage")
        await self._validate_rule(payload, None)
        rule = AutomationRule(
            id=uuid4(), created_by_id=actor_id, **payload.model_dump(exclude={"reason"})
        )
        self.session.add(rule)
        self._event(
            "RULE",
            rule.id,
            "automation_rule.created",
            payload.reason,
            request_id,
            actor_id=actor_id,
            after=rule_state(rule),
        )
        await self._commit("Automation rule name already exists")
        return rule

    async def update_rule(
        self, actor_id: UUID, rule_id: UUID, payload: RuleUpdate, request_id: str
    ) -> AutomationRule:
        await self._require(actor_id, "alert:manage")
        rule = await self.repository.rule(rule_id, lock=True)
        if rule is None:
            raise HTTPException(404, "Automation rule not found")
        await self._validate_rule(payload, rule)
        before = rule_state(rule)
        for key, value in payload.model_dump(exclude={"reason"}, exclude_unset=True).items():
            setattr(rule, key, value)
        self._event(
            "RULE",
            rule.id,
            "automation_rule.updated",
            payload.reason,
            request_id,
            actor_id=actor_id,
            before=before,
            after=rule_state(rule),
        )
        await self._commit("Automation rule update conflicts with existing configuration")
        await self.session.refresh(rule)
        return rule

    async def list_alerts(
        self,
        actor_id: UUID,
        state: str | None,
        severity: str | None,
        asset_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AlertRecord], int]:
        access = await AssetService(self.session).access(actor_id, "alert:view")
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        return await self.repository.alerts(access, state, severity, asset_id, offset, limit)

    async def visible_alert(
        self,
        actor_id: UUID,
        alert_id: UUID,
        permission: str = "alert:view",
        *,
        lock: bool = False,
    ) -> AlertRecord:
        access = await AssetService(self.session).access(actor_id, permission)
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        record = await self.repository.visible_alert(alert_id, access, lock=lock)
        if record is None:
            raise HTTPException(404, "Alert not found")
        return record

    async def transition(
        self,
        actor_id: UUID,
        alert_id: UUID,
        target: AlertState,
        reason: str,
        request_id: str,
    ) -> AlertRecord:
        permission = {
            AlertState.ACKNOWLEDGED: "alert:acknowledge",
            AlertState.RESOLVED: "alert:resolve",
            AlertState.SUPPRESSED: "alert:manage",
        }.get(target)
        if permission is None:
            raise HTTPException(422, "Unsupported alert transition")
        record = await self.visible_alert(actor_id, alert_id, permission, lock=True)
        alert = record.alert
        allowed = {
            AlertState.TRIGGERED: {
                AlertState.ACKNOWLEDGED,
                AlertState.RESOLVED,
                AlertState.SUPPRESSED,
            },
            AlertState.ACKNOWLEDGED: {AlertState.RESOLVED, AlertState.SUPPRESSED},
            AlertState.SUPPRESSED: {AlertState.RESOLVED},
            AlertState.RESOLVED: set(),
        }
        if target not in allowed[AlertState(alert.state)]:
            raise HTTPException(409, f"Cannot transition {alert.state} alert to {target}")
        now = utc_now()
        before: dict[str, object] = {"state": alert.state}
        alert.state = target
        if target == AlertState.ACKNOWLEDGED:
            alert.acknowledged_at, alert.acknowledged_by_id = now, actor_id
        elif target == AlertState.SUPPRESSED:
            alert.suppressed_at, alert.suppressed_by_id = now, actor_id
        else:
            alert.resolved_at, alert.resolved_by_id = now, actor_id
        self._event(
            "ALERT",
            alert.id,
            f"alert.{target.lower()}",
            reason,
            request_id,
            actor_id=actor_id,
            alert_id=alert.id,
            before=before,
            after={"state": target},
        )
        await self._commit("Alert transition conflicted with another request")
        return record

    @staticmethod
    def _matches(policy: AlertPolicy, observed: float) -> bool:
        if policy.operator == AlertOperator.GREATER_THAN:
            return observed > policy.threshold
        return observed >= policy.threshold

    def _resolve(self, alert: Alert, now: datetime, reason: str, request_id: str) -> None:
        before: dict[str, object] = {
            "state": alert.state,
            "observed_value": alert.observed_value,
        }
        alert.state = AlertState.RESOLVED
        alert.resolved_at = now
        self._event(
            "ALERT",
            alert.id,
            "alert.auto_resolved",
            reason,
            request_id,
            alert_id=alert.id,
            before=before,
            after={"state": AlertState.RESOLVED},
        )

    async def _evaluate(
        self, agent: DeviceAgent, policy: AlertPolicy, observed: float, observed_at: datetime
    ) -> None:
        existing = await self.repository.active_alert(policy.id, agent.id, lock=True)
        if not self._matches(policy, observed):
            if existing:
                existing.observed_value = observed
                existing.last_observed_at = observed_at
                self._resolve(existing, observed_at, "Condition cleared", "condition-cleared")
            return
        if existing:
            existing.observed_value = observed
            existing.last_observed_at = observed_at
            return
        alert = Alert(
            policy_id=policy.id,
            agent_id=agent.id,
            asset_id=agent.asset_id,
            source="DEVICE_AGENT",
            severity=policy.severity,
            metric=policy.metric,
            threshold=policy.threshold,
            observed_value=observed,
            state=AlertState.TRIGGERED,
            triggered_at=observed_at,
            last_observed_at=observed_at,
        )
        self.session.add(alert)
        await self.session.flush()
        self._event(
            "ALERT",
            alert.id,
            "alert.triggered",
            "Configured condition matched",
            f"alert:{alert.id}",
            alert_id=alert.id,
            after={
                "state": alert.state,
                "metric": alert.metric,
                "threshold": alert.threshold,
                "observed_value": alert.observed_value,
            },
        )
        await self._automate(alert)

    async def evaluate_metric(self, agent: DeviceAgent, metric: DeviceMetric) -> None:
        values = {
            AlertMetric.CPU_PERCENT: metric.cpu_percent,
            AlertMetric.MEMORY_PERCENT: metric.memory_percent,
            AlertMetric.DISK_PERCENT: metric.disk_percent,
        }
        for policy in await self.repository.policies(enabled_only=True):
            if policy.metric in values:
                await self._evaluate(
                    agent, policy, values[AlertMetric(policy.metric)], metric.sampled_at
                )

    async def evaluate_device(self, agent: DeviceAgent, observed_at: datetime) -> None:
        values = {
            AlertMetric.DEVICE_OFFLINE: 1.0 if agent.status == "OFFLINE" else 0.0,
            AlertMetric.HEARTBEAT_MISSED: float(agent.missed_heartbeat_count),
        }
        for policy in await self.repository.policies(enabled_only=True):
            if policy.metric in values:
                await self._evaluate(agent, policy, values[AlertMetric(policy.metric)], observed_at)

    async def _incident(self, alert: Alert, rule: AutomationRule, asset: Asset) -> Ticket:
        impact = ImpactLevel.HIGH if alert.severity in {"HIGH", "CRITICAL"} else ImpactLevel.MEDIUM
        urgency = ImpactLevel.HIGH if alert.severity == "CRITICAL" else ImpactLevel.MEDIUM
        priority = await SlaService(self.session).resolve_priority(impact, urgency)
        ticket_id = uuid4()
        ticket = Ticket(
            id=ticket_id,
            reference=f"INC-{utc_now():%Y%m%d}-{ticket_id.hex[:8].upper()}",
            title=f"{alert.metric.replace('_', ' ').title()} alert on {asset.asset_tag}",
            description=(
                f"Automated incident from alert {alert.id}. Observed {alert.observed_value:g}; "
                f"configured threshold {alert.threshold:g}."
            ),
            requester_id=rule.created_by_id,
            department_id=asset.department_id,
            location_id=asset.location_id,
            asset_id=asset.id,
            category_id=None,
            subcategory_id=None,
            impact=impact,
            urgency=urgency,
            priority=priority,
            status=TicketStatus.NEW,
            assignment_team_id=rule.assignment_team_id,
            assigned_technician_id=None,
            record_type=TicketType.INCIDENT,
            source=TicketSource.AUTOMATION,
        )
        self.session.add(ticket)
        await self.session.flush()
        if rule.assignment_team_id:
            self.session.add(
                TicketAssignment(
                    ticket_id=ticket.id,
                    team_id=rule.assignment_team_id,
                    assigned_by_id=rule.created_by_id,
                    reason=f"Automation rule {rule.name}",
                    started_at=utc_now(),
                )
            )
        self.session.add(
            TicketEvent(
                ticket_id=ticket.id,
                actor_id=rule.created_by_id,
                event_type="incident.automated_from_alert",
                before_state=None,
                after_state={"alert_id": str(alert.id), "rule_id": str(rule.id)},
                reason=f"Automation rule {rule.name}",
                request_id=f"automation:{alert.id}"[:128],
                created_at=utc_now(),
            )
        )
        await SlaService(self.session).initialize(ticket)
        alert.incident_ticket_id = ticket.id
        return ticket

    async def _notify(self, alert: Alert, rule: AutomationRule, ticket: Ticket | None) -> int:
        assert rule.assignment_team_id is not None
        created = 0
        for user_id in await self.repository.active_team_user_ids(rule.assignment_team_id):
            preference = await self.repository.preference(user_id)
            if preference and not preference.in_app_enabled:
                continue
            minimum = preference.minimum_alert_severity if preference else AlertSeverity.WARNING
            if SEVERITY_RANK[AlertSeverity(alert.severity)] < SEVERITY_RANK[AlertSeverity(minimum)]:
                continue
            self.session.add(
                Notification(
                    user_id=user_id,
                    alert_id=alert.id,
                    ticket_id=ticket.id if ticket else None,
                    event_type="critical_alert" if alert.severity == "CRITICAL" else "device_alert",
                    title=f"{alert.severity.title()} device alert",
                    body=f"{alert.metric.replace('_', ' ').title()} condition was triggered.",
                    dedupe_key=f"alert:{alert.id}:user:{user_id}",
                    created_at=utc_now(),
                )
            )
            created += 1
        return created

    async def _automate(self, alert: Alert) -> None:
        asset = await self.session.get(Asset, alert.asset_id)
        assert asset is not None
        for rule in await self.repository.rules(enabled_only=True):
            if (
                rule.source != alert.source
                or SEVERITY_RANK[AlertSeverity(alert.severity)]
                < SEVERITY_RANK[AlertSeverity(rule.minimum_severity)]
            ):
                continue
            if await self.repository.execution(rule.id, alert.id):
                continue
            ticket: Ticket | None = None
            try:
                async with self.session.begin_nested():
                    if rule.create_incident:
                        ticket = await self._incident(alert, rule, asset)
                    count = await self._notify(alert, rule, ticket) if rule.notify_team else 0
                    await self.session.flush()
                status, error = ExecutionStatus.SUCCEEDED, None
            except (HTTPException, IntegrityError):
                ticket = None
                status, error, count = ExecutionStatus.FAILED, "ACTION_FAILED", 0
            self.session.add(
                AutomationExecution(
                    rule_id=rule.id,
                    alert_id=alert.id,
                    incident_ticket_id=ticket.id if ticket else None,
                    status=status,
                    notification_count=count,
                    error_code=error,
                    executed_at=utc_now(),
                )
            )

    async def executions(self, actor_id: UUID, limit: int) -> list[AutomationExecution]:
        await self._require(actor_id, "alert:manage")
        return await self.repository.executions(limit)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AlertRepository(session)

    async def preference(self, user_id: UUID) -> NotificationPreference:
        value = await self.repository.preference(user_id)
        if value is None:
            value = NotificationPreference(
                user_id=user_id,
                in_app_enabled=True,
                minimum_alert_severity=AlertSeverity.WARNING,
            )
        return value

    async def update_preference(
        self, user_id: UUID, in_app_enabled: bool, minimum_alert_severity: str
    ) -> NotificationPreference:
        value = await self.repository.preference(user_id)
        if value is None:
            value = NotificationPreference(user_id=user_id)
            self.session.add(value)
        value.in_app_enabled = in_app_enabled
        value.minimum_alert_severity = minimum_alert_severity
        await self.session.commit()
        return value

    async def list(
        self, user_id: UUID, unread_only: bool, offset: int, limit: int
    ) -> tuple[list[Notification], int, int]:
        return await self.repository.notifications(user_id, unread_only, offset, limit)

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> Notification:
        value = await self.repository.notification(notification_id, user_id)
        if value is None:
            raise HTTPException(404, "Notification not found")
        if value.read_at is None:
            value.read_at = utc_now()
            await self.session.commit()
        return value
