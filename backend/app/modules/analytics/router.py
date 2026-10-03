from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.access.dependencies import require_permission
from app.modules.analytics.schemas import DashboardResponse
from app.modules.analytics.service import AnalyticsService
from app.modules.identity.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    actor: Annotated[User, Depends(require_permission("analytics:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    window_days: Annotated[int, Query(ge=7, le=365)] = 30,
) -> DashboardResponse:
    return await AnalyticsService(session).dashboard(actor.id, window_days)
