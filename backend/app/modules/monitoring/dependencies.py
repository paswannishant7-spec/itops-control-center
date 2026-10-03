from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.monitoring.models import CredentialStatus, DeviceAgent
from app.modules.monitoring.repository import MonitoringRepository
from app.modules.monitoring.security import secret_matches


async def get_current_agent(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> DeviceAgent:
    unauthorized = HTTPException(
        401,
        "Agent authentication required",
        headers={"WWW-Authenticate": "Agent"},
    )
    scheme, separator, value = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "agent":
        raise unauthorized
    identifier, separator, secret = value.partition(".")
    if not separator or not secret:
        raise unauthorized
    try:
        agent_id = UUID(identifier)
    except ValueError:
        raise unauthorized from None
    agent = await MonitoringRepository(session).agent(agent_id)
    if (
        agent is None
        or agent.status == "DISABLED"
        or agent.credential_status != CredentialStatus.ACTIVE
        or not agent.credential_hash
        or not secret_matches(secret, agent.credential_hash)
    ):
        raise unauthorized
    return agent
