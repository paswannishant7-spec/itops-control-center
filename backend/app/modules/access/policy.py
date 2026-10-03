from dataclasses import dataclass
from uuid import UUID

from app.modules.access.catalog import PERMISSIONS


@dataclass(frozen=True)
class AccessScope:
    """Caller supplies ownership and team IDs from trusted database queries."""

    user_id: UUID
    permissions: frozenset[str]
    team_ids: frozenset[UUID] = frozenset()

    def allows(self, permission: str) -> bool:
        return permission in PERMISSIONS and permission in self.permissions

    def can_view(self, domain: str, owner_id: UUID, team_id: UUID | None) -> bool:
        return (
            self.allows(f"{domain}:view_all")
            or (self.allows(f"{domain}:view_own") and owner_id == self.user_id)
            or (
                self.allows(f"{domain}:view_team")
                and team_id is not None
                and team_id in self.team_ids
            )
        )
