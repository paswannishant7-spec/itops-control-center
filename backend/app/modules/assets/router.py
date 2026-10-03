from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.assets.models import AssetHealthStatus, AssetStatus, AssetType
from app.modules.assets.repository import AssetRecord, AssignmentRecord, EventRecord
from app.modules.assets.schemas import (
    AssetAssignmentCreate,
    AssetCreate,
    AssetEventResponse,
    AssetHistoryResponse,
    AssetPage,
    AssetResponse,
    AssetRetire,
    AssetTicketSummary,
    AssetUpdate,
    AssignmentResponse,
    OwnerSummary,
    ReferenceSummary,
)
from app.modules.assets.service import AssetService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.tickets.service import TicketService

router = APIRouter(prefix="/assets", tags=["asset management"])


def owner(value: User | None) -> OwnerSummary | None:
    return (
        OwnerSummary(id=value.id, display_name=value.display_name, email=value.email)
        if value
        else None
    )


def reference(value: object | None) -> ReferenceSummary | None:
    if value is None:
        return None
    return ReferenceSummary(id=value.id, code=value.code, name=value.name)  # type: ignore[attr-defined]


def asset_response(value: AssetRecord) -> AssetResponse:
    asset = value.asset
    return AssetResponse(
        id=asset.id,
        asset_tag=asset.asset_tag,
        serial_number=asset.serial_number,
        hostname=asset.hostname,
        asset_type=asset.asset_type,
        manufacturer=asset.manufacturer,
        model=asset.model,
        operating_system=asset.operating_system,
        ip_address=asset.ip_address,
        mac_address=asset.mac_address,
        owner=owner(value.owner),
        department=reference(value.department),
        location=reference(value.location),
        purchase_date=asset.purchase_date,
        warranty_end=asset.warranty_end,
        status=asset.status,
        last_seen=asset.last_seen,
        health_status=asset.health_status,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def assignment_response(value: AssignmentRecord) -> AssignmentResponse:
    assignment = value.assignment
    assigned_by = owner(value.assigned_by)
    assert assigned_by is not None
    return AssignmentResponse(
        id=assignment.id,
        owner=owner(value.owner),
        department=reference(value.department),
        location=reference(value.location),
        assigned_by=assigned_by,
        reason=assignment.reason,
        started_at=assignment.started_at,
        ended_at=assignment.ended_at,
    )


def event_response(value: EventRecord) -> AssetEventResponse:
    actor = owner(value.actor)
    assert actor is not None
    return AssetEventResponse(
        id=value.event.id,
        action=value.event.action,
        actor=actor,
        before_state=value.event.before_state,
        after_state=value.event.after_state,
        reason=value.event.reason,
        created_at=value.event.created_at,
    )


@router.get("", response_model=AssetPage)
async def assets(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    asset_type: AssetType | None = None,
    asset_status: Annotated[AssetStatus | None, Query(alias="status")] = None,
    health_status: AssetHealthStatus | None = None,
    owner_id: UUID | None = None,
    department_id: UUID | None = None,
    location_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AssetPage:
    records, total = await AssetService(session).list_assets(
        actor.id,
        search=search,
        asset_type=asset_type,
        status=asset_status,
        health_status=health_status,
        owner_id=owner_id,
        department_id=department_id,
        location_id=location_id,
        offset=offset,
        limit=limit,
    )
    return AssetPage(
        items=[asset_response(value) for value in records],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssetResponse:
    service = AssetService(session)
    asset = await service.create_asset(
        actor.id,
        payload.model_dump(exclude={"reason"}),
        payload.reason,
        request.state.request_id,
    )
    return asset_response(await service.get_asset(actor.id, asset.id))


@router.get("/{asset_id}", response_model=AssetResponse)
async def asset_detail(
    asset_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssetResponse:
    return asset_response(await AssetService(session).get_asset(actor.id, asset_id))


@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssetResponse:
    service = AssetService(session)
    await service.update_asset(
        actor.id,
        asset_id,
        payload.model_dump(exclude={"reason"}, exclude_unset=True),
        payload.reason,
        request.state.request_id,
    )
    return asset_response(await service.get_asset(actor.id, asset_id))


@router.post("/{asset_id}/assignments", response_model=AssetResponse)
async def assign_asset(
    asset_id: UUID,
    payload: AssetAssignmentCreate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssetResponse:
    service = AssetService(session)
    await service.assign(
        actor.id,
        asset_id,
        payload.owner_id,
        payload.department_id,
        payload.location_id,
        payload.clear,
        payload.reason,
        request.state.request_id,
    )
    return asset_response(await service.get_asset(actor.id, asset_id))


@router.post("/{asset_id}/retire", response_model=AssetResponse)
async def retire_asset(
    asset_id: UUID,
    payload: AssetRetire,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssetResponse:
    service = AssetService(session)
    await service.retire(actor.id, asset_id, payload.reason, request.state.request_id)
    return asset_response(await service.get_asset(actor.id, asset_id))


@router.get("/{asset_id}/history", response_model=AssetHistoryResponse)
async def asset_history(
    asset_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssetHistoryResponse:
    assignments, events = await AssetService(session).history(actor.id, asset_id)
    return AssetHistoryResponse(
        assignments=[assignment_response(value) for value in assignments],
        events=[event_response(value) for value in events],
    )


@router.get("/{asset_id}/tickets", response_model=list[AssetTicketSummary])
async def asset_tickets(
    asset_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AssetTicketSummary]:
    service = AssetService(session)
    await service.get_asset(actor.id, asset_id)
    ticket_access = await TicketService(session).access(actor.id)
    tickets = await service.repository.tickets(asset_id, ticket_access)
    return [
        AssetTicketSummary(
            id=value.id,
            reference=value.reference,
            title=value.title,
            status=value.status,
            priority=value.priority,
            updated_at=value.updated_at,
        )
        for value in tickets
    ]
