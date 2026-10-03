import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.access.repository import AccessRepository
from app.modules.alerts.service import AlertService
from app.modules.identity.models import User, UserStatus
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.security import TokenService, TokenValidationError
from app.modules.identity.service import utc_now
from app.modules.monitoring.service import MonitoringService
from app.modules.realtime.models import RealtimeEvent, RealtimeTopic
from app.modules.realtime.repository import RealtimeRepository
from app.modules.sla.models import SlaInstance
from app.modules.tickets.service import TicketService


@dataclass(frozen=True)
class RealtimePrincipal:
    user_id: UUID
    session_id: UUID
    permissions: frozenset[str]
    access_token: str = field(repr=False)


class RealtimeGateway:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = RealtimeRepository(session)

    def origin_allowed(self, origin: str | None) -> bool:
        allowed = {str(value).rstrip("/") for value in self.settings.cors_origins}
        return origin is not None and origin.rstrip("/") in allowed

    async def authenticate(self, token: str) -> RealtimePrincipal | None:
        if not token or len(token) > 4096:
            return None
        try:
            user_id, session_id = TokenService(self.settings).decode_access_token(token)
        except (TokenValidationError, RuntimeError):
            return None
        identity = IdentityRepository(self.session)
        user = await self.session.scalar(
            select(User).where(User.id == user_id).execution_options(populate_existing=True)
        )
        if (
            user is None
            or user.status != UserStatus.ACTIVE
            or not await identity.active_session(session_id, user_id, utc_now())
        ):
            return None
        _, permissions = await AccessRepository(self.session).grants(user_id)
        return RealtimePrincipal(user_id, session_id, frozenset(permissions), token)

    @staticmethod
    def topics(principal: RealtimePrincipal) -> list[str]:
        values = [RealtimeTopic.NOTIFICATIONS]
        if principal.permissions & {"ticket:view_own", "ticket:view_team", "ticket:view_all"}:
            values.extend((RealtimeTopic.TICKETS, RealtimeTopic.SLA))
        if "alert:view" in principal.permissions:
            values.append(RealtimeTopic.ALERTS)
        if "monitoring:view" in principal.permissions:
            values.append(RealtimeTopic.DEVICES)
        return sorted(value.value for value in values)

    async def visible_resource(
        self, principal: RealtimePrincipal, event: RealtimeEvent
    ) -> tuple[bool, UUID | None]:
        if event.recipient_id is not None and event.recipient_id != principal.user_id:
            return False, None
        topic = RealtimeTopic(event.topic)
        if topic == RealtimeTopic.ACCESS:
            return True, None
        if topic == RealtimeTopic.NOTIFICATIONS:
            return event.recipient_id == principal.user_id, None
        if topic == RealtimeTopic.TICKETS:
            if event.resource_id is None:
                return False, None
            if event.internal and "ticket:internal_note" not in principal.permissions:
                return False, None
            try:
                await TicketService(self.session).get_ticket(principal.user_id, event.resource_id)
            except HTTPException:
                return False, None
            return True, event.resource_id
        if topic == RealtimeTopic.SLA:
            if event.resource_id is None:
                return False, None
            instance = await self.session.get(SlaInstance, event.resource_id)
            if instance is None:
                return False, None
            try:
                await TicketService(self.session).get_ticket(principal.user_id, instance.ticket_id)
            except HTTPException:
                return False, None
            return True, instance.ticket_id
        if topic == RealtimeTopic.ALERTS:
            if "alert:view" not in principal.permissions:
                return False, None
            if event.resource_id is None:
                return True, None
            try:
                await AlertService(self.session).visible_alert(principal.user_id, event.resource_id)
            except HTTPException:
                return False, None
            return True, event.resource_id
        if topic == RealtimeTopic.DEVICES:
            if "monitoring:view" not in principal.permissions or event.resource_id is None:
                return False, None
            try:
                await MonitoringService(self.session, self.settings).visible_agent(
                    principal.user_id, event.resource_id
                )
            except HTTPException:
                return False, None
            return True, event.resource_id
        return False, None

    async def _close(self, websocket: WebSocket, code: int) -> None:
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=code)

    async def _initial_principal(self, websocket: WebSocket) -> RealtimePrincipal | None:
        try:
            value = await asyncio.wait_for(
                websocket.receive_json(), timeout=self.settings.realtime_auth_timeout_seconds
            )
        except (TimeoutError, ValueError, WebSocketDisconnect):
            return None
        if (
            not isinstance(value, dict)
            or set(value) != {"type", "access_token"}
            or value.get("type") != "authenticate"
            or not isinstance(value.get("access_token"), str)
        ):
            return None
        return await self.authenticate(value["access_token"])

    async def run(self, websocket: WebSocket) -> None:
        await websocket.accept()
        if not self.origin_allowed(websocket.headers.get("origin")):
            await self._close(websocket, 4403)
            return
        try:
            principal = await self._initial_principal(websocket)
        except SQLAlchemyError:
            await self._close(websocket, 1013)
            return
        if principal is None:
            await self._close(websocket, 4401)
            return
        try:
            await self.repository.publish_pending(self.settings.realtime_batch_size)
            cursor = await self.repository.latest_sequence()
            await self.session.rollback()
            await websocket.send_json(
                {
                    "type": "ready",
                    "protocol": 1,
                    "cursor": cursor,
                    "topics": self.topics(principal),
                    "heartbeat_seconds": self.settings.realtime_heartbeat_seconds,
                }
            )
            last_auth = last_ping = last_pong = monotonic()
            last_prune = monotonic()
            while True:
                await self.repository.publish_pending(self.settings.realtime_batch_size)
                first = await self.repository.first_sequence()
                if first is not None and cursor < first - 1:
                    cursor = await self.repository.latest_sequence()
                    await websocket.send_json(
                        {"type": "resync", "reason": "backlog", "cursor": cursor}
                    )
                events = await self.repository.events_after(
                    cursor, self.settings.realtime_batch_size + 1
                )
                if events:
                    principal = await self.authenticate_token_principal(principal)
                    last_auth = monotonic()
                    if principal is None:
                        await self._close(websocket, 4401)
                        return
                if len(events) > self.settings.realtime_batch_size:
                    cursor = await self.repository.latest_sequence()
                    await websocket.send_json(
                        {"type": "resync", "reason": "backlog", "cursor": cursor}
                    )
                else:
                    access_changed = False
                    for event in events:
                        assert event.sequence is not None
                        visible, resource_id = await self.visible_resource(principal, event)
                        cursor = event.sequence
                        if not visible:
                            continue
                        if event.topic == RealtimeTopic.ACCESS:
                            access_changed = True
                            continue
                        await websocket.send_json(
                            {
                                "type": "invalidate",
                                "sequence": event.sequence,
                                "topic": event.topic,
                                "resource_id": str(resource_id) if resource_id else None,
                            }
                        )
                    if access_changed:
                        await websocket.send_json(
                            {
                                "type": "resync",
                                "reason": "access_changed",
                                "cursor": cursor,
                            }
                        )
                await self.session.rollback()
                now = monotonic()
                if now - last_auth >= self.settings.realtime_heartbeat_seconds:
                    principal = await self.authenticate_token_principal(principal)
                    last_auth = now
                    if principal is None:
                        await self._close(websocket, 4401)
                        return
                if now - last_prune >= 60:
                    await self.repository.prune(
                        datetime.now(UTC) - timedelta(hours=self.settings.realtime_retention_hours)
                    )
                    last_prune = now
                if now - last_pong > self.settings.realtime_heartbeat_seconds * 2:
                    await self._close(websocket, 1013)
                    return
                if now - last_ping >= self.settings.realtime_heartbeat_seconds:
                    await websocket.send_json({"type": "ping"})
                    last_ping = now
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=self.settings.realtime_poll_interval_seconds,
                    )
                except TimeoutError:
                    continue
                if not isinstance(message, dict) or set(message) != {"type"}:
                    await self._close(websocket, 1008)
                    return
                if message["type"] != "pong":
                    await self._close(websocket, 1008)
                    return
                last_pong = monotonic()
        except WebSocketDisconnect:
            return
        except SQLAlchemyError:
            await self.session.rollback()
            await self._close(websocket, 1013)

    async def authenticate_token_principal(
        self, principal: RealtimePrincipal
    ) -> RealtimePrincipal | None:
        return await self.authenticate(principal.access_token)
