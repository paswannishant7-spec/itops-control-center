from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import ColumnElement, Select, false, func, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.assets.models import Asset, AssetAssignment, AssetEvent
from app.modules.directory.models import Department, Location, Team
from app.modules.identity.models import User
from app.modules.tickets.models import Ticket


@dataclass(frozen=True)
class AssetAccess:
    user_id: UUID
    permissions: frozenset[str]
    team_department_ids: frozenset[UUID]

    @property
    def can_view_any(self) -> bool:
        return bool(self.permissions & {"asset:view_own", "asset:view_team", "asset:view_all"})


@dataclass(frozen=True)
class AssetRecord:
    asset: Asset
    owner: User | None
    department: Department | None
    location: Location | None


@dataclass(frozen=True)
class AssignmentRecord:
    assignment: AssetAssignment
    owner: User | None
    department: Department | None
    location: Location | None
    assigned_by: User


@dataclass(frozen=True)
class EventRecord:
    event: AssetEvent
    actor: User


type AssetRow = tuple[Asset, User, Department, Location]


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def access_predicate(self, access: AssetAccess) -> ColumnElement[bool]:
        if "asset:view_all" in access.permissions:
            return Asset.id.is_not(None)
        predicates: list[ColumnElement[bool]] = []
        if "asset:view_own" in access.permissions:
            predicates.append(Asset.owner_id == access.user_id)
        if "asset:view_team" in access.permissions and access.team_department_ids:
            predicates.append(Asset.department_id.in_(access.team_department_ids))
        return or_(*predicates) if predicates else false()

    def _record_statement(self) -> Select[AssetRow]:
        return (
            select(Asset, User, Department, Location)
            .outerjoin(User, User.id == Asset.owner_id)
            .outerjoin(Department, Department.id == Asset.department_id)
            .outerjoin(Location, Location.id == Asset.location_id)
        )

    @staticmethod
    def _record(row: Row[AssetRow]) -> AssetRecord:
        return AssetRecord(row[0], row[1], row[2], row[3])

    async def assets(
        self,
        access: AssetAccess,
        *,
        search: str | None,
        asset_type: str | None,
        status: str | None,
        health_status: str | None,
        owner_id: UUID | None,
        department_id: UUID | None,
        location_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AssetRecord], int]:
        criteria: list[ColumnElement[bool]] = [self.access_predicate(access)]
        if search:
            term = f"%{search.strip()}%"
            criteria.append(
                or_(
                    Asset.asset_tag.ilike(term),
                    Asset.serial_number.ilike(term),
                    Asset.hostname.ilike(term),
                    Asset.manufacturer.ilike(term),
                    Asset.model.ilike(term),
                )
            )
        for value, column in (
            (asset_type, Asset.asset_type),
            (status, Asset.status),
            (health_status, Asset.health_status),
            (owner_id, Asset.owner_id),
            (department_id, Asset.department_id),
            (location_id, Asset.location_id),
        ):
            if value is not None:
                criteria.append(column == value)
        total = int(
            cast(
                int | None,
                await self.session.scalar(select(func.count()).select_from(Asset).where(*criteria)),
            )
            or 0
        )
        rows = (
            await self.session.execute(
                self._record_statement()
                .where(*criteria)
                .order_by(Asset.asset_tag, Asset.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [self._record(row) for row in rows], total

    async def visible_asset(
        self, asset_id: UUID, access: AssetAccess, *, for_update: bool = False
    ) -> AssetRecord | None:
        statement = self._record_statement().where(
            Asset.id == asset_id, self.access_predicate(access)
        )
        if for_update:
            statement = statement.with_for_update(of=Asset)
        row = (await self.session.execute(statement)).one_or_none()
        return self._record(row) if row else None

    async def asset(self, asset_id: UUID, *, for_update: bool = False) -> Asset | None:
        statement = select(Asset).where(Asset.id == asset_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Asset | None, await self.session.scalar(statement))

    async def team_departments(self, team_ids: frozenset[UUID]) -> frozenset[UUID]:
        if not team_ids:
            return frozenset()
        values = await self.session.scalars(
            select(Team.department_id).where(
                Team.id.in_(team_ids), Team.department_id.is_not(None), Team.status == "ACTIVE"
            )
        )
        return frozenset(value for value in values if value is not None)

    async def active_assignment(self, asset_id: UUID) -> AssetAssignment | None:
        return cast(
            AssetAssignment | None,
            await self.session.scalar(
                select(AssetAssignment)
                .where(AssetAssignment.asset_id == asset_id, AssetAssignment.ended_at.is_(None))
                .with_for_update()
            ),
        )

    async def assignments(self, asset_id: UUID) -> list[AssignmentRecord]:
        owner = aliased(User, name="asset_owner")
        assigned_by = aliased(User, name="asset_assigner")
        rows = (
            await self.session.execute(
                select(AssetAssignment, owner, Department, Location, assigned_by)
                .outerjoin(owner, owner.id == AssetAssignment.owner_id)
                .outerjoin(Department, Department.id == AssetAssignment.department_id)
                .outerjoin(Location, Location.id == AssetAssignment.location_id)
                .join(assigned_by, assigned_by.id == AssetAssignment.assigned_by_id)
                .where(AssetAssignment.asset_id == asset_id)
                .order_by(AssetAssignment.started_at.desc(), AssetAssignment.id.desc())
            )
        ).all()
        return [AssignmentRecord(row[0], row[1], row[2], row[3], row[4]) for row in rows]

    async def events(self, asset_id: UUID) -> list[EventRecord]:
        rows = (
            await self.session.execute(
                select(AssetEvent, User)
                .join(User, User.id == AssetEvent.actor_id)
                .where(AssetEvent.asset_id == asset_id)
                .order_by(AssetEvent.created_at.desc(), AssetEvent.id.desc())
            )
        ).all()
        return [EventRecord(row[0], row[1]) for row in rows]

    async def tickets(self, asset_id: UUID, access: object) -> list[Ticket]:
        from app.modules.tickets.repository import TicketAccess, TicketRepository

        assert isinstance(access, TicketAccess)
        repository = TicketRepository(self.session)
        values, _ = await repository.tickets(
            access,
            search=None,
            status=None,
            priority=None,
            sla_state=None,
            team_id=None,
            technician_id=None,
            department_id=None,
            asset_id=asset_id,
            created_from=None,
            created_to=None,
            offset=0,
            limit=100,
        )
        return [value.ticket for value in values]
