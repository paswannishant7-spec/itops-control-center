from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.models import UserRole
from app.modules.directory.models import Department, Location, Team, TeamMember
from app.modules.identity.models import User, UserStatus


@dataclass(frozen=True)
class ReferenceRecord:
    record: Department | Location
    user_count: int
    team_count: int


@dataclass(frozen=True)
class UserRecord:
    user: User
    department: Department | None
    location: Location | None
    roles: tuple[str, ...]
    teams: tuple[Team, ...]


@dataclass(frozen=True)
class TeamRecord:
    team: Team
    department: Department | None
    location: Location | None
    member_count: int


@dataclass(frozen=True)
class MemberRecord:
    membership: TeamMember
    user: User
    roles: tuple[str, ...]


class DirectoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def department(self, record_id: UUID, *, for_update: bool = False) -> Department | None:
        statement = select(Department).where(Department.id == record_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Department | None, await self.session.scalar(statement))

    async def location(self, record_id: UUID, *, for_update: bool = False) -> Location | None:
        statement = select(Location).where(Location.id == record_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Location | None, await self.session.scalar(statement))

    async def team(self, record_id: UUID, *, for_update: bool = False) -> Team | None:
        statement = select(Team).where(Team.id == record_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Team | None, await self.session.scalar(statement))

    async def user(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(User | None, await self.session.scalar(statement))

    async def references(self, kind: str) -> list[ReferenceRecord]:
        model = Department if kind == "department" else Location
        user_fk = User.department_id if kind == "department" else User.location_id
        team_fk = Team.department_id if kind == "department" else Team.location_id
        user_count = (
            select(func.count(User.id))
            .where(user_fk == model.id)
            .correlate(model)
            .scalar_subquery()
        )
        team_count = (
            select(func.count(Team.id))
            .where(team_fk == model.id)
            .correlate(model)
            .scalar_subquery()
        )
        rows = (
            await self.session.execute(
                select(model, user_count, team_count).order_by(model.status, model.name, model.id)
            )
        ).all()
        return [ReferenceRecord(row[0], int(row[1]), int(row[2])) for row in rows]

    async def reference_record(self, kind: str, record_id: UUID) -> ReferenceRecord | None:
        model = Department if kind == "department" else Location
        user_fk = User.department_id if kind == "department" else User.location_id
        team_fk = Team.department_id if kind == "department" else Team.location_id
        user_count = (
            select(func.count(User.id))
            .where(user_fk == model.id)
            .correlate(model)
            .scalar_subquery()
        )
        team_count = (
            select(func.count(Team.id))
            .where(team_fk == model.id)
            .correlate(model)
            .scalar_subquery()
        )
        row = (
            await self.session.execute(
                select(model, user_count, team_count).where(model.id == record_id)
            )
        ).one_or_none()
        return ReferenceRecord(row[0], int(row[1]), int(row[2])) if row else None

    async def teams(self) -> list[TeamRecord]:
        member_count = (
            select(func.count(TeamMember.id))
            .where(TeamMember.team_id == Team.id, TeamMember.ended_at.is_(None))
            .correlate(Team)
            .scalar_subquery()
        )
        rows = (
            await self.session.execute(
                select(Team, Department, Location, member_count)
                .outerjoin(Department, Department.id == Team.department_id)
                .outerjoin(Location, Location.id == Team.location_id)
                .order_by(Team.status, Team.name, Team.id)
            )
        ).all()
        return [TeamRecord(row[0], row[1], row[2], int(row[3])) for row in rows]

    async def team_record(self, team_id: UUID) -> TeamRecord | None:
        member_count = (
            select(func.count(TeamMember.id))
            .where(TeamMember.team_id == Team.id, TeamMember.ended_at.is_(None))
            .correlate(Team)
            .scalar_subquery()
        )
        row = (
            await self.session.execute(
                select(Team, Department, Location, member_count)
                .outerjoin(Department, Department.id == Team.department_id)
                .outerjoin(Location, Location.id == Team.location_id)
                .where(Team.id == team_id)
            )
        ).one_or_none()
        return TeamRecord(row[0], row[1], row[2], int(row[3])) if row else None

    async def active_members(self, team_id: UUID) -> list[MemberRecord]:
        rows = (
            await self.session.execute(
                select(TeamMember, User)
                .join(User, User.id == TeamMember.user_id)
                .where(TeamMember.team_id == team_id, TeamMember.ended_at.is_(None))
                .order_by(User.display_name, User.email, User.id)
            )
        ).all()
        roles = await self._roles([row[1].id for row in rows])
        return [MemberRecord(row[0], row[1], roles.get(row[1].id, ())) for row in rows]

    async def active_membership(
        self, team_id: UUID, user_id: UUID, *, for_update: bool = False
    ) -> TeamMember | None:
        statement = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
            TeamMember.ended_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return cast(TeamMember | None, await self.session.scalar(statement))

    async def active_memberships_for_team(
        self, team_id: UUID, *, for_update: bool = False
    ) -> list[TeamMember]:
        statement = select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.ended_at.is_(None)
        )
        if for_update:
            statement = statement.order_by(TeamMember.user_id).with_for_update()
        return list(await self.session.scalars(statement))

    async def active_memberships_for_user(
        self, user_id: UUID, *, for_update: bool = False
    ) -> list[TeamMember]:
        statement = select(TeamMember).where(
            TeamMember.user_id == user_id, TeamMember.ended_at.is_(None)
        )
        if for_update:
            statement = statement.order_by(TeamMember.team_id).with_for_update()
        return list(await self.session.scalars(statement))

    async def reference_has_active_assignments(self, kind: str, record_id: UUID) -> bool:
        user_fk = User.department_id if kind == "department" else User.location_id
        team_fk = Team.department_id if kind == "department" else Team.location_id
        active_user = await self.session.scalar(
            select(User.id).where(user_fk == record_id, User.status == UserStatus.ACTIVE).limit(1)
        )
        active_team = await self.session.scalar(
            select(Team.id).where(team_fk == record_id, Team.status == "ACTIVE").limit(1)
        )
        return active_user is not None or active_team is not None

    async def active_team_ids(self, user_id: UUID) -> frozenset[UUID]:
        qualified = exists(
            select(UserRole.user_id).where(
                UserRole.user_id == user_id,
                UserRole.role_code.in_(("TECHNICIAN", "IT_MANAGER")),
            )
        )
        ids = await self.session.scalars(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .join(User, User.id == TeamMember.user_id)
            .where(
                TeamMember.user_id == user_id,
                TeamMember.ended_at.is_(None),
                Team.status == "ACTIVE",
                User.status == UserStatus.ACTIVE,
                qualified,
            )
            .order_by(TeamMember.team_id)
        )
        return frozenset(ids)

    async def eligible_technicians(
        self, team_id: UUID, search: str | None, limit: int
    ) -> list[UserRecord]:
        qualified = exists(
            select(UserRole.user_id).where(
                UserRole.user_id == User.id,
                UserRole.role_code.in_(("TECHNICIAN", "IT_MANAGER")),
            )
        )
        already_member = exists(
            select(TeamMember.id).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == User.id,
                TeamMember.ended_at.is_(None),
            )
        )
        statement = (
            select(User, Department, Location)
            .outerjoin(Department, Department.id == User.department_id)
            .outerjoin(Location, Location.id == User.location_id)
            .where(User.status == UserStatus.ACTIVE, qualified, ~already_member)
            .order_by(User.display_name, User.email, User.id)
            .limit(limit)
        )
        if search:
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(User.display_name).like(term),
                    func.lower(User.email).like(term),
                    func.lower(User.employee_number).like(term),
                )
            )
        rows = (await self.session.execute(statement)).all()
        roles = await self._roles([row[0].id for row in rows])
        return [UserRecord(row[0], row[1], row[2], roles.get(row[0].id, ()), ()) for row in rows]

    async def users(
        self,
        *,
        search: str | None,
        status: str | None,
        department_id: UUID | None,
        location_id: UUID | None,
        role: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[UserRecord], int]:
        criteria = []
        if search:
            term = f"%{search.strip().lower()}%"
            criteria.append(
                or_(
                    func.lower(User.display_name).like(term),
                    func.lower(User.email).like(term),
                    func.lower(User.employee_number).like(term),
                )
            )
        if status:
            criteria.append(User.status == status)
        if department_id:
            criteria.append(User.department_id == department_id)
        if location_id:
            criteria.append(User.location_id == location_id)
        if role:
            criteria.append(
                exists(
                    select(UserRole.user_id).where(
                        UserRole.user_id == User.id, UserRole.role_code == role
                    )
                )
            )
        total = int(await self.session.scalar(select(func.count(User.id)).where(*criteria)) or 0)
        statement = (
            select(User, Department, Location)
            .outerjoin(Department, Department.id == User.department_id)
            .outerjoin(Location, Location.id == User.location_id)
            .where(*criteria)
            .order_by(User.display_name, User.email, User.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).all()
        user_ids = [row[0].id for row in rows]
        roles, teams = await self._roles(user_ids), await self._teams(user_ids)
        return (
            [
                UserRecord(
                    row[0],
                    row[1],
                    row[2],
                    roles.get(row[0].id, ()),
                    teams.get(row[0].id, ()),
                )
                for row in rows
            ],
            total,
        )

    async def user_record(self, user_id: UUID) -> UserRecord | None:
        row = (
            await self.session.execute(
                select(User, Department, Location)
                .outerjoin(Department, Department.id == User.department_id)
                .outerjoin(Location, Location.id == User.location_id)
                .where(User.id == user_id)
            )
        ).one_or_none()
        if not row:
            return None
        roles, teams = await self._roles([user_id]), await self._teams([user_id])
        return UserRecord(row[0], row[1], row[2], roles.get(user_id, ()), teams.get(user_id, ()))

    async def _roles(self, user_ids: list[UUID]) -> dict[UUID, tuple[str, ...]]:
        if not user_ids:
            return {}
        rows = (
            await self.session.execute(
                select(UserRole.user_id, UserRole.role_code)
                .where(UserRole.user_id.in_(user_ids))
                .order_by(UserRole.user_id, UserRole.role_code)
            )
        ).all()
        result: dict[UUID, list[str]] = {}
        for user_id, code in rows:
            result.setdefault(user_id, []).append(code)
        return {key: tuple(value) for key, value in result.items()}

    async def _teams(self, user_ids: list[UUID]) -> dict[UUID, tuple[Team, ...]]:
        if not user_ids:
            return {}
        rows = (
            await self.session.execute(
                select(TeamMember.user_id, Team)
                .join(Team, Team.id == TeamMember.team_id)
                .where(TeamMember.user_id.in_(user_ids), TeamMember.ended_at.is_(None))
                .order_by(TeamMember.user_id, Team.name, Team.id)
            )
        ).all()
        result: dict[UUID, list[Team]] = {}
        for user_id, team in rows:
            result.setdefault(user_id, []).append(team)
        return {key: tuple(value) for key, value in result.items()}
