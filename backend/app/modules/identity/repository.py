from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import RefreshSession, User


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def user_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.strip().lower()))
        return result.scalar_one_or_none()

    async def user_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def active_session(self, session_id: UUID, user_id: UUID, now: datetime) -> bool:
        return (
            await self.session.scalar(
                select(RefreshSession.id).where(
                    RefreshSession.id == session_id,
                    RefreshSession.user_id == user_id,
                    RefreshSession.revoked_at.is_(None),
                    RefreshSession.expires_at > now,
                )
            )
        ) is not None

    async def refresh_by_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshSession | None:
        statement = select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    def add_refresh(self, refresh: RefreshSession) -> None:
        self.session.add(refresh)

    async def revoke_family(self, family_id: UUID, revoked_at: datetime) -> None:
        await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == family_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )

    async def revoke_user_sessions(self, user_id: UUID, revoked_at: datetime) -> None:
        await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )

    async def commit(self) -> None:
        await self.session.commit()

    async def flush(self) -> None:
        await self.session.flush()
