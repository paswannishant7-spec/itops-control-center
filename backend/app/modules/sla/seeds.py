from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sla.models import (
    BusinessCalendar,
    BusinessWindow,
    PriorityMatrix,
    SlaPolicy,
)

CALENDAR_ID = UUID("01991fa0-0000-7000-8000-000000000001")
POLICY_IDS = {
    "CRITICAL": UUID("01991fa0-0000-7000-8000-000000000011"),
    "HIGH": UUID("01991fa0-0000-7000-8000-000000000012"),
    "MEDIUM": UUID("01991fa0-0000-7000-8000-000000000013"),
    "LOW": UUID("01991fa0-0000-7000-8000-000000000014"),
}


def add_default_sla_configuration(session: AsyncSession) -> None:
    session.add_all(
        [
            PriorityMatrix(impact=impact, urgency=urgency, priority=priority)
            for impact, urgency, priority in (
                ("LOW", "LOW", "LOW"),
                ("LOW", "MEDIUM", "MEDIUM"),
                ("LOW", "HIGH", "MEDIUM"),
                ("MEDIUM", "LOW", "MEDIUM"),
                ("MEDIUM", "MEDIUM", "MEDIUM"),
                ("MEDIUM", "HIGH", "HIGH"),
                ("HIGH", "LOW", "MEDIUM"),
                ("HIGH", "MEDIUM", "HIGH"),
                ("HIGH", "HIGH", "CRITICAL"),
            )
        ]
    )
    session.add(
        BusinessCalendar(
            id=CALENDAR_ID,
            name="Default 24x7",
            timezone="UTC",
            is_active=True,
            is_default=True,
        )
    )
    session.add_all(
        [
            BusinessWindow(
                id=UUID(f"01991fa0-0000-7000-8000-{weekday + 101:012d}"),
                calendar_id=CALENDAR_ID,
                weekday=weekday,
                start_minute=0,
                end_minute=1440,
            )
            for weekday in range(7)
        ]
    )
    session.add_all(
        [
            SlaPolicy(
                id=POLICY_IDS[priority],
                name=name,
                priority=priority,
                calendar_id=CALENDAR_ID,
                response_target_minutes=response,
                resolution_target_minutes=resolution,
                at_risk_percent=80,
                is_active=True,
            )
            for priority, name, response, resolution in (
                ("CRITICAL", "P1 Critical", 15, 120),
                ("HIGH", "P2 High", 60, 480),
                ("MEDIUM", "P3 Medium", 240, 1440),
                ("LOW", "P4 Low", 480, 4320),
            )
        ]
    )
