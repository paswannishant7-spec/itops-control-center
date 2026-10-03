from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.access.dependencies import require_permission
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User
from app.modules.sla.models import SlaState
from app.modules.tickets.models import TicketPriority, TicketStatus
from app.modules.tickets.repository import (
    AttachmentRecord,
    CommentRecord,
    EventRecord,
    TicketRecord,
    TicketRepository,
)
from app.modules.tickets.schemas import (
    CategoryResponse,
    CommentPage,
    EventPage,
    NamedReference,
    PersonReference,
    TicketAssignmentRequest,
    TicketAttachmentResponse,
    TicketCommentCreate,
    TicketCommentResponse,
    TicketCreate,
    TicketDetail,
    TicketEventResponse,
    TicketPage,
    TicketSummary,
    TicketTransitionRequest,
    TicketUpdate,
)
from app.modules.tickets.service import TicketService
from app.modules.tickets.storage import ClamAVScanner, LocalAttachmentStorage

router = APIRouter(prefix="/tickets", tags=["tickets"])


def person(user: User) -> PersonReference:
    return PersonReference(id=user.id, display_name=user.display_name, email=user.email)


def named(record: object | None) -> NamedReference | None:
    if record is None:
        return None
    return NamedReference(id=record.id, name=record.name)  # type: ignore[attr-defined]


