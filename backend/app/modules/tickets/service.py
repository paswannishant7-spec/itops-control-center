from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.repository import AccessRepository
from app.modules.directory.repository import DirectoryRepository
from app.modules.identity.models import User
from app.modules.tickets.models import (
    CommentVisibility,
    ImpactLevel,
    Ticket,
    TicketAssignment,
    TicketAttachment,
    TicketComment,
    TicketEvent,
    TicketPriority,
    TicketSource,
    TicketStatus,
    TicketType,
)
from app.modules.tickets.repository import (
    AttachmentRecord,
    CommentRecord,
    EventRecord,
    TicketAccess,
    TicketRecord,
    TicketRepository,
)
from app.modules.tickets.storage import (
    AttachmentMalwareDetected,
    AttachmentScanError,
    AttachmentScanner,
    AttachmentValidationError,
    LocalAttachmentStorage,
    validate_attachment,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def calculate_priority(impact: str, urgency: str) -> TicketPriority:
    score = {ImpactLevel.LOW: 1, ImpactLevel.MEDIUM: 2, ImpactLevel.HIGH: 3}
    total = score[ImpactLevel(impact)] + score[ImpactLevel(urgency)]
    if total == 6:
        return TicketPriority.CRITICAL
    if total >= 5:
        return TicketPriority.HIGH
    if total >= 3:
        return TicketPriority.MEDIUM
    return TicketPriority.LOW


LEGAL_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.NEW: frozenset({TicketStatus.OPEN}),
    TicketStatus.OPEN: frozenset({TicketStatus.IN_PROGRESS, TicketStatus.CANCELLED}),
    TicketStatus.IN_PROGRESS: frozenset(
        {
            TicketStatus.PENDING_USER,
            TicketStatus.PENDING_VENDOR,
            TicketStatus.ESCALATED,
            TicketStatus.RESOLVED,
        }
    ),
    TicketStatus.PENDING_USER: frozenset({TicketStatus.IN_PROGRESS}),
    TicketStatus.PENDING_VENDOR: frozenset({TicketStatus.IN_PROGRESS}),
    TicketStatus.ESCALATED: frozenset({TicketStatus.IN_PROGRESS}),
    TicketStatus.RESOLVED: frozenset({TicketStatus.CLOSED, TicketStatus.OPEN}),
    TicketStatus.CLOSED: frozenset(),
    TicketStatus.CANCELLED: frozenset(),
}


def transition_permission(current: TicketStatus, target: TicketStatus) -> str:
    if target == TicketStatus.ESCALATED:
        return "ticket:escalate"
    if target == TicketStatus.RESOLVED:
        return "ticket:resolve"
    if target == TicketStatus.CLOSED:
        return "ticket:close"
    if current == TicketStatus.RESOLVED and target == TicketStatus.OPEN:
        return "ticket:reopen"
    return "ticket:update"


def ticket_state(ticket: Ticket) -> dict[str, object]:
    return {
        "reference": ticket.reference,
        "title": ticket.title,
        "status": ticket.status,
        "impact": ticket.impact,
        "urgency": ticket.urgency,
        "priority": ticket.priority,
        "assignment_team_id": (
            str(ticket.assignment_team_id) if ticket.assignment_team_id else None
        ),
        "assigned_technician_id": (
            str(ticket.assigned_technician_id) if ticket.assigned_technician_id else None
        ),
        "category_id": str(ticket.category_id) if ticket.category_id else None,
        "subcategory_id": str(ticket.subcategory_id) if ticket.subcategory_id else None,
        "asset_id": str(ticket.asset_id) if ticket.asset_id else None,
        "resolution_code": ticket.resolution_code,
    }


