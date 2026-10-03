from dataclasses import dataclass
from datetime import date
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sla.models import (
    BusinessCalendar,
    BusinessHoliday,
    BusinessWindow,
    PriorityMatrix,
    SlaEvent,
    SlaInstance,
    SlaPause,
    SlaPolicy,
)
from app.modules.tickets.models import Ticket


@dataclass(frozen=True)
class CalendarBundle:
    calendar: BusinessCalendar
    windows: list[BusinessWindow]
    holidays: frozenset[date]


class SlaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def matrix(self) -> list[PriorityMatrix]:
        return list(
            await self.session.scalars(
                select(PriorityMatrix).order_by(PriorityMatrix.impact, PriorityMatrix.urgency)
            )
        )

    async def priority(self, impact: str, urgency: str) -> str | None:
        record = await self.session.get(PriorityMatrix, (impact, urgency))
        return record.priority if record else None

    async def policies(self) -> list[SlaPolicy]:
        return list(await self.session.scalars(select(SlaPolicy).order_by(SlaPolicy.priority)))

    async def active_policy(self, priority: str) -> SlaPolicy | None:
        return cast(
            SlaPolicy | None,
            await self.session.scalar(
                select(SlaPolicy).where(
                    SlaPolicy.priority == priority, SlaPolicy.is_active.is_(True)
                )
            ),
        )

    async def policy(self, policy_id: UUID, lock: bool = False) -> SlaPolicy | None:
        statement = select(SlaPolicy).where(SlaPolicy.id == policy_id)
        return cast(
            SlaPolicy | None,
            await self.session.scalar(statement.with_for_update() if lock else statement),
        )

    async def calendars(self) -> list[BusinessCalendar]:
        return list(
            await self.session.scalars(
                select(BusinessCalendar).order_by(
                    BusinessCalendar.is_default.desc(), BusinessCalendar.name
                )
            )
        )

    async def calendar_bundle(self, calendar_id: UUID) -> CalendarBundle | None:
        calendar = await self.session.get(BusinessCalendar, calendar_id)
        if calendar is None:
            return None
        windows = list(
            await self.session.scalars(
                select(BusinessWindow)
                .where(BusinessWindow.calendar_id == calendar_id)
                .order_by(BusinessWindow.weekday, BusinessWindow.start_minute)
            )
        )
        holidays = frozenset(
            await self.session.scalars(
                select(BusinessHoliday.holiday_date).where(
                    BusinessHoliday.calendar_id == calendar_id
                )
            )
        )
        return CalendarBundle(calendar, windows, holidays)

    async def calendar_holidays(self, calendar_id: UUID) -> list[BusinessHoliday]:
        return list(
            await self.session.scalars(
                select(BusinessHoliday)
                .where(BusinessHoliday.calendar_id == calendar_id)
                .order_by(BusinessHoliday.holiday_date)
            )
        )

    async def replace_calendar_children(self, calendar_id: UUID) -> None:
        await self.session.execute(
            delete(BusinessHoliday).where(BusinessHoliday.calendar_id == calendar_id)
        )
        await self.session.execute(
            delete(BusinessWindow).where(BusinessWindow.calendar_id == calendar_id)
        )

    async def instance(self, ticket_id: UUID, lock: bool = False) -> SlaInstance | None:
        statement = select(SlaInstance).where(SlaInstance.ticket_id == ticket_id)
        return cast(
            SlaInstance | None,
            await self.session.scalar(statement.with_for_update() if lock else statement),
        )

    async def pauses(self, instance_id: UUID) -> list[SlaPause]:
        return list(
            await self.session.scalars(
                select(SlaPause)
                .where(SlaPause.instance_id == instance_id)
                .order_by(SlaPause.started_at)
            )
        )

    async def active_pause(self, instance_id: UUID) -> SlaPause | None:
        return cast(
            SlaPause | None,
            await self.session.scalar(
                select(SlaPause).where(
                    SlaPause.instance_id == instance_id, SlaPause.ended_at.is_(None)
                )
            ),
        )

    async def active_instances(self, limit: int) -> list[tuple[SlaInstance, Ticket]]:
        rows = await self.session.execute(
            select(SlaInstance, Ticket)
            .join(Ticket, Ticket.id == SlaInstance.ticket_id)
            .where(SlaInstance.state != "COMPLETED")
            .order_by(SlaInstance.updated_at)
            .limit(limit)
            .with_for_update(skip_locked=True, of=SlaInstance)
        )
        return [(row[0], row[1]) for row in rows]

    async def has_event(self, key: str) -> bool:
        return (
            await self.session.scalar(select(SlaEvent.id).where(SlaEvent.idempotency_key == key))
        ) is not None