def ticket_summary(record: TicketRecord) -> TicketSummary:
    ticket = record.ticket
    return TicketSummary(
        id=ticket.id,
        reference=ticket.reference,
        title=ticket.title,
        requester=person(record.requester),
        department=named(record.department),
        location=named(record.location),
        impact=ticket.impact,
        urgency=ticket.urgency,
        priority=ticket.priority,
        sla_state=record.sla_instance.state if record.sla_instance else None,
        status=ticket.status,
        assignment_team=named(record.team),
        assigned_technician=person(record.technician) if record.technician else None,
        record_type=ticket.record_type,
        source=ticket.source,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def ticket_detail(record: TicketRecord) -> TicketDetail:
    ticket = record.ticket
    return TicketDetail(
        **ticket_summary(record).model_dump(),
        description=ticket.description,
        asset_id=ticket.asset_id,
        category=named(record.category),
        subcategory=named(record.subcategory),
        first_response_at=ticket.first_response_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        reopened_at=ticket.reopened_at,
        resolution_summary=ticket.resolution_summary,
        resolution_code=ticket.resolution_code,
    )


def comment_response(record: CommentRecord) -> TicketCommentResponse:
    return TicketCommentResponse(
        id=record.comment.id,
        author=person(record.author),
        body=record.comment.body,
        visibility=record.comment.visibility,
        created_at=record.comment.created_at,
        updated_at=record.comment.updated_at,
    )


def attachment_response(record: AttachmentRecord) -> TicketAttachmentResponse:
    return TicketAttachmentResponse(
        id=record.attachment.id,
        original_name=record.attachment.original_name,
        content_type=record.attachment.content_type,
        size_bytes=record.attachment.size_bytes,
        uploader=person(record.uploader),
        created_at=record.attachment.created_at,
    )


def event_response(record: EventRecord) -> TicketEventResponse:
    return TicketEventResponse(
        id=record.event.id,
        event_type=record.event.event_type,
        actor=person(record.actor),
        before_state=record.event.before_state,
        after_state=record.event.after_state,
        reason=record.event.reason,
        created_at=record.event.created_at,
    )


def ensure_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise HTTPException(422, "Date filters must include a timezone")
    return value


async def read_limited_body(request: Request, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Attachment is too large")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/categories", response_model=list[CategoryResponse])
async def categories(
    actor: Annotated[User, Depends(require_permission("ticket:create"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CategoryResponse]:
    del actor
    values = await TicketRepository(session).categories()
    return [
        CategoryResponse(
            id=category.id,
            code=category.code,
            name=category.name,
            subcategories=[NamedReference(id=item.id, name=item.name) for item in subcategories],
        )
        for category, subcategories in values
    ]


@router.post("", response_model=TicketDetail, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("ticket:create"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketDetail:
    ticket = await TicketService(session).create_ticket(
        actor, payload.model_dump(), request.state.request_id
    )
    return ticket_detail(await TicketService(session).get_ticket(actor.id, ticket.id))


@router.get("", response_model=TicketPage)
async def tickets(
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=200)] = None,
    ticket_status: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority: TicketPriority | None = None,
    sla_state: SlaState | None = None,
    team_id: UUID | None = None,
    technician_id: UUID | None = None,
    department_id: UUID | None = None,
    asset_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TicketPage:
    created_from = ensure_aware(created_from)
    created_to = ensure_aware(created_to)
    if created_from and created_to and created_from > created_to:
        raise HTTPException(422, "created_from must be before created_to")
    values, total = await TicketService(session).list_tickets(
        actor.id,
        search=search,
        status=ticket_status,
        priority=priority,
        sla_state=sla_state,
        team_id=team_id,
        technician_id=technician_id,
        department_id=department_id,
        asset_id=asset_id,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )
    return TicketPage(
        items=[ticket_summary(value) for value in values],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketDetail:
    return ticket_detail(await TicketService(session).get_ticket(actor.id, ticket_id))


@router.patch("/{ticket_id}", response_model=TicketDetail)
async def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketDetail:
    await TicketService(session).update_ticket(
        actor.id,
        ticket_id,
        payload.model_dump(exclude={"reason"}, exclude_unset=True),
        payload.reason,
        request.state.request_id,
    )
    return ticket_detail(await TicketService(session).get_ticket(actor.id, ticket_id))


@router.post("/{ticket_id}/transitions", response_model=TicketDetail)
async def transition_ticket(
    ticket_id: UUID,
    payload: TicketTransitionRequest,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketDetail:
    await TicketService(session).transition(
        actor.id,
        ticket_id,
        payload.status,
        payload.reason,
        request.state.request_id,
        payload.resolution_summary,
        payload.resolution_code,
    )
    return ticket_detail(await TicketService(session).get_ticket(actor.id, ticket_id))


@router.put("/{ticket_id}/assignment", response_model=TicketDetail)
async def assign_ticket(
    ticket_id: UUID,
    payload: TicketAssignmentRequest,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketDetail:
    await TicketService(session).assign_ticket(
        actor.id,
        ticket_id,
        payload.team_id,
        payload.technician_id,
        payload.reason,
        request.state.request_id,
    )
    return ticket_detail(await TicketService(session).get_ticket(actor.id, ticket_id))


@router.get("/{ticket_id}/comments", response_model=CommentPage)
async def comments(
    ticket_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CommentPage:
    values, total = await TicketService(session).list_comments(actor.id, ticket_id, offset, limit)
    return CommentPage(
        items=[comment_response(value) for value in values],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    ticket_id: UUID,
    payload: TicketCommentCreate,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TicketCommentResponse:
    comment = await TicketService(session).add_comment(
        actor.id,
        ticket_id,
        payload.body,
        payload.visibility,
        request.state.request_id,
    )
    return TicketCommentResponse(
        id=comment.id,
        author=person(actor),
        body=comment.body,
        visibility=comment.visibility,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.get("/{ticket_id}/attachments", response_model=list[TicketAttachmentResponse])
async def attachments(
    ticket_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TicketAttachmentResponse]:
    values = await TicketService(session).list_attachments(actor.id, ticket_id)
    return [attachment_response(value) for value in values]


@router.post(
    "/{ticket_id}/attachments",
    response_model=TicketAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_attachment(
    ticket_id: UUID,
    request: Request,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    filename: Annotated[str, Query(min_length=1, max_length=255)],
) -> TicketAttachmentResponse:
    data = await read_limited_body(request, settings.attachment_max_bytes)
    content_type = request.headers.get("content-type", "application/octet-stream")
    scanner = None
    if settings.attachment_clamav_host:
        scanner = ClamAVScanner(
            settings.attachment_clamav_host,
            settings.attachment_clamav_port,
            settings.attachment_scan_timeout_seconds,
        )
    elif settings.attachment_scan_required:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Malware scanner is unavailable")
    attachment = await TicketService(session).add_attachment(
        actor.id,
        ticket_id,
        filename,
        content_type,
        data,
        LocalAttachmentStorage(settings.attachment_storage_path),
        settings.attachment_max_bytes,
        request.state.request_id,
        scanner,
    )
    return TicketAttachmentResponse(
        id=attachment.id,
        original_name=attachment.original_name,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        uploader=person(actor),
        created_at=attachment.created_at,
    )


@router.get("/{ticket_id}/attachments/{attachment_id}")
async def download_attachment(
    ticket_id: UUID,
    attachment_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    attachment = await TicketService(session).download_attachment(
        actor.id, ticket_id, attachment_id
    )
    path = LocalAttachmentStorage(settings.attachment_storage_path).path_for(attachment.storage_key)
    if not path.is_file():
        raise HTTPException(404, "Attachment content not found")
    return FileResponse(
        Path(path), media_type=attachment.content_type, filename=attachment.original_name
    )


@router.get("/{ticket_id}/events", response_model=EventPage)
async def events(
    ticket_id: UUID,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EventPage:
    values, total = await TicketService(session).list_events(actor.id, ticket_id, offset, limit)
    return EventPage(
        items=[event_response(value) for value in values],
        total=total,
        offset=offset,
        limit=limit,
    )
