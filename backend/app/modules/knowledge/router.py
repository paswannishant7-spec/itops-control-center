from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.access.dependencies import require_permission
from app.modules.identity.models import User
from app.modules.knowledge.models import ArticleStatus, KnowledgeArticleVersion, KnowledgeEvent
from app.modules.knowledge.repository import ArticleRecord, KnowledgeRepository
from app.modules.knowledge.schemas import (
    ArticleCreate,
    ArticlePage,
    ArticleResponse,
    ArticleVersionCreate,
    CategoryResponse,
    CategoryWrite,
    EventResponse,
    Person,
    TransitionRequest,
    VersionResponse,
)
from app.modules.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def person(user: User) -> Person:
    return Person(id=user.id, display_name=user.display_name)


def version_response(version: KnowledgeArticleVersion, author: User) -> VersionResponse:
    return VersionResponse(
        id=version.id,
        version=version.version,
        title=version.title,
        summary=version.summary,
        content=version.content,
        change_summary=version.change_summary,
        author=person(author),
        created_at=version.created_at,
    )


def article_response(record: ArticleRecord) -> ArticleResponse:
    article = record.article
    return ArticleResponse(
        id=article.id,
        slug=article.slug,
        category=CategoryResponse.model_validate(record.category, from_attributes=True),
        author=person(record.author),
        owner=person(record.owner),
        status=article.status,
        tags=article.tags,
        version=version_response(record.version, record.version_author),
        published_version=(
            record.version.version if article.published_version_id == record.version.id else None
        ),
        published_at=article.published_at,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


async def refreshed(service: KnowledgeService, actor_id: UUID, article_id: UUID) -> ArticleResponse:
    record, _ = await service.get(actor_id, article_id)
    return article_response(record)


@router.get("/categories", response_model=list[CategoryResponse])
async def categories(
    actor: Annotated[User, Depends(require_permission("knowledge:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CategoryResponse]:
    permissions = await KnowledgeService(session).permissions(actor.id)
    values = await KnowledgeRepository(session).categories(
        include_inactive="knowledge:publish" in permissions
    )
    return [CategoryResponse.model_validate(item, from_attributes=True) for item in values]


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryWrite,
    actor: Annotated[User, Depends(require_permission("knowledge:publish"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CategoryResponse:
    del actor
    value = await KnowledgeService(session).save_category(payload.model_dump())
    return CategoryResponse.model_validate(value, from_attributes=True)


@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def replace_category(
    category_id: UUID,
    payload: CategoryWrite,
    actor: Annotated[User, Depends(require_permission("knowledge:publish"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CategoryResponse:
    del actor
    value = await KnowledgeService(session).save_category(payload.model_dump(), category_id)
    return CategoryResponse.model_validate(value, from_attributes=True)


@router.get("/articles", response_model=ArticlePage)
async def articles(
    actor: Annotated[User, Depends(require_permission("knowledge:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    category_id: UUID | None = None,
    article_status: Annotated[ArticleStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ArticlePage:
    permissions = await KnowledgeService(session).permissions(actor.id)
    values, total = await KnowledgeRepository(session).articles(
        actor.id,
        permissions,
        search=search,
        category_id=category_id,
        status=article_status,
        offset=offset,
        limit=limit,
    )
    return ArticlePage(
        items=[article_response(item) for item in values], total=total, offset=offset, limit=limit
    )


@router.post("/articles", response_model=ArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_article(
    payload: ArticleCreate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("knowledge:create"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArticleResponse:
    service = KnowledgeService(session)
    article_id = await service.create_article(
        actor.id, payload.model_dump(), request.state.request_id
    )
    return await refreshed(service, actor.id, article_id)


@router.get("/articles/{article_id}", response_model=ArticleResponse)
async def article(
    article_id: UUID,
    actor: Annotated[User, Depends(require_permission("knowledge:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArticleResponse:
    return await refreshed(KnowledgeService(session), actor.id, article_id)


@router.post(
    "/articles/{article_id}/versions",
    response_model=ArticleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    article_id: UUID,
    payload: ArticleVersionCreate,
    request: Request,
    actor: Annotated[User, Depends(require_permission("knowledge:update"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArticleResponse:
    service = KnowledgeService(session)
    await service.add_version(actor.id, article_id, payload.model_dump(), request.state.request_id)
    return await refreshed(service, actor.id, article_id)


@router.get("/articles/{article_id}/versions", response_model=list[VersionResponse])
async def versions(
    article_id: UUID,
    actor: Annotated[User, Depends(require_permission("knowledge:update"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[VersionResponse]:
    service = KnowledgeService(session)
    await service.get(actor.id, article_id)
    return [
        version_response(version, author)
        for version, author in await KnowledgeRepository(session).versions(article_id)
    ]


@router.post("/articles/{article_id}/transitions", response_model=ArticleResponse)
async def transition(
    article_id: UUID,
    payload: TransitionRequest,
    request: Request,
    actor: Annotated[User, Depends(require_permission("knowledge:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArticleResponse:
    service = KnowledgeService(session)
    await service.transition(
        actor.id, article_id, payload.status, payload.reason, request.state.request_id
    )
    return await refreshed(service, actor.id, article_id)


@router.get("/articles/{article_id}/events", response_model=list[EventResponse])
async def events(
    article_id: UUID,
    actor: Annotated[User, Depends(require_permission("knowledge:review"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EventResponse]:
    await KnowledgeService(session).get(actor.id, article_id)
    values: list[EventResponse] = []
    for event, user in await KnowledgeRepository(session).events(article_id):
        assert isinstance(event, KnowledgeEvent)
        values.append(
            EventResponse(
                id=event.id,
                action=event.action,
                actor=person(user),
                before_state=event.before_state,
                after_state=event.after_state,
                reason=event.reason,
                created_at=event.created_at,
            )
        )
    return values
