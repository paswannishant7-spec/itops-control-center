import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db import models as _database_models  # noqa: F401
from app.db.base import Base
from app.modules.access.models import RoleAssignmentEvent
from app.modules.alerts.models import Alert, AlertEvent, Notification
from app.modules.directory.models import DirectoryEvent
from app.modules.identity.models import RefreshSession, User, UserStatus
from app.modules.identity.security import TokenService
from app.modules.monitoring.models import DeviceAgent
from app.modules.realtime.capture import install_realtime_capture
from app.modules.realtime.models import RealtimeEvent, RealtimeTopic
from app.modules.realtime.repository import RealtimeRepository
from app.modules.realtime.service import RealtimeGateway, RealtimePrincipal
from app.modules.sla.models import SlaEvent, SlaInstance
from app.modules.tickets.models import TicketEvent

pytestmark = pytest.mark.anyio


@pytest.fixture
async def database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    install_realtime_capture()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def user() -> User:
    return User(
        id=uuid4(),
        email=f"realtime-{uuid4().hex}@example.com",
        display_name="Realtime Operator",
        employee_number=None,
        job_title=None,
        department_id=None,
        location_id=None,
        password_hash="not-used",
        status=UserStatus.ACTIVE,
        password_changed_at=datetime.now(UTC),
    )


async def test_transactional_capture_rollback_and_ordered_publication(database) -> None:
    actor = user()
    async with database() as session:
        session.add(actor)
        await session.commit()
        notification = Notification(
            id=uuid4(),
            user_id=actor.id,
            alert_id=None,
            ticket_id=None,
            event_type="test",
            title="Content stays outside the outbox",
            body="Sensitive body",
            dedupe_key=f"test:{uuid4()}",
        )
        session.add(notification)
        await session.commit()
        notification.read_at = datetime.now(UTC)
        await session.commit()
        internal = TicketEvent(
            id=uuid4(),
            ticket_id=uuid4(),
            actor_id=actor.id,
            event_type="ticket.comment_added",
            before_state=None,
            after_state={"visibility": "INTERNAL", "body": "never copied"},
            reason="Internal note",
            request_id="realtime-test",
        )
        session.add(internal)
        await session.commit()

        agent = DeviceAgent(id=uuid4(), asset_id=uuid4())
        alert_id = uuid4()
        session.add_all(
            [
                SlaEvent(
                    id=uuid4(),
                    instance_id=uuid4(),
                    event_type="sla.at_risk",
                    idempotency_key=f"realtime:{uuid4()}",
                    payload={},
                    notification_required=True,
                ),
                AlertEvent(
                    id=uuid4(),
                    entity_type="ALERT",
                    entity_id=alert_id,
                    alert_id=alert_id,
                    actor_id=None,
                    action="alert.triggered",
                    before_state=None,
                    after_state={"state": "TRIGGERED"},
                    reason="Threshold matched",
                    request_id="alert-realtime",
                ),
                agent,
                RoleAssignmentEvent(
                    id=uuid4(),
                    actor_id=actor.id,
                    user_id=actor.id,
                    before_roles=[],
                    after_roles=["TECHNICIAN"],
                    reason="Change access",
                    request_id="role-realtime",
                ),
                DirectoryEvent(
                    id=uuid4(),
                    actor_id=actor.id,
                    action="team.updated",
                    entity_type="team",
                    entity_id=uuid4(),
                    before_state=None,
                    after_state=None,
                    reason="Change team scope",
                    request_id="directory-realtime",
                ),
            ]
        )
        await session.commit()
        agent.status = "ONLINE"
        agent.last_seen = datetime.now(UTC)
        await session.commit()
        alert = Alert(
            id=alert_id,
            policy_id=uuid4(),
            agent_id=agent.id,
            asset_id=agent.asset_id,
            incident_ticket_id=None,
            source="DEVICE_AGENT",
            severity="CRITICAL",
            metric="CPU_PERCENT",
            threshold=90,
            observed_value=95,
            state="TRIGGERED",
            triggered_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )
        session.add(alert)
        await session.commit()
        alert.observed_value = 99
        alert.last_observed_at = datetime.now(UTC)
        await session.commit()

        rolled_back = TicketEvent(
            id=uuid4(),
            ticket_id=uuid4(),
            actor_id=actor.id,
            event_type="ticket.status_changed",
            before_state=None,
            after_state=None,
            reason="Rolled back",
            request_id="rollback-test",
        )
        session.add(rolled_back)
        await session.flush()
        await session.rollback()

        events = list(await session.scalars(select(RealtimeEvent)))
        assert len(events) == 10
        assert {value.topic for value in events} == {
            "access",
            "alerts",
            "devices",
            "notifications",
            "sla",
            "tickets",
        }
        assert all(not hasattr(value, "body") for value in events)
        ticket_signal = next(value for value in events if value.topic == "tickets")
        assert ticket_signal.internal is True

        repository = RealtimeRepository(session)
        assert await repository.publish_pending(6) == 6
        assert await repository.publish_pending(6) == 4
        published = list(
            await session.scalars(select(RealtimeEvent).order_by(RealtimeEvent.sequence))
        )
        assert [value.sequence for value in published] == list(range(1, 11))
        assert await repository.latest_sequence() == 10
        assert await repository.first_sequence() == 1
        assert len(await repository.events_after(8, 10)) == 2
        assert await repository.prune(datetime.now(UTC) + timedelta(minutes=1)) == 10
        assert await repository.first_sequence() is None


