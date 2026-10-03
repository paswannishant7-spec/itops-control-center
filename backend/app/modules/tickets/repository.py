from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, Select, false, func, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.directory.models import Department, Location, Team
from app.modules.identity.models import User
from app.modules.sla.models import SlaInstance
from app.modules.tickets.models import (
    Ticket,
    TicketAssignment,
    TicketAttachment,
    TicketCategory,
    TicketComment,
    TicketEvent,
    TicketSubcategory,
)


@dataclass(frozen=True)
class TicketAccess:
    user_id: UUID
    permissions: frozenset[str]
    team_ids: frozenset[UUID]
    team_department_ids: frozenset[UUID]

    @property
    def can_view_any(self) -> bool:
        return bool(self.permissions & {"ticket:view_own", "ticket:view_team", "ticket:view_all"})


@dataclass(frozen=True)
class TicketRecord:
    ticket: Ticket
    requester: User
    department: Department | None
    location: Location | None
    team: Team | None
    technician: User | None
    category: TicketCategory | None
    subcategory: TicketSubcategory | None
    sla_instance: SlaInstance | None


@dataclass(frozen=True)
class CommentRecord:
    comment: TicketComment
    author: User


@dataclass(frozen=True)
class AttachmentRecord:
    attachment: TicketAttachment
    uploader: User


@dataclass(frozen=True)
class EventRecord:
    event: TicketEvent
    actor: User


type TicketRow = tuple[
    Ticket,
    User,
    Department,
    Location,
    Team,
    User,
    TicketCategory,
    TicketSubcategory,
    SlaInstance,
]


class TicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def access_predicate(self, access: TicketAccess) -> ColumnElement[bool]:
        predicates: list[ColumnElement[bool]] = []
        if "ticket:view_all" in access.permissions:
            return Ticket.id.is_not(None)
        if "ticket:view_own" in access.permissions:
            predicates.append(Ticket.requester_id == access.user_id)
        if "ticket:view_team" in access.permissions:
            predicates.append(Ticket.assigned_technician_id == access.user_id)
            if access.team_ids:
                predicates.append(Ticket.assignment_team_id.in_(access.team_ids))
            if access.team_department_ids:
                predicates.append(
                    Ticket.assignment_team_id.is_(None)
                    & Ticket.department_id.in_(access.team_department_ids)
                )
        return or_(*predicates) if predicates else false()

    def _record_statement(self) -> Select[TicketRow]:
        requester = aliased(User, name="requester")
        technician = aliased(User, name="technician")
        return (
            select(
                Ticket,
                requester,
                Department,
                Location,
                Team,
                technician,
                TicketCategory,
                TicketSubcategory,
                SlaInstance,
            )
            .join(requester, requester.id == Ticket.requester_id)
            .outerjoin(Department, Department.id == Ticket.department_id)
            .outerjoin(Location, Location.id == Ticket.location_id)
            .outerjoin(Team, Team.id == Ticket.assignment_team_id)
            .outerjoin(technician, technician.id == Ticket.assigned_technician_id)
            .outerjoin(TicketCategory, TicketCategory.id == Ticket.category_id)
            .outerjoin(TicketSubcategory, TicketSubcategory.id == Ticket.subcategory_id)
            .outerjoin(SlaInstance, SlaInstance.ticket_id == Ticket.id)
        )

    @staticmethod
    def _record(row: Row[TicketRow]) -> TicketRecord:
        return TicketRecord(
            ticket=row[0],
            requester=row[1],
            department=row[2],
            location=row[3],
            team=row[4],
            technician=row[5],
            category=row[6],
            subcategory=row[7],
            sla_instance=row[8],
        )

    async def visible_ticket(
        self, ticket_id: UUID, access: TicketAccess, *, for_update: bool = False
    ) -> TicketRecord | None:
        statement = self._record_statement().where(
            Ticket.id == ticket_id, self.access_predicate(access)
        )
        if for_update:
            statement = statement.with_for_update(of=Ticket)
        row = (await self.session.execute(statement)).one_or_none()
        return self._record(row) if row else None

    async def tickets(
        self,
        access: TicketAccess,
        *,
        search: str | None,
        status: str | None,
        priority: str | None,
        sla_state: str | None,
        team_id: UUID | None,
        technician_id: UUID | None,
        department_id: UUID | None,
        asset_id: UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[TicketRecord], int]:
        criteria: list[ColumnElement[bool]] = [self.access_predicate(access)]
        if search:
            term = f"%{search.strip()}%"
            criteria.append(
                or_(
                    Ticket.reference.ilike(term),
                    Ticket.title.ilike(term),
                    Ticket.description.ilike(term),
                )
            )
        if status:
            criteria.append(Ticket.status == status)
        if priority:
            criteria.append(Ticket.priority == priority)
        if sla_state:
            criteria.append(SlaInstance.state == sla_state)
        if team_id:
            criteria.append(Ticket.assignment_team_id == team_id)
        if technician_id:
            criteria.append(Ticket.assigned_technician_id == technician_id)
        if department_id:
            criteria.append(Ticket.department_id == department_id)
        if asset_id:
            criteria.append(Ticket.asset_id == asset_id)
        if created_from:
            criteria.append(Ticket.created_at >= created_from)
        if created_to:
            criteria.append(Ticket.created_at <= created_to)
        total = int(
            cast(
                int | None,
                await self.session.scalar(
                    select(func.count())
                    .select_from(Ticket)
                    .outerjoin(SlaInstance, SlaInstance.ticket_id == Ticket.id)
                    .where(*criteria)
                ),
            )
            or 0
        )
        rows = (
            await self.session.execute(
                self._record_statement()
                .where(*criteria)
                .order_by(Ticket.updated_at.desc(), Ticket.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [self._record(row) for row in rows], total

    async def team_departments(self, team_ids: frozenset[UUID]) -> frozenset[UUID]:
        if not team_ids:
            return frozenset()
        values = await self.session.scalars(
            select(Team.department_id).where(Team.id.in_(team_ids), Team.department_id.is_not(None))
        )
        return frozenset(value for value in values if value is not None)

    async def active_team(self, team_id: UUID) -> Team | None:
        return cast(
            Team | None,
            await self.session.scalar(
                select(Team).where(Team.id == team_id, Team.status == "ACTIVE").with_for_update()
            ),
        )

    async def eligible_technician(self, team_id: UUID, user_id: UUID) -> User | None:
        from app.modules.access.models import UserRole
        from app.modules.directory.models import TeamMember
        from app.modules.identity.models import UserStatus

        return cast(
            User | None,
            await self.session.scalar(
                select(User)
                .join(TeamMember, TeamMember.user_id == User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .where(
                    User.id == user_id,
                    User.status == UserStatus.ACTIVE,
                    TeamMember.team_id == team_id,
                    TeamMember.ended_at.is_(None),
                    UserRole.role_code.in_(("TECHNICIAN", "IT_MANAGER")),
                )
                .with_for_update()
            ),
        )

    async def active_assignment(self, ticket_id: UUID) -> TicketAssignment | None:
        return cast(
            TicketAssignment | None,
            await self.session.scalar(
                select(TicketAssignment)
                .where(
                    TicketAssignment.ticket_id == ticket_id,
                    TicketAssignment.ended_at.is_(None),
                )
                .with_for_update()
            ),
        )

    async def category_pair(
        self, category_id: UUID | None, subcategory_id: UUID | None
    ) -> tuple[TicketCategory | None, TicketSubcategory | None]:
        category = (
            await self.session.scalar(
                select(TicketCategory).where(
                    TicketCategory.id == category_id, TicketCategory.is_active.is_(True)
                )
            )
            if category_id
            else None
        )
        subcategory = (
            await self.session.scalar(
                select(TicketSubcategory).where(
                    TicketSubcategory.id == subcategory_id,
                    TicketSubcategory.is_active.is_(True),
                )
            )
            if subcategory_id
            else None
        )
        return category, subcategory

    async def categories(self) -> list[tuple[TicketCategory, list[TicketSubcategory]]]:
        categories = list(
            await self.session.scalars(
                select(TicketCategory)
                .where(TicketCategory.is_active.is_(True))
                .order_by(TicketCategory.name, TicketCategory.id)
            )
        )
        subcategories: list[TicketSubcategory] = (
            list(
                await self.session.scalars(
                    select(TicketSubcategory)
                    .where(
                        TicketSubcategory.is_active.is_(True),
                        TicketSubcategory.category_id.in_([item.id for item in categories]),
                    )
                    .order_by(TicketSubcategory.name, TicketSubcategory.id)
                )
            )
            if categories
            else []
        )
        grouped: dict[UUID, list[TicketSubcategory]] = {}
        for item in subcategories:
            grouped.setdefault(item.category_id, []).append(item)
        return [(item, grouped.get(item.id, [])) for item in categories]

    async def comments(
        self, ticket_id: UUID, *, include_internal: bool, offset: int, limit: int
    ) -> tuple[list[CommentRecord], int]:
        criteria = [TicketComment.ticket_id == ticket_id]
        if not include_internal:
            criteria.append(TicketComment.visibility == "PUBLIC")
        total = int(
            await self.session.scalar(select(func.count(TicketComment.id)).where(*criteria)) or 0
        )
        rows = (
            await self.session.execute(
                select(TicketComment, User)
                .join(User, User.id == TicketComment.author_id)
                .where(*criteria)
                .order_by(TicketComment.created_at, TicketComment.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [CommentRecord(row[0], row[1]) for row in rows], total

    async def attachments(self, ticket_id: UUID) -> list[AttachmentRecord]:
        rows = (
            await self.session.execute(
                select(TicketAttachment, User)
                .join(User, User.id == TicketAttachment.uploader_id)
                .where(TicketAttachment.ticket_id == ticket_id)
                .order_by(TicketAttachment.created_at, TicketAttachment.id)
            )
        ).all()
        return [AttachmentRecord(row[0], row[1]) for row in rows]

    async def attachment(self, ticket_id: UUID, attachment_id: UUID) -> TicketAttachment | None:
        return cast(
            TicketAttachment | None,
            await self.session.scalar(
                select(TicketAttachment).where(
                    TicketAttachment.id == attachment_id,
                    TicketAttachment.ticket_id == ticket_id,
                )
            ),
        )

    async def events(
        self, ticket_id: UUID, *, offset: int, limit: int
    ) -> tuple[list[EventRecord], int]:
        total = int(
            await self.session.scalar(
                select(func.count(TicketEvent.id)).where(TicketEvent.ticket_id == ticket_id)
            )
            or 0
        )
        rows = (
            await self.session.execute(
                select(TicketEvent, User)
                .join(User, User.id == TicketEvent.actor_id)
                .where(TicketEvent.ticket_id == ticket_id)
                .order_by(TicketEvent.created_at, TicketEvent.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [EventRecord(row[0], row[1]) for row in rows], total
