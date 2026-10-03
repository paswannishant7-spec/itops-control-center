from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.modules.access.models import RoleAssignmentEvent
from app.modules.alerts.models import Alert, AlertEvent, Notification
from app.modules.directory.models import DirectoryEvent
from app.modules.monitoring.models import DeviceAgent
from app.modules.realtime.models import RealtimeEvent, RealtimeTopic
from app.modules.sla.models import SlaEvent
from app.modules.tickets.models import TicketEvent

CAPTURE_INSTALLED = False
SEEN_KEY = "realtime_event_keys"


def _changed(value: object, *names: str) -> bool:
    state = inspect(value)
    if state is None:
        return False
    return any(state.attrs[name].history.has_changes() for name in names)


def _signal(
    session: Session,
    topic: RealtimeTopic,
    resource_id: UUID | None,
    recipient_id: UUID | None = None,
    *,
    internal: bool = False,
) -> None:
    key = (topic.value, resource_id, recipient_id, internal)
    seen = session.info.setdefault(SEEN_KEY, set())
    if key in seen:
        return
    seen.add(key)
    session.add(
        RealtimeEvent(
            id=uuid4(),
            topic=topic,
            resource_id=resource_id,
            recipient_id=recipient_id,
            internal=internal,
            created_at=datetime.now(UTC),
        )
    )


def _capture(session: Session, _flush_context: object, _instances: object) -> None:
    for value in tuple(session.new):
        if isinstance(value, TicketEvent):
            visibility = (value.after_state or {}).get("visibility")
            _signal(
                session,
                RealtimeTopic.TICKETS,
                value.ticket_id,
                internal=str(visibility) == "INTERNAL",
            )
        elif isinstance(value, SlaEvent):
            _signal(session, RealtimeTopic.SLA, value.instance_id)
        elif isinstance(value, AlertEvent):
            resource_id = value.alert_id if value.entity_type == "ALERT" else None
            _signal(session, RealtimeTopic.ALERTS, resource_id)
        elif isinstance(value, Notification):
            _signal(session, RealtimeTopic.NOTIFICATIONS, None, value.user_id)
        elif isinstance(value, DeviceAgent):
            _signal(session, RealtimeTopic.DEVICES, value.id)
        elif isinstance(value, RoleAssignmentEvent):
            _signal(session, RealtimeTopic.ACCESS, None, value.user_id)
        elif isinstance(value, DirectoryEvent):
            _signal(session, RealtimeTopic.ACCESS, None)

    for value in tuple(session.dirty):
        if isinstance(value, Alert) and _changed(
            value, "state", "observed_value", "last_observed_at", "incident_ticket_id"
        ):
            _signal(session, RealtimeTopic.ALERTS, value.id)
        elif isinstance(value, Notification) and _changed(value, "read_at"):
            _signal(session, RealtimeTopic.NOTIFICATIONS, None, value.user_id)
        elif isinstance(value, DeviceAgent) and _changed(
            value, "status", "credential_status", "missed_heartbeat_count"
        ):
            _signal(session, RealtimeTopic.DEVICES, value.id)


def _clear(session: Session) -> None:
    session.info.pop(SEEN_KEY, None)


def install_realtime_capture() -> None:
    global CAPTURE_INSTALLED
    if CAPTURE_INSTALLED:
        return
    event.listen(Session, "before_flush", _capture)
    event.listen(Session, "after_commit", _clear)
    event.listen(Session, "after_rollback", _clear)
    CAPTURE_INSTALLED = True
