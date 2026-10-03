from hashlib import sha256
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.ai.models import TicketEmbedding
from app.modules.ai.provider import ClassificationProvider, ProviderError
from app.modules.ai.rag import normalize_content
from app.modules.ai.repository import AIRepository, SimilarTicketRecord
from app.modules.ai.schemas import SimilarTicketItem, SimilarTicketResponse
from app.modules.ai.service import redact
from app.modules.tickets.models import Ticket
from app.modules.tickets.repository import TicketRepository
from app.modules.tickets.service import TicketService


def ticket_representation(ticket: Ticket, maximum_characters: int) -> tuple[str, str]:
    title, _ = redact(ticket.title)
    description, _ = redact(ticket.description)
    value = normalize_content(f"{title}\n{description[:maximum_characters]}")
    return value, sha256(value.encode()).hexdigest()


class SimilarTicketService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AIRepository(session)
        self.ticket_repository = TicketRepository(session)

    async def search(
        self, actor_id: UUID, ticket_id: UUID, provider: ClassificationProvider
    ) -> SimilarTicketResponse:
        ticket_service = TicketService(self.session)
        access = await ticket_service.access(actor_id)
        current_record = await self.ticket_repository.visible_ticket(ticket_id, access)
        if current_record is None:
            raise HTTPException(404, "Ticket not found")
        candidates = await self.repository.historical_ticket_candidates(
            access,
            ticket_id,
            limit=self.settings.similar_ticket_candidate_pool,
        )
        tickets = [current_record.ticket, *candidates]
        representations = {
            ticket.id: ticket_representation(ticket, self.settings.ai_max_input_characters)
            for ticket in tickets
        }
        existing = await self.repository.ticket_embeddings(
            [ticket.id for ticket in tickets], provider.name, provider.embedding_model
        )
        by_ticket = {item.ticket_id: item for item in existing}
        stale = [
            ticket
            for ticket in tickets
            if ticket.id not in by_ticket
            or by_ticket[ticket.id].representation_hash != representations[ticket.id][1]
        ]
        if stale:
            try:
                response = await provider.embed([representations[ticket.id][0] for ticket in stale])
            except ProviderError as error:
                await self.session.rollback()
                raise HTTPException(
                    503, f"Similar-ticket search unavailable: {error.code}"
                ) from error
            if len(response.embeddings) != len(stale):
                await self.session.rollback()
                raise HTTPException(503, "Embedding provider returned an invalid ticket batch")
            for ticket, vector in zip(stale, response.embeddings, strict=True):
                if len(vector) != self.settings.ai_embedding_dimensions:
                    await self.session.rollback()
                    raise HTTPException(
                        503, "Ticket embedding dimensions do not match configuration"
                    )
                embedding = by_ticket.get(ticket.id)
                if embedding is None:
                    embedding = TicketEmbedding(
                        ticket_id=ticket.id,
                        provider=provider.name,
                        model=provider.embedding_model,
                        dimensions=len(vector),
                        embedding=vector,
                        representation_hash=representations[ticket.id][1],
                        source_updated_at=ticket.updated_at,
                    )
                    self.session.add(embedding)
                    by_ticket[ticket.id] = embedding
                else:
                    embedding.embedding = vector
                    embedding.dimensions = len(vector)
                    embedding.representation_hash = representations[ticket.id][1]
                    embedding.source_updated_at = ticket.updated_at
            await self.session.flush()

        query_embedding = by_ticket.get(ticket_id)
        if query_embedding is None:
            raise HTTPException(503, "Current ticket embedding is unavailable")
        query_vector = [float(value) for value in query_embedding.embedding]
        matches = await self.repository.similar_tickets(
            access,
            ticket_id,
            query_vector,
            provider.name,
            provider.embedding_model,
            limit=self.settings.similar_ticket_top_k,
            minimum_similarity=self.settings.similar_ticket_min_similarity,
            scan_limit=self.settings.similar_ticket_candidate_pool,
        )
        await self.session.commit()
        return SimilarTicketResponse(
            ticket_id=ticket_id,
            provider=provider.name,
            model=provider.embedding_model,
            indexed_embeddings=len(stale),
            reused_embeddings=len(tickets) - len(stale),
            items=[self.item(match) for match in matches],
        )

    @staticmethod
    def item(match: SimilarTicketRecord) -> SimilarTicketItem:
        ticket = match.ticket
        return SimilarTicketItem(
            ticket_id=ticket.id,
            reference=ticket.reference,
            title=ticket.title,
            similarity=max(-1.0, min(1.0, match.similarity)),
            status=ticket.status,
            priority=ticket.priority,
            category=match.category.name if match.category else None,
            subcategory=match.subcategory.name if match.subcategory else None,
            resolution_summary=cast(str, ticket.resolution_summary),
            resolution_code=ticket.resolution_code,
            resolved_at=ticket.resolved_at,
            closed_at=ticket.closed_at,
        )
