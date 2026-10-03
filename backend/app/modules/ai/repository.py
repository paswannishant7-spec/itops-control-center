from collections.abc import Iterable
from dataclasses import dataclass
from math import sqrt
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.models import (
    AIFeedback,
    AIInteraction,
    AIRecommendation,
    KnowledgeChunk,
    KnowledgeEmbedding,
    TicketEmbedding,
)
from app.modules.knowledge.models import KnowledgeArticle, KnowledgeArticleVersion
from app.modules.tickets.models import Ticket, TicketCategory, TicketComment, TicketSubcategory
from app.modules.tickets.repository import TicketAccess, TicketRepository


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: KnowledgeChunk
    article: KnowledgeArticle
    version: KnowledgeArticleVersion
    similarity: float


@dataclass(frozen=True)
class SimilarTicketRecord:
    ticket: Ticket
    category: TicketCategory | None
    subcategory: TicketSubcategory | None
    similarity: float


class AIRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_classification(
        self, ticket_id: UUID
    ) -> tuple[AIInteraction, AIRecommendation] | None:
        row = (
            await self.session.execute(
                select(AIInteraction, AIRecommendation)
                .join(AIRecommendation, AIRecommendation.interaction_id == AIInteraction.id)
                .where(
                    AIInteraction.ticket_id == ticket_id,
                    AIInteraction.task_type == "CLASSIFICATION",
                )
                .order_by(AIInteraction.created_at.desc(), AIInteraction.id.desc())
                .limit(1)
            )
        ).one_or_none()
        return cast(tuple[AIInteraction, AIRecommendation] | None, row)

    async def latest_troubleshooting(
        self, ticket_id: UUID
    ) -> tuple[AIInteraction, AIRecommendation] | None:
        row = (
            await self.session.execute(
                select(AIInteraction, AIRecommendation)
                .join(AIRecommendation, AIRecommendation.interaction_id == AIInteraction.id)
                .where(
                    AIInteraction.ticket_id == ticket_id,
                    AIInteraction.task_type == "TROUBLESHOOTING",
                )
                .order_by(AIInteraction.created_at.desc(), AIInteraction.id.desc())
                .limit(1)
            )
        ).one_or_none()
        return cast(tuple[AIInteraction, AIRecommendation] | None, row)

    async def latest_assistant(
        self, ticket_id: UUID, task_type: str
    ) -> tuple[AIInteraction, AIRecommendation] | None:
        row = (
            await self.session.execute(
                select(AIInteraction, AIRecommendation)
                .join(AIRecommendation, AIRecommendation.interaction_id == AIInteraction.id)
                .where(
                    AIInteraction.ticket_id == ticket_id,
                    AIInteraction.task_type == task_type,
                )
                .order_by(AIInteraction.created_at.desc(), AIInteraction.id.desc())
                .limit(1)
            )
        ).one_or_none()
        return cast(tuple[AIInteraction, AIRecommendation] | None, row)

    async def public_comments(self, ticket_id: UUID, limit: int) -> list[TicketComment]:
        newest = list(
            await self.session.scalars(
                select(TicketComment)
                .where(
                    TicketComment.ticket_id == ticket_id,
                    TicketComment.visibility == "PUBLIC",
                )
                .order_by(TicketComment.created_at.desc(), TicketComment.id.desc())
                .limit(limit)
            )
        )
        return list(reversed(newest))

    async def recommendation(
        self, ticket_id: UUID, recommendation_id: UUID
    ) -> tuple[AIInteraction, AIRecommendation] | None:
        row = (
            await self.session.execute(
                select(AIInteraction, AIRecommendation)
                .join(AIRecommendation, AIRecommendation.interaction_id == AIInteraction.id)
                .where(
                    AIRecommendation.id == recommendation_id,
                    AIRecommendation.ticket_id == ticket_id,
                    AIInteraction.ticket_id == ticket_id,
                )
            )
        ).one_or_none()
        return cast(tuple[AIInteraction, AIRecommendation] | None, row)

    async def feedback(self, recommendation_id: UUID) -> AIFeedback | None:
        return cast(
            AIFeedback | None,
            await self.session.scalar(
                select(AIFeedback).where(AIFeedback.recommendation_id == recommendation_id)
            ),
        )

    async def feedback_counts(self) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(AIFeedback.action, func.count(AIFeedback.id)).group_by(AIFeedback.action)
            )
        ).all()
        return {str(action): int(count) for action, count in rows}

    async def published_version(
        self, article_id: UUID
    ) -> tuple[KnowledgeArticle, KnowledgeArticleVersion] | None:
        row = (
            await self.session.execute(
                select(KnowledgeArticle, KnowledgeArticleVersion)
                .join(
                    KnowledgeArticleVersion,
                    KnowledgeArticleVersion.id == KnowledgeArticle.published_version_id,
                )
                .where(
                    KnowledgeArticle.id == article_id,
                    KnowledgeArticle.status == "PUBLISHED",
                )
            )
        ).one_or_none()
        return cast(tuple[KnowledgeArticle, KnowledgeArticleVersion] | None, row)

    async def chunks_for_version(self, version_id: UUID) -> list[KnowledgeChunk]:
        return list(
            await self.session.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.version_id == version_id)
                .order_by(KnowledgeChunk.ordinal)
            )
        )

    async def embeddings_for_chunks(
        self, chunk_ids: list[UUID], provider: str, model: str
    ) -> list[KnowledgeEmbedding]:
        if not chunk_ids:
            return []
        return list(
            await self.session.scalars(
                select(KnowledgeEmbedding).where(
                    KnowledgeEmbedding.chunk_id.in_(chunk_ids),
                    KnowledgeEmbedding.provider == provider,
                    KnowledgeEmbedding.model == model,
                )
            )
        )

    async def retrieve(
        self,
        query_vector: list[float],
        provider: str,
        model: str,
        *,
        limit: int,
        minimum_similarity: float,
    ) -> list[RetrievedChunk]:
        criteria = (
            KnowledgeArticle.status == "PUBLISHED",
            KnowledgeArticle.published_version_id == KnowledgeChunk.version_id,
            KnowledgeEmbedding.provider == provider,
            KnowledgeEmbedding.model == model,
        )
        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""
        base = (
            select(KnowledgeChunk, KnowledgeArticle, KnowledgeArticleVersion, KnowledgeEmbedding)
            .join(KnowledgeEmbedding, KnowledgeEmbedding.chunk_id == KnowledgeChunk.id)
            .join(KnowledgeArticle, KnowledgeArticle.id == KnowledgeChunk.article_id)
            .join(KnowledgeArticleVersion, KnowledgeArticleVersion.id == KnowledgeChunk.version_id)
            .where(*criteria)
        )
        if dialect == "postgresql":
            distance = KnowledgeEmbedding.embedding.cosine_distance(query_vector)
            rows = (
                await self.session.execute(
                    select(
                        KnowledgeChunk,
                        KnowledgeArticle,
                        KnowledgeArticleVersion,
                        (1 - distance).label("similarity"),
                    )
                    .join(KnowledgeEmbedding, KnowledgeEmbedding.chunk_id == KnowledgeChunk.id)
                    .join(KnowledgeArticle, KnowledgeArticle.id == KnowledgeChunk.article_id)
                    .join(
                        KnowledgeArticleVersion,
                        KnowledgeArticleVersion.id == KnowledgeChunk.version_id,
                    )
                    .where(*criteria, (1 - distance) >= minimum_similarity)
                    .order_by(distance, KnowledgeChunk.id)
                    .limit(limit)
                )
            ).all()
            return [RetrievedChunk(row[0], row[1], row[2], float(row[3])) for row in rows]

        # SQLite exists only for deterministic local tests. Bound the candidate set; production
        # PostgreSQL always performs indexed pgvector distance ordering in the database.
        rows = (await self.session.execute(base.limit(200))).all()

        def cosine(vector: object) -> float:
            values = [float(value) for value in cast(Iterable[float], vector)]
            denominator = sqrt(sum(v * v for v in values)) * sqrt(sum(v * v for v in query_vector))
            return (
                sum(a * b for a, b in zip(values, query_vector, strict=True)) / denominator
                if denominator
                else 0.0
            )

        ranked = [RetrievedChunk(row[0], row[1], row[2], cosine(row[3].embedding)) for row in rows]
        return [
            item
            for item in sorted(ranked, key=lambda item: (-item.similarity, str(item.chunk.id)))
            if item.similarity >= minimum_similarity
        ][:limit]

    async def historical_ticket_candidates(
        self, access: TicketAccess, current_ticket_id: UUID, *, limit: int
    ) -> list[Ticket]:
        visibility = TicketRepository(self.session).access_predicate(access)
        return list(
            await self.session.scalars(
                select(Ticket)
                .where(
                    Ticket.id != current_ticket_id,
                    Ticket.status.in_(("RESOLVED", "CLOSED")),
                    Ticket.resolution_summary.is_not(None),
                    visibility,
                )
                .order_by(Ticket.resolved_at.desc(), Ticket.updated_at.desc(), Ticket.id.desc())
                .limit(limit)
            )
        )

    async def ticket_embeddings(
        self, ticket_ids: list[UUID], provider: str, model: str
    ) -> list[TicketEmbedding]:
        if not ticket_ids:
            return []
        return list(
            await self.session.scalars(
                select(TicketEmbedding).where(
                    TicketEmbedding.ticket_id.in_(ticket_ids),
                    TicketEmbedding.provider == provider,
                    TicketEmbedding.model == model,
                )
            )
        )

    async def similar_tickets(
        self,
        access: TicketAccess,
        current_ticket_id: UUID,
        query_vector: list[float],
        provider: str,
        model: str,
        *,
        limit: int,
        minimum_similarity: float,
        scan_limit: int,
    ) -> list[SimilarTicketRecord]:
        visibility = TicketRepository(self.session).access_predicate(access)
        criteria = (
            Ticket.id != current_ticket_id,
            Ticket.status.in_(("RESOLVED", "CLOSED")),
            Ticket.resolution_summary.is_not(None),
            TicketEmbedding.provider == provider,
            TicketEmbedding.model == model,
            visibility,
        )
        joins = (
            select(Ticket, TicketCategory, TicketSubcategory, TicketEmbedding)
            .join(TicketEmbedding, TicketEmbedding.ticket_id == Ticket.id)
            .outerjoin(TicketCategory, TicketCategory.id == Ticket.category_id)
            .outerjoin(TicketSubcategory, TicketSubcategory.id == Ticket.subcategory_id)
            .where(*criteria)
        )
        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""
        if dialect == "postgresql":
            distance = TicketEmbedding.embedding.cosine_distance(query_vector)
            rows = (
                await self.session.execute(
                    select(
                        Ticket,
                        TicketCategory,
                        TicketSubcategory,
                        (1 - distance).label("similarity"),
                    )
                    .join(TicketEmbedding, TicketEmbedding.ticket_id == Ticket.id)
                    .outerjoin(TicketCategory, TicketCategory.id == Ticket.category_id)
                    .outerjoin(TicketSubcategory, TicketSubcategory.id == Ticket.subcategory_id)
                    .where(*criteria, (1 - distance) >= minimum_similarity)
                    .order_by(distance, Ticket.id)
                    .limit(limit)
                )
            ).all()
            return [SimilarTicketRecord(row[0], row[1], row[2], float(row[3])) for row in rows]

        rows = (await self.session.execute(joins.limit(scan_limit))).all()

        def cosine(vector: object) -> float:
            values = [float(value) for value in cast(Iterable[float], vector)]
            denominator = sqrt(sum(v * v for v in values)) * sqrt(sum(v * v for v in query_vector))
            return (
                sum(a * b for a, b in zip(values, query_vector, strict=True)) / denominator
                if denominator
                else 0.0
            )

        ranked = [
            SimilarTicketRecord(row[0], row[1], row[2], cosine(row[3].embedding)) for row in rows
        ]
        return [
            item
            for item in sorted(ranked, key=lambda item: (-item.similarity, str(item.ticket.id)))
            if item.similarity >= minimum_similarity
        ][:limit]
