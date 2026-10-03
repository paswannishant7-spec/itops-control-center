from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class InteractionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FALLBACK = "FALLBACK"


class RecommendationSource(StrEnum):
    MODEL = "MODEL"
    FALLBACK = "FALLBACK"


class FeedbackAction(StrEnum):
    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"
    REGENERATED = "REGENERATED"


class AIInteraction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_interactions"
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(160))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('CLASSIFICATION', 'TROUBLESHOOTING', 'RESPONSE_DRAFT', 'SUMMARIZATION')",
            name="task_type_valid",
        ),
        CheckConstraint("status IN ('SUCCEEDED', 'FALLBACK')", name="status_valid"),
        CheckConstraint("attempts > 0 AND attempts <= 2", name="attempts_valid"),
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        Index("ix_ai_interactions_ticket_created", "ticket_id", "created_at"),
    )


class AIRecommendation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_recommendations"
    interaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_interactions.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    output_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "output_type IN ('CLASSIFICATION', 'TROUBLESHOOTING', "
            "'RESPONSE_DRAFT', 'SUMMARIZATION')",
            name="output_type_valid",
        ),
        CheckConstraint("source IN ('MODEL', 'FALLBACK')", name="source_valid"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_valid"),
        Index("ix_ai_recommendations_ticket_created", "ticket_id", "created_at"),
    )


class AIFeedback(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_feedback"
    interaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_interactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recommendation_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_recommendations.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    feedback_text: Mapped[str | None] = mapped_column(String(1000))
    edited_content: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    output_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "action IN ('ACCEPTED', 'EDITED', 'REJECTED', 'REGENERATED')",
            name="action_valid",
        ),
        CheckConstraint(
            "output_type IN ('CLASSIFICATION', 'TROUBLESHOOTING', "
            "'RESPONSE_DRAFT', 'SUMMARIZATION')",
            name="output_type_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_valid"),
        CheckConstraint(
            "(action = 'EDITED' AND edited_content IS NOT NULL) OR "
            "(action <> 'EDITED' AND edited_content IS NULL)",
            name="edited_content_valid",
        ),
        Index("ix_ai_feedback_ticket_created", "ticket_id", "created_at"),
    )


class KnowledgeChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_chunks"
    article_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_article_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "version_id", "ordinal", name="uq_knowledge_chunks_version_ordinal_unique"
        ),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("character_count > 0", name="character_count_positive"),
        Index("ix_knowledge_chunks_article_version", "article_id", "version_id"),
    )


class KnowledgeEmbedding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_embeddings"
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "provider",
            "model",
            name="uq_knowledge_embeddings_chunk_provider_model_unique",
        ),
        CheckConstraint("dimensions = 1536", name="dimensions_supported"),
        Index(
            "ix_knowledge_embeddings_vector_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class TicketEmbedding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ticket_embeddings"
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    representation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "provider",
            "model",
            name="uq_ticket_embeddings_ticket_provider_model_unique",
        ),
        CheckConstraint("dimensions = 1536", name="dimensions_supported"),
        Index(
            "ix_ticket_embeddings_vector_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
