from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alerts.models import (
    Alert,
    AlertPolicy,
    AutomationExecution,
    AutomationRule,
    Notification,
    NotificationPreference,
)
from app.modules.assets.models import Asset
from app.modules.assets.repository import AssetAccess, AssetRepository
from app.modules.directory.models import DirectoryStatus, Team, TeamMember
from app.modules.identity.models import User, UserStatus
from app.modules.tickets.models import Ticket


@dataclass(frozen=True)
class AlertRecord:
    alert: Alert
    asset: Asset
    incident: Ticket | None


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def policy(self, policy_id: UUID, *, lock: bool = False) -> AlertPolicy | None:
        statement = select(AlertPolicy).where(AlertPolicy.id == policy_id)
        if lock:
            statement = statement.with_for_update()
        return cast(AlertPolicy | None, await self.session.scalar(statement))

    async def policies(self, enabled_only: bool = False) -> list[AlertPolicy]:
        statement = select(AlertPolicy)
        if enabled_only:
            statement = statement.where(AlertPolicy.enabled.is_(True))
        return list(await self.session.scalars(statement.order_by(AlertPolicy.name)))

    async def rule(self, rule_id: UUID, *, lock: bool = False) -> AutomationRule | None:
        statement = select(AutomationRule).where(AutomationRule.id == rule_id)
        if lock:
            statement = statement.with_for_update()
        return cast(AutomationRule | None, await self.session.scalar(statement))

    async def rules(self, enabled_only: bool = False) -> list[AutomationRule]:
        statement = select(AutomationRule)
        if enabled_only:
            statement = statement.where(AutomationRule.enabled.is_(True))
        return list(await self.session.scalars(statement.order_by(AutomationRule.name)))

    async def active_alert(
        self, policy_id: UUID, agent_id: UUID, *, lock: bool = False
    ) -> Alert | None:
        statement = select(Alert).where(
            Alert.policy_id == policy_id,
            Alert.agent_id == agent_id,
            Alert.state.in_(("TRIGGERED", "ACKNOWLEDGED", "SUPPRESSED")),
        )
        if lock:
            statement = statement.with_for_update()
        return cast(Alert | None, await self.session.scalar(statement))

    def _alert_statement(self, access: AssetAccess) -> Select[tuple[Alert, Asset, Ticket]]:
        return (
            select(Alert, Asset, Ticket)
            .join(Asset, Asset.id == Alert.asset_id)
            .outerjoin(Ticket, Ticket.id == Alert.incident_ticket_id)
            .where(AssetRepository(self.session).access_predicate(access))
        )

    async def visible_alert(
        self, alert_id: UUID, access: AssetAccess, *, lock: bool = False
    ) -> AlertRecord | None:
        statement = self._alert_statement(access).where(Alert.id == alert_id)
        if lock:
            statement = statement.with_for_update(of=Alert)
        row = (await self.session.execute(statement)).one_or_none()
        return AlertRecord(row[0], row[1], row[2]) if row else None

    async def alerts(
        self,
        access: AssetAccess,
        state: str | None,
        severity: str | None,
        asset_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AlertRecord], int]:
        criteria = []
        if state:
            criteria.append(Alert.state == state)
        if severity:
            criteria.append(Alert.severity == severity)
        if asset_id:
            criteria.append(Alert.asset_id == asset_id)
        base = self._alert_statement(access).where(*criteria)
        rows = (
            await self.session.execute(
                base.order_by(Alert.triggered_at.desc(), Alert.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        total = int(
            cast(
                int | None,
                await self.session.scalar(
                    select(func.count())
                    .select_from(Alert)
                    .join(Asset, Asset.id == Alert.asset_id)
                    .where(AssetRepository(self.session).access_predicate(access), *criteria)
                ),
            )
            or 0
        )
        return [AlertRecord(row[0], row[1], row[2]) for row in rows], total

    async def team(self, team_id: UUID) -> Team | None:
        return cast(
            Team | None,
            await self.session.scalar(
                select(Team).where(Team.id == team_id, Team.status == DirectoryStatus.ACTIVE)
            ),
        )

    async def active_alerts_for_policy(self, policy_id: UUID) -> list[Alert]:
        return list(
            await self.session.scalars(
                select(Alert).where(
                    Alert.policy_id == policy_id,
                    Alert.state.in_(("TRIGGERED", "ACKNOWLEDGED", "SUPPRESSED")),
                )
            )
        )

    async def active_team_user_ids(self, team_id: UUID) -> list[UUID]:
        values = await self.session.scalars(
            select(TeamMember.user_id)
            .join(User, User.id == TeamMember.user_id)
            .where(
                TeamMember.team_id == team_id,
                TeamMember.ended_at.is_(None),
                User.status == UserStatus.ACTIVE,
            )
        )
        return list(values)

    async def execution(self, rule_id: UUID, alert_id: UUID) -> AutomationExecution | None:
        return cast(
            AutomationExecution | None,
            await self.session.scalar(
                select(AutomationExecution).where(
                    AutomationExecution.rule_id == rule_id,
                    AutomationExecution.alert_id == alert_id,
                )
            ),
        )

    async def executions(self, limit: int) -> list[AutomationExecution]:
        return list(
            await self.session.scalars(
                select(AutomationExecution)
                .order_by(AutomationExecution.executed_at.desc())
                .limit(limit)
            )
        )

    async def preference(self, user_id: UUID) -> NotificationPreference | None:
        return cast(
            NotificationPreference | None,
            await self.session.scalar(
                select(NotificationPreference).where(NotificationPreference.user_id == user_id)
            ),
        )

    async def notifications(
        self, user_id: UUID, unread_only: bool, offset: int, limit: int
    ) -> tuple[list[Notification], int, int]:
        criteria = [Notification.user_id == user_id]
        if unread_only:
            criteria.append(Notification.read_at.is_(None))
        total = int(
            cast(
                int | None,
                await self.session.scalar(
                    select(func.count()).select_from(Notification).where(*criteria)
                ),
            )
            or 0
        )
        unread = int(
            cast(
                int | None,
                await self.session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.user_id == user_id, Notification.read_at.is_(None))
                ),
            )
            or 0
        )
        values = await self.session.scalars(
            select(Notification)
            .where(*criteria)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(values), total, unread

    async def notification(self, notification_id: UUID, user_id: UUID) -> Notification | None:
        return cast(
            Notification | None,
            await self.session.scalar(
                select(Notification).where(
                    Notification.id == notification_id, Notification.user_id == user_id
                )
            ),
        )
