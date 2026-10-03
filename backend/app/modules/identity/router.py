from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.core.config import Settings, get_settings
from app.modules.identity.dependencies import get_auth_service, get_current_user
from app.modules.identity.models import User
from app.modules.identity.rate_limit import (
    login_rate_limiter,
    private_rate_limit_key,
    refresh_rate_limiter,
)
from app.modules.identity.schemas import LoginRequest, MessageResponse, TokenResponse, UserResponse
from app.modules.identity.service import AuthenticationError, AuthResult, AuthService

router = APIRouter(prefix="/auth")


def set_refresh_cookie(response: Response, result: AuthResult, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=result.refresh_token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path=f"{settings.api_v1_prefix}/auth",
    )


def token_response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token,
        expires_in=result.access_expires_in,
        user=UserResponse.model_validate(result.user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    login_rate_limiter.limit = settings.login_rate_limit_attempts
    login_rate_limiter.window_seconds = settings.login_rate_limit_window_seconds
    key = private_rate_limit_key(
        request.client.host if request.client else "unknown", str(payload.email)
    )
    if not login_rate_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(login_rate_limiter.retry_after(key))},
        )
    try:
        result = await service.login(
            str(payload.email),
            payload.password,
            request.headers.get("user-agent"),
            request.client.host if request.client else None,
        )
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from None
    set_refresh_cookie(response, result, settings)
    return token_response(result)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie(alias="itops_refresh")] = None,
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    refresh_rate_limiter.limit = settings.refresh_rate_limit_attempts
    refresh_rate_limiter.window_seconds = settings.refresh_rate_limit_window_seconds
    key = private_rate_limit_key(
        request.client.host if request.client else "unknown", refresh_token
    )
    if not refresh_rate_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many refresh attempts",
            headers={"Retry-After": str(refresh_rate_limiter.retry_after(key))},
        )
    try:
        result = await service.refresh(
            refresh_token,
            request.headers.get("user-agent"),
            request.client.host if request.client else None,
        )
    except AuthenticationError:
        response.delete_cookie(settings.refresh_cookie_name, path=f"{settings.api_v1_prefix}/auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from None
    set_refresh_cookie(response, result, settings)
    return token_response(result)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie(alias="itops_refresh")] = None,
) -> MessageResponse:
    await service.logout(refresh_token)
    response.delete_cookie(settings.refresh_cookie_name, path=f"{settings.api_v1_prefix}/auth")
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse.model_validate(user)