class TicketService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = TicketRepository(session)

    async def access(self, user_id: UUID, required: str | None = None) -> TicketAccess:
        _, grants = await AccessRepository(self.session).grants(user_id)
        permissions = frozenset(grants)
        if required and required not in permissions:
            raise HTTPException(403, "Permission denied")
        team_ids = (
            await DirectoryRepository(self.session).active_team_ids(user_id)
            if "ticket:view_team" in permissions
            else frozenset()
        )
        return TicketAccess(
            user_id=user_id,
            permissions=permissions,
            team_ids=team_ids,
            team_department_ids=await self.repository.team_departments(team_ids),
        )

    async def _visible(
        self, user_id: UUID, ticket_id: UUID, *, required: str | None = None, lock: bool = False
    ) -> tuple[TicketRecord, TicketAccess]:
        access = await self.access(user_id, required)
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        record = await self.repository.visible_ticket(ticket_id, access, for_update=lock)
        if record is None:
            raise HTTPException(404, "Ticket not found")
        return record, access

    def _event(
        self,
        ticket_id: UUID,
        actor_id: UUID,
        event_type: str,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
        reason: str,
        request_id: str,
    ) -> None:
        self.session.add(
            TicketEvent(
                ticket_id=ticket_id,
                actor_id=actor_id,
                event_type=event_type,
                before_state=before,
                after_state=after,
                reason=reason,
                request_id=request_id[:128],
                created_at=utc_now(),
            )
        )

    async def _commit(self, conflict: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, conflict) from None

    async def _validate_categories(
        self, category_id: UUID | None, subcategory_id: UUID | None
    ) -> None:
        if subcategory_id and not category_id:
            raise HTTPException(422, "A subcategory requires a category")
        category, subcategory = await self.repository.category_pair(category_id, subcategory_id)
        if category_id and category is None:
            raise HTTPException(422, "Category does not exist or is inactive")
        if subcategory_id and (subcategory is None or subcategory.category_id != category_id):
            raise HTTPException(422, "Subcategory does not belong to the active category")

    async def create_ticket(
        self, actor: User, values: dict[str, object], request_id: str
    ) -> Ticket:
        await self.access(actor.id, "ticket:create")
        category_id = values.get("category_id")
        subcategory_id = values.get("subcategory_id")
        await self._validate_categories(
            category_id if isinstance(category_id, UUID) else None,
            subcategory_id if isinstance(subcategory_id, UUID) else None,
        )
        asset_id = values.get("asset_id")
        if isinstance(asset_id, UUID):
            from app.modules.assets.service import AssetService

            await AssetService(self.session).require_linkable(actor.id, asset_id)
        impact = str(values["impact"])
        urgency = str(values["urgency"])
        from app.modules.sla.service import SlaService

        priority = await SlaService(self.session).resolve_priority(impact, urgency)
        ticket_id = uuid4()
        record = Ticket(
            id=ticket_id,
            reference=f"IT-{utc_now():%Y%m%d}-{ticket_id.hex[:8].upper()}",
            requester_id=actor.id,
            department_id=actor.department_id,
            location_id=actor.location_id,
            priority=priority,
            status=TicketStatus.NEW,
            record_type=TicketType.REQUEST,
            source=TicketSource.PORTAL,
            **values,
        )
        self.session.add(record)
        await self.session.flush()
        await SlaService(self.session).initialize(record)
        self._event(
            record.id,
            actor.id,
            "ticket.created",
            None,
            ticket_state(record),
            "Ticket submitted",
            request_id,
        )
        await self._commit("Ticket could not be created")
        return record

    async def list_tickets(
        self,
        actor_id: UUID,
        *,
        search: str | None,
        status: str | None,
        priority: str | None,
        sla_state: str | None = None,
        team_id: UUID | None,
        technician_id: UUID | None,
        department_id: UUID | None,
        asset_id: UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[TicketRecord], int]:
        access = await self.access(actor_id)
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        return await self.repository.tickets(
            access,
            search=search,
            status=status,
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

    async def get_ticket(self, actor_id: UUID, ticket_id: UUID) -> TicketRecord:
        record, _ = await self._visible(actor_id, ticket_id)
        return record

    async def update_ticket(
        self,
        actor_id: UUID,
        ticket_id: UUID,
        values: dict[str, object],
        reason: str,
        request_id: str,
    ) -> Ticket:
        record, _ = await self._visible(actor_id, ticket_id, required="ticket:update", lock=True)
        ticket = record.ticket
        if ticket.status in {TicketStatus.CLOSED, TicketStatus.CANCELLED}:
            raise HTTPException(409, "Closed or cancelled tickets cannot be edited")
        category_id = values.get("category_id", ticket.category_id)
        subcategory_id = values.get("subcategory_id", ticket.subcategory_id)
        await self._validate_categories(
            category_id if isinstance(category_id, UUID) else None,
            subcategory_id if isinstance(subcategory_id, UUID) else None,
        )
        asset_id = values.get("asset_id")
        if isinstance(asset_id, UUID):
            from app.modules.assets.service import AssetService

            await AssetService(self.session).require_linkable(actor_id, asset_id)
        before = ticket_state(ticket)
        for key, value in values.items():
            setattr(ticket, key, value)
        if "impact" in values or "urgency" in values:
            from app.modules.sla.service import SlaService

            ticket.priority = await SlaService(self.session).resolve_priority(
                ticket.impact, ticket.urgency
            )
            await SlaService(self.session).reconfigure(ticket)
        after = ticket_state(ticket)
        if before == after and not ({"title", "description"} & values.keys()):
            return ticket
        self._event(ticket.id, actor_id, "ticket.updated", before, after, reason, request_id)
        await self._commit("Ticket could not be updated")
        return ticket

    async def assign_ticket(
        self,
        actor_id: UUID,
        ticket_id: UUID,
        team_id: UUID,
        technician_id: UUID | None,
        reason: str,
        request_id: str,
    ) -> Ticket:
        access = await self.access(actor_id)
        if not ({"ticket:assign", "ticket:reassign"} & access.permissions):
            raise HTTPException(403, "Permission denied")
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        record = await self.repository.visible_ticket(ticket_id, access, for_update=True)
        if record is None:
            raise HTTPException(404, "Ticket not found")
        ticket = record.ticket
        required = "ticket:reassign" if ticket.assignment_team_id else "ticket:assign"
        if required not in access.permissions:
            raise HTTPException(403, "Permission denied")
        if ticket.status in {TicketStatus.CLOSED, TicketStatus.CANCELLED}:
            raise HTTPException(409, "Closed or cancelled tickets cannot be assigned")
        team = await self.repository.active_team(team_id)
        if team is None:
            raise HTTPException(422, "Assignment team does not exist or is inactive")
        if "ticket:view_all" not in access.permissions and team_id not in access.team_ids:
            raise HTTPException(403, "Technicians can assign only to their active teams")
        if (
            technician_id
            and await self.repository.eligible_technician(team_id, technician_id) is None
        ):
            raise HTTPException(422, "Technician is not an active eligible team member")
        if ticket.assignment_team_id == team_id and ticket.assigned_technician_id == technician_id:
            return ticket
        before = ticket_state(ticket)
        now = utc_now()
        active = await self.repository.active_assignment(ticket.id)
        if active:
            active.ended_at = now
        ticket.assignment_team_id = team_id
        ticket.assigned_technician_id = technician_id
        self.session.add(
            TicketAssignment(
                ticket_id=ticket.id,
                team_id=team_id,
                technician_id=technician_id,
                assigned_by_id=actor_id,
                reason=reason,
                started_at=now,
            )
        )
        self._event(
            ticket.id,
            actor_id,
            "ticket.assigned" if active is None else "ticket.reassigned",
            before,
            ticket_state(ticket),
            reason,
            request_id,
        )
        await self._commit("Ticket assignment conflicted with another update")
        return ticket

    async def transition(
        self,
        actor_id: UUID,
        ticket_id: UUID,
        target: TicketStatus,
        reason: str,
        request_id: str,
        resolution_summary: str | None,
        resolution_code: str | None,
    ) -> Ticket:
        access = await self.access(actor_id)
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        record = await self.repository.visible_ticket(ticket_id, access, for_update=True)
        if record is None:
            raise HTTPException(404, "Ticket not found")
        ticket = record.ticket
        current = TicketStatus(ticket.status)
        required = transition_permission(current, target)
        if required not in access.permissions:
            raise HTTPException(403, "Permission denied")
        if target not in LEGAL_TRANSITIONS[current]:
            raise HTTPException(409, f"Transition from {current} to {target} is not allowed")
        if (
            target not in {TicketStatus.CANCELLED, TicketStatus.OPEN}
            and not ticket.assignment_team_id
        ):
            raise HTTPException(409, "Assign the ticket before advancing its workflow")
        if target == TicketStatus.RESOLVED and not (
            resolution_summary
            and resolution_summary.strip()
            and resolution_code
            and resolution_code.strip()
        ):
            raise HTTPException(422, "Resolution summary and code are required")
        before = ticket_state(ticket)
        now = utc_now()
        ticket.status = target
        if target == TicketStatus.RESOLVED:
            ticket.resolved_at = now
            ticket.resolution_summary = resolution_summary
            ticket.resolution_code = resolution_code
        elif target == TicketStatus.CLOSED:
            ticket.closed_at = now
        elif current == TicketStatus.RESOLVED and target == TicketStatus.OPEN:
            ticket.reopened_at = now
            ticket.resolved_at = None
            ticket.closed_at = None
            ticket.resolution_summary = None
            ticket.resolution_code = None
        from app.modules.sla.service import SlaService

        await SlaService(self.session).on_transition(ticket.id, current, target, now)
        self._event(
            ticket.id,
            actor_id,
            "ticket.status_changed",
            before,
            ticket_state(ticket),
            reason,
            request_id,
        )
        await self._commit("Ticket status conflicted with another update")
        return ticket

    async def add_comment(
        self,
        actor_id: UUID,
        ticket_id: UUID,
        body: str,
        visibility: CommentVisibility,
        request_id: str,
    ) -> TicketComment:
        record, access = await self._visible(
            actor_id, ticket_id, required="ticket:comment", lock=True
        )
        if (
            visibility == CommentVisibility.INTERNAL
            and "ticket:internal_note" not in access.permissions
        ):
            raise HTTPException(403, "Permission denied")
        if record.ticket.status in {TicketStatus.CLOSED, TicketStatus.CANCELLED}:
            raise HTTPException(409, "Closed or cancelled tickets cannot receive comments")
        comment = TicketComment(
            ticket_id=ticket_id,
            author_id=actor_id,
            body=body,
            visibility=visibility,
        )
        self.session.add(comment)
        if (
            actor_id != record.ticket.requester_id
            and visibility == CommentVisibility.PUBLIC
            and record.ticket.first_response_at is None
        ):
            responded_at = utc_now()
            record.ticket.first_response_at = responded_at
            from app.modules.sla.service import SlaService

            await SlaService(self.session).on_first_response(ticket_id, responded_at)
        await self.session.flush()
        self._event(
            ticket_id,
            actor_id,
            "ticket.comment_added",
            None,
            {"comment_id": str(comment.id), "visibility": visibility},
            "Comment added",
            request_id,
        )
        await self._commit("Comment could not be added")
        return comment

    async def list_comments(
        self, actor_id: UUID, ticket_id: UUID, offset: int, limit: int
    ) -> tuple[list[CommentRecord], int]:
        _, access = await self._visible(actor_id, ticket_id)
        return await self.repository.comments(
            ticket_id,
            include_internal="ticket:internal_note" in access.permissions,
            offset=offset,
            limit=limit,
        )

    async def list_events(
        self, actor_id: UUID, ticket_id: UUID, offset: int, limit: int
    ) -> tuple[list[EventRecord], int]:
        await self._visible(actor_id, ticket_id)
        return await self.repository.events(ticket_id, offset=offset, limit=limit)

    async def list_attachments(self, actor_id: UUID, ticket_id: UUID) -> list[AttachmentRecord]:
        await self._visible(actor_id, ticket_id)
        return await self.repository.attachments(ticket_id)

    async def add_attachment(
        self,
        actor_id: UUID,
        ticket_id: UUID,
        filename: str,
        content_type: str,
        data: bytes,
        storage: LocalAttachmentStorage,
        max_bytes: int,
        request_id: str,
        scanner: AttachmentScanner | None = None,
    ) -> TicketAttachment:
        ticket_record, _ = await self._visible(
            actor_id, ticket_id, required="ticket:comment", lock=True
        )
        if ticket_record.ticket.status in {TicketStatus.CLOSED, TicketStatus.CANCELLED}:
            raise HTTPException(409, "Closed or cancelled tickets cannot receive attachments")
        try:
            clean_name = validate_attachment(filename, content_type, data, max_bytes)
        except AttachmentValidationError as exc:
            raise HTTPException(422, str(exc)) from None
        if scanner is not None:
            try:
                await scanner.scan(data)
            except AttachmentMalwareDetected as exc:
                raise HTTPException(422, str(exc)) from None
            except AttachmentScanError as exc:
                raise HTTPException(503, str(exc)) from None
        normalized_type = content_type.split(";", 1)[0].strip().lower()
        storage_key = storage.new_key(Path(clean_name).suffix)
        await storage.put(storage_key, data)
        record = TicketAttachment(
            ticket_id=ticket_id,
            uploader_id=actor_id,
            original_name=clean_name,
            storage_key=storage_key,
            content_type=normalized_type,
            size_bytes=len(data),
            sha256=sha256(data).hexdigest(),
        )
        self.session.add(record)
        try:
            await self.session.flush()
            self._event(
                ticket_id,
                actor_id,
                "ticket.attachment_added",
                None,
                {
                    "attachment_id": str(record.id),
                    "content_type": normalized_type,
                    "size_bytes": len(data),
                },
                "Attachment added",
                request_id,
            )
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            await storage.delete(storage_key)
            raise
        return record

    async def download_attachment(
        self, actor_id: UUID, ticket_id: UUID, attachment_id: UUID
    ) -> TicketAttachment:
        await self._visible(actor_id, ticket_id)
        record = await self.repository.attachment(ticket_id, attachment_id)
        if record is None:
            raise HTTPException(404, "Attachment not found")
        return record
