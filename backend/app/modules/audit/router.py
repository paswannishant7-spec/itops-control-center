from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.access.dependencies import require_permission
from app.modules.audit.schemas import AuditEventPage, AuditSource
from app.modules.audit.service import AuditService
from app.modules.identity.models import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=AuditEventPage)
async def events(
    actor: Annotated[User, Depends(require_permission("audit:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    source: AuditSource | None = None,
    action: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    entity_id: UUID | None = None,
    actor_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditEventPage:
    del actor
    return await AuditService(session).page(
        source=source,
        action=action,
        entity_id=entity_id,
        actor_id=actor_id,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )
