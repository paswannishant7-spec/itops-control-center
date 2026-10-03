from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.models import Permission, Role, RolePermission, UserRole


class AccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def grants(self, user_id: UUID) -> tuple[list[str], list[str]]:
        roles = list(
            await self.session.scalars(
                select(UserRole.role_code)
                .where(UserRole.user_id == user_id)
                .order_by(UserRole.role_code)
            )
        )
        permissions = list(
            await self.session.scalars(
                select(RolePermission.permission_code)
                .join(UserRole, UserRole.role_code == RolePermission.role_code)
                .where(UserRole.user_id == user_id)
                .distinct()
                .order_by(RolePermission.permission_code)
            )
        )
        return roles, permissions

    async def roles(self) -> list[dict[str, object]]:
        codes = list(await self.session.scalars(select(Role.code).order_by(Role.code)))
        mappings = (
            await self.session.execute(
                select(RolePermission.role_code, RolePermission.permission_code).order_by(
                    RolePermission.permission_code
                )
            )
        ).all()
        return [
            {"code": code, "permissions": [p for r, p in mappings if r == code]} for code in codes
        ]

    async def permissions(self) -> list[str]:
        return list(await self.session.scalars(select(Permission.code).order_by(Permission.code)))

    async def replace_roles(self, user_id: UUID, codes: list[str]) -> None:
        await self.session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        self.session.add_all([UserRole(user_id=user_id, role_code=code) for code in codes])
