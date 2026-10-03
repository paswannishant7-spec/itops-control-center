from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.access.dependencies import require_permission
from app.modules.ai.assistant import AssistantService
from app.modules.ai.provider import ClassificationProvider, classification_provider
from app.modules.ai.rag import RAGService
from app.modules.ai.schemas import (
    AssistantResponse,
    AssistantTask,
    ClassificationResponse,
    FeedbackCreate,
    FeedbackMetrics,
    FeedbackResponse,
    KnowledgeIndexResponse,
    SimilarTicketResponse,
    TroubleshootingResponse,
)
from app.modules.ai.service import AIService
from app.modules.ai.similar import SimilarTicketService
from app.modules.identity.models import User

router = APIRouter(prefix="/ai", tags=["AI assistance"])


def get_classification_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClassificationProvider:
    return classification_provider(settings)


@router.post(
    "/tickets/{ticket_id}/classifications",
    response_model=ClassificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def classify_ticket(
    ticket_id: UUID,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[ClassificationProvider, Depends(get_classification_provider)],
) -> ClassificationResponse:
    return await AIService(session, settings).classify(actor.id, ticket_id, provider)


@router.get(
    "/tickets/{ticket_id}/classifications/latest", response_model=ClassificationResponse | None
)
async def latest_classification(
    ticket_id: UUID,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClassificationResponse | None:
    return await AIService(session, settings).latest(actor.id, ticket_id)


@router.post(
    "/knowledge/{article_id}/index",
    response_model=KnowledgeIndexResponse,
    status_code=status.HTTP_201_CREATED,
)
async def index_published_article(
    article_id: UUID,
    actor: Annotated[User, Depends(require_permission("knowledge:publish"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[ClassificationProvider, Depends(get_classification_provider)],
) -> KnowledgeIndexResponse:
    del actor
    return await RAGService(session, settings).index_article(article_id, provider)


@router.post(
    "/tickets/{ticket_id}/troubleshooting",
    response_model=TroubleshootingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def troubleshoot_ticket(
    ticket_id: UUID,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[ClassificationProvider, Depends(get_classification_provider)],
) -> TroubleshootingResponse:
    return await RAGService(session, settings).troubleshoot(actor.id, ticket_id, provider)


@router.get(
    "/tickets/{ticket_id}/troubleshooting/latest",
    response_model=TroubleshootingResponse | None,
)
async def latest_troubleshooting(
    ticket_id: UUID,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TroubleshootingResponse | None:
    return await RAGService(session, settings).latest(actor.id, ticket_id)


@router.post(
    "/tickets/{ticket_id}/similar",
    response_model=SimilarTicketResponse,
)
async def similar_tickets(
    ticket_id: UUID,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[ClassificationProvider, Depends(get_classification_provider)],
) -> SimilarTicketResponse:
    return await SimilarTicketService(session, settings).search(actor.id, ticket_id, provider)


@router.post(
    "/tickets/{ticket_id}/assistant/{task_type}",
    response_model=AssistantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_assistant_output(
    ticket_id: UUID,
    task_type: AssistantTask,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[ClassificationProvider, Depends(get_classification_provider)],
) -> AssistantResponse:
    return await AssistantService(session, settings).generate(
        actor.id, ticket_id, task_type, provider
    )


@router.get(
    "/tickets/{ticket_id}/assistant/{task_type}/latest",
    response_model=AssistantResponse | None,
)
async def latest_assistant_output(
    ticket_id: UUID,
    task_type: AssistantTask,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssistantResponse | None:
    return await AssistantService(session, settings).latest(actor.id, ticket_id, task_type)


@router.post(
    "/tickets/{ticket_id}/recommendations/{recommendation_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def review_recommendation(
    ticket_id: UUID,
    recommendation_id: UUID,
    request: FeedbackCreate,
    actor: Annotated[User, Depends(require_permission("ai:use"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FeedbackResponse:
    return await AssistantService(session, settings).review(
        actor.id, ticket_id, recommendation_id, request
    )


@router.get("/feedback/metrics", response_model=FeedbackMetrics)
async def feedback_metrics(
    actor: Annotated[User, Depends(require_permission("analytics:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FeedbackMetrics:
    return await AssistantService(session, settings).metrics(actor.id)
