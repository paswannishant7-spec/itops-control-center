import json
from hashlib import sha256
from time import monotonic
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.ai.models import (
    AIFeedback,
    AIInteraction,
    AIRecommendation,
    InteractionStatus,
    RecommendationSource,
)
from app.modules.ai.provider import ClassificationProvider, ProviderError, ProviderResponse
from app.modules.ai.repository import AIRepository
from app.modules.ai.schemas import (
    AssistantResponse,
    AssistantTask,
    FeedbackActionValue,
    FeedbackCreate,
    FeedbackMetrics,
    FeedbackResponse,
    ResponseDraftOutput,
    TicketSummaryOutput,
)
from app.modules.ai.service import confidence_band, redact
from app.modules.tickets.models import Ticket, TicketComment
from app.modules.tickets.service import TicketService

PROMPT_VERSION = "technician-assistant-v1"
PUBLIC_COMMENT_LIMIT = 20
COMMENT_CHARACTER_LIMIT = 800


def assistant_fallback(task_type: AssistantTask) -> ResponseDraftOutput | TicketSummaryOutput:
    if task_type == AssistantTask.RESPONSE_DRAFT:
        return ResponseDraftOutput(
            draft="",
            key_points=[],
            safety_notes=["Drafting is unavailable; write and review the response manually."],
            confidence=0.0,
        )
    return TicketSummaryOutput(
        summary="Ticket summarization is temporarily unavailable.",
        key_facts=[],
        open_questions=[],
        suggested_next_step="Review the ticket and public conversation manually.",
        confidence=0.0,
    )