async def authenticated_gateway(
    database,
) -> tuple[RealtimeGateway, Settings, str, User, AsyncSession]:
    settings = Settings(
        jwt_secret="realtime-test-secret-at-least-thirty-two-chars",
        cors_origins=["http://testserver"],
        realtime_poll_interval_seconds=0.1,
    )
    session = database()
    actor = user()
    refresh = RefreshSession(
        id=uuid4(),
        user_id=actor.id,
        family_id=uuid4(),
        token_hash=uuid4().hex + uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add_all([actor, refresh])
    await session.commit()
    token = TokenService(settings).create_access_token(actor.id, refresh.id)
    return RealtimeGateway(session, settings), settings, token, actor, session


class FakeWebSocket:
    def __init__(self, origin: str | None, inbound: list[object]) -> None:
        self.headers = {"origin": origin} if origin else {}
        self.inbound = inbound
        self.sent: list[dict[str, object]] = []
        self.accepted = False
        self.closed: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int) -> None:
        self.closed = code

    async def send_json(self, value: dict[str, object]) -> None:
        self.sent.append(value)

    async def receive_json(self) -> object:
        if self.inbound:
            return self.inbound.pop(0)
        raise WebSocketDisconnect(code=1000)


async def test_gateway_authentication_origin_and_protocol(database) -> None:
    gateway, _, token, actor, session = await authenticated_gateway(database)
    assert gateway.origin_allowed("http://testserver") is True
    assert gateway.origin_allowed("https://attacker.example") is False
    principal = await gateway.authenticate(token)
    assert principal is not None and principal.user_id == actor.id
    actor_id = principal.user_id
    assert RealtimeGateway.topics(principal) == ["notifications"]

    event = RealtimeEvent(
        id=uuid4(),
        sequence=1,
        topic=RealtimeTopic.TICKETS,
        resource_id=uuid4(),
        recipient_id=None,
        internal=False,
    )
    session.add(event)
    await session.commit()
    loaded = await session.get(RealtimeEvent, event.id)
    assert loaded is not None
    assert await gateway.authenticate(token) is not None
    assert loaded.topic == RealtimeTopic.TICKETS and loaded.sequence == 1

    socket = FakeWebSocket("http://testserver", [{"type": "authenticate", "access_token": token}])
    await gateway.run(cast(WebSocket, cast(Any, socket)))
    assert socket.accepted is True and socket.closed is None
    assert socket.sent[0]["type"] == "ready"
    assert socket.sent[0]["protocol"] == 1
    assert token not in json.dumps(socket.sent)

    foreign = RealtimeEvent(
        topic=RealtimeTopic.NOTIFICATIONS,
        recipient_id=uuid4(),
        resource_id=None,
        internal=False,
    )
    assert await gateway.visible_resource(principal, foreign) == (False, None)
    own = RealtimeEvent(
        topic=RealtimeTopic.NOTIFICATIONS,
        recipient_id=actor_id,
        resource_id=None,
        internal=False,
    )
    assert await gateway.visible_resource(principal, own) == (True, None)

    rejected_origin = FakeWebSocket(
        "https://attacker.example", [{"type": "authenticate", "access_token": token}]
    )
    await gateway.run(cast(WebSocket, cast(Any, rejected_origin)))
    assert rejected_origin.closed == 4403
    malformed = FakeWebSocket("http://testserver", [{"type": "hello", "token": token}])
    await gateway.run(cast(WebSocket, cast(Any, malformed)))
    assert malformed.closed == 4401

    refresh = await session.get(RefreshSession, principal.session_id)
    assert refresh is not None
    refresh.revoked_at = datetime.now(UTC)
    await session.commit()
    assert await gateway.authenticate(token) is None
    await session.close()


