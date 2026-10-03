from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.access.models import RoleAssignmentEvent, UserRole
from app.modules.identity.models import User, UserStatus
from app.modules.identity.security import PasswordService


async def seed_initial_admin(session: AsyncSession) -> None:
    settings = get_settings()
    if (
        not settings.initial_admin_email
        or settings.initial_admin_password is None
        or not settings.initial_admin_password.get_secret_value()
    ):
        return
    email = settings.initial_admin_email.strip().lower()
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        return
    user = User(
        email=email,
        display_name=settings.initial_admin_name,
        password_hash=PasswordService().hash(settings.initial_admin_password.get_secret_value()),
        status=UserStatus.ACTIVE,
        password_changed_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    session.add(
        RoleAssignmentEvent(
            actor_id=user.id,
            user_id=user.id,
            before_roles=[],
            after_roles=["ADMIN"],
            reason="Initial administrator bootstrap",
            request_id="bootstrap",
        )
    )