class AssistantService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AIRepository(session)

    def minimized_input(
        self, ticket: Ticket, comments: list[TicketComment]
    ) -> tuple[dict[str, object], dict[str, object]]:
        title, title_redactions = redact(ticket.title)
        description, description_redactions = redact(ticket.description)
        description = description[: self.settings.ai_max_input_characters]
        resolution, resolution_redactions = redact(ticket.resolution_summary or "")
        redactions = title_redactions + description_redactions + resolution_redactions
        conversation: list[dict[str, object]] = []
        for comment in comments:
            body, count = redact(comment.body[:COMMENT_CHARACTER_LIMIT])
            redactions += count
            conversation.append(
                {
                    "speaker": "requester"
                    if comment.author_id == ticket.requester_id
                    else "support",
                    "content": body,
                }
            )
        value: dict[str, object] = {
            "untrusted_ticket": {
                "title": title,
                "description": description,
                "status": ticket.status,
                "priority": ticket.priority,
                "impact": ticket.impact,
                "urgency": ticket.urgency,
                "resolution": resolution[:1000] or None,
            },
            "untrusted_public_conversation": conversation,
        }
        metadata: dict[str, object] = {
            "description_characters": len(description),
            "public_comments": len(conversation),
            "comment_character_limit": COMMENT_CHARACTER_LIMIT,
            "redactions": redactions,
            "internal_comments_included": False,
            "identities_included": False,
        }
        return value, metadata

    async def generate(
        self,
        actor_id: UUID,
        ticket_id: UUID,
        task_type: AssistantTask,
        provider: ClassificationProvider,
    ) -> AssistantResponse:
        ticket = (await TicketService(self.session).get_ticket(actor_id, ticket_id)).ticket
        comments = await self.repository.public_comments(ticket_id, PUBLIC_COMMENT_LIMIT)
        minimized, metadata = self.minimized_input(ticket, comments)
        metadata["task_type"] = task_type
        request_hash = sha256(
            json.dumps(minimized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        output_model: type[BaseModel] = (
            ResponseDraftOutput
            if task_type == AssistantTask.RESPONSE_DRAFT
            else TicketSummaryOutput
        )
        started = monotonic()
        result: ResponseDraftOutput | TicketSummaryOutput | None = None
        provider_response: ProviderResponse | None = None
        error_code: str | None = None
        attempts = 0
        for attempt in range(1, 3):
            attempts = attempt
            try:
                provider_response = await provider.assist(
                    task_type, minimized, cast(dict[str, object], output_model.model_json_schema())
                )
                result = cast(
                    ResponseDraftOutput | TicketSummaryOutput,
                    output_model.model_validate(provider_response.output),
                )
                break
            except ValidationError:
                provider_response = None
                error_code = "invalid_output"
            except ProviderError as error:
                provider_response = None
                error_code = error.code
                if not error.retryable:
                    break
        result = result or assistant_fallback(task_type)
        source = RecommendationSource.MODEL if provider_response else RecommendationSource.FALLBACK
        status = InteractionStatus.SUCCEEDED if provider_response else InteractionStatus.FALLBACK
        interaction = AIInteraction(
            ticket_id=ticket_id,
            actor_id=actor_id,
            task_type=task_type,
            provider=provider.name,
            model=provider.model,
            status=status,
            prompt_version=PROMPT_VERSION,
            request_hash=request_hash,
            input_metadata=metadata,
            provider_request_id=provider_response.request_id if provider_response else None,
            attempts=attempts,
            latency_ms=max(0, int((monotonic() - started) * 1000)),
            input_tokens=provider_response.input_tokens if provider_response else None,
            output_tokens=provider_response.output_tokens if provider_response else None,
            error_code=error_code if status == InteractionStatus.FALLBACK else None,
        )
        self.session.add(interaction)
        await self.session.flush()
        recommendation = AIRecommendation(
            interaction_id=interaction.id,
            ticket_id=ticket_id,
            output_type=task_type,
            source=source,
            confidence=result.confidence,
            payload=result.model_dump(mode="json"),
        )
        self.session.add(recommendation)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(interaction)
        return await self.response(interaction, recommendation)

    async def response(
        self, interaction: AIInteraction, recommendation: AIRecommendation
    ) -> AssistantResponse:
        task_type = AssistantTask(interaction.task_type)
        output = (
            ResponseDraftOutput.model_validate(recommendation.payload)
            if task_type == AssistantTask.RESPONSE_DRAFT
            else TicketSummaryOutput.model_validate(recommendation.payload)
        )
        feedback = await self.repository.feedback(recommendation.id)
        return AssistantResponse(
            interaction_id=interaction.id,
            recommendation_id=recommendation.id,
            ticket_id=interaction.ticket_id,
            task_type=task_type,
            source=recommendation.source,
            provider=interaction.provider,
            model=interaction.model,
            status=interaction.status,
            confidence_band=confidence_band(output.confidence, self.settings),
            fallback_reason=interaction.error_code,
            recommendation=output,
            feedback=self.feedback_response(feedback) if feedback else None,
            created_at=interaction.created_at,
        )

    async def latest(
        self, actor_id: UUID, ticket_id: UUID, task_type: AssistantTask
    ) -> AssistantResponse | None:
        await TicketService(self.session).get_ticket(actor_id, ticket_id)
        value = await self.repository.latest_assistant(ticket_id, task_type)
        return await self.response(*value) if value else None

    async def review(
        self,
        actor_id: UUID,
        ticket_id: UUID,
        recommendation_id: UUID,
        request: FeedbackCreate,
    ) -> FeedbackResponse:
        await TicketService(self.session).get_ticket(actor_id, ticket_id)
        record = await self.repository.recommendation(ticket_id, recommendation_id)
        if record is None:
            raise HTTPException(404, "AI recommendation not found")
        interaction, recommendation = record
        if await self.repository.feedback(recommendation_id) is not None:
            raise HTTPException(409, "AI recommendation has already been reviewed")
        if request.action == FeedbackActionValue.EDITED and request.edited_content is None:
            raise HTTPException(422, "Edited feedback requires edited content")
        if request.action != FeedbackActionValue.EDITED and request.edited_content is not None:
            raise HTTPException(422, "Edited content is only valid for edited feedback")
        feedback = AIFeedback(
            interaction_id=interaction.id,
            recommendation_id=recommendation.id,
            ticket_id=ticket_id,
            actor_id=actor_id,
            action=request.action,
            feedback_text=request.feedback_text,
            edited_content=request.edited_content,
            confidence=recommendation.confidence,
            output_type=recommendation.output_type,
        )
        self.session.add(feedback)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise HTTPException(409, "AI recommendation has already been reviewed") from error
        await self.session.refresh(feedback)
        return self.feedback_response(feedback)

    async def metrics(self, actor_id: UUID) -> FeedbackMetrics:
        access = await TicketService(self.session).access(actor_id)
        if "ticket:view_all" not in access.permissions:
            raise HTTPException(403, "All-ticket scope is required for AI feedback metrics")
        counts = await self.repository.feedback_counts()
        accepted = counts.get(FeedbackActionValue.ACCEPTED, 0)
        edited = counts.get(FeedbackActionValue.EDITED, 0)
        rejected = counts.get(FeedbackActionValue.REJECTED, 0)
        regenerated = counts.get(FeedbackActionValue.REGENERATED, 0)
        reviewed = accepted + edited + rejected
        denominator = reviewed or 1
        return FeedbackMetrics(
            reviewed_recommendations=reviewed,
            accepted=accepted,
            edited=edited,
            rejected=rejected,
            regenerated=regenerated,
            acceptance_rate=accepted / denominator if reviewed else 0,
            edit_rate=edited / denominator if reviewed else 0,
            rejection_rate=rejected / denominator if reviewed else 0,
            label="Operational review rates; not a scientific AI accuracy measure.",
        )

    @staticmethod
    def feedback_response(feedback: AIFeedback) -> FeedbackResponse:
        return FeedbackResponse.model_validate(feedback, from_attributes=True)
