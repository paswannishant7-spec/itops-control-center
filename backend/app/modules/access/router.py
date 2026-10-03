from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.access.catalog import RoleCode
from app.modules.access.dependencies import require_permission
from app.modules.access.repository import AccessRepository
from app.modules.access.service import AccessService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User

router = APIRouter(prefix="/access", tags=["access control"])


class GrantsResponse(BaseModel):
    roles: list[str]
    permissions: list[str]


class RoleResponse(BaseModel):
    code: str
    permissions: list[str]


class AssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    roles: list[RoleCode] = Field(max_length=4)
    reason: str = Field(min_length=3, max_length=500)


@router.get("/me", response_model=GrantsResponse, summary="Current database permissions")
async def own_grants(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GrantsResponse:
    roles, permissions = await AccessRepository(session).grants(user.id)
    return GrantsResponse(roles=roles, permissions=permissions)


@router.get("/roles", response_model=list[RoleResponse], summary="System roles; requires role:view")
async def roles(
    user: Annotated[User, Depends(require_permission("role:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, object]]:
    return await AccessRepository(session).roles()


@router.get(
    "/permissions", response_model=list[str], summary="Permission catalog; requires permission:view"
)
async def permissions(
    user: Annotated[User, Depends(require_permission("permission:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[str]:
    return await AccessRepository(session).permissions()


@router.get(
    "/users/{user_id}/roles",
    response_model=GrantsResponse,
    summary="User grants; requires role:manage",
)
async def user_roles(
    user_id: UUID,
    actor: Annotated[User, Depends(require_permission("role:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GrantsResponse:
    from fastapi import HTTPException

    if await session.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    roles, permissions = await AccessRepository(session).grants(user_id)
    return GrantsResponse(roles=roles, permissions=permissions)


@router.put(
    "/users/{user_id}/roles",
    response_model=list[str],
    summary="Replace roles; requires role:manage; audited",
)
async def assign(
    user_id: UUID,
    payload: AssignmentRequest,
    request: Request,
    actor: Annotated[User, Depends(require_permission("role:manage"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[str]:
    return await AccessService(session).replace_roles(
        actor.id, user_id, list(payload.roles), payload.reason, request.state.request_id
    )
