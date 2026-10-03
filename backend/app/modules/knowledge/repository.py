from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import ColumnElement, Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.identity.models import User
from app.modules.knowledge.models import (
    KnowledgeArticle,
    KnowledgeArticleVersion,
    KnowledgeCategory,
    KnowledgeEvent,
)


@dataclass(frozen=True)
class ArticleRecord:
    article: KnowledgeArticle
    version: KnowledgeArticleVersion
    category: KnowledgeCategory
    author: User
    owner: User
    version_author: User


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def visibility(user_id: UUID, permissions: frozenset[str]) -> ColumnElement[bool]:
        if permissions & {"knowledge:review", "knowledge:publish", "knowledge:archive"}:
            return KnowledgeArticle.id.is_not(None)
        return or_(
            KnowledgeArticle.status == "PUBLISHED",
            KnowledgeArticle.owner_id == user_id if "knowledge:update" in permissions else false(),
        )

    def statement(self) -> Select[Any]:
        author = aliased(User, name="knowledge_author")
        owner = aliased(User, name="knowledge_owner")
        version_author = aliased(User, name="knowledge_version_author")
        return (
            select(
                KnowledgeArticle,
                KnowledgeArticleVersion,
                KnowledgeCategory,
                author,
                owner,
                version_author,
            )
            .join(
                KnowledgeArticleVersion,
                KnowledgeArticleVersion.id == KnowledgeArticle.current_version_id,
            )
            .join(KnowledgeCategory, KnowledgeCategory.id == KnowledgeArticle.category_id)
            .join(author, author.id == KnowledgeArticle.author_id)
            .join(owner, owner.id == KnowledgeArticle.owner_id)
            .join(version_author, version_author.id == KnowledgeArticleVersion.author_id)
        )

    @staticmethod
    def record(row: Any) -> ArticleRecord:
        return ArticleRecord(row[0], row[1], row[2], row[3], row[4], row[5])

    async def articles(
        self,
        user_id: UUID,
        permissions: frozenset[str],
        *,
        search: str | None,
        category_id: UUID | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ArticleRecord], int]:
        criteria = [self.visibility(user_id, permissions)]
        if search:
            term = f"%{search.strip()}%"
            criteria.append(
                or_(
                    KnowledgeArticle.slug.ilike(term),
                    KnowledgeArticleVersion.title.ilike(term),
                    KnowledgeArticleVersion.summary.ilike(term),
                    KnowledgeArticleVersion.content.ilike(term),
                )
            )
        if category_id:
            criteria.append(KnowledgeArticle.category_id == category_id)
        if status:
            criteria.append(KnowledgeArticle.status == status)
        count_from = KnowledgeArticle.__table__.join(
            KnowledgeArticleVersion,
            KnowledgeArticleVersion.id == KnowledgeArticle.current_version_id,
        )
        total = int(
            await self.session.scalar(select(func.count()).select_from(count_from).where(*criteria))
            or 0
        )
        rows = (
            await self.session.execute(
                self.statement()
                .where(*criteria)
                .order_by(KnowledgeArticle.updated_at.desc(), KnowledgeArticle.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [self.record(row) for row in rows], total

    async def article(
        self, article_id: UUID, user_id: UUID, permissions: frozenset[str], *, lock: bool = False
    ) -> ArticleRecord | None:
        statement = self.statement().where(
            KnowledgeArticle.id == article_id, self.visibility(user_id, permissions)
        )
        if lock:
            statement = statement.with_for_update(of=KnowledgeArticle)
        row = (await self.session.execute(statement)).one_or_none()
        return self.record(row) if row else None

    async def category(
        self, category_id: UUID, *, active_only: bool = False
    ) -> KnowledgeCategory | None:
        criteria = [KnowledgeCategory.id == category_id]
        if active_only:
            criteria.append(KnowledgeCategory.is_active.is_(True))
        return cast(
            KnowledgeCategory | None,
            await self.session.scalar(select(KnowledgeCategory).where(*criteria)),
        )

    async def categories(self, *, include_inactive: bool) -> list[KnowledgeCategory]:
        statement = select(KnowledgeCategory)
        if not include_inactive:
            statement = statement.where(KnowledgeCategory.is_active.is_(True))
        return list(
            await self.session.scalars(
                statement.order_by(KnowledgeCategory.name, KnowledgeCategory.id)
            )
        )

    async def versions(self, article_id: UUID) -> list[tuple[KnowledgeArticleVersion, User]]:
        rows = (
            await self.session.execute(
                select(KnowledgeArticleVersion, User)
                .join(User, User.id == KnowledgeArticleVersion.author_id)
                .where(KnowledgeArticleVersion.article_id == article_id)
                .order_by(KnowledgeArticleVersion.version.desc())
            )
        ).all()
        return [(row[0], row[1]) for row in rows]

    async def events(self, article_id: UUID) -> list[tuple[KnowledgeEvent, User]]:
        rows = (
            await self.session.execute(
                select(KnowledgeEvent, User)
                .join(User, User.id == KnowledgeEvent.actor_id)
                .where(KnowledgeEvent.article_id == article_id)
                .order_by(KnowledgeEvent.created_at, KnowledgeEvent.id)
            )
        ).all()
        return [(row[0], row[1]) for row in rows]
