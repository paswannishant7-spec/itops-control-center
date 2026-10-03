from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tickets.models import ImpactLevel, TicketPriority


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClassificationOutput(StrictModel):
    category_id: UUID | None
    subcategory_id: UUID | None
    category: str | None = Field(max_length=120)
    subcategory: str | None = Field(max_length=120)
    impact: ImpactLevel
    urgency: ImpactLevel
    priority_recommendation: TicketPriority
    possible_causes: list[Annotated[str, Field(min_length=2, max_length=240)]] = Field(max_length=8)
    recommended_checks: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(
        max_length=10
    )
    confidence: float = Field(ge=0, le=1)


class ConfidenceBand(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class ClassificationResponse(StrictModel):
    interaction_id: UUID
    ticket_id: UUID
    source: str
    provider: str
    model: str
    status: str
    confidence_band: ConfidenceBand
    fallback_reason: str | None
    recommendation: ClassificationOutput
    created_at: datetime


class TroubleshootingOutput(StrictModel):
    summary: str = Field(min_length=2, max_length=1000)
    known_facts: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(max_length=10)
    possible_causes: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(max_length=8)
    recommended_actions: list[Annotated[str, Field(min_length=2, max_length=600)]] = Field(
        max_length=10
    )
    uncertain_assumptions: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(
        max_length=8
    )
    cited_chunk_ids: list[UUID] = Field(max_length=12)
    confidence: float = Field(ge=0, le=1)


class KnowledgeCitation(StrictModel):
    article_id: UUID
    version_id: UUID
    chunk_id: UUID
    article_slug: str
    article_title: str
    article_version: int
    chunk_ordinal: int
    excerpt: str
    similarity: float = Field(ge=-1, le=1)


class TroubleshootingResponse(StrictModel):
    interaction_id: UUID
    ticket_id: UUID
    source: str
    provider: str
    model: str
    status: str
    confidence_band: ConfidenceBand
    fallback_reason: str | None
    recommendation: TroubleshootingOutput
    citations: list[KnowledgeCitation]
    created_at: datetime


class KnowledgeIndexResponse(StrictModel):
    article_id: UUID
    version_id: UUID
    article_version: int
    chunks: int
    embeddings_created: int
    embeddings_reused: int
    provider: str
    model: str


class SimilarTicketItem(StrictModel):
    ticket_id: UUID
    reference: str
    title: str
    similarity: float = Field(ge=-1, le=1)
    status: str
    priority: str
    category: str | None
    subcategory: str | None
    resolution_summary: str
    resolution_code: str | None
    resolved_at: datetime | None
    closed_at: datetime | None


class SimilarTicketResponse(StrictModel):
    ticket_id: UUID
    provider: str
    model: str
    indexed_embeddings: int
    reused_embeddings: int
    items: list[SimilarTicketItem]


class AssistantTask(StrEnum):
    RESPONSE_DRAFT = "RESPONSE_DRAFT"
    SUMMARIZATION = "SUMMARIZATION"


class ResponseDraftOutput(StrictModel):
    draft: str = Field(max_length=2000)
    key_points: list[Annotated[str, Field(min_length=2, max_length=300)]] = Field(max_length=8)
    safety_notes: list[Annotated[str, Field(min_length=2, max_length=300)]] = Field(max_length=6)
    confidence: float = Field(ge=0, le=1)


class TicketSummaryOutput(StrictModel):
    summary: str = Field(min_length=2, max_length=1400)
    key_facts: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(max_length=10)
    open_questions: list[Annotated[str, Field(min_length=2, max_length=400)]] = Field(max_length=8)
    suggested_next_step: str = Field(min_length=2, max_length=500)
    confidence: float = Field(ge=0, le=1)


class FeedbackActionValue(StrEnum):
    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"
    REGENERATED = "REGENERATED"


class FeedbackCreate(StrictModel):
    action: FeedbackActionValue
    feedback_text: str | None = Field(default=None, min_length=2, max_length=1000)
    edited_content: str | None = Field(default=None, min_length=2, max_length=4000)


class FeedbackResponse(StrictModel):
    id: UUID
    interaction_id: UUID
    recommendation_id: UUID
    ticket_id: UUID
    actor_id: UUID
    action: FeedbackActionValue
    feedback_text: str | None
    edited_content: str | None
    confidence: float = Field(ge=0, le=1)
    output_type: str
    created_at: datetime


class AssistantResponse(StrictModel):
    interaction_id: UUID
    recommendation_id: UUID
    ticket_id: UUID
    task_type: AssistantTask
    source: str
    provider: str
    model: str
    status: str
    confidence_band: ConfidenceBand
    fallback_reason: str | None
    recommendation: ResponseDraftOutput | TicketSummaryOutput
    feedback: FeedbackResponse | None
    created_at: datetime


class FeedbackMetrics(StrictModel):
    reviewed_recommendations: int
    accepted: int
    edited: int
    rejected: int
    regenerated: int
    acceptance_rate: float = Field(ge=0, le=1)
    edit_rate: float = Field(ge=0, le=1)
    rejection_rate: float = Field(ge=0, le=1)
    label: str
