"""Enterprise seed and end-to-end authentication regression coverage."""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.modules.access.catalog import PERMISSIONS, ROLE_PERMISSIONS
from app.modules.access.models import (
    Permission,
    Role,
    RoleAssignmentEvent,
    RolePermission,
    UserRole,
)
from app.modules.alerts.models import Alert
from app.modules.directory.models import Department, Location, Team, TeamMember
from app.modules.directory.seeds import seed_enterprise_directory
from app.modules.identity.models import User, UserStatus
from app.modules.identity.rate_limit import login_rate_limiter, refresh_rate_limiter
from app.modules.identity.security import PasswordService
from app.modules.sla.models import PriorityMatrix
from app.modules.sla.seeds import add_default_sla_configuration
from app.modules.tickets.models import CommentVisibility, Ticket, TicketComment, TicketEvent
from scripts.demo_seed import seed_demo

pytestmark = pytest.mark.anyio
PASSWORD = "Enterprise-Test-42!"
SETTINGS = Settings(
    environment="test",
    jwt_secret="test-enterprise-signing-key-at-least-32-characters",
    enterprise_seed_password=PASSWORD,
    login_rate_limit_attempts=100,
    refresh_rate_limit_attempts=100,
)


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
                    [
                        RolePermission(role_code=role, permission_code=permission)
                        for role, permissions in ROLE_PERMISSIONS.items()
                        for permission in permissions
                    ]
                )
            await session.commit()
        yield factory
        await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def seeded_database(database, monkeypatch):
    monkeypatch.setattr("app.modules.directory.seeds.get_settings", lambda: SETTINGS)
    async with database() as session:
        await seed_enterprise_directory(session)
        await session.commit()
    yield database


@pytest.fixture
async def client(seeded_database):
    app = create_app()

    async def session():
        async with seeded_database() as value:
            yield value

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    login_rate_limiter.reset()
    refresh_rate_limiter.reset()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as value:
        yield value


async def test_enterprise_seed_is_realistic_secure_and_idempotent(
    seeded_database, monkeypatch
) -> None:
    monkeypatch.setattr("app.modules.directory.seeds.get_settings", lambda: SETTINGS)
    async with seeded_database() as session:
        await seed_enterprise_directory(session)
        await session.commit()

        role_counts = dict(
            (
                await session.execute(
                    select(UserRole.role_code, func.count()).group_by(UserRole.role_code)
                )
            ).all()
        )
        status_counts = dict(
            (await session.execute(select(User.status, func.count()).group_by(User.status))).all()
        )
        nishant = await session.scalar(
            select(User).where(User.email == "nishant.paswan@example.com")
        )

        assert await session.scalar(select(func.count()).select_from(User)) == 35
        assert role_counts == {"ADMIN": 2, "IT_MANAGER": 4, "TECHNICIAN": 9, "EMPLOYEE": 20}
        assert status_counts == {"ACTIVE": 33, "DISABLED": 1, "LOCKED": 1}
        assert await session.scalar(select(func.count()).select_from(Department)) == 8
        assert await session.scalar(select(func.count()).select_from(Team)) == 6
        assert await session.scalar(select(func.count()).select_from(Location)) == 4
        assert await session.scalar(select(func.count()).select_from(TeamMember)) == 15
        assert await session.scalar(select(func.count()).select_from(RoleAssignmentEvent)) == 35
        assert nishant is not None
        assert nishant.display_name == "Nishant Paswan"
        assert nishant.status == UserStatus.ACTIVE
        assert nishant.department_id is not None and nishant.location_id is not None
        assert nishant.password_hash.startswith("$argon2id$")
        assert nishant.password_hash != PASSWORD
        assert PasswordService().verify(nishant.password_hash, PASSWORD)
        assert list(
            await session.scalars(select(UserRole.role_code).where(UserRole.user_id == nishant.id))
        ) == ["ADMIN"]
        assert (
            await session.scalar(
                select(func.count()).select_from(User).where(User.department_id.is_(None))
            )
            == 0
        )


async def test_enterprise_seed_does_not_restore_revoked_role(seeded_database, monkeypatch) -> None:
    monkeypatch.setattr("app.modules.directory.seeds.get_settings", lambda: SETTINGS)
    async with seeded_database() as session:
        user = await session.scalar(select(User).where(User.email == "maya.chen@example.com"))
        assert user is not None
        await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        await session.commit()
        await seed_enterprise_directory(session)
        await session.commit()
        assert (
            list(
                await session.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id))
            )
            == []
        )


