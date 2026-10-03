import json
import re
from hashlib import sha256
from time import monotonic
from typing import cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.ai.models import (
    AIInteraction,
    AIRecommendation,
    InteractionStatus,
    RecommendationSource,
)
from app.modules.ai.provider import ClassificationProvider, ProviderError, ProviderResponse
from app.modules.ai.repository import AIRepository
from app.modules.ai.schemas import ClassificationOutput, ClassificationResponse, ConfidenceBand
from app.modules.tickets.models import Ticket, TicketCategory, TicketSubcategory
from app.modules.tickets.repository import TicketRepository
from app.modules.tickets.service import TicketService

PROMPT_VERSION = "ticket-classification-v1"
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_ -]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]+=*"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)


def redact(value: str) -> tuple[str, int]:
    count = 0
    for pattern in SECRET_PATTERNS:
        value, replacements = pattern.subn("[REDACTED]", value)
        count += replacements
    return value, count


def confidence_band(confidence: float, settings: Settings) -> ConfidenceBand:
    if confidence >= settings.ai_high_confidence_threshold:
        return ConfidenceBand.HIGH
    if confidence >= settings.ai_moderate_confidence_threshold:
        return ConfidenceBand.MODERATE
    return ConfidenceBand.LOW


def fallback(ticket: Ticket) -> ClassificationOutput:
    return ClassificationOutput(
        category_id=None,
        subcategory_id=None,
        category=None,
        subcategory=None,
        impact=ticket.impact,
        urgency=ticket.urgency,
        priority_recommendation=ticket.priority,
        possible_causes=[],
        recommended_checks=[
            "Review the ticket details with a technician.",
            "Confirm impact and urgency before changing priority.",
        ],
        confidence=0.0,
    )


class AIService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AIRepository(session)

    def minimized_input(
        self,
        ticket: Ticket,
        categories: list[tuple[TicketCategory, list[TicketSubcategory]]],
        department_name: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        title, title_redactions = redact(ticket.title)
        description, description_redactions = redact(ticket.description)
        truncated = len(description) > self.settings.ai_max_input_characters
        description = description[: self.settings.ai_max_input_characters]
        taxonomy = [
            {
                "id": str(category.id),
                "name": category.name,
                "subcategories": [
                    {"id": str(subcategory.id), "name": subcategory.name}
                    for subcategory in subcategories
                ],
            }
            for category, subcategories in categories
        ]
        value: dict[str, object] = {
            "untrusted_ticket": {
                "title": title,
                "description": description,
                "department": department_name,
                "asset_present": ticket.asset_id is not None,
                "current_impact": ticket.impact,
                "current_urgency": ticket.urgency,
            },
            "allowed_taxonomy": taxonomy,
        }
        metadata: dict[str, object] = {
            "title_characters": len(title),
            "description_characters": len(description),
            "description_truncated": truncated,
            "taxonomy_categories": len(taxonomy),
            "redactions": title_redactions + description_redactions,
        }
        return value, metadata

    @staticmethod
    def validate_taxonomy(
        output: ClassificationOutput,
        categories: list[tuple[TicketCategory, list[TicketSubcategory]]],
    ) -> None:
        allowed = {
            category.id: (category.name, {item.id: item.name for item in subcategories})
            for category, subcategories in categories
        }
        if output.category_id is None:
            if any((output.subcategory_id, output.category, output.subcategory)):
                raise ValueError("Subcategory requires a category")
            return
        if output.category_id not in allowed:
            raise ValueError("Unknown category")
        category_name, subcategories = allowed[output.category_id]
        if output.category != category_name:
            raise ValueError("Category name does not match taxonomy")
        if output.subcategory_id is None:
            if output.subcategory is not None:
                raise ValueError("Subcategory name requires an ID")
            return
        if output.subcategory_id not in subcategories:
            raise ValueError("Unknown subcategory")
        if output.subcategory != subcategories[output.subcategory_id]:
            raise ValueError("Subcategory name does not match taxonomy")

    async def classify(
        self, actor_id: UUID, ticket_id: UUID, provider: ClassificationProvider
    ) -> ClassificationResponse:
        ticket_record = await TicketService(self.session).get_ticket(actor_id, ticket_id)
        record = ticket_record.ticket
        categories = await TicketRepository(self.session).categories()
        minimized, input_metadata = self.minimized_input(
            record,
            categories,
            ticket_record.department.name if ticket_record.department else None,
        )
        request_hash = sha256(
            json.dumps(minimized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        started = monotonic()
        result: ClassificationOutput | None = None
        provider_response: ProviderResponse | None = None
        error_code: str | None = None
        attempts = 0
        for attempt in range(1, 3):
            attempts = attempt
            try:
                provider_response = await provider.classify(
                    minimized, cast(dict[str, object], ClassificationOutput.model_json_schema())
                )
                result = ClassificationOutput.model_validate(provider_response.output)
                self.validate_taxonomy(result, categories)
                break
            except (ValidationError, ValueError):
                result = None
                provider_response = None
                error_code = "invalid_output"
            except ProviderError as error:
                result = None
                provider_response = None
                error_code = error.code
                if not error.retryable:
                    break
        source = RecommendationSource.MODEL if result is not None else RecommendationSource.FALLBACK
        status = InteractionStatus.SUCCEEDED if result is not None else InteractionStatus.FALLBACK
        result = result or fallback(record)
        latency_ms = max(0, int((monotonic() - started) * 1000))
        interaction = AIInteraction(
            ticket_id=ticket_id,
            actor_id=actor_id,
            task_type="CLASSIFICATION",
            provider=provider.name,
            model=provider.model,
            status=status,
            prompt_version=PROMPT_VERSION,
            request_hash=request_hash,
            input_metadata=input_metadata,
            provider_request_id=provider_response.request_id if provider_response else None,
            attempts=attempts,
            latency_ms=latency_ms,
            input_tokens=provider_response.input_tokens if provider_response else None,
            output_tokens=provider_response.output_tokens if provider_response else None,
            error_code=error_code if status == InteractionStatus.FALLBACK else None,
        )
        self.session.add(interaction)
        await self.session.flush()
        recommendation = AIRecommendation(
            interaction_id=interaction.id,
            ticket_id=ticket_id,
            output_type="CLASSIFICATION",
            source=source,
            confidence=result.confidence,
            payload=result.model_dump(mode="json"),
        )
        self.session.add(recommendation)
        await self.session.commit()
        await self.session.refresh(interaction)
        return self.response(interaction, recommendation)

    def response(
        self, interaction: AIInteraction, recommendation: AIRecommendation
    ) -> ClassificationResponse:
        output = ClassificationOutput.model_validate(recommendation.payload)
        return ClassificationResponse(
            interaction_id=interaction.id,
            ticket_id=interaction.ticket_id,
            source=recommendation.source,
            provider=interaction.provider,
            model=interaction.model,
            status=interaction.status,
            confidence_band=confidence_band(output.confidence, self.settings),
            fallback_reason=interaction.error_code,
            recommendation=output,
            created_at=interaction.created_at,
        )

    async def latest(self, actor_id: UUID, ticket_id: UUID) -> ClassificationResponse | None:
        await TicketService(self.session).get_ticket(actor_id, ticket_id)
        value = await self.repository.latest_classification(ticket_id)
        return self.response(*value) if value else None
