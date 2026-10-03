"""SQL-backed authorization tests. PostgreSQL in CI; SQLite locally."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.modules.access.catalog import PERMISSIONS, ROLE_PERMISSIONS
from app.modules.access.dependencies import require_permission
from app.modules.access.models import (
    Permission,
    Role,
    RoleAssignmentEvent,
    RolePermission,
    UserRole,
)
from app.modules.access.policy import AccessScope
from app.modules.access.repository import AccessRepository
from app.modules.access.service import AccessService
from app.modules.identity.models import RefreshSession, User, UserStatus
from app.modules.identity.security import PasswordService, TokenService
from app.modules.identity.seeds import seed_initial_admin

pytestmark = pytest.mark.anyio
SETTINGS = Settings(jwt_secret="test-only-rbac-signing-key-32-characters")
PASSWORD = "Correct-Horse-7!"


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
                session.add_all([Role(code=r) for r in ROLE_PERMISSIONS])
                session.add_all([Permission(code=p) for p in PERMISSIONS])
                await session.flush()
                session.add_all(
                    [
                        RolePermission(role_code=r, permission_code=p)
                        for r, values in ROLE_PERMISSIONS.items()
                        for p in values
                    ]
                )
                await session.commit()
        yield factory
        await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def client(database):
    app = create_app()
    from fastapi import Depends

    for permission in PERMISSIONS:

        async def probe():
            return {"allowed": True}

        app.add_api_route(
            f"/_test/{permission}", probe, dependencies=[Depends(require_permission(permission))]
        )

    async def session():
        async with database() as value:
            yield value

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def user(factory, role=None):
    async with factory() as session:
        value = User(
            id=uuid4(),
            email=f"{uuid4().hex}@example.com",
            display_name="Test operator",
            password_hash=PasswordService().hash(PASSWORD),
            status=UserStatus.ACTIVE,
            password_changed_at=datetime.now(UTC),
        )
        session.add(value)
        await session.flush()
        session_id = uuid4()
        session.add(
            RefreshSession(
                id=session_id,
                user_id=value.id,
                family_id=uuid4(),
                token_hash=uuid4().hex + uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        if role:
            session.add(UserRole(user_id=value.id, role_code=role))
        await session.commit()
        value.test_session_id = session_id
        return value


def auth(value: User) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {TokenService(SETTINGS).create_access_token(value.id, value.test_session_id)}"
        )
    }


@pytest.mark.parametrize(
    "role,expected",
    [("EMPLOYEE", 403), ("TECHNICIAN", 403), ("IT_MANAGER", 403), ("ADMIN", 200), (None, 403)],
)
async def test_catalog_permissions_use_real_database_and_signed_tokens(
    database, client, role, expected
):
    actor = await user(database, role)
    for permission in PERMISSIONS:
        result = await client.get(f"/_test/{permission}", headers=auth(actor))
        assert result.status_code == (
            200 if role and permission in ROLE_PERMISSIONS[role] else 403
        ), (role, permission)
    response = await client.get("/api/v1/access/roles", headers=auth(actor))
    assert response.status_code == expected
    own = await client.get("/api/v1/access/me", headers=auth(actor))
    assert own.status_code == 200
    assert set(own.json()["permissions"]) == (ROLE_PERMISSIONS[role] if role else set())
    permission_list = await client.get("/api/v1/access/permissions", headers=auth(actor))
    assert permission_list.status_code == expected


async def test_anonymous_tampered_and_disabled_users_denied(database, client):
    actor = await user(database, "ADMIN")
    for headers in ({}, {"Authorization": "Bearer forged"}):
        response = await client.get("/api/v1/access/roles", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    async with database() as session:
        db_user = await session.get(User, actor.id)
        db_user.status = UserStatus.DISABLED
        await session.commit()
    assert (await client.get("/api/v1/access/roles", headers=auth(actor))).status_code == 401


async def test_assignment_change_is_audited_and_revocation_applies_to_existing_token(
    database, client
):
    admin, target = await user(database, "ADMIN"), await user(database, "ADMIN")
    target_headers = auth(target)
    payload = {"roles": ["EMPLOYEE"], "reason": "Transfer to employee support"}
    response = await client.put(
        f"/api/v1/access/users/{target.id}/roles", json=payload, headers=auth(admin)
    )
    assert response.status_code == 200
    assert response.json() == ["EMPLOYEE"]
    assert (await client.get("/api/v1/access/roles", headers=target_headers)).status_code == 403
    detail = await client.get(f"/api/v1/access/users/{target.id}/roles", headers=auth(admin))
    assert detail.json()["roles"] == ["EMPLOYEE"]
    # Retrying the same desired state must not create a duplicate audit event.
    assert (
        await client.put(
            f"/api/v1/access/users/{target.id}/roles", json=payload, headers=auth(admin)
        )
    ).status_code == 200
    async with database() as session:
        events = list(
            await session.scalars(
                select(RoleAssignmentEvent).where(RoleAssignmentEvent.user_id == target.id)
            )
        )
        assert len(events) == 1
        assert events[0].before_roles == ["ADMIN"]
        assert events[0].after_roles == ["EMPLOYEE"]
        assert events[0].actor_id == admin.id


async def test_employee_cannot_read_or_escalate_other_users(database, client):
    employee, target = await user(database, "EMPLOYEE"), await user(database, "TECHNICIAN")
    path = f"/api/v1/access/users/{target.id}/roles"
    assert (await client.get(path, headers=auth(employee))).status_code == 403
    assert (
        await client.put(
            path, json={"roles": ["ADMIN"], "reason": "escalation"}, headers=auth(employee)
        )
    ).status_code == 403
    async with database() as session:
        assert (await AccessRepository(session).grants(target.id))[0] == ["TECHNICIAN"]


async def test_assignment_validation_and_self_protection(database, client):
    admin = await user(database, "ADMIN")
    headers = auth(admin)
    assert (
        await client.put(
            f"/api/v1/access/users/{admin.id}/roles",
            headers=headers,
            json={"roles": [], "reason": "remove own role"},
        )
    ).status_code == 409
    assert (
        await client.put(
            f"/api/v1/access/users/{uuid4()}/roles",
            headers=headers,
            json={"roles": ["ADMIN"], "reason": "test"},
        )
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/access/users/{uuid4()}/roles", headers=headers)
    ).status_code == 404
    for payload in (
        {"roles": ["SUPERUSER"], "reason": "test"},
        {"roles": ["ADMIN"], "reason": " "},
        {"roles": ["ADMIN"], "reason": "test", "permissions": ["*"]},
    ):
        assert (
            await client.put(
                f"/api/v1/access/users/{admin.id}/roles", headers=headers, json=payload
            )
        ).status_code == 422


async def test_no_roles_denies_all_and_combined_roles_form_union(database, client):
    admin, target = await user(database, "ADMIN"), await user(database, "EMPLOYEE")
    for desired in (["EMPLOYEE", "TECHNICIAN", "TECHNICIAN"], []):
        response = await client.put(
            f"/api/v1/access/users/{target.id}/roles",
            headers=auth(admin),
            json={"roles": desired, "reason": "Change scope"},
        )
        assert response.status_code == 200
        own = await client.get("/api/v1/access/me", headers=auth(target))
        assert set(own.json()["permissions"]) == (
            ROLE_PERMISSIONS["TECHNICIAN"] if desired else set()
        )


async def test_bootstrap_creates_admin_once_and_does_not_restore_removed_roles(
    database, monkeypatch
):
    settings = Settings(
        initial_admin_email="bootstrap@example.com", initial_admin_password=PASSWORD
    )
    monkeypatch.setattr("app.modules.identity.seeds.get_settings", lambda: settings)
    async with database() as session:
        await seed_initial_admin(session)
        await session.commit()
        bootstrap = await session.scalar(select(User).where(User.email == "bootstrap@example.com"))
        assert (await AccessRepository(session).grants(bootstrap.id))[0] == ["ADMIN"]
        await AccessRepository(session).replace_roles(bootstrap.id, [])
        await session.commit()
        await seed_initial_admin(session)
        await session.commit()
        assert (await AccessRepository(session).grants(bootstrap.id))[0] == []


async def test_service_rechecks_actor_and_unknown_permissions(database):
    admin, employee = await user(database, "ADMIN"), await user(database, "EMPLOYEE")
    from fastapi import HTTPException

    async with database() as session:
        with pytest.raises(HTTPException):
            await AccessService(session).require(employee.id, "role:manage")
        with pytest.raises(HTTPException):
            await AccessService(session).replace_roles(
                admin.id, employee.id, ["UNKNOWN"], "test", "test"
            )
        with pytest.raises(HTTPException):
            await AccessService(session).replace_roles(uuid4(), employee.id, [], "test", "test")
    with pytest.raises(ValueError):
        require_permission("invented:permission")


async def test_schema_constraints(database):
    from sqlalchemy.exc import IntegrityError

    employee = await user(database, "EMPLOYEE")
    async with database() as session:
        session.add(UserRole(user_id=employee.id, role_code="EMPLOYEE"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        session.add(UserRole(user_id=uuid4(), role_code="EMPLOYEE"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_real_login_to_authorized_endpoint(database, client):
    admin = await user(database, "ADMIN")
    response = await client.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": PASSWORD}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    grants = await client.get("/api/v1/access/me", headers={"Authorization": f"Bearer {token}"})
    assert grants.status_code == 200
    assert "role:manage" in grants.json()["permissions"]


def test_ownership_team_scope_and_unknown_domain_fail_closed():
    owner, stranger, team, other = uuid4(), uuid4(), uuid4(), uuid4()
    employee = AccessScope(owner, ROLE_PERMISSIONS["EMPLOYEE"])
    assert employee.can_view("ticket", owner, None)
    assert not employee.can_view("ticket", stranger, team)
    tech = AccessScope(owner, ROLE_PERMISSIONS["TECHNICIAN"], frozenset({team}))
    assert tech.can_view("ticket", stranger, team)
    assert not tech.can_view("ticket", stranger, other)
    assert not tech.can_view("ticket", stranger, None)
    assert not AccessScope(owner, frozenset({"unknown:view_all"})).can_view(
        "unknown", stranger, None
    )
    assert AccessScope(owner, ROLE_PERMISSIONS["ADMIN"]).can_view("ticket", stranger, None)


def test_catalog_has_no_implicit_admin_bypass():
    assert set(ROLE_PERMISSIONS["ADMIN"]) == PERMISSIONS
    assert all(p in PERMISSIONS for grants in ROLE_PERMISSIONS.values() for p in grants)
    assert "role:manage" not in ROLE_PERMISSIONS["IT_MANAGER"]
    assert "ticket:internal_note" not in ROLE_PERMISSIONS["EMPLOYEE"]


async def test_existing_phase3_bootstrap_checks_password_and_refuses_reinitialization(database):
    from app.modules.access.bootstrap import bootstrap_existing

    actor = await user(database)
    async with database() as session:
        with pytest.raises(ValueError):
            await bootstrap_existing(session, Settings())
        with pytest.raises(ValueError):
            await bootstrap_existing(
                session, Settings(initial_admin_email=actor.email, initial_admin_password="wrong")
            )
        await bootstrap_existing(
            session, Settings(initial_admin_email=actor.email, initial_admin_password=PASSWORD)
        )
        await session.commit()
        assert (await AccessRepository(session).grants(actor.id))[0] == ["ADMIN"]
        with pytest.raises(ValueError):
            await bootstrap_existing(
                session, Settings(initial_admin_email=actor.email, initial_admin_password=PASSWORD)
            )


async def test_assignment_audit_failure_rolls_back_role_change(database, monkeypatch):
    admin, target = await user(database, "ADMIN"), await user(database, "EMPLOYEE")
    async with database() as session:
        original_add = session.add

        def fail_audit(instance):
            if isinstance(instance, RoleAssignmentEvent):
                raise RuntimeError("simulated audit failure")
            original_add(instance)

        monkeypatch.setattr(session, "add", fail_audit)
        with pytest.raises(RuntimeError):
            await AccessService(session).replace_roles(
                admin.id, target.id, ["TECHNICIAN"], "test", "rollback"
            )
        await session.rollback()
    async with database() as session:
        assert (await AccessRepository(session).grants(target.id))[0] == ["EMPLOYEE"]
