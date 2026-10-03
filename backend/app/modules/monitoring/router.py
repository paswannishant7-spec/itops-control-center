from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.monitoring.dependencies import get_current_agent
from app.modules.monitoring.models import AgentStatus, DeviceAgent, DeviceMetric
from app.modules.monitoring.repository import AgentRecord
from app.modules.monitoring.schemas import (
    AgentCredentialResponse,
    AgentEnroll,
    AgentPage,
    AgentSummary,
    DisableAgent,
    EnrollmentCreate,
    EnrollmentResponse,
    HeartbeatCreate,
    IngestResponse,
    MetricCreate,
    MetricPage,
    MetricResponse,
)
from app.modules.monitoring.service import MonitoringService, utc_now

router = APIRouter(prefix="/monitoring", tags=["device monitoring"])


def agent_summary(value: AgentRecord) -> AgentSummary:
    agent = value.agent
    return AgentSummary(
        agent_id=agent.id,
        device_id=agent.asset_id,
        asset_tag=value.asset.asset_tag,
        hostname=value.asset.hostname,
        status=agent.status,
        credential_status=agent.credential_status,
        credential_prefix=agent.credential_prefix,
        last_seen=agent.last_seen,
        last_heartbeat=agent.last_heartbeat_at,
        missed_heartbeat_count=agent.missed_heartbeat_count,
        agent_version=agent.agent_version,
        enrolled_at=agent.enrolled_at,
    )


def metric_response(value: DeviceMetric) -> MetricResponse:
    return MetricResponse(
        id=value.id,
        sampled_at=value.sampled_at,
        received_at=value.received_at,
        cpu_percent=value.cpu_percent,
        memory_percent=value.memory_percent,
        memory_used_bytes=value.memory_used_bytes,
        memory_total_bytes=value.memory_total_bytes,
        disk_percent=value.disk_percent,
        disk_used_bytes=value.disk_used_bytes,
        disk_total_bytes=value.disk_total_bytes,
        network_bytes_sent=value.network_bytes_sent,
        network_bytes_received=value.network_bytes_received,
    )


@router.post("/enrollments", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def create_enrollment(
    payload: EnrollmentCreate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EnrollmentResponse:
    agent, token = await MonitoringService(session, settings).create_enrollment(
        actor.id,
        payload.asset_id,
        payload.expires_in_minutes,
        payload.reason,
        request.state.request_id,
    )
    assert agent.enrollment_expires_at is not None
    return EnrollmentResponse(
        agent_id=agent.id,
        device_id=agent.asset_id,
        enrollment_token=token,
        expires_at=agent.enrollment_expires_at,
    )


@router.post("/enroll", response_model=AgentCredentialResponse)
async def enroll_agent(
    payload: AgentEnroll,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentCredentialResponse:
    agent, credential = await MonitoringService(session, settings).enroll(
        payload.enrollment_token, payload.agent_version
    )
    return AgentCredentialResponse(
        agent_id=agent.id,
        device_id=agent.asset_id,
        credential=credential,
        credential_status=agent.credential_status,
    )


@router.get("/agents", response_model=AgentPage)
async def agents(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    agent_status: Annotated[AgentStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AgentPage:
    values, total = await MonitoringService(session, settings).list_agents(
        actor.id, agent_status, offset, limit
    )
    return AgentPage(
        items=[agent_summary(value) for value in values],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/agents/{agent_id}", response_model=AgentSummary)
async def agent_detail(
    agent_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentSummary:
    return agent_summary(
        await MonitoringService(session, settings).visible_agent(actor.id, agent_id)
    )


@router.get("/agents/{agent_id}/metrics", response_model=MetricPage)
async def agent_metrics(
    agent_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> MetricPage:
    values, total = await MonitoringService(session, settings).metrics(
        actor.id, agent_id, offset, limit
    )
    return MetricPage(
        items=[metric_response(value) for value in values],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/agents/{agent_id}/disable", response_model=AgentSummary)
async def disable_agent(
    agent_id: UUID,
    payload: DisableAgent,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentSummary:
    service = MonitoringService(session, settings)
    await service.disable(actor.id, agent_id, payload.reason, request.state.request_id)
    return agent_summary(await service.visible_agent(actor.id, agent_id, "monitoring:manage"))


@router.post("/agent/heartbeat", response_model=IngestResponse)
async def heartbeat(
    payload: HeartbeatCreate,
    agent: Annotated[DeviceAgent, Depends(get_current_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestResponse:
    value = await MonitoringService(session, settings).heartbeat(agent, payload)
    return IngestResponse(accepted=True, server_time=utc_now(), status=value.status)


@router.post("/agent/metrics", response_model=IngestResponse)
async def metrics(
    payload: MetricCreate,
    agent: Annotated[DeviceAgent, Depends(get_current_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestResponse:
    accepted, value = await MonitoringService(session, settings).metric(agent, payload)
    return IngestResponse(accepted=accepted, server_time=utc_now(), status=value.status)
