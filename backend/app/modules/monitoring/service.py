from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.assets.models import Asset, AssetEvent, AssetHealthStatus, AssetStatus
from app.modules.assets.repository import AssetAccess
from app.modules.assets.service import AssetService
from app.modules.monitoring.models import (
    AgentStatus,
    CredentialStatus,
    DeviceAgent,
    DeviceHeartbeat,
    DeviceMetric,
)
from app.modules.monitoring.repository import AgentRecord, MonitoringRepository
from app.modules.monitoring.schemas import HeartbeatCreate, MetricCreate
from app.modules.monitoring.security import new_secret, secret_hash


def utc_now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class MonitoringService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = MonitoringRepository(session)

    async def _commit(self, detail: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, detail) from None

    async def _asset_access(self, actor_id: UUID, required: str) -> AssetAccess:
        service = AssetService(self.session)
        return await service.access(actor_id, required)

    async def list_agents(
        self, actor_id: UUID, status: str | None, offset: int, limit: int
    ) -> tuple[list[AgentRecord], int]:
        access = await self._asset_access(actor_id, "monitoring:view")
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        return await self.repository.agents(access, status, offset, limit)

    async def visible_agent(
        self, actor_id: UUID, agent_id: UUID, required: str = "monitoring:view"
    ) -> AgentRecord:
        access = await self._asset_access(actor_id, required)
        record = await self.repository.visible_agent(agent_id, access)
        if record is None:
            raise HTTPException(404, "Device agent not found")
        return record

    async def create_enrollment(
        self,
        actor_id: UUID,
        asset_id: UUID,
        expires_in_minutes: int,
        reason: str,
        request_id: str,
    ) -> tuple[DeviceAgent, str]:
        asset_record, _ = await AssetService(self.session)._visible(
            actor_id, asset_id, required="monitoring:manage", lock=True
        )
        if asset_record.asset.status in {AssetStatus.RETIRED, AssetStatus.DISPOSED}:
            raise HTTPException(409, "Terminal assets cannot enroll an agent")
        agent = await self.repository.agent_for_asset(asset_id, lock=True)
        if agent is None:
            agent = DeviceAgent(id=uuid4(), asset_id=asset_id)
            self.session.add(agent)
        token = new_secret()
        now = utc_now()
        agent.enrollment_token_hash = secret_hash(token)
        agent.enrollment_expires_at = now + timedelta(minutes=expires_in_minutes)
        agent.credential_hash = None
        agent.credential_prefix = None
        agent.credential_status = CredentialStatus.PENDING
        agent.status = AgentStatus.UNREGISTERED
        agent.missed_heartbeat_count = 0
        self.session.add(
            AssetEvent(
                asset_id=asset_id,
                actor_id=actor_id,
                action="agent.enrollment_created",
                before_state=None,
                after_state={
                    "agent_id": str(agent.id),
                    "expires_at": agent.enrollment_expires_at.isoformat(),
                },
                reason=reason,
                request_id=request_id[:128],
                created_at=now,
            )
        )
        await self._commit("Agent enrollment conflicted with another request")
        return agent, token

    async def enroll(self, enrollment_token: str, agent_version: str) -> tuple[DeviceAgent, str]:
        agent = await self.repository.agent_by_enrollment_hash(secret_hash(enrollment_token))
        now = utc_now()
        if (
            agent is None
            or agent.enrollment_expires_at is None
            or aware(agent.enrollment_expires_at) < now
            or agent.credential_status != CredentialStatus.PENDING
        ):
            raise HTTPException(401, "Enrollment token is invalid or expired")
        credential = new_secret()
        agent.credential_hash = secret_hash(credential)
        agent.credential_prefix = credential[:8]
        agent.credential_status = CredentialStatus.ACTIVE
        agent.status = AgentStatus.OFFLINE
        agent.enrollment_token_hash = None
        agent.enrollment_expires_at = None
        agent.enrolled_at = now
        agent.agent_version = agent_version
        await self._commit("Agent enrollment could not be completed")
        return agent, credential

    @staticmethod
    def _valid_observation(value: datetime, now: datetime) -> bool:
        observed = aware(value)
        return now - timedelta(hours=24) <= observed <= now + timedelta(minutes=5)

    async def heartbeat(self, agent: DeviceAgent, payload: HeartbeatCreate) -> DeviceAgent:
        now = utc_now()
        if not self._valid_observation(payload.observed_at, now):
            raise HTTPException(422, "Heartbeat timestamp is outside the accepted window")
        if aware(payload.boot_time) > aware(payload.observed_at):
            raise HTTPException(422, "Boot time cannot follow observation time")
        agent = await self.repository.agent(agent.id, lock=True) or agent
        resulting_status = (
            AgentStatus.DEGRADED
            if not payload.available or payload.collection_errors
            else AgentStatus.ONLINE
        )
        agent.status = resulting_status
        agent.last_seen = now
        agent.last_heartbeat_at = now
        agent.missed_heartbeat_count = 0
        self.session.add(
            DeviceHeartbeat(
                agent_id=agent.id,
                received_at=now,
                resulting_status=resulting_status,
                **payload.model_dump(),
            )
        )
        asset = await self.session.get(Asset, agent.asset_id)
        assert asset is not None
        asset.last_seen = now
        asset.hostname = payload.hostname
        asset.operating_system = payload.operating_system
        asset.ip_address = payload.ip_addresses[0] if payload.ip_addresses else None
        asset.health_status = (
            AssetHealthStatus.WARNING
            if resulting_status == AgentStatus.DEGRADED
            else AssetHealthStatus.HEALTHY
        )
        from app.modules.alerts.service import AlertService

        await AlertService(self.session).evaluate_device(agent, now)
        await self._commit("Heartbeat could not be recorded")
        return agent

    async def metric(self, agent: DeviceAgent, payload: MetricCreate) -> tuple[bool, DeviceAgent]:
        now = utc_now()
        if not self._valid_observation(payload.sampled_at, now):
            raise HTTPException(422, "Metric timestamp is outside the accepted window")
        agent = await self.repository.agent(agent.id, lock=True) or agent
        if (
            agent.last_metric_at
            and (now - aware(agent.last_metric_at)).total_seconds()
            < self.settings.monitoring_metric_min_interval_seconds
        ):
            return False, agent
        metric = DeviceMetric(agent_id=agent.id, received_at=now, **payload.model_dump())
        self.session.add(metric)
        agent.last_metric_at = now
        agent.last_seen = now
        from app.modules.alerts.service import AlertService

        await AlertService(self.session).evaluate_metric(agent, metric)
        await self._commit("Metric sample could not be recorded")
        return True, agent

    async def metrics(
        self, actor_id: UUID, agent_id: UUID, offset: int, limit: int
    ) -> tuple[list[DeviceMetric], int]:
        await self.visible_agent(actor_id, agent_id)
        return await self.repository.metrics(agent_id, offset, limit)

    async def disable(
        self, actor_id: UUID, agent_id: UUID, reason: str, request_id: str
    ) -> DeviceAgent:
        record = await self.visible_agent(actor_id, agent_id, "monitoring:manage")
        agent = await self.repository.agent(record.agent.id, lock=True)
        assert agent is not None
        agent.status = AgentStatus.DISABLED
        agent.credential_status = CredentialStatus.REVOKED
        agent.credential_hash = None
        agent.enrollment_token_hash = None
        self.session.add(
            AssetEvent(
                asset_id=agent.asset_id,
                actor_id=actor_id,
                action="agent.disabled",
                before_state=None,
                after_state={"agent_id": str(agent.id), "status": AgentStatus.DISABLED},
                reason=reason,
                request_id=request_id[:128],
                created_at=utc_now(),
            )
        )
        await self._commit("Agent could not be disabled")
        return agent

    async def reconcile(
        self, now: datetime | None = None, limit: int = 500
    ) -> tuple[int, int, int]:
        current = aware(now or utc_now())
        cutoff = current - timedelta(seconds=self.settings.monitoring_heartbeat_timeout_seconds)
        agents = await self.repository.stale_agents(cutoff, limit)
        for agent in agents:
            assert agent.last_heartbeat_at is not None
            elapsed = (current - aware(agent.last_heartbeat_at)).total_seconds()
            agent.missed_heartbeat_count = max(
                1, int(elapsed // self.settings.monitoring_expected_heartbeat_seconds)
            )
            agent.status = AgentStatus.OFFLINE
            asset = await self.session.get(Asset, agent.asset_id)
            if asset is not None:
                asset.health_status = AssetHealthStatus.OFFLINE
            from app.modules.alerts.service import AlertService

            await AlertService(self.session).evaluate_device(agent, current)
        before = current - timedelta(days=self.settings.monitoring_retention_days)
        pruned_metrics, pruned_heartbeats = await self.repository.prune(before)
        await self.session.commit()
        return len(agents), pruned_metrics, pruned_heartbeats
