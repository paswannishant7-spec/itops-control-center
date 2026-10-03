from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset
from app.modules.assets.repository import AssetAccess, AssetRepository
from app.modules.monitoring.models import DeviceAgent, DeviceHeartbeat, DeviceMetric


@dataclass(frozen=True)
class AgentRecord:
    agent: DeviceAgent
    asset: Asset


class MonitoringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def agent(self, agent_id: UUID, *, lock: bool = False) -> DeviceAgent | None:
        statement = select(DeviceAgent).where(DeviceAgent.id == agent_id)
        if lock:
            statement = statement.with_for_update()
        return cast(DeviceAgent | None, await self.session.scalar(statement))

    async def agent_for_asset(self, asset_id: UUID, *, lock: bool = False) -> DeviceAgent | None:
        statement = select(DeviceAgent).where(DeviceAgent.asset_id == asset_id)
        if lock:
            statement = statement.with_for_update()
        return cast(DeviceAgent | None, await self.session.scalar(statement))

    async def agent_by_enrollment_hash(self, value: str) -> DeviceAgent | None:
        return cast(
            DeviceAgent | None,
            await self.session.scalar(
                select(DeviceAgent)
                .where(DeviceAgent.enrollment_token_hash == value)
                .with_for_update()
            ),
        )

    async def visible_agent(
        self, agent_id: UUID, access: AssetAccess, *, lock: bool = False
    ) -> AgentRecord | None:
        statement = (
            select(DeviceAgent, Asset)
            .join(Asset, Asset.id == DeviceAgent.asset_id)
            .where(
                DeviceAgent.id == agent_id,
                AssetRepository(self.session).access_predicate(access),
            )
        )
        if lock:
            statement = statement.with_for_update(of=DeviceAgent)
        row = (await self.session.execute(statement)).one_or_none()
        return AgentRecord(row[0], row[1]) if row else None

    async def agents(
        self,
        access: AssetAccess,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AgentRecord], int]:
        predicate = AssetRepository(self.session).access_predicate(access)
        criteria = [predicate]
        if status:
            criteria.append(DeviceAgent.status == status)
        total = int(
            cast(
                int | None,
                await self.session.scalar(
                    select(func.count())
                    .select_from(DeviceAgent)
                    .join(Asset, Asset.id == DeviceAgent.asset_id)
                    .where(*criteria)
                ),
            )
            or 0
        )
        rows = (
            await self.session.execute(
                select(DeviceAgent, Asset)
                .join(Asset, Asset.id == DeviceAgent.asset_id)
                .where(*criteria)
                .order_by(DeviceAgent.status, Asset.asset_tag, DeviceAgent.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [AgentRecord(row[0], row[1]) for row in rows], total

    async def metrics(
        self, agent_id: UUID, offset: int, limit: int
    ) -> tuple[list[DeviceMetric], int]:
        total = int(
            cast(
                int | None,
                await self.session.scalar(
                    select(func.count())
                    .select_from(DeviceMetric)
                    .where(DeviceMetric.agent_id == agent_id)
                ),
            )
            or 0
        )
        values = await self.session.scalars(
            select(DeviceMetric)
            .where(DeviceMetric.agent_id == agent_id)
            .order_by(DeviceMetric.sampled_at.desc(), DeviceMetric.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(values), total

    async def stale_agents(self, cutoff: datetime, limit: int) -> list[DeviceAgent]:
        values = await self.session.scalars(
            select(DeviceAgent)
            .where(
                DeviceAgent.credential_status == "ACTIVE",
                DeviceAgent.status.in_(("ONLINE", "DEGRADED", "OFFLINE")),
                DeviceAgent.last_heartbeat_at.is_not(None),
                DeviceAgent.last_heartbeat_at < cutoff,
            )
            .order_by(DeviceAgent.last_heartbeat_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(values)

    async def prune(self, before: datetime) -> tuple[int, int]:
        metrics = await self.session.execute(
            delete(DeviceMetric).where(DeviceMetric.received_at < before)
        )
        heartbeats = await self.session.execute(
            delete(DeviceHeartbeat).where(DeviceHeartbeat.received_at < before)
        )
        return int(metrics.rowcount or 0), int(heartbeats.rowcount or 0)  # type: ignore[attr-defined]
