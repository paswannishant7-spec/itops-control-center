from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.ai.models import AIFeedback
from app.modules.alerts.models import Alert
from app.modules.assets.models import Asset
from app.modules.assets.repository import AssetAccess, AssetRepository
from app.modules.directory.models import Department
from app.modules.identity.models import User
from app.modules.monitoring.models import DeviceAgent
from app.modules.sla.models import SlaInstance
from app.modules.tickets.models import Ticket, TicketCategory, TicketSubcategory
from app.modules.tickets.repository import TicketAccess, TicketRepository


@dataclass(frozen=True)
class AnalyticsTicket:
    ticket: Ticket
    sla: SlaInstance | None
    category_name: str | None
    subcategory_name: str | None
    department_name: str | None
    technician_name: str | None
    asset_tag: str | None


@dataclass(frozen=True)
class AnalyticsDevice:
    agent: DeviceAgent
    asset: Asset


@dataclass(frozen=True)
class AnalyticsAlert:
    alert: Alert
    asset: Asset


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def tickets(self, access: TicketAccess, window_start: datetime) -> list[AnalyticsTicket]:
        technician = aliased(User, name="analytics_technician")
        active = (
            "NEW",
            "OPEN",
            "IN_PROGRESS",
            "PENDING_USER",
            "PENDING_VENDOR",
            "ESCALATED",
        )
        rows = (
            await self.session.execute(
                select(
                    Ticket,
                    SlaInstance,
                    TicketCategory.name,
                    TicketSubcategory.name,
                    Department.name,
                    technician.display_name,
                    Asset.asset_tag,
                )
                .outerjoin(SlaInstance, SlaInstance.ticket_id == Ticket.id)
                .outerjoin(TicketCategory, TicketCategory.id == Ticket.category_id)
                .outerjoin(TicketSubcategory, TicketSubcategory.id == Ticket.subcategory_id)
                .outerjoin(Department, Department.id == Ticket.department_id)
                .outerjoin(technician, technician.id == Ticket.assigned_technician_id)
                .outerjoin(Asset, Asset.id == Ticket.asset_id)
                .where(
                    TicketRepository(self.session).access_predicate(access),
                    or_(
                        Ticket.status.in_(active),
                        Ticket.created_at >= window_start,
                        Ticket.resolved_at >= window_start,
                        Ticket.first_response_at >= window_start,
                    ),
                )
            )
        ).all()
        return [
            AnalyticsTicket(row[0], row[1], row[2], row[3], row[4], row[5], row[6]) for row in rows
        ]

    async def devices(self, access: AssetAccess) -> list[AnalyticsDevice]:
        rows = (
            await self.session.execute(
                select(DeviceAgent, Asset)
                .join(Asset, Asset.id == DeviceAgent.asset_id)
                .where(AssetRepository(self.session).access_predicate(access))
            )
        ).all()
        return [AnalyticsDevice(row[0], row[1]) for row in rows]

    async def alerts(self, access: AssetAccess) -> list[AnalyticsAlert]:
        rows = (
            await self.session.execute(
                select(Alert, Asset)
                .join(Asset, Asset.id == Alert.asset_id)
                .where(
                    AssetRepository(self.session).access_predicate(access),
                    Alert.state.in_(("TRIGGERED", "ACKNOWLEDGED")),
                )
            )
        ).all()
        return [AnalyticsAlert(row[0], row[1]) for row in rows]

    async def feedback_actions(self, access: TicketAccess, window_start: datetime) -> list[str]:
        values = await self.session.scalars(
            select(AIFeedback.action)
            .join(Ticket, Ticket.id == AIFeedback.ticket_id)
            .where(
                TicketRepository(self.session).access_predicate(access),
                AIFeedback.created_at >= window_start,
            )
        )
        return [str(value) for value in values]
