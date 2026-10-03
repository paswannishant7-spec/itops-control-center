from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.realtime.service import RealtimeGateway

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.websocket("/ws")
async def realtime_socket(
    websocket: WebSocket,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    await RealtimeGateway(session, settings).run(websocket)
