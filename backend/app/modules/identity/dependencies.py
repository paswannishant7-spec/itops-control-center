from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.identity.models import User, UserStatus
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.security import TokenService, TokenValidationError
from app.modules.identity.service import AuthService, utc_now

bearer = HTTPBearer(auto_error=False)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(IdentityRepository(session), settings)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        user_id, session_id = TokenService(settings).decode_access_token(credentials.credentials)
    except (TokenValidationError, RuntimeError):
        raise unauthorized from None
    repository = IdentityRepository(session)
    user = await repository.user_by_id(user_id)
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or not await repository.active_session(session_id, user_id, utc_now())
    ):
        raise unauthorized
    return user
