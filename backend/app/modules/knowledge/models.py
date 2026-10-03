from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ArticleStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class KnowledgeCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_categories"
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        Index("uq_knowledge_categories_code_normalized", func.lower(code), unique=True),
        Index("uq_knowledge_categories_name_normalized", func.lower(name), unique=True),
    )


class KnowledgeArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_articles"
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    current_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "knowledge_article_versions.id",
            name="fk_knowledge_articles_current_version",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    published_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "knowledge_article_versions.id",
            name="fk_knowledge_articles_published_version",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'IN_REVIEW', 'PUBLISHED', 'ARCHIVED')",
            name="status_valid",
        ),
        Index("uq_knowledge_articles_slug_normalized", func.lower(slug), unique=True),
        Index("ix_knowledge_articles_status_updated", "status", "updated_at"),
    )


class KnowledgeArticleVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_article_versions"
    article_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "version",
            name="uq_knowledge_article_versions_article_version_unique",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_knowledge_versions_article_created", "article_id", "created_at"),
    )


class KnowledgeEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_events"
    article_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, object] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_knowledge_events_article_created", "article_id", "created_at"),)
