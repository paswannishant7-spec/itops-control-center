from sqlalchemy import event
from sqlalchemy.orm import Session

from app.modules.access.models import RoleAssignmentEvent
from app.modules.ai.models import AIFeedback, AIInteraction
from app.modules.alerts.models import AlertEvent
from app.modules.assets.models import AssetEvent
from app.modules.directory.models import DirectoryEvent
from app.modules.knowledge.models import KnowledgeEvent
from app.modules.sla.models import SlaEvent
from app.modules.tickets.models import TicketEvent


class AuditMutationError(RuntimeError):
    pass


AUDIT_MODELS = (
    RoleAssignmentEvent,
    DirectoryEvent,
    TicketEvent,
    SlaEvent,
    KnowledgeEvent,
    AssetEvent,
    AlertEvent,
    AIInteraction,
    AIFeedback,
)


def install_audit_immutability() -> None:
    if event.contains(Session, "before_flush", reject_audit_mutation):
        return
    event.listen(Session, "before_flush", reject_audit_mutation)


def reject_audit_mutation(session: Session, *_: object) -> None:
    if any(isinstance(value, AUDIT_MODELS) for value in session.dirty):
        raise AuditMutationError("Audit records are append-only and cannot be updated")
    if any(isinstance(value, AUDIT_MODELS) for value in session.deleted):
        raise AuditMutationError("Audit records are append-only and cannot be deleted")
