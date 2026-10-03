from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.knowledge.models import ArticleStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CategoryWrite(StrictModel):
    code: str = Field(min_length=2, max_length=48, pattern=r"^[A-Z0-9_]+$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class CategoryResponse(CategoryWrite):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ArticleContent(StrictModel):
    title: str = Field(min_length=3, max_length=240)
    summary: str = Field(min_length=3, max_length=1000)
    content: str = Field(min_length=10, max_length=100_000)
    change_summary: str = Field(min_length=3, max_length=500)


class ArticleCreate(ArticleContent):
    slug: str = Field(min_length=3, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category_id: UUID
    tags: list[Annotated[str, Field(min_length=1, max_length=48)]] = Field(
        default_factory=list, max_length=20
    )

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(tag.strip().lower() for tag in value))
        if any(not tag for tag in normalized):
            raise ValueError("Tags cannot be blank")
        return normalized


class ArticleVersionCreate(ArticleContent):
    category_id: UUID | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=48)]] | None = Field(
        default=None, max_length=20
    )

    @field_validator("tags")
    @classmethod
    def normalize_optional_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = list(dict.fromkeys(tag.strip().lower() for tag in value))
        if any(not tag for tag in normalized):
            raise ValueError("Tags cannot be blank")
        return normalized


class TransitionRequest(StrictModel):
    status: ArticleStatus
    reason: str = Field(min_length=3, max_length=500)


class Person(StrictModel):
    id: UUID
    display_name: str


class VersionResponse(StrictModel):
    id: UUID
    version: int
    title: str
    summary: str
    content: str
    change_summary: str
    author: Person
    created_at: datetime


class ArticleResponse(StrictModel):
    id: UUID
    slug: str
    category: CategoryResponse
    author: Person
    owner: Person
    status: ArticleStatus
    tags: list[str]
    version: VersionResponse
    published_version: int | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArticlePage(StrictModel):
    items: list[ArticleResponse]
    total: int
    offset: int
    limit: int


class EventResponse(StrictModel):
    id: UUID
    action: str
    actor: Person
    before_state: dict[str, object] | None
    after_state: dict[str, object] | None
    reason: str
    created_at: datetime
