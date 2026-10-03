from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.catalog import PERMISSIONS
from app.modules.access.models import Role, RoleAssignmentEvent
from app.modules.access.repository import AccessRepository
from app.modules.identity.models import User, UserStatus


class AccessService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AccessRepository(session)

    async def require(self, user_id: UUID, permission: str) -> None:
        _, grants = await self.repository.grants(user_id)
        if permission not in PERMISSIONS or permission not in grants:
            raise HTTPException(403, "Permission denied")

    async def lock_and_require(self, user_id: UUID, permission: str) -> set[str]:
        """Serialize privileged writes with role changes, then recheck the actor."""
        known = set(
            await self.session.scalars(select(Role.code).order_by(Role.code).with_for_update())
        )
        actor = await self.session.get(User, user_id, populate_existing=True)
        if actor is None or actor.status != UserStatus.ACTIVE:
            raise HTTPException(403, "Permission denied")
        await self.require(user_id, permission)
        return known

    async def replace_roles(
        self, actor_id: UUID, target_id: UUID, roles: list[str], reason: str, request_id: str
    ) -> list[str]:
        # Lock the catalog in consistent order to serialize admin assignment changes.
        known = await self.lock_and_require(actor_id, "role:manage")
        if target_id == actor_id:
            raise HTTPException(409, "Another administrator must change your roles")
        target = await self.session.scalar(
            select(User).where(User.id == target_id).with_for_update()
        )
        if target is None:
            raise HTTPException(404, "User not found")
        if not set(roles) <= known:
            raise HTTPException(422, "Unknown role")
        if not ({"TECHNICIAN", "IT_MANAGER"} & set(roles)):
            # Team membership is a scope grant, so a technician-role downgrade must
            # not leave dormant scope that can silently revive after re-enablement.
            from app.modules.directory.models import TeamMember

            active_membership = await self.session.scalar(
                select(TeamMember.id).where(
                    TeamMember.user_id == target_id, TeamMember.ended_at.is_(None)
                )
            )
            if active_membership is not None:
                raise HTTPException(409, "Remove active team memberships before changing roles")
        before, _ = await self.repository.grants(target_id)
        after = sorted(set(roles))
        if before != after:
            await self.repository.replace_roles(target_id, after)
            self.session.add(
                RoleAssignmentEvent(
                    actor_id=actor_id,
                    user_id=target_id,
                    before_roles=before,
                    after_roles=after,
                    reason=reason,
                    request_id=request_id[:128],
                )
            )
            await self.session.commit()
        return after