async def test_gateway_applies_topic_and_record_visibility(database, monkeypatch) -> None:
    gateway, _, token, actor, session = await authenticated_gateway(database)
    actor_id = actor.id

    async def visible(*_args, **_kwargs):
        return object()

    monkeypatch.setattr("app.modules.tickets.service.TicketService.get_ticket", visible)
    monkeypatch.setattr("app.modules.alerts.service.AlertService.visible_alert", visible)
    monkeypatch.setattr("app.modules.monitoring.service.MonitoringService.visible_agent", visible)
    principal = RealtimePrincipal(
        actor_id,
        uuid4(),
        frozenset(
            {
                "ticket:view_own",
                "ticket:internal_note",
                "alert:view",
                "monitoring:view",
            }
        ),
        token,
    )

    def signal(
        topic: RealtimeTopic,
        resource_id=None,
        recipient_id=None,
        *,
        internal: bool = False,
    ) -> RealtimeEvent:
        return RealtimeEvent(
            topic=topic,
            resource_id=resource_id,
            recipient_id=recipient_id,
            internal=internal,
        )

    ticket_id = uuid4()
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.TICKETS, ticket_id)) == (
        True,
        ticket_id,
    )
    assert await gateway.visible_resource(
        principal, signal(RealtimeTopic.TICKETS, ticket_id, internal=True)
    ) == (True, ticket_id)
    limited = RealtimePrincipal(actor_id, uuid4(), frozenset(), token)
    assert await gateway.visible_resource(
        limited, signal(RealtimeTopic.TICKETS, ticket_id, internal=True)
    ) == (False, None)
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.TICKETS)) == (False, None)

    instance = SlaInstance(
        id=uuid4(),
        ticket_id=ticket_id,
        policy_id=uuid4(),
        calendar_id=uuid4(),
        state="ON_TRACK",
        response_target_seconds=60,
        resolution_target_seconds=120,
        at_risk_percent=80,
        response_elapsed_seconds=0,
        resolution_elapsed_seconds=0,
    )
    session.add(instance)
    await session.commit()
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.SLA, instance.id)) == (
        True,
        ticket_id,
    )
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.SLA)) == (
        False,
        None,
    )

    alert_id = uuid4()
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.ALERTS, alert_id)) == (
        True,
        alert_id,
    )
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.ALERTS)) == (
        True,
        None,
    )
    assert await gateway.visible_resource(limited, signal(RealtimeTopic.ALERTS, alert_id)) == (
        False,
        None,
    )

    agent_id = uuid4()
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.DEVICES, agent_id)) == (
        True,
        agent_id,
    )
    assert await gateway.visible_resource(limited, signal(RealtimeTopic.DEVICES, agent_id)) == (
        False,
        None,
    )
    assert await gateway.visible_resource(
        principal, signal(RealtimeTopic.ACCESS, recipient_id=actor_id)
    ) == (True, None)
    assert await gateway.visible_resource(
        principal, signal(RealtimeTopic.ACCESS, recipient_id=uuid4())
    ) == (False, None)

    async def hidden(*_args, **_kwargs):
        raise HTTPException(404, "Hidden")

    monkeypatch.setattr("app.modules.tickets.service.TicketService.get_ticket", hidden)
    assert await gateway.visible_resource(principal, signal(RealtimeTopic.TICKETS, ticket_id)) == (
        False,
        None,
    )
    await session.close()
