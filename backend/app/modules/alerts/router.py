from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.alerts.models import AlertPolicy, AlertSeverity, AlertState, AutomationRule
from app.modules.alerts.repository import AlertRecord
from app.modules.alerts.schemas import (
    AlertPage,
    AlertResponse,
    AlertTransition,
    ExecutionPage,
    ExecutionResponse,
    NotificationPage,
    NotificationResponse,
    PolicyCreate,
    PolicyPage,
    PolicyResponse,
    PolicyUpdate,
    PreferenceResponse,
    PreferenceUpdate,
    RuleCreate,
    RulePage,
    RuleResponse,
    RuleUpdate,
)
from app.modules.alerts.service import AlertService, NotificationService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User

router = APIRouter()
alerts = APIRouter(prefix="/alerts", tags=["alerts"])
automation = APIRouter(prefix="/automation", tags=["alert automation"])
notifications = APIRouter(prefix="/notifications", tags=["notifications"])


def policy_response(value: AlertPolicy) -> PolicyResponse:
    return PolicyResponse.model_validate(value, from_attributes=True)


def rule_response(value: AutomationRule) -> RuleResponse:
    return RuleResponse.model_validate(value, from_attributes=True)


def alert_response(value: AlertRecord) -> AlertResponse:
    alert = value.alert
    return AlertResponse(
        id=alert.id,
        policy_id=alert.policy_id,
        agent_id=alert.agent_id,
        asset_id=alert.asset_id,
        asset_tag=value.asset.asset_tag,
        incident_ticket_id=alert.incident_ticket_id,
        incident_reference=value.incident.reference if value.incident else None,
        source=alert.source,
        severity=alert.severity,
        metric=alert.metric,
        threshold=alert.threshold,
        observed_value=alert.observed_value,
        state=alert.state,
        triggered_at=alert.triggered_at,
        last_observed_at=alert.last_observed_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        suppressed_at=alert.suppressed_at,
    )


@alerts.get("/policies", response_model=PolicyPage)
async def list_policies(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyPage:
    values = await AlertService(session).policies(actor.id)
    return PolicyPage(items=[policy_response(value) for value in values], total=len(values))


@alerts.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyResponse:
    value = await AlertService(session).create_policy(actor.id, payload, request.state.request_id)
    return policy_response(value)


@alerts.patch("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    payload: PolicyUpdate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyResponse:
    value = await AlertService(session).update_policy(
        actor.id, policy_id, payload, request.state.request_id
    )
    return policy_response(value)


@alerts.get("", response_model=AlertPage)
async def list_alerts(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    alert_state: Annotated[AlertState | None, Query(alias="state")] = None,
    severity: AlertSeverity | None = None,
    asset_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AlertPage:
    values, total = await AlertService(session).list_alerts(
        actor.id, alert_state, severity, asset_id, offset, limit
    )
    return AlertPage(
        items=[alert_response(value) for value in values],
        total=total,
        offset=offset,
        limit=limit,
    )


@alerts.get("/{alert_id}", response_model=AlertResponse)
async def alert_detail(
    alert_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlertResponse:
    return alert_response(await AlertService(session).visible_alert(actor.id, alert_id))


async def perform_transition(
    alert_id: UUID,
    target: AlertState,
    payload: AlertTransition,
    request: Request,
    actor: User,
    session: AsyncSession,
) -> AlertResponse:
    return alert_response(
        await AlertService(session).transition(
            actor.id, alert_id, target, payload.reason, request.state.request_id
        )
    )


@alerts.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    payload: AlertTransition,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlertResponse:
    return await perform_transition(
        alert_id, AlertState.ACKNOWLEDGED, payload, request, actor, session
    )


@alerts.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: UUID,
    payload: AlertTransition,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlertResponse:
    return await perform_transition(alert_id, AlertState.RESOLVED, payload, request, actor, session)


@alerts.post("/{alert_id}/suppress", response_model=AlertResponse)
async def suppress_alert(
    alert_id: UUID,
    payload: AlertTransition,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlertResponse:
    return await perform_transition(
        alert_id, AlertState.SUPPRESSED, payload, request, actor, session
    )


@automation.get("/rules", response_model=RulePage)
async def list_rules(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RulePage:
    values = await AlertService(session).rules(actor.id)
    return RulePage(items=[rule_response(value) for value in values], total=len(values))


@automation.post("/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RuleResponse:
    value = await AlertService(session).create_rule(actor.id, payload, request.state.request_id)
    return rule_response(value)


@automation.patch("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    payload: RuleUpdate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RuleResponse:
    value = await AlertService(session).update_rule(
        actor.id, rule_id, payload, request.state.request_id
    )
    return rule_response(value)


@automation.get("/executions", response_model=ExecutionPage)
async def list_executions(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ExecutionPage:
    values = await AlertService(session).executions(actor.id, limit)
    return ExecutionPage(
        items=[ExecutionResponse.model_validate(value, from_attributes=True) for value in values],
        total=len(values),
    )


@notifications.get("", response_model=NotificationPage)
async def list_notifications(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    unread_only: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> NotificationPage:
    values, total, unread = await NotificationService(session).list(
        actor.id, unread_only, offset, limit
    )
    return NotificationPage(
        items=[
            NotificationResponse.model_validate(value, from_attributes=True) for value in values
        ],
        total=total,
        unread=unread,
        offset=offset,
        limit=limit,
    )


@notifications.get("/preferences/me", response_model=PreferenceResponse)
async def get_preferences(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PreferenceResponse:
    value = await NotificationService(session).preference(actor.id)
    return PreferenceResponse.model_validate(value, from_attributes=True)


@notifications.put("/preferences/me", response_model=PreferenceResponse)
async def update_preferences(
    payload: PreferenceUpdate,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PreferenceResponse:
    value = await NotificationService(session).update_preference(
        actor.id, payload.in_app_enabled, payload.minimum_alert_severity
    )
    return PreferenceResponse.model_validate(value, from_attributes=True)


@notifications.post("/{notification_id}/read", response_model=NotificationResponse)
async def read_notification(
    notification_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationResponse:
    value = await NotificationService(session).mark_read(actor.id, notification_id)
    return NotificationResponse.model_validate(value, from_attributes=True)


router.include_router(alerts)
router.include_router(automation)
router.include_router(notifications)
