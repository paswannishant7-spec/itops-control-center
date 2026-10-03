from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.access.catalog import PERMISSIONS
from app.modules.access.service import AccessService
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.models import User


def require_permission(permission: str) -> Callable[..., Awaitable[User]]:
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission}")

    async def check(
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> User:
        await AccessService(session).require(user.id, permission)
        return user

    return check
