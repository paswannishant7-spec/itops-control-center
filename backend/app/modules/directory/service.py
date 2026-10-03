from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.models import RoleAssignmentEvent, UserRole
from app.modules.access.repository import AccessRepository
from app.modules.access.service import AccessService
from app.modules.directory.models import (
    Department,
    DirectoryEvent,
    DirectoryStatus,
    Location,
    Team,
    TeamMember,
)
from app.modules.directory.repository import DirectoryRepository
from app.modules.identity.models import User, UserStatus
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.security import PasswordPolicyError, PasswordService


def utc_now() -> datetime:
    return datetime.now(UTC)


def reference_state(record: Department | Location) -> dict[str, object]:
    state: dict[str, object] = {
        "code": record.code,
        "name": record.name,
        "description": record.description if isinstance(record, Department) else None,
        "status": record.status,
    }
    if isinstance(record, Location):
        state.pop("description")
        state.update({"timezone": record.timezone, "address": record.address})
    return state


def team_state(record: Team) -> dict[str, object]:
    return {
        "code": record.code,
        "name": record.name,
        "description": record.description,
        "status": record.status,
        "department_id": str(record.department_id) if record.department_id else None,
        "location_id": str(record.location_id) if record.location_id else None,
    }


def user_state(record: User, roles: list[str] | tuple[str, ...] = ()) -> dict[str, object]:
    return {
        "email": record.email,
        "display_name": record.display_name,
        "employee_number": record.employee_number,
        "job_title": record.job_title,
        "status": record.status,
        "department_id": str(record.department_id) if record.department_id else None,
        "location_id": str(record.location_id) if record.location_id else None,
        "roles": list(roles),
    }


class DirectoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DirectoryRepository(session)
        self.access = AccessService(session)

    def _event(
        self,
        actor_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
        reason: str,
        request_id: str,
    ) -> None:
        self.session.add(
            DirectoryEvent(
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before_state=before,
                after_state=after,
                reason=reason,
                request_id=request_id[:128],
            )
        )

    async def _commit(self, conflict: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, conflict) from None

    async def _flush(self, conflict: str) -> None:
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, conflict) from None

    async def _active_references(
        self, department_id: UUID | None, location_id: UUID | None
    ) -> None:
        if department_id:
            department = await self.repository.department(department_id, for_update=True)
            if department is None:
                raise HTTPException(422, "Department does not exist")
            if department.status != DirectoryStatus.ACTIVE:
                raise HTTPException(409, "Department is inactive")
        if location_id:
            location = await self.repository.location(location_id, for_update=True)
            if location is None:
                raise HTTPException(422, "Location does not exist")
            if location.status != DirectoryStatus.ACTIVE:
                raise HTTPException(409, "Location is inactive")

    async def create_department(
        self, actor_id: UUID, values: dict[str, object], reason: str, request_id: str
    ) -> Department:
        await self.access.lock_and_require(actor_id, "department:manage")
        record = Department(id=uuid4(), **values)
        self.session.add(record)
        await self._flush("A department with that code or name already exists")
        self._event(
            actor_id,
            "department.created",
            "department",
            record.id,
            None,
            reference_state(record),
            reason,
            request_id,
        )
        await self._commit("A department with that code or name already exists")
        return record

    async def update_department(
        self,
        actor_id: UUID,
        record_id: UUID,
        values: dict[str, object],
        reason: str,
        request_id: str,
    ) -> Department:
        await self.access.lock_and_require(actor_id, "department:manage")
        record = await self.repository.department(record_id, for_update=True)
        if record is None:
            raise HTTPException(404, "Department not found")
        before = reference_state(record)
        if (
            values.get("status") == DirectoryStatus.INACTIVE
            and record.status != DirectoryStatus.INACTIVE
            and await self.repository.reference_has_active_assignments("department", record.id)
        ):
            raise HTTPException(409, "Reassign active users and teams before deactivation")
        for key, value in values.items():
            setattr(record, key, value)
        after = reference_state(record)
        if before == after:
            return record
        self._event(
            actor_id,
            "department.updated",
            "department",
            record.id,
            before,
            after,
            reason,
            request_id,
        )
        await self._commit("A department with that name already exists")
        return record

    async def create_location(
        self, actor_id: UUID, values: dict[str, object], reason: str, request_id: str
    ) -> Location:
        await self.access.lock_and_require(actor_id, "location:manage")
        record = Location(id=uuid4(), **values)
        self.session.add(record)
        await self._flush("A location with that code or name already exists")
        self._event(
            actor_id,
            "location.created",
            "location",
            record.id,
            None,
            reference_state(record),
            reason,
            request_id,
        )
        await self._commit("A location with that code or name already exists")
        return record

    async def update_location(
        self,
        actor_id: UUID,
        record_id: UUID,
        values: dict[str, object],
        reason: str,
        request_id: str,
    ) -> Location:
        await self.access.lock_and_require(actor_id, "location:manage")
        record = await self.repository.location(record_id, for_update=True)
        if record is None:
            raise HTTPException(404, "Location not found")
        before = reference_state(record)
        if (
            values.get("status") == DirectoryStatus.INACTIVE
            and record.status != DirectoryStatus.INACTIVE
            and await self.repository.reference_has_active_assignments("location", record.id)
        ):
            raise HTTPException(409, "Reassign active users and teams before deactivation")
        for key, value in values.items():
            setattr(record, key, value)
        after = reference_state(record)
        if before == after:
            return record
        self._event(
            actor_id,
            "location.updated",
            "location",
            record.id,
            before,
            after,
            reason,
            request_id,
        )
        await self._commit("A location with that name already exists")
        return record

    async def create_team(
        self, actor_id: UUID, values: dict[str, object], reason: str, request_id: str
    ) -> Team:
        await self.access.lock_and_require(actor_id, "team:manage")
        await self._active_references(
            values.get("department_id"),  # type: ignore[arg-type]
            values.get("location_id"),  # type: ignore[arg-type]
        )
        record = Team(id=uuid4(), **values)
        self.session.add(record)
        await self._flush("A team with that code or name already exists")
        self._event(
            actor_id,
            "team.created",
            "team",
            record.id,
            None,
            team_state(record),
            reason,
            request_id,
        )
        await self._commit("A team with that code or name already exists")
        return record

    async def update_team(
        self,
        actor_id: UUID,
        team_id: UUID,
        values: dict[str, object],
        reason: str,
        request_id: str,
    ) -> Team:
        await self.access.lock_and_require(actor_id, "team:manage")
        record = await self.repository.team(team_id, for_update=True)
        if record is None:
            raise HTTPException(404, "Team not found")
        department_id = values.get("department_id", record.department_id)
        location_id = values.get("location_id", record.location_id)
        await self._active_references(
            department_id,  # type: ignore[arg-type]
            location_id,  # type: ignore[arg-type]
        )
        before = team_state(record)
        for key, value in values.items():
            setattr(record, key, value)
        after = team_state(record)
        if before == after:
            return record
        if before["status"] == "ACTIVE" and after["status"] == "INACTIVE":
            ended_at = utc_now()
            for membership in await self.repository.active_memberships_for_team(
                team_id, for_update=True
            ):
                membership.ended_at = ended_at
                self._event(
                    actor_id,
                    "team.member_removed",
                    "team_membership",
                    membership.id,
                    {
                        "team_id": str(team_id),
                        "user_id": str(membership.user_id),
                        "member_role": membership.member_role,
                    },
                    None,
                    reason,
                    request_id,
                )
        self._event(actor_id, "team.updated", "team", team_id, before, after, reason, request_id)
        await self._commit("A team with that name already exists")
        return record

    async def create_user(
        self, actor_id: UUID, values: dict[str, object], reason: str, request_id: str
    ) -> User:
        known_roles = await self.access.lock_and_require(actor_id, "user:create")
        await self.access.require(actor_id, "role:manage")
        roles = sorted(set(cast(list[str], values.pop("roles"))))
        if not set(roles) <= known_roles:
            raise HTTPException(422, "Unknown role")
        await self._active_references(
            values.get("department_id"),  # type: ignore[arg-type]
            values.get("location_id"),  # type: ignore[arg-type]
        )
        password = str(values.pop("initial_password"))
        try:
            password_hash = PasswordService().hash(password)
        except PasswordPolicyError as exc:
            raise HTTPException(422, str(exc)) from None
        values["email"] = str(values["email"]).lower()
        record = User(
            id=uuid4(),
            **values,
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
            password_changed_at=utc_now(),
        )
        self.session.add(record)
        await self._flush("A user with that email or employee number already exists")
        self.session.add_all([UserRole(user_id=record.id, role_code=role) for role in roles])
        self.session.add(
            RoleAssignmentEvent(
                actor_id=actor_id,
                user_id=record.id,
                before_roles=[],
                after_roles=roles,
                reason=reason,
                request_id=request_id[:128],
            )
        )
        self._event(
            actor_id,
            "user.created",
            "user",
            record.id,
            None,
            user_state(record, roles),
            reason,
            request_id,
        )
        await self._commit("A user with that email or employee number already exists")
        return record

    async def update_user(
        self,
        actor_id: UUID,
        user_id: UUID,
        values: dict[str, object],
        reason: str,
        request_id: str,
    ) -> User:
        await self.access.lock_and_require(actor_id, "user:update")
        record = await self.repository.user(user_id, for_update=True)
        if record is None:
            raise HTTPException(404, "User not found")
        before_roles, _ = await AccessRepository(self.session).grants(user_id)
        before = user_state(record, before_roles)
        department_id = values.get("department_id", record.department_id)
        location_id = values.get("location_id", record.location_id)
        await self._active_references(
            department_id,  # type: ignore[arg-type]
            location_id,  # type: ignore[arg-type]
        )
        if "email" in values:
            values["email"] = str(values["email"]).lower()
        for key, value in values.items():
            setattr(record, key, value)
        after = user_state(record, before_roles)
        if before == after:
            return record
        self._event(actor_id, "user.updated", "user", user_id, before, after, reason, request_id)
        await self._commit("A user with that email or employee number already exists")
        return record

    async def update_user_status(
        self,
        actor_id: UUID,
        user_id: UUID,
        status: UserStatus,
        reason: str,
        request_id: str,
    ) -> User:
        await self.access.lock_and_require(actor_id, "user:disable")
        if actor_id == user_id:
            raise HTTPException(409, "Another administrator must change your account status")
        record = await self.repository.user(user_id, for_update=True)
        if record is None:
            raise HTTPException(404, "User not found")
        roles, _ = await AccessRepository(self.session).grants(user_id)
        before = user_state(record, roles)
        if record.status == status:
            return record
        if status != UserStatus.ACTIVE:
            ended_at = utc_now()
            await IdentityRepository(self.session).revoke_user_sessions(user_id, ended_at)
            for membership in await self.repository.active_memberships_for_user(
                user_id, for_update=True
            ):
                membership.ended_at = ended_at
                self._event(
                    actor_id,
                    "team.member_removed",
                    "team_membership",
                    membership.id,
                    {
                        "team_id": str(membership.team_id),
                        "user_id": str(user_id),
                        "member_role": membership.member_role,
                    },
                    None,
                    reason,
                    request_id,
                )
        record.status = status
        after = user_state(record, roles)
        self._event(
            actor_id, "user.status_changed", "user", user_id, before, after, reason, request_id
        )
        await self._commit("User status could not be changed")
        return record

    async def assign_member(
        self,
        actor_id: UUID,
        team_id: UUID,
        user_id: UUID,
        member_role: str,
        reason: str,
        request_id: str,
    ) -> TeamMember:
        await self.access.lock_and_require(actor_id, "team:manage")
        team = await self.repository.team(team_id, for_update=True)
        if team is None:
            raise HTTPException(404, "Team not found")
        if team.status != DirectoryStatus.ACTIVE:
            raise HTTPException(409, "Cannot assign members to an inactive team")
        user = await self.repository.user(user_id, for_update=True)
        if user is None:
            raise HTTPException(404, "User not found")
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(409, "Only active users can join a team")
        roles, _ = await AccessRepository(self.session).grants(user_id)
        if not ({"TECHNICIAN", "IT_MANAGER"} & set(roles)):
            raise HTTPException(409, "User is not eligible for technician assignment")
        existing = await self.repository.active_membership(team_id, user_id, for_update=True)
        if existing and existing.member_role == member_role:
            return existing
        now = utc_now()
        if existing:
            existing.ended_at = now
        record = TeamMember(
            id=uuid4(),
            team_id=team_id,
            user_id=user_id,
            member_role=member_role,
            started_at=now,
        )
        self.session.add(record)
        await self._flush("User already has an active membership in this team")
        self._event(
            actor_id,
            "team.member_assigned",
            "team_membership",
            record.id,
            (
                {
                    "team_id": str(team_id),
                    "user_id": str(user_id),
                    "member_role": existing.member_role,
                }
                if existing
                else None
            ),
            {"team_id": str(team_id), "user_id": str(user_id), "member_role": member_role},
            reason,
            request_id,
        )
        await self._commit("User already has an active membership in this team")
        return record

    async def remove_member(
        self,
        actor_id: UUID,
        team_id: UUID,
        user_id: UUID,
        reason: str,
        request_id: str,
    ) -> None:
        await self.access.lock_and_require(actor_id, "team:manage")
        team = await self.repository.team(team_id, for_update=True)
        if team is None:
            raise HTTPException(404, "Team not found")
        record = await self.repository.active_membership(team_id, user_id, for_update=True)
        if record is None:
            raise HTTPException(404, "Active team membership not found")
        before: dict[str, object] = {
            "team_id": str(team_id),
            "user_id": str(user_id),
            "member_role": record.member_role,
        }
        record.ended_at = utc_now()
        self._event(
            actor_id,
            "team.member_removed",
            "team_membership",
            record.id,
            before,
            None,
            reason,
            request_id,
        )
        await self._commit("Team membership could not be removed")
