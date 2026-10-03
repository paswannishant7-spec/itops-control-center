from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.access.dependencies import require_permission
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.sla.models import SlaPolicy
from app.modules.sla.repository import SlaRepository
from app.modules.sla.schemas import (
    CalendarResponse,
    CalendarWrite,
    MatrixEntry,
    MatrixUpdate,
    PolicyResponse,
    PolicyWrite,
    SlaSnapshot,
)
from app.modules.sla.service import SlaService
from app.modules.tickets.models import ImpactLevel
from app.modules.tickets.service import TicketService

router = APIRouter(prefix="/sla", tags=["service levels"])


async def calendar_response(repository: SlaRepository, calendar_id: UUID) -> CalendarResponse:
    bundle = await repository.calendar_bundle(calendar_id)
    assert bundle is not None
    calendar = bundle.calendar
    return CalendarResponse(
        id=calendar.id,
        name=calendar.name,
        timezone=calendar.timezone,
        is_active=calendar.is_active,
        is_default=calendar.is_default,
        windows=[
            {
                "weekday": item.weekday,
                "start_minute": item.start_minute,
                "end_minute": item.end_minute,
            }
            for item in bundle.windows
        ],
        holidays=[
            {"holiday_date": item.holiday_date, "name": item.name}
            for item in await repository.calendar_holidays(calendar.id)
        ],
        created_at=calendar.created_at,
        updated_at=calendar.updated_at,
    )


def policy_response(policy: SlaPolicy) -> PolicyResponse:
    return PolicyResponse.model_validate(policy, from_attributes=True)


@router.get("/priority-matrix", response_model=list[MatrixEntry])
async def priority_matrix(
    actor: Annotated[User, Depends(require_permission("sla:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MatrixEntry]:
    del actor
    return [
        MatrixEntry.model_validate(item, from_attributes=True)
        for item in await SlaRepository(session).matrix()
    ]


@router.put("/priority-matrix/{impact}/{urgency}", response_model=MatrixEntry)
async def update_priority_matrix(
    impact: ImpactLevel,
    urgency: ImpactLevel,
    payload: MatrixUpdate,
    actor: Annotated[User, Depends(require_permission("sla:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MatrixEntry:
    del actor
    record = await SlaService(session).set_matrix(impact, urgency, payload.priority)
    return MatrixEntry.model_validate(record, from_attributes=True)


@router.get("/calendars", response_model=list[CalendarResponse])
async def calendars(
    actor: Annotated[User, Depends(require_permission("sla:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CalendarResponse]:
    del actor
    repository = SlaRepository(session)
    return [await calendar_response(repository, item.id) for item in await repository.calendars()]


@router.post("/calendars", response_model=CalendarResponse, status_code=201)
async def create_calendar(
    payload: CalendarWrite,
    actor: Annotated[User, Depends(require_permission("sla:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CalendarResponse:
    del actor
    calendar = await SlaService(session).save_calendar(payload.model_dump())
    return await calendar_response(SlaRepository(session), calendar.id)


@router.put("/calendars/{calendar_id}", response_model=CalendarResponse)
async def replace_calendar(
    calendar_id: UUID,
    payload: CalendarWrite,
    actor: Annotated[User, Depends(require_permission("sla:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CalendarResponse:
    del actor
    calendar = await SlaService(session).save_calendar(payload.model_dump(), calendar_id)
    return await calendar_response(SlaRepository(session), calendar.id)


@router.get("/policies", response_model=list[PolicyResponse])
async def policies(
    actor: Annotated[User, Depends(require_permission("sla:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PolicyResponse]:
    del actor
    return [policy_response(item) for item in await SlaRepository(session).policies()]


@router.post("/policies", response_model=PolicyResponse, status_code=201)
async def create_policy(
    payload: PolicyWrite,
    actor: Annotated[User, Depends(require_permission("sla:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyResponse:
    del actor
    return policy_response(await SlaService(session).save_policy(payload.model_dump()))


@router.put("/policies/{policy_id}", response_model=PolicyResponse)
async def replace_policy(
    policy_id: UUID,
    payload: PolicyWrite,
    actor: Annotated[User, Depends(require_permission("sla:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyResponse:
    del actor
    return policy_response(await SlaService(session).save_policy(payload.model_dump(), policy_id))


@router.get("/tickets/{ticket_id}", response_model=SlaSnapshot | None)
async def ticket_sla(
    ticket_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SlaSnapshot | None:
    ticket = (await TicketService(session).get_ticket(actor.id, ticket_id)).ticket
    snapshot = await SlaService(session).snapshot(ticket)
    return SlaSnapshot.model_validate(snapshot) if snapshot else None
