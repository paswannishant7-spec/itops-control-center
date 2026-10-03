from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.repository import AccessRepository
from app.modules.knowledge.models import (
    ArticleStatus,
    KnowledgeArticle,
    KnowledgeArticleVersion,
    KnowledgeCategory,
    KnowledgeEvent,
)
from app.modules.knowledge.repository import ArticleRecord, KnowledgeRepository

LEGAL_TRANSITIONS: dict[ArticleStatus, frozenset[ArticleStatus]] = {
    ArticleStatus.DRAFT: frozenset({ArticleStatus.IN_REVIEW}),
    ArticleStatus.IN_REVIEW: frozenset({ArticleStatus.DRAFT, ArticleStatus.PUBLISHED}),
    ArticleStatus.PUBLISHED: frozenset({ArticleStatus.ARCHIVED}),
    ArticleStatus.ARCHIVED: frozenset({ArticleStatus.DRAFT}),
}


def article_state(article: KnowledgeArticle) -> dict[str, object]:
    return {
        "status": article.status,
        "category_id": str(article.category_id),
        "current_version_id": str(article.current_version_id)
        if article.current_version_id
        else None,
        "published_version_id": (
            str(article.published_version_id) if article.published_version_id else None
        ),
    }


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = KnowledgeRepository(session)

    async def permissions(self, user_id: UUID) -> frozenset[str]:
        _, grants = await AccessRepository(self.session).grants(user_id)
        return frozenset(grants)

    async def save_category(
        self, values: dict[str, object], category_id: UUID | None = None
    ) -> KnowledgeCategory:
        category = await self.repository.category(category_id) if category_id is not None else None
        if category_id is not None and category is None:
            raise HTTPException(404, "Knowledge category not found")
        if category is None:
            category = KnowledgeCategory()
            self.session.add(category)
        for key, value in values.items():
            setattr(category, key, value)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise HTTPException(409, "Knowledge category code or name already exists") from error
        await self.session.refresh(category)
        return category

    def event(
        self,
        article: KnowledgeArticle,
        actor_id: UUID,
        action: str,
        before: dict[str, object] | None,
        reason: str,
        request_id: str,
    ) -> None:
        self.session.add(
            KnowledgeEvent(
                article_id=article.id,
                actor_id=actor_id,
                action=action,
                before_state=before,
                after_state=article_state(article),
                reason=reason,
                request_id=request_id[:128],
                created_at=datetime.now(UTC),
            )
        )

    async def create_article(
        self, actor_id: UUID, values: dict[str, object], request_id: str
    ) -> UUID:
        category_id = values.pop("category_id")
        assert isinstance(category_id, UUID)
        if await self.repository.category(category_id, active_only=True) is None:
            raise HTTPException(422, "An active knowledge category is required")
        article = KnowledgeArticle(
            slug=values.pop("slug"),
            category_id=category_id,
            author_id=actor_id,
            owner_id=actor_id,
            status=ArticleStatus.DRAFT,
            tags=values.pop("tags"),
        )
        self.session.add(article)
        await self.session.flush()
        version = KnowledgeArticleVersion(
            article_id=article.id, version=1, author_id=actor_id, **values
        )
        self.session.add(version)
        await self.session.flush()
        article.current_version_id = version.id
        self.event(article, actor_id, "knowledge.created", None, "Initial draft", request_id)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise HTTPException(409, "Article slug already exists") from error
        return article.id

    async def get(
        self, actor_id: UUID, article_id: UUID, *, lock: bool = False
    ) -> tuple[ArticleRecord, frozenset[str]]:
        permissions = await self.permissions(actor_id)
        record = await self.repository.article(article_id, actor_id, permissions, lock=lock)
        if record is None:
            raise HTTPException(404, "Knowledge article not found")
        return record, permissions

    async def add_version(
        self,
        actor_id: UUID,
        article_id: UUID,
        values: dict[str, object],
        request_id: str,
    ) -> UUID:
        record, permissions = await self.get(actor_id, article_id, lock=True)
        if "knowledge:update" not in permissions:
            raise HTTPException(403, "Permission denied")
        article = record.article
        if article.owner_id != actor_id and "knowledge:review" not in permissions:
            raise HTTPException(403, "Only the owner or a reviewer can revise this article")
        if article.status != ArticleStatus.DRAFT:
            raise HTTPException(409, "Only draft articles can be revised")
        category_id = values.pop("category_id", None)
        if category_id is not None:
            assert isinstance(category_id, UUID)
            if await self.repository.category(category_id, active_only=True) is None:
                raise HTTPException(422, "An active knowledge category is required")
            article.category_id = category_id
        tags = values.pop("tags", None)
        if tags is not None:
            article.tags = cast(list[str], tags)
        before = article_state(article)
        version = KnowledgeArticleVersion(
            article_id=article.id,
            version=record.version.version + 1,
            author_id=actor_id,
            **values,
        )
        self.session.add(version)
        await self.session.flush()
        article.current_version_id = version.id
        self.event(
            article,
            actor_id,
            "knowledge.version_created",
            before,
            version.change_summary,
            request_id,
        )
        await self.session.commit()
        return article.id

    async def transition(
        self,
        actor_id: UUID,
        article_id: UUID,
        target: ArticleStatus,
        reason: str,
        request_id: str,
    ) -> UUID:
        record, permissions = await self.get(actor_id, article_id, lock=True)
        article = record.article
        current = ArticleStatus(article.status)
        if target not in LEGAL_TRANSITIONS[current]:
            raise HTTPException(409, f"Cannot transition article from {current} to {target}")
        required = {
            ArticleStatus.IN_REVIEW: "knowledge:update",
            ArticleStatus.PUBLISHED: "knowledge:publish",
            ArticleStatus.ARCHIVED: "knowledge:archive",
            ArticleStatus.DRAFT: "knowledge:review",
        }[target]
        if required not in permissions:
            raise HTTPException(403, "Permission denied")
        if target == ArticleStatus.IN_REVIEW and article.owner_id != actor_id:
            raise HTTPException(403, "Only the owner can submit this article")
        before = article_state(article)
        article.status = target
        if target == ArticleStatus.PUBLISHED:
            article.published_version_id = article.current_version_id
            article.published_at = datetime.now(UTC)
        elif current == ArticleStatus.ARCHIVED:
            article.published_version_id = None
            article.published_at = None
        self.event(
            article, actor_id, f"knowledge.{target.value.lower()}", before, reason, request_id
        )
        await self.session.commit()
        return article.id
