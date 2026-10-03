from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.access.catalog import RoleCode
from app.modules.access.dependencies import require_permission
from app.modules.directory.models import Department, Location, Team
from app.modules.directory.repository import (
    DirectoryRepository,
    MemberRecord,
    ReferenceRecord,
    TeamRecord,
    UserRecord,
)
from app.modules.directory.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    ReferenceSummary,
    TeamCreate,
    TeamDetailResponse,
    TeamMemberRemoval,
    TeamMemberRequest,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdate,
    TechnicianCandidate,
    UserCreate,
    UserDirectoryResponse,
    UserPage,
    UserStatusUpdate,
    UserUpdate,
)
from app.modules.directory.service import DirectoryService
from app.modules.identity.models import User, UserStatus

router = APIRouter(prefix="/directory", tags=["organizational directory"])


def summary(record: Department | Location | Team | None) -> ReferenceSummary | None:
    if record is None:
        return None
    return ReferenceSummary(id=record.id, code=record.code, name=record.name)


def department_response(value: ReferenceRecord) -> DepartmentResponse:
    record = value.record
    assert isinstance(record, Department)
    return DepartmentResponse(
        id=record.id,
        code=record.code,
        name=record.name,
        description=record.description,
        status=record.status,
        user_count=value.user_count,
        team_count=value.team_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def location_response(value: ReferenceRecord) -> LocationResponse:
    record = value.record
    assert isinstance(record, Location)
    return LocationResponse(
        id=record.id,
        code=record.code,
        name=record.name,
        timezone=record.timezone,
        address=record.address,
        status=record.status,
        user_count=value.user_count,
        team_count=value.team_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def team_response(value: TeamRecord) -> TeamResponse:
    record = value.team
    return TeamResponse(
        id=record.id,
        code=record.code,
        name=record.name,
        description=record.description,
        status=record.status,
        department=summary(value.department),
        location=summary(value.location),
        member_count=value.member_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def member_response(value: MemberRecord) -> TeamMemberResponse:
    return TeamMemberResponse(
        user_id=value.user.id,
        display_name=value.user.display_name,
        email=value.user.email,
        job_title=value.user.job_title,
        status=value.user.status,
        member_role=value.membership.member_role,
        roles=list(value.roles),
    )


def user_response(value: UserRecord) -> UserDirectoryResponse:
    user = value.user
    return UserDirectoryResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        employee_number=user.employee_number,
        job_title=user.job_title,
        status=user.status,
        department=summary(value.department),
        location=summary(value.location),
        roles=list(value.roles),
        teams=[summary(team) for team in value.teams if summary(team) is not None],
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def read_reference(session: AsyncSession, kind: str, record_id: UUID) -> ReferenceRecord:
    value = await DirectoryRepository(session).reference_record(kind, record_id)
    if value is None:
        raise HTTPException(404, f"{kind.title()} not found")
    return value


@router.get("/departments", response_model=list[DepartmentResponse])
async def departments(
    actor: Annotated[User, Depends(require_permission("department:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DepartmentResponse]:
    return [
        department_response(value)
        for value in await DirectoryRepository(session).references("department")
    ]


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("department:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DepartmentResponse:
    record = await DirectoryService(session).create_department(
        actor.id,
        payload.model_dump(exclude={"reason"}),
        payload.reason,
        request.state.request_id,
    )
    return department_response(await read_reference(session, "department", record.id))


@router.patch("/departments/{record_id}", response_model=DepartmentResponse)
async def update_department(
    record_id: UUID,
    payload: DepartmentUpdate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("department:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DepartmentResponse:
    record = await DirectoryService(session).update_department(
        actor.id,
        record_id,
        payload.model_dump(exclude={"reason"}, exclude_unset=True),
        payload.reason,
        request.state.request_id,
    )
    return department_response(await read_reference(session, "department", record.id))


@router.get("/locations", response_model=list[LocationResponse])
async def locations(
    actor: Annotated[User, Depends(require_permission("location:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[LocationResponse]:
    return [
        location_response(value)
        for value in await DirectoryRepository(session).references("location")
    ]


@router.post("/locations", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
async def create_location(
    payload: LocationCreate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("location:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LocationResponse:
    record = await DirectoryService(session).create_location(
        actor.id,
        payload.model_dump(exclude={"reason"}),
        payload.reason,
        request.state.request_id,
    )
    return location_response(await read_reference(session, "location", record.id))


@router.patch("/locations/{record_id}", response_model=LocationResponse)
async def update_location(
    record_id: UUID,
    payload: LocationUpdate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("location:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LocationResponse:
    record = await DirectoryService(session).update_location(
        actor.id,
        record_id,
        payload.model_dump(exclude={"reason"}, exclude_unset=True),
        payload.reason,
        request.state.request_id,
    )
    return location_response(await read_reference(session, "location", record.id))


@router.get("/teams", response_model=list[TeamResponse])
async def teams(
    actor: Annotated[User, Depends(require_permission("team:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TeamResponse]:
    return [team_response(value) for value in await DirectoryRepository(session).teams()]


@router.post("/teams", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("team:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TeamResponse:
    record = await DirectoryService(session).create_team(
        actor.id,
        payload.model_dump(exclude={"reason"}),
        payload.reason,
        request.state.request_id,
    )
    value = await DirectoryRepository(session).team_record(record.id)
    assert value is not None
    return team_response(value)


@router.get("/teams/{team_id}", response_model=TeamDetailResponse)
async def team_detail(
    team_id: UUID,
    actor: Annotated[User, Depends(require_permission("team:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TeamDetailResponse:
    repository = DirectoryRepository(session)
    value = await repository.team_record(team_id)
    if value is None:
        raise HTTPException(404, "Team not found")
    base = team_response(value).model_dump()
    return TeamDetailResponse(
        **base,
        members=[member_response(item) for item in await repository.active_members(team_id)],
    )


@router.patch("/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: UUID,
    payload: TeamUpdate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("team:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TeamResponse:
    record = await DirectoryService(session).update_team(
        actor.id,
        team_id,
        payload.model_dump(exclude={"reason"}, exclude_unset=True),
        payload.reason,
        request.state.request_id,
    )
    value = await DirectoryRepository(session).team_record(record.id)
    assert value is not None
    return team_response(value)


@router.get("/teams/{team_id}/eligible-technicians", response_model=list[TechnicianCandidate])
async def eligible_technicians(
    team_id: UUID,
    actor: Annotated[User, Depends(require_permission("team:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[TechnicianCandidate]:
    repository = DirectoryRepository(session)
    if await repository.team(team_id) is None:
        raise HTTPException(404, "Team not found")
    values = await repository.eligible_technicians(team_id, search, limit)
    return [
        TechnicianCandidate(
            id=value.user.id,
            display_name=value.user.display_name,
            email=value.user.email,
            job_title=value.user.job_title,
            roles=list(value.roles),
        )
        for value in values
    ]


@router.put("/teams/{team_id}/members/{user_id}", response_model=TeamMemberResponse)
async def assign_member(
    team_id: UUID,
    user_id: UUID,
    payload: TeamMemberRequest,
    request: Request,
    actor: Annotated[User, Depends(require_permission("team:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TeamMemberResponse:
    await DirectoryService(session).assign_member(
        actor.id,
        team_id,
        user_id,
        payload.member_role,
        payload.reason,
        request.state.request_id,
    )
    member = next(
        (
            value
            for value in await DirectoryRepository(session).active_members(team_id)
            if value.user.id == user_id
        ),
        None,
    )
    assert member is not None
    return member_response(member)


@router.delete("/teams/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    payload: TeamMemberRemoval,
    request: Request,
    actor: Annotated[User, Depends(require_permission("team:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await DirectoryService(session).remove_member(
        actor.id, team_id, user_id, payload.reason, request.state.request_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users", response_model=UserPage)
async def users(
    actor: Annotated[User, Depends(require_permission("user:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None,
    department_id: UUID | None = None,
    location_id: UUID | None = None,
    role: RoleCode | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> UserPage:
    values, total = await DirectoryRepository(session).users(
        search=search,
        status=user_status,
        department_id=department_id,
        location_id=location_id,
        role=role,
        offset=offset,
        limit=limit,
    )
    return UserPage(
        items=[user_response(value) for value in values],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/users", response_model=UserDirectoryResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("user:create"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDirectoryResponse:
    record = await DirectoryService(session).create_user(
        actor.id,
        payload.model_dump(exclude={"reason"}),
        payload.reason,
        request.state.request_id,
    )
    value = await DirectoryRepository(session).user_record(record.id)
    assert value is not None
    return user_response(value)


@router.get("/users/{user_id}", response_model=UserDirectoryResponse)
async def user_detail(
    user_id: UUID,
    actor: Annotated[User, Depends(require_permission("user:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDirectoryResponse:
    value = await DirectoryRepository(session).user_record(user_id)
    if value is None:
        raise HTTPException(404, "User not found")
    return user_response(value)


@router.patch("/users/{user_id}", response_model=UserDirectoryResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("user:update"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDirectoryResponse:
    record = await DirectoryService(session).update_user(
        actor.id,
        user_id,
        payload.model_dump(exclude={"reason"}, exclude_unset=True),
        payload.reason,
        request.state.request_id,
    )
    value = await DirectoryRepository(session).user_record(record.id)
    assert value is not None
    return user_response(value)


@router.put("/users/{user_id}/status", response_model=UserDirectoryResponse)
async def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("user:disable"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDirectoryResponse:
    record = await DirectoryService(session).update_user_status(
        actor.id, user_id, payload.status, payload.reason, request.state.request_id
    )
    value = await DirectoryRepository(session).user_record(record.id)
    assert value is not None
    return user_response(value)
