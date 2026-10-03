import json
import re
from hashlib import sha256
from time import monotonic
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.ai.models import (
    AIInteraction,
    AIRecommendation,
    InteractionStatus,
    KnowledgeChunk,
    KnowledgeEmbedding,
    RecommendationSource,
)
from app.modules.ai.provider import ClassificationProvider, ProviderError, ProviderResponse
from app.modules.ai.repository import AIRepository, RetrievedChunk
from app.modules.ai.schemas import (
    KnowledgeCitation,
    KnowledgeIndexResponse,
    TroubleshootingOutput,
    TroubleshootingResponse,
)
from app.modules.ai.service import confidence_band, redact
from app.modules.tickets.models import Ticket
from app.modules.tickets.service import TicketService

PROMPT_VERSION = "knowledge-troubleshooting-v1"


def normalize_content(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def chunk_content(value: str, maximum: int, overlap: int) -> list[str]:
    normalized = normalize_content(value)
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + maximum, len(normalized))
        if end < len(normalized):
            split = max(
                normalized.rfind("\n\n", start + maximum // 2, end),
                normalized.rfind(". ", start + maximum // 2, end),
                normalized.rfind(" ", start + maximum // 2, end),
            )
            if split > start:
                end = split + (1 if normalized[split] == "." else 0)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def troubleshooting_fallback(reason: str) -> TroubleshootingOutput:
    summary = (
        "No relevant published knowledge was found."
        if reason == "no_knowledge_matches"
        else "Knowledge-grounded troubleshooting is temporarily unavailable."
    )
    return TroubleshootingOutput(
        summary=summary,
        known_facts=[],
        possible_causes=[],
        recommended_actions=[
            "Review the ticket with a technician and follow approved operational procedures."
        ],
        uncertain_assumptions=[],
        cited_chunk_ids=[],
        confidence=0.0,
    )


class RAGService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AIRepository(session)

    async def index_article(
        self, article_id: UUID, provider: ClassificationProvider
    ) -> KnowledgeIndexResponse:
        record = await self.repository.published_version(article_id)
        if record is None:
            raise HTTPException(
                409, "Only the published version of a published article can be indexed"
            )
        article, version = record
        existing_chunks = await self.repository.chunks_for_version(version.id)
        if not existing_chunks:
            combined = f"{version.title}\n\n{version.summary}\n\n{version.content}"
            minimized, _ = redact(normalize_content(combined))
            values = chunk_content(
                minimized,
                self.settings.rag_chunk_characters,
                self.settings.rag_chunk_overlap_characters,
            )
            if not values:
                raise HTTPException(422, "Published article has no indexable content")
            existing_chunks = [
                KnowledgeChunk(
                    article_id=article.id,
                    version_id=version.id,
                    ordinal=ordinal,
                    content=value,
                    content_hash=sha256(value.encode()).hexdigest(),
                    character_count=len(value),
                )
                for ordinal, value in enumerate(values)
            ]
            self.session.add_all(existing_chunks)
            await self.session.flush()

        existing_embeddings = await self.repository.embeddings_for_chunks(
            [chunk.id for chunk in existing_chunks], provider.name, provider.embedding_model
        )
        embedded_chunk_ids = {item.chunk_id for item in existing_embeddings}
        missing = [chunk for chunk in existing_chunks if chunk.id not in embedded_chunk_ids]
        if missing:
            try:
                response = await provider.embed([chunk.content for chunk in missing])
            except ProviderError as error:
                await self.session.rollback()
                raise HTTPException(
                    503, f"Knowledge embedding unavailable: {error.code}"
                ) from error
            if len(response.embeddings) != len(missing):
                await self.session.rollback()
                raise HTTPException(503, "Knowledge embedding provider returned an invalid batch")
            for chunk, vector in zip(missing, response.embeddings, strict=True):
                if len(vector) != self.settings.ai_embedding_dimensions:
                    await self.session.rollback()
                    raise HTTPException(
                        503, "Knowledge embedding dimensions do not match configuration"
                    )
                self.session.add(
                    KnowledgeEmbedding(
                        chunk_id=chunk.id,
                        provider=provider.name,
                        model=provider.embedding_model,
                        dimensions=len(vector),
                        embedding=vector,
                        content_hash=chunk.content_hash,
                    )
                )
        await self.session.commit()
        return KnowledgeIndexResponse(
            article_id=article.id,
            version_id=version.id,
            article_version=version.version,
            chunks=len(existing_chunks),
            embeddings_created=len(missing),
            embeddings_reused=len(existing_embeddings),
            provider=provider.name,
            model=provider.embedding_model,
        )

    @staticmethod
    def citation(item: RetrievedChunk) -> KnowledgeCitation:
        return KnowledgeCitation(
            article_id=item.article.id,
            version_id=item.version.id,
            chunk_id=item.chunk.id,
            article_slug=item.article.slug,
            article_title=item.version.title,
            article_version=item.version.version,
            chunk_ordinal=item.chunk.ordinal,
            excerpt=item.chunk.content[:400],
            similarity=max(-1.0, min(1.0, item.similarity)),
        )

    def minimized_query(self, ticket: Ticket) -> tuple[str, dict[str, object]]:
        title, title_redactions = redact(ticket.title)
        description, description_redactions = redact(ticket.description)
        description = description[: self.settings.ai_max_input_characters]
        query = normalize_content(f"{title}\n{description}")
        return query, {
            "query_characters": len(query),
            "redactions": title_redactions + description_redactions,
        }

    async def troubleshoot(
        self, actor_id: UUID, ticket_id: UUID, provider: ClassificationProvider
    ) -> TroubleshootingResponse:
        ticket = (await TicketService(self.session).get_ticket(actor_id, ticket_id)).ticket
        query, metadata = self.minimized_query(ticket)
        request_hash = sha256(query.encode()).hexdigest()
        started = monotonic()
        error_code: str | None = None
        provider_response: ProviderResponse | None = None
        retrieved: list[RetrievedChunk] = []
        result: TroubleshootingOutput | None = None
        attempts = 1
        input_tokens: int | None = None
        try:
            embedding = await provider.embed([query])
            if (
                len(embedding.embeddings) != 1
                or len(embedding.embeddings[0]) != self.settings.ai_embedding_dimensions
            ):
                raise ProviderError("invalid_embedding_output")
            input_tokens = embedding.input_tokens
            retrieved = await self.repository.retrieve(
                embedding.embeddings[0],
                provider.name,
                provider.embedding_model,
                limit=self.settings.rag_top_k,
                minimum_similarity=self.settings.rag_min_similarity,
            )
            metadata["retrieved_chunks"] = len(retrieved)
            metadata["embedding_model"] = provider.embedding_model
            if not retrieved:
                error_code = "no_knowledge_matches"
            else:
                untrusted_chunks = [
                    {
                        "chunk_id": str(item.chunk.id),
                        "article_title": redact(item.version.title)[0],
                        "article_version": item.version.version,
                        "content": item.chunk.content,
                    }
                    for item in retrieved
                ]
                minimized: dict[str, object] = {
                    "untrusted_ticket": {"content": query},
                    "untrusted_knowledge_chunks": untrusted_chunks,
                }
                request_hash = sha256(
                    json.dumps(minimized, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                allowed_ids = {item.chunk.id for item in retrieved}
                for attempt in range(1, 3):
                    attempts = attempt
                    try:
                        provider_response = await provider.troubleshoot(
                            minimized,
                            cast(dict[str, object], TroubleshootingOutput.model_json_schema()),
                        )
                        candidate = TroubleshootingOutput.model_validate(provider_response.output)
                        cited = set(candidate.cited_chunk_ids)
                        if not cited or not cited.issubset(allowed_ids):
                            raise ValueError("Citations must reference retrieved chunks")
                        result = candidate
                        break
                    except (ValidationError, ValueError):
                        error_code = "invalid_citations_or_output"
                        provider_response = None
                    except ProviderError as error:
                        error_code = error.code
                        provider_response = None
                        if not error.retryable:
                            break
        except ProviderError as error:
            error_code = error.code

        result = result or troubleshooting_fallback(error_code or "provider_unavailable")
        source = RecommendationSource.MODEL if provider_response else RecommendationSource.FALLBACK
        status = InteractionStatus.SUCCEEDED if provider_response else InteractionStatus.FALLBACK
        citations = [
            self.citation(item) for item in retrieved if item.chunk.id in result.cited_chunk_ids
        ]
        interaction = AIInteraction(
            ticket_id=ticket_id,
            actor_id=actor_id,
            task_type="TROUBLESHOOTING",
            provider=provider.name,
            model=provider.model,
            status=status,
            prompt_version=PROMPT_VERSION,
            request_hash=request_hash,
            input_metadata=metadata,
            provider_request_id=provider_response.request_id if provider_response else None,
            attempts=attempts,
            latency_ms=max(0, int((monotonic() - started) * 1000)),
            input_tokens=(provider_response.input_tokens if provider_response else input_tokens),
            output_tokens=provider_response.output_tokens if provider_response else None,
            error_code=error_code if status == InteractionStatus.FALLBACK else None,
        )
        self.session.add(interaction)
        await self.session.flush()
        recommendation = AIRecommendation(
            interaction_id=interaction.id,
            ticket_id=ticket_id,
            output_type="TROUBLESHOOTING",
            source=source,
            confidence=result.confidence,
            payload={
                "recommendation": result.model_dump(mode="json"),
                "citations": [citation.model_dump(mode="json") for citation in citations],
            },
        )
        self.session.add(recommendation)
        await self.session.commit()
        await self.session.refresh(interaction)
        return self.response(interaction, recommendation)

    def response(
        self, interaction: AIInteraction, recommendation: AIRecommendation
    ) -> TroubleshootingResponse:
        payload = recommendation.payload
        result = TroubleshootingOutput.model_validate(payload["recommendation"])
        citation_values = cast(list[object], payload["citations"])
        citations = [KnowledgeCitation.model_validate(value) for value in citation_values]
        return TroubleshootingResponse(
            interaction_id=interaction.id,
            ticket_id=interaction.ticket_id,
            source=recommendation.source,
            provider=interaction.provider,
            model=interaction.model,
            status=interaction.status,
            confidence_band=confidence_band(result.confidence, self.settings),
            fallback_reason=interaction.error_code,
            recommendation=result,
            citations=citations,
            created_at=interaction.created_at,
        )

    async def latest(self, actor_id: UUID, ticket_id: UUID) -> TroubleshootingResponse | None:
        await TicketService(self.session).get_ticket(actor_id, ticket_id)
        value = await self.repository.latest_troubleshooting(ticket_id)
        return self.response(*value) if value else None