async def test_fictional_demo_seed_is_repeatable(seeded_database) -> None:
    async with seeded_database() as session:
        if not await session.scalar(select(PriorityMatrix.impact).limit(1)):
            add_default_sla_configuration(session)
            await session.commit()
        first = await seed_demo(session, SETTINGS)
        assert first == {"categories": 7, "articles": 8, "assets": 10, "tickets": 20, "agents": 3}
        assert await session.scalar(select(func.count()).select_from(Ticket)) == 20
        assert await session.scalar(select(func.count()).select_from(TicketEvent)) > 20
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TicketComment)
                .where(TicketComment.visibility == CommentVisibility.INTERNAL)
            )
            >= 2
        )
        alert_count = await session.scalar(select(func.count()).select_from(Alert))
        second = await seed_demo(session, SETTINGS)
        assert second == {key: 0 for key in first}
        assert await session.scalar(select(func.count()).select_from(Alert)) == alert_count


async def test_real_authentication_rbac_lifecycle_and_session_matrix(client) -> None:
    async def login(email: str, password: str = PASSWORD) -> httpx.Response:
        return await client.post("/api/v1/auth/login", json={"email": email, "password": password})

    for email, role in (
        ("nishant.paswan@example.com", "ADMIN"),
        ("priya.raman@example.com", "ADMIN"),
        ("aisha.mehta@example.com", "IT_MANAGER"),
        ("maya.chen@example.com", "TECHNICIAN"),
        ("jordan.lee@example.com", "EMPLOYEE"),
    ):
        response = await login(email)
        assert response.status_code == 200, response.text
        assert response.json()["user"]["email"] == email
        token = response.json()["access_token"]
        grants = await client.get("/api/v1/access/me", headers={"Authorization": f"Bearer {token}"})
        assert grants.status_code == 200
        assert grants.json()["roles"] == [role]

    for email, password, expected in (
        ("random-user@example.invalid", "RandomPassword123!", 422),
        ("random-user-unknown@example.com", "RandomPassword123!", 401),
        ("unknown-login-id", "RandomPassword123!", 422),
        ("nishant.paswan@example.com", "Completely-Wrong-42!", 401),
        ("rohan.desai@example.com", PASSWORD, 401),
        ("amina.yusuf@example.com", PASSWORD, 401),
        ("not-an-email", PASSWORD, 422),
        ("", PASSWORD, 422),
        ("nishant.paswan@example.com", "", 422),
    ):
        client.cookies.clear()
        response = await login(email, password)
        assert response.status_code == expected, response.text
        assert "itops_refresh" not in response.cookies

    for payload in ({}, {"email": "nishant.paswan@example.com"}, {"password": PASSWORD}):
        client.cookies.clear()
        response = await client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 422
        assert "itops_refresh" not in response.cookies

    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (await client.get("/api/v1/access/roles")).status_code == 401

    injected = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "jordan.lee@example.com",
            "password": PASSWORD,
            "role": "ADMIN",
        },
    )
    assert injected.status_code == 422

    admin_login = await login("nishant.paswan@example.com")
    admin_id = admin_login.json()["user"]["id"]
    assert (
        await client.get(
            "/api/v1/access/roles",
            headers={"Authorization": f"Bearer {admin_login.json()['access_token']}"},
        )
    ).status_code == 200

    for email in (
        "jordan.lee@example.com",
        "maya.chen@example.com",
        "aisha.mehta@example.com",
    ):
        response = await login(email)
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        assert (await client.get("/api/v1/access/roles", headers=headers)).status_code == 403
        assert (
            await client.put(
                f"/api/v1/access/users/{admin_id}/roles",
                headers=headers,
                json={"roles": ["ADMIN"], "reason": "client-side escalation attempt"},
            )
        ).status_code == 403

    session_login = await login("nishant.paswan@example.com")
    old_access = session_login.json()["access_token"]
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    ).status_code == 401
    new_access = refreshed.json()["access_token"]
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    ).status_code == 200
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    ).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


def test_enterprise_seed_is_blocked_in_production() -> None:
    with pytest.raises(ValidationError, match="Enterprise demo seeding"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://itops:test-only@database:5432/itops",
            jwt_secret="test-only-production-secret-at-least-32-characters",
            secure_cookies=True,
            cors_origins=["https://support.example.com"],
            attachment_scan_required=True,
            attachment_clamav_host="clamav.internal",
            enterprise_seed_password=PASSWORD,
        )
