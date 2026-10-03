from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.access.models import RoleAssignmentEvent
from app.modules.ai.models import AIFeedback
from app.modules.alerts.models import AlertEvent
from app.modules.assets.models import AssetEvent
from app.modules.audit.schemas import AuditEventPage, AuditEventResponse, AuditSource
from app.modules.directory.models import DirectoryEvent
from app.modules.knowledge.models import KnowledgeEvent
from app.modules.sla.models import SlaEvent
from app.modules.tickets.models import TicketEvent

SENSITIVE_MARKERS = ("password", "secret", "token", "authorization", "cookie", "api_key")


def sanitize_state(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if any(marker in str(key).lower() for marker in SENSITIVE_MARKERS)
                else sanitize_state(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_state(item) for item in value]
    return value


def _state(value: object) -> dict[str, object] | None:
    clean = sanitize_state(value)
    return clean if isinstance(clean, dict) else None


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _criteria(
        statement: Select[tuple[Any]],
        model: Any,
        *,
        action_column: InstrumentedAttribute[Any],
        entity_column: InstrumentedAttribute[Any],
        action: str | None,
        entity_id: UUID | None,
        actor_id: UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> Select[tuple[Any]]:
        if action:
            statement = statement.where(action_column == action)
        if entity_id:
            statement = statement.where(entity_column == entity_id)
        if actor_id and hasattr(model, "actor_id"):
            statement = statement.where(model.actor_id == actor_id)
        if created_from:
            statement = statement.where(model.created_at >= created_from)
        if created_to:
            statement = statement.where(model.created_at <= created_to)
        return statement

    async def page(
        self,
        *,
        source: AuditSource | None,
        action: str | None,
        entity_id: UUID | None,
        actor_id: UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        offset: int,
        limit: int,
    ) -> AuditEventPage:
        if created_from and created_to and created_from > created_to:
            from fastapi import HTTPException

            raise HTTPException(422, "created_from must not be after created_to")
        models: Iterable[
            tuple[AuditSource, Any, InstrumentedAttribute[Any], InstrumentedAttribute[Any]]
        ] = (
            (
                AuditSource.ACCESS,
                RoleAssignmentEvent,
                RoleAssignmentEvent.id,
                RoleAssignmentEvent.user_id,
            ),
            (
                AuditSource.DIRECTORY,
                DirectoryEvent,
                DirectoryEvent.action,
                DirectoryEvent.entity_id,
            ),
            (AuditSource.TICKET, TicketEvent, TicketEvent.event_type, TicketEvent.ticket_id),
            (AuditSource.SLA, SlaEvent, SlaEvent.event_type, SlaEvent.instance_id),
            (
                AuditSource.KNOWLEDGE,
                KnowledgeEvent,
                KnowledgeEvent.action,
                KnowledgeEvent.article_id,
            ),
            (AuditSource.ASSET, AssetEvent, AssetEvent.action, AssetEvent.asset_id),
            (AuditSource.ALERT, AlertEvent, AlertEvent.action, AlertEvent.entity_id),
            (AuditSource.AI, AIFeedback, AIFeedback.action, AIFeedback.ticket_id),
        )
        records: list[AuditEventResponse] = []
        total = 0
        for source_name, model, action_column, entity_column in models:
            if source and source != source_name:
                continue
            query_action = action
            if source_name == AuditSource.ACCESS:
                if action and action != "role.assignment.changed":
                    continue
                query_action = None
            elif source_name == AuditSource.AI and action:
                prefix = "ai.feedback."
                if not action.startswith(prefix):
                    continue
                query_action = action.removeprefix(prefix).upper()
            base = self._criteria(
                select(model),
                model,
                action_column=action_column,
                entity_column=entity_column,
                action=query_action,
                entity_id=entity_id,
                actor_id=actor_id,
                created_from=created_from,
                created_to=created_to,
            )
            count_statement = base.with_only_columns(
                func.count(), maintain_column_froms=True
            ).order_by(None)
            total += int(await self.session.scalar(count_statement) or 0)
            rows = await self.session.scalars(
                base.order_by(model.created_at.desc()).limit(offset + limit)
            )
            records.extend(self._normalize(source_name, row) for row in rows)
        records.sort(key=lambda item: item.created_at, reverse=True)
        return AuditEventPage(
            items=records[offset : offset + limit], total=total, offset=offset, limit=limit
        )

    @staticmethod
    def _normalize(source: AuditSource, row: Any) -> AuditEventResponse:
        if source == AuditSource.ACCESS:
            return AuditEventResponse(
                id=row.id,
                source=source,
                action="role.assignment.changed",
                entity_type="USER",
                entity_id=row.user_id,
                actor_id=row.actor_id,
                before_state={"roles": row.before_roles},
                after_state={"roles": row.after_roles},
                reason=row.reason,
                request_id=row.request_id,
                created_at=row.created_at,
            )
        if source == AuditSource.DIRECTORY:
            entity_type, entity_id, action = row.entity_type, row.entity_id, row.action
        elif source == AuditSource.TICKET:
            entity_type, entity_id, action = "TICKET", row.ticket_id, row.event_type
        elif source == AuditSource.SLA:
            entity_type, entity_id, action = "SLA_INSTANCE", row.instance_id, row.event_type
        elif source == AuditSource.KNOWLEDGE:
            entity_type, entity_id, action = "KNOWLEDGE_ARTICLE", row.article_id, row.action
        elif source == AuditSource.ASSET:
            entity_type, entity_id, action = "ASSET", row.asset_id, row.action
        elif source == AuditSource.ALERT:
            entity_type, entity_id, action = row.entity_type, row.entity_id, row.action
        else:
            entity_type, entity_id, action = (
                "TICKET",
                row.ticket_id,
                f"ai.feedback.{row.action.lower()}",
            )
        if source == AuditSource.SLA:
            before_state, after_state = None, _state(row.payload)
            reason, request_id, actor_id = "Automated SLA lifecycle event", None, None
        elif source == AuditSource.AI:
            before_state = None
            after_state = {"output_type": row.output_type, "confidence": row.confidence}
            reason, request_id, actor_id = "AI recommendation reviewed", None, row.actor_id
        else:
            before_state, after_state = _state(row.before_state), _state(row.after_state)
            reason, request_id, actor_id = row.reason, row.request_id, row.actor_id
        return AuditEventResponse(
            id=row.id,
            source=source,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
            request_id=request_id,
            created_at=row.created_at,
        )
