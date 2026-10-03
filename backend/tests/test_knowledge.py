"""Phase 8 knowledge-base lifecycle and permission tests."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.modules.access.catalog import PERMISSIONS, ROLE_PERMISSIONS
from app.modules.access.models import Permission, Role, RolePermission, UserRole
from app.modules.identity.models import RefreshSession, User, UserStatus
from app.modules.identity.security import PasswordService, TokenService
from app.modules.knowledge.models import (
    ArticleStatus,
    KnowledgeArticle,
    KnowledgeArticleVersion,
    KnowledgeCategory,
)
from app.modules.knowledge.repository import ArticleRecord
from app.modules.knowledge.schemas import ArticleCreate, ArticleVersionCreate
from app.modules.knowledge.service import KnowledgeService

pytestmark = pytest.mark.anyio
PASSWORD = "Correct-Horse-7!"


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret="test-knowledge-signing-key-at-least-32-characters")


@pytest.fixture
async def database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.getenv("ITOPS_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine = (
        create_async_engine(url, poolclass=NullPool)
        if not url.startswith("sqlite")
        else create_async_engine(url)
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def configure(connection, record):
            del record
            connection.execute("PRAGMA foreign_keys=ON")

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    async with engine.connect() as connection:
        outer = await connection.begin()
        if url.startswith("sqlite"):
            await connection.execute(text("BEGIN"))
        factory = async_sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with factory() as session:
            if not await session.scalar(select(Role.code).limit(1)):
                session.add_all([Role(code=role) for role in ROLE_PERMISSIONS])
                session.add_all([Permission(code=permission) for permission in PERMISSIONS])
                await session.flush()
                session.add_all(
                    RolePermission(role_code=role, permission_code=permission)
                    for role, permissions in ROLE_PERMISSIONS.items()
                    for permission in permissions
                )
            await session.commit()
        yield factory
        await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def client(database, settings):
    app = create_app()

    async def session():
        async with database() as value:
            yield value

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_settings] = lambda: settings
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as value:
        yield value


async def make_user(factory, settings: Settings, role: str, name: str) -> User:
    async with factory() as session:
        user = User(
            id=uuid4(),
            email=f"{name.lower()}@example.com",
            display_name=name.title(),
            password_hash=PasswordService().hash(PASSWORD),
            status=UserStatus.ACTIVE,
            password_changed_at=datetime.now(UTC),
        )
        refresh_id = uuid4()
        session.add(user)
        await session.flush()
        session.add_all(
            [
                UserRole(user_id=user.id, role_code=role),
                RefreshSession(
                    id=refresh_id,
                    user_id=user.id,
                    family_id=uuid4(),
                    token_hash=uuid4().hex + uuid4().hex,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                ),
            ]
        )
        await session.commit()
        user.test_session_id = refresh_id
        user.test_settings = settings
        return user


def auth(user: User) -> dict[str, str]:
    token = TokenService(user.test_settings).create_access_token(user.id, user.test_session_id)
    return {"Authorization": f"Bearer {token}"}


async def category(client: httpx.AsyncClient, manager: User, *, active: bool = True) -> dict:
    response = await client.post(
        "/api/v1/knowledge/categories",
        headers=auth(manager),
        json={
            "code": "NETWORK",
            "name": "Network access",
            "description": "Connectivity and remote access",
            "is_active": active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def article_payload(category_id: str) -> dict[str, object]:
    return {
        "slug": "repair-corporate-vpn-profile",
        "category_id": category_id,
        "title": "Repair a corporate VPN profile",
        "summary": "Restore a damaged managed VPN profile.",
        "content": "Disconnect the VPN, replace the managed profile, then reconnect safely.",
        "change_summary": "Initial troubleshooting procedure",
        "tags": ["VPN", "remote-access", "vpn"],
    }


async def test_versioned_article_review_publish_search_and_archive(
    client, database, settings
) -> None:
    employee = await make_user(database, settings, "EMPLOYEE", "employee")
    technician = await make_user(database, settings, "TECHNICIAN", "technician")
    other_technician = await make_user(database, settings, "TECHNICIAN", "othertech")
    manager = await make_user(database, settings, "IT_MANAGER", "manager")
    knowledge_category = await category(client, manager)

    created = await client.post(
        "/api/v1/knowledge/articles",
        headers=auth(technician),
        json=article_payload(knowledge_category["id"]),
    )
    assert created.status_code == 201, created.text
    article = created.json()
    article_id = article["id"]
    assert article["status"] == "DRAFT"
    assert article["tags"] == ["vpn", "remote-access"]
    assert article["version"]["version"] == 1

    assert (await client.get("/api/v1/knowledge/articles", headers=auth(employee))).json()[
        "total"
    ] == 0
    hidden = await client.get(f"/api/v1/knowledge/articles/{article_id}", headers=auth(employee))
    assert hidden.status_code == 404
    hidden_from_peer = await client.get(
        f"/api/v1/knowledge/articles/{article_id}", headers=auth(other_technician)
    )
    assert hidden_from_peer.status_code == 404

    revised = await client.post(
        f"/api/v1/knowledge/articles/{article_id}/versions",
        headers=auth(technician),
        json={
            "title": "Repair a managed corporate VPN profile",
            "summary": "Safely restore a damaged managed VPN profile.",
            "content": (
                "Disconnect the VPN. Replace the managed profile. Reconnect and verify access."
            ),
            "change_summary": "Added verification step",
        },
    )
    assert revised.status_code == 201
    assert revised.json()["version"]["version"] == 2
    versions = await client.get(
        f"/api/v1/knowledge/articles/{article_id}/versions", headers=auth(technician)
    )
    assert [item["version"] for item in versions.json()] == [2, 1]

    submitted = await client.post(
        f"/api/v1/knowledge/articles/{article_id}/transitions",
        headers=auth(technician),
        json={"status": "IN_REVIEW", "reason": "Ready for operational review"},
    )
    assert submitted.status_code == 200
    denied = await client.post(
        f"/api/v1/knowledge/articles/{article_id}/transitions",
        headers=auth(technician),
        json={"status": "PUBLISHED", "reason": "Attempted self publication"},
    )
    assert denied.status_code == 403

    published = await client.post(
        f"/api/v1/knowledge/articles/{article_id}/transitions",
        headers=auth(manager),
        json={"status": "PUBLISHED", "reason": "Procedure verified by service owner"},
    )
    assert published.status_code == 200
    assert published.json()["published_version"] == 2
    assert published.json()["published_at"] is not None

    found = await client.get(
        "/api/v1/knowledge/articles?search=verify&status=PUBLISHED",
        headers=auth(employee),
    )
    assert found.status_code == 200
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["version"]["title"].startswith("Repair")

    archived = await client.post(
        f"/api/v1/knowledge/articles/{article_id}/transitions",
        headers=auth(manager),
        json={"status": "ARCHIVED", "reason": "Superseded by device automation"},
    )
    assert archived.status_code == 200
    assert (await client.get("/api/v1/knowledge/articles", headers=auth(employee))).json()[
        "total"
    ] == 0
    events = await client.get(
        f"/api/v1/knowledge/articles/{article_id}/events", headers=auth(manager)
    )
    assert [item["action"] for item in events.json()] == [
        "knowledge.created",
        "knowledge.version_created",
        "knowledge.in_review",
        "knowledge.published",
        "knowledge.archived",
    ]


async def test_category_validation_conflicts_and_workflow_guards(
    client, database, settings
) -> None:
    employee = await make_user(database, settings, "EMPLOYEE", "reader")
    technician = await make_user(database, settings, "TECHNICIAN", "writer")
    manager = await make_user(database, settings, "IT_MANAGER", "reviewer")
    denied = await client.post(
        "/api/v1/knowledge/categories",
        headers=auth(technician),
        json={"code": "APPS", "name": "Applications", "is_active": True},
    )
    assert denied.status_code == 403
    knowledge_category = await category(client, manager)
    conflict = await client.post(
        "/api/v1/knowledge/categories",
        headers=auth(manager),
        json={"code": "NETWORK", "name": "Another name", "is_active": True},
    )
    assert conflict.status_code == 409
    missing = await client.put(
        f"/api/v1/knowledge/categories/{uuid4()}",
        headers=auth(manager),
        json={"code": "MISSING", "name": "Missing category", "is_active": True},
    )
    assert missing.status_code == 404

    inactive = await client.put(
        f"/api/v1/knowledge/categories/{knowledge_category['id']}",
        headers=auth(manager),
        json={
            **{key: knowledge_category[key] for key in ("code", "name", "description")},
            "is_active": False,
        },
    )
    assert inactive.status_code == 200
    invalid_article = await client.post(
        "/api/v1/knowledge/articles",
        headers=auth(technician),
        json=article_payload(knowledge_category["id"]),
    )
    assert invalid_article.status_code == 422
    assert (await client.get("/api/v1/knowledge/categories", headers=auth(employee))).json() == []
    assert (
        len((await client.get("/api/v1/knowledge/categories", headers=auth(manager))).json()) == 1
    )


def service_record(*, status: ArticleStatus = ArticleStatus.DRAFT) -> ArticleRecord:
    actor_id = uuid4()
    article = KnowledgeArticle(
        id=uuid4(),
        slug="unit-tested-article",
        category_id=uuid4(),
        author_id=actor_id,
        owner_id=actor_id,
        status=status,
        tags=[],
        current_version_id=uuid4(),
    )
    version = KnowledgeArticleVersion(
        id=article.current_version_id,
        article_id=article.id,
        version=1,
        title="Unit tested article",
        summary="Unit test summary",
        content="Unit test content is sufficiently long.",
        change_summary="Initial test version",
        author_id=actor_id,
    )
    person = MagicMock(id=actor_id, display_name="Unit Author")
    return ArticleRecord(article, version, MagicMock(), person, person, person)


async def test_knowledge_service_guardrails_without_database_greenlets() -> None:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    service = KnowledgeService(session)
    service.repository.category = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as missing_category:
        await service.save_category({"name": "Missing"}, uuid4())
    assert missing_category.value.status_code == 404

    service.repository.category = AsyncMock(return_value=KnowledgeCategory(id=uuid4()))
    session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    with pytest.raises(HTTPException) as conflict:
        await service.save_category({"name": "Duplicate"})
    assert conflict.value.status_code == 409
    session.commit.side_effect = None

    service.repository.category = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as inactive:
        await service.create_article(
            uuid4(),
            {
                "slug": "missing-category",
                "category_id": uuid4(),
                "tags": [],
                "title": "Missing category",
                "summary": "Cannot be created",
                "content": "This article has no active category.",
                "change_summary": "Initial draft",
            },
            "request",
        )
    assert inactive.value.status_code == 422

    service.repository.category = AsyncMock(return_value=KnowledgeCategory(id=uuid4()))

    def unit_article_values() -> dict[str, object]:
        return {
            "slug": "mock-created-article",
            "category_id": uuid4(),
            "tags": ["mock"],
            "title": "Mock-created article",
            "summary": "Created without a database greenlet",
            "content": "This content exercises the transaction orchestration path.",
            "change_summary": "Initial mock draft",
        }

    await service.create_article(uuid4(), unit_article_values(), "request")
    session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    with pytest.raises(HTTPException) as slug_conflict:
        await service.create_article(uuid4(), unit_article_values(), "request")
    assert slug_conflict.value.status_code == 409
    session.commit.side_effect = None

    record = service_record()
    service.permissions = AsyncMock(return_value=frozenset({"knowledge:view"}))
    service.repository.article = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as hidden:
        await service.get(record.owner.id, record.article.id)
    assert hidden.value.status_code == 404

    service.get = AsyncMock(return_value=(record, frozenset()))
    with pytest.raises(HTTPException) as no_update:
        await service.add_version(record.owner.id, record.article.id, {}, "request")
    assert no_update.value.status_code == 403

    service.get = AsyncMock(return_value=(record, frozenset({"knowledge:update"})))
    with pytest.raises(HTTPException) as wrong_owner:
        await service.add_version(uuid4(), record.article.id, {}, "request")
    assert wrong_owner.value.status_code == 403
    record.article.status = ArticleStatus.IN_REVIEW
    with pytest.raises(HTTPException) as locked:
        await service.add_version(record.owner.id, record.article.id, {}, "request")
    assert locked.value.status_code == 409

    record.article.status = ArticleStatus.DRAFT
    service.get = AsyncMock(
        return_value=(record, frozenset({"knowledge:update", "knowledge:review"}))
    )
    service.repository.category = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as invalid_category:
        await service.add_version(
            record.owner.id,
            record.article.id,
            {
                "category_id": uuid4(),
                "title": "Updated article",
                "summary": "Updated summary",
                "content": "Updated content remains sufficiently long.",
                "change_summary": "Updated category",
            },
            "request",
        )
    assert invalid_category.value.status_code == 422

    service.repository.category = AsyncMock(return_value=KnowledgeCategory(id=uuid4()))
    await service.add_version(
        record.owner.id,
        record.article.id,
        {
            "category_id": uuid4(),
            "tags": ["updated"],
            "title": "Updated article",
            "summary": "Updated summary",
            "content": "Updated content remains sufficiently long.",
            "change_summary": "Updated details",
        },
        "request",
    )
    assert record.article.tags == ["updated"]

    record.article.status = ArticleStatus.DRAFT
    service.get = AsyncMock(return_value=(record, frozenset({"knowledge:update"})))
    with pytest.raises(HTTPException) as illegal:
        await service.transition(
            record.owner.id,
            record.article.id,
            ArticleStatus.PUBLISHED,
            "Invalid jump",
            "request",
        )
    assert illegal.value.status_code == 409
    with pytest.raises(HTTPException) as submit_other:
        await service.transition(
            uuid4(), record.article.id, ArticleStatus.IN_REVIEW, "Wrong owner", "request"
        )
    assert submit_other.value.status_code == 403

    record.article.status = ArticleStatus.IN_REVIEW
    service.get = AsyncMock(return_value=(record, frozenset({"knowledge:view"})))
    with pytest.raises(HTTPException) as cannot_publish:
        await service.transition(
            record.owner.id, record.article.id, ArticleStatus.PUBLISHED, "No grant", "request"
        )
    assert cannot_publish.value.status_code == 403

    service.get = AsyncMock(return_value=(record, frozenset({"knowledge:publish"})))
    await service.transition(
        record.owner.id, record.article.id, ArticleStatus.PUBLISHED, "Approved", "request"
    )
    assert record.article.published_version_id == record.article.current_version_id
    record.article.status = ArticleStatus.ARCHIVED
    service.get = AsyncMock(return_value=(record, frozenset({"knowledge:review"})))
    await service.transition(
        record.owner.id, record.article.id, ArticleStatus.DRAFT, "Restore", "request"
    )
    assert record.article.published_version_id is None


def test_knowledge_tag_validation_normalizes_and_rejects_blanks() -> None:
    base = {
        "title": "Validated article",
        "summary": "Validation summary",
        "content": "Validation content is long enough.",
        "change_summary": "Validation update",
    }
    assert ArticleCreate(
        **base, slug="validated-article", category_id=uuid4(), tags=["VPN", "vpn"]
    ).tags == ["vpn"]
    assert ArticleVersionCreate(**base, tags=None).tags is None
    assert ArticleVersionCreate(**base, tags=["VPN", "vpn"]).tags == ["vpn"]
    with pytest.raises(ValidationError):
        ArticleVersionCreate(**base, tags=[" "])
