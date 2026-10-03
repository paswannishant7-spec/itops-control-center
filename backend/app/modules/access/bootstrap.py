"""Explicit upgrade path for an existing Phase 3 identity."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.access.models import Role, RoleAssignmentEvent, UserRole
from app.modules.identity.models import User, UserStatus
from app.modules.identity.security import PasswordService


async def bootstrap_existing(session: AsyncSession, settings: Settings) -> None:
    await session.execute(select(Role.code).order_by(Role.code).with_for_update())
    if await session.scalar(select(RoleAssignmentEvent.id).limit(1)) is not None:
        raise ValueError("Access control is already initialized; use another administrator")
    if (
        await session.scalar(select(UserRole.user_id).where(UserRole.role_code == "ADMIN").limit(1))
        is not None
    ):
        raise ValueError("An administrator already exists")
    if not settings.initial_admin_email or not settings.initial_admin_password:
        raise ValueError("Configure bootstrap identity and password in the environment")
    user = await session.scalar(
        select(User)
        .where(User.email == settings.initial_admin_email.strip().lower())
        .with_for_update()
    )
    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or not PasswordService().verify(
            user.password_hash, settings.initial_admin_password.get_secret_value()
        )
    ):
        raise ValueError("Bootstrap identity verification failed")
    session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    session.add(
        RoleAssignmentEvent(
            actor_id=user.id,
            user_id=user.id,
            before_roles=[],
            after_roles=["ADMIN"],
            reason="Explicit upgrade from Phase 3 identity",
            request_id="bootstrap-existing",
        )
    )
