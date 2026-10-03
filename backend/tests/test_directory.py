"""Phase 5 directory API tests. PostgreSQL in CI; isolated SQLite locally."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.modules.access.catalog import PERMISSIONS, ROLE_PERMISSIONS
from app.modules.access.models import Permission, Role, RolePermission, UserRole
from app.modules.directory.models import (
    Department,
    DirectoryEvent,
    Location,
    Team,
    TeamMember,
)
from app.modules.directory.repository import DirectoryRepository
from app.modules.directory.service import DirectoryService
from app.modules.identity.models import RefreshSession, User, UserStatus
from app.modules.identity.security import PasswordService, TokenService

pytestmark = pytest.mark.anyio
SETTINGS = Settings(jwt_secret="test-directory-signing-key-at-least-32-characters")
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
async def client(database):
    app = create_app()

    async def session():
        async with database() as value:
            yield value

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as value:
        yield value


async def make_user(
    factory: async_sessionmaker[AsyncSession],
    roles: tuple[str, ...] = (),
    *,
    email: str | None = None,
    status: UserStatus = UserStatus.ACTIVE,
    department_id: UUID | None = None,
    location_id: UUID | None = None,
) -> User:
    async with factory() as session:
        value = User(
            id=uuid4(),
            email=email or f"{uuid4().hex}@example.com",
            display_name="Test operator",
            employee_number=None,
            job_title="Support specialist",
            department_id=department_id,
            location_id=location_id,
            password_hash=PasswordService().hash(PASSWORD),
            status=status,
            password_changed_at=datetime.now(UTC),
        )
        session_id = uuid4()
        session.add(value)
        await session.flush()
        session.add(
            RefreshSession(
                id=session_id,
                user_id=value.id,
                family_id=uuid4(),
                token_hash=uuid4().hex + uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.add_all([UserRole(user_id=value.id, role_code=role) for role in roles])
        await session.commit()
        value.test_session_id = session_id
        return value


def auth(value: User) -> dict[str, str]:
    token = TokenService(SETTINGS).create_access_token(value.id, value.test_session_id)
    return {"Authorization": f"Bearer {token}"}


async def create_references(client: httpx.AsyncClient, admin: User) -> tuple[dict, dict]:
    department = await client.post(
        "/api/v1/directory/departments",
        headers=auth(admin),
        json={
            "code": "it",
            "name": "Information Technology",
            "description": "Internal technology services",
            "reason": "Create operating structure",
        },
    )
    location = await client.post(
        "/api/v1/directory/locations",
        headers=auth(admin),
        json={
            "code": "blr",
            "name": "Bengaluru Office",
            "timezone": "UTC",
            "address": "Technology campus",
            "reason": "Create operating structure",
        },
    )
    assert department.status_code == location.status_code == 201
    return department.json(), location.json()


async def create_team(
    client: httpx.AsyncClient,
    actor: User,
    department: dict,
    location: dict,
    *,
    code: str = "SERVICE_DESK",
) -> dict:
    response = await client.post(
        "/api/v1/directory/teams",
        headers=auth(actor),
        json={
            "code": code,
            "name": code.replace("_", " ").title(),
            "description": "Regional technical support",
            "department_id": department["id"],
            "location_id": location["id"],
            "reason": "Establish support coverage",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_endpoint_permission_matrix_and_404_non_disclosure(database, client):
    admin = await make_user(database, ("ADMIN",))
    manager = await make_user(database, ("IT_MANAGER",))
    technician = await make_user(database, ("TECHNICIAN",))
    employee = await make_user(database, ("EMPLOYEE",))

    for path in ("departments", "locations", "teams"):
        for actor, expected in (
            (admin, 200),
            (manager, 200),
            (technician, 200),
            (employee, 403),
        ):
            assert (
                await client.get(f"/api/v1/directory/{path}", headers=auth(actor))
            ).status_code == expected
        assert (await client.get(f"/api/v1/directory/{path}")).status_code == 401

    for actor, expected in ((admin, 200), (manager, 403), (technician, 403), (employee, 403)):
        assert (
            await client.get("/api/v1/directory/users", headers=auth(actor))
        ).status_code == expected

    missing = f"/api/v1/directory/users/{uuid4()}"
    assert (await client.get(missing, headers=auth(employee))).status_code == 403
    assert (await client.get(missing, headers=auth(admin))).status_code == 404

    department, location = await create_references(client, admin)
    assert (
        await client.post(
            "/api/v1/directory/teams",
            headers=auth(technician),
            json={
                "code": "NOPE",
                "name": "Not allowed",
                "department_id": department["id"],
                "location_id": location["id"],
                "reason": "Should be rejected",
            },
        )
    ).status_code == 403
    assert (await create_team(client, manager, department, location))["code"] == "SERVICE_DESK"


async def test_reference_crud_conflicts_counts_and_safe_deactivation(database, client):
    admin = await make_user(database, ("ADMIN",))
    department, location = await create_references(client, admin)
    assert department["code"] == "IT"
    assert location["code"] == "BLR"
    assert (
        await client.post(
            "/api/v1/directory/departments",
            headers=auth(admin),
            json={
                "code": "OPS",
                "name": "information technology",
                "reason": "Exercise normalized uniqueness",
            },
        )
    ).status_code == 409
    invalid_timezone = await client.post(
        "/api/v1/directory/locations",
        headers=auth(admin),
        json={
            "code": "BAD",
            "name": "Invalid timezone office",
            "timezone": "Mars/Olympus",
            "reason": "Validate input",
        },
    )
    assert invalid_timezone.status_code == 422

    employee = await make_user(
        database,
        ("EMPLOYEE",),
        department_id=UUID(department["id"]),
        location_id=UUID(location["id"]),
    )
    listing = await client.get("/api/v1/directory/departments", headers=auth(admin))
    assert listing.json()[0]["user_count"] == 1
    blocked = await client.patch(
        f"/api/v1/directory/departments/{department['id']}",
        headers=auth(admin),
        json={"status": "INACTIVE", "reason": "Retire organizational unit"},
    )
    assert blocked.status_code == 409
    moved = await client.patch(
        f"/api/v1/directory/users/{employee.id}",
        headers=auth(admin),
        json={
            "department_id": None,
            "location_id": None,
            "job_title": "Service consumer",
            "reason": "Move outside support organization",
        },
    )
    assert moved.status_code == 200
    retired = await client.patch(
        f"/api/v1/directory/departments/{department['id']}",
        headers=auth(admin),
        json={"status": "INACTIVE", "reason": "Retire organizational unit"},
    )
    assert retired.status_code == 200
    assert retired.json()["status"] == "INACTIVE"
    assert (
        await client.patch(
            f"/api/v1/directory/locations/{location['id']}",
            headers=auth(admin),
            json={"address": "Updated campus", "reason": "Correct address"},
        )
    ).json()["address"] == "Updated campus"
    async with database() as session:
        assert int(await session.scalar(select(func.count(DirectoryEvent.id))) or 0) >= 5


async def test_user_creation_search_update_and_session_safe_status_cycle(database, client):
    admin = await make_user(database, ("ADMIN",))
    department, location = await create_references(client, admin)
    payload = {
        "email": "New.Technician@Example.com",
        "display_name": "New Technician",
        "initial_password": PASSWORD,
        "employee_number": "EMP-0042",
        "job_title": "Endpoint Technician",
        "department_id": department["id"],
        "location_id": location["id"],
        "roles": ["TECHNICIAN"],
        "reason": "Approved service desk hire",
    }
    created = await client.post("/api/v1/directory/users", headers=auth(admin), json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "new.technician@example.com"
    assert body["roles"] == ["TECHNICIAN"]
    assert "password" not in created.text and "hash" not in created.text
    user_id = body["id"]

    duplicate = await client.post(
        "/api/v1/directory/users",
        headers=auth(admin),
        json={**payload, "email": "NEW.TECHNICIAN@example.com", "employee_number": "EMP-0043"},
    )
    assert duplicate.status_code == 409
    weak = await client.post(
        "/api/v1/directory/users",
        headers=auth(admin),
        json={
            **payload,
            "email": "weak@example.com",
            "employee_number": "EMP-0044",
            "initial_password": "weak-password",
        },
    )
    assert weak.status_code == 422
    page = await client.get(
        "/api/v1/directory/users?search=new.technician&role=TECHNICIAN&limit=1",
        headers=auth(admin),
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1 and page.json()["limit"] == 1
    assert (
        await client.get("/api/v1/directory/users?limit=0", headers=auth(admin))
    ).status_code == 422

    login = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": PASSWORD}
    )
    old_access = login.json()["access_token"]
    old_refresh = client.cookies.get("itops_refresh")
    disabled = await client.put(
        f"/api/v1/directory/users/{user_id}/status",
        headers=auth(admin),
        json={"status": "DISABLED", "reason": "Employment ended"},
    )
    assert disabled.status_code == 200 and disabled.json()["status"] == "DISABLED"
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    ).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    enabled = await client.put(
        f"/api/v1/directory/users/{user_id}/status",
        headers=auth(admin),
        json={"status": "ACTIVE", "reason": "Employment reinstated"},
    )
    assert enabled.status_code == 200 and enabled.json()["status"] == "ACTIVE"
    client.cookies.set("itops_refresh", old_refresh)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    ).status_code == 401
    assert (
        await client.put(
            f"/api/v1/directory/users/{admin.id}/status",
            headers=auth(admin),
            json={"status": "DISABLED", "reason": "Unsafe self change"},
        )
    ).status_code == 409


async def test_team_membership_history_scope_and_role_downgrade(database, client):
    admin = await make_user(database, ("ADMIN",))
    manager = await make_user(database, ("IT_MANAGER",))
    technician = await make_user(database, ("TECHNICIAN",), email="tech@example.com")
    employee = await make_user(database, ("EMPLOYEE",), email="employee@example.com")
    department, location = await create_references(client, admin)
    team = await create_team(client, manager, department, location)

    candidates = await client.get(
        f"/api/v1/directory/teams/{team['id']}/eligible-technicians?search=tech",
        headers=auth(manager),
    )
    assert candidates.status_code == 200
    assert [item["id"] for item in candidates.json()] == [str(technician.id)]
    assigned = await client.put(
        f"/api/v1/directory/teams/{team['id']}/members/{technician.id}",
        headers=auth(manager),
        json={"member_role": "LEAD", "reason": "Lead regional support"},
    )
    assert assigned.status_code == 200 and assigned.json()["member_role"] == "LEAD"
    assert (
        await client.put(
            f"/api/v1/directory/teams/{team['id']}/members/{employee.id}",
            headers=auth(manager),
            json={"member_role": "MEMBER", "reason": "Invalid assignment test"},
        )
    ).status_code == 409
    detail = await client.get(f"/api/v1/directory/teams/{team['id']}", headers=auth(manager))
    assert detail.json()["member_count"] == 1 and detail.json()["members"][0]["roles"] == [
        "TECHNICIAN"
    ]
    async with database() as session:
        assert UUID(team["id"]) in await DirectoryRepository(session).active_team_ids(technician.id)

    downgrade = await client.put(
        f"/api/v1/access/users/{technician.id}/roles",
        headers=auth(admin),
        json={"roles": ["EMPLOYEE"], "reason": "Move out of support"},
    )
    assert downgrade.status_code == 409
    changed_role = await client.put(
        f"/api/v1/directory/teams/{team['id']}/members/{technician.id}",
        headers=auth(manager),
        json={"member_role": "MEMBER", "reason": "Rotate team lead"},
    )
    assert changed_role.status_code == 200
    removed = await client.request(
        "DELETE",
        f"/api/v1/directory/teams/{team['id']}/members/{technician.id}",
        headers={**auth(manager), "Content-Type": "application/json"},
        json={"reason": "Transfer to another support team"},
    )
    assert removed.status_code == 204
    async with database() as session:
        history = list(
            await session.scalars(
                select(TeamMember)
                .where(TeamMember.team_id == UUID(team["id"]))
                .order_by(TeamMember.started_at)
            )
        )
        assert len(history) == 2 and all(item.ended_at is not None for item in history)
        assert not await DirectoryRepository(session).active_team_ids(technician.id)

    assert (
        await client.put(
            f"/api/v1/directory/teams/{team['id']}/members/{technician.id}",
            headers=auth(manager),
            json={"member_role": "MEMBER", "reason": "Return to service desk"},
        )
    ).status_code == 200
    retired = await client.patch(
        f"/api/v1/directory/teams/{team['id']}",
        headers=auth(manager),
        json={"status": "INACTIVE", "reason": "Support model changed"},
    )
    assert retired.status_code == 200
    assert (
        await client.put(
            f"/api/v1/directory/teams/{team['id']}/members/{technician.id}",
            headers=auth(manager),
            json={"member_role": "MEMBER", "reason": "Cannot restore"},
        )
    ).status_code == 409
    assert (
        await client.put(
            f"/api/v1/access/users/{technician.id}/roles",
            headers=auth(admin),
            json={"roles": ["EMPLOYEE"], "reason": "Move out of support"},
        )
    ).status_code == 200


async def test_inactive_references_and_missing_resources_are_controlled(database, client):
    admin = await make_user(database, ("ADMIN",))
    department, location = await create_references(client, admin)
    for kind, record in (("departments", department), ("locations", location)):
        assert (
            await client.patch(
                f"/api/v1/directory/{kind}/{record['id']}",
                headers=auth(admin),
                json={"status": "INACTIVE", "reason": "Retire unused reference"},
            )
        ).status_code == 200
    rejected = await client.post(
        "/api/v1/directory/teams",
        headers=auth(admin),
        json={
            "code": "INACTIVE_REF",
            "name": "Inactive Reference Team",
            "department_id": department["id"],
            "location_id": location["id"],
            "reason": "Validate inactive references",
        },
    )
    assert rejected.status_code == 409
    missing_reference = await client.post(
        "/api/v1/directory/teams",
        headers=auth(admin),
        json={
            "code": "MISSING_REF",
            "name": "Missing Reference Team",
            "department_id": str(uuid4()),
            "reason": "Validate missing references",
        },
    )
    assert missing_reference.status_code == 422
    assert (
        await client.patch(
            f"/api/v1/directory/teams/{uuid4()}",
            headers=auth(admin),
            json={"name": "Missing team", "reason": "Validate not found"},
        )
    ).status_code == 404


async def test_constraints_and_audit_failure_rollback(database):
    admin = await make_user(database, ("ADMIN",))
    technician = await make_user(database, ("TECHNICIAN",))
    async with database() as session:
        department = Department(
            id=uuid4(), code="IT", name="Information Technology", status="ACTIVE"
        )
        location = Location(
            id=uuid4(), code="HQ", name="Headquarters", timezone="UTC", status="ACTIVE"
        )
        team = Team(
            id=uuid4(),
            code="DESK",
            name="Service Desk",
            status="ACTIVE",
            department_id=department.id,
            location_id=location.id,
        )
        session.add_all([department, location, team])
        await session.commit()
        session.add_all(
            [
                TeamMember(
                    id=uuid4(), team_id=team.id, user_id=technician.id, member_role="MEMBER"
                ),
                TeamMember(id=uuid4(), team_id=team.id, user_id=technician.id, member_role="LEAD"),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with database() as session:
        original_add = session.add

        def fail_audit(instance):
            if isinstance(instance, DirectoryEvent):
                raise RuntimeError("simulated directory audit outage")
            original_add(instance)

        session.add = fail_audit  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            await DirectoryService(session).create_department(
                admin.id,
                {"code": "SEC", "name": "Security", "description": None},
                "Create security organization",
                "request-test",
            )
        await session.rollback()
    async with database() as session:
        assert await session.scalar(select(Department.id).where(Department.code == "SEC")) is None


async def test_noop_updates_do_not_duplicate_audit_and_status_validation(database, client):
    admin = await make_user(database, ("ADMIN",))
    department, _ = await create_references(client, admin)
    before = None
    async with database() as session:
        before = int(await session.scalar(select(func.count(DirectoryEvent.id))) or 0)
    same = await client.patch(
        f"/api/v1/directory/departments/{department['id']}",
        headers=auth(admin),
        json={"name": department["name"], "reason": "Idempotent retry"},
    )
    assert same.status_code == 200
    async with database() as session:
        assert int(await session.scalar(select(func.count(DirectoryEvent.id))) or 0) == before
    assert (
        await client.patch(
            f"/api/v1/directory/departments/{department['id']}",
            headers=auth(admin),
            json={"reason": "No fields supplied"},
        )
    ).status_code == 422
    assert (
        await client.put(
            f"/api/v1/directory/users/{uuid4()}/status",
            headers=auth(admin),
            json={"status": "DELETED", "reason": "Invalid lifecycle"},
        )
    ).status_code == 422


async def test_directory_service_layer_happy_paths_and_guards(database):
    """Exercise service transactions directly as a second boundary below HTTP."""
    admin = await make_user(database, ("ADMIN",))
    manager = await make_user(database, ("IT_MANAGER",))
    technician = await make_user(database, ("TECHNICIAN",))
    async with database() as session:
        service = DirectoryService(session)
        department = await service.create_department(
            admin.id,
            {"code": "OPS", "name": "Operations", "description": None},
            "Create operations",
            "direct-service",
        )
        location = await service.create_location(
            admin.id,
            {"code": "REMOTE", "name": "Remote", "timezone": "UTC", "address": None},
            "Create remote location",
            "direct-service",
        )
        team = await service.create_team(
            manager.id,
            {
                "code": "PLATFORM",
                "name": "Platform Support",
                "description": None,
                "department_id": department.id,
                "location_id": location.id,
            },
            "Create platform coverage",
            "direct-service",
        )
        await service.update_department(
            admin.id,
            department.id,
            {"description": "Business operations"},
            "Clarify remit",
            "direct-service",
        )
        await service.update_location(
            admin.id,
            location.id,
            {"address": "Distributed workforce"},
            "Clarify address",
            "direct-service",
        )
        await service.update_team(
            manager.id,
            team.id,
            {"description": "Platform incident response"},
            "Clarify remit",
            "direct-service",
        )
        created = await service.create_user(
            admin.id,
            {
                "email": "service.created@example.com",
                "display_name": "Service Created",
                "employee_number": "EMP-SVC",
                "job_title": "Technician",
                "department_id": department.id,
                "location_id": location.id,
                "initial_password": PASSWORD,
                "roles": ["TECHNICIAN"],
            },
            "Approved hire",
            "direct-service",
        )
        await service.update_user(
            admin.id,
            created.id,
            {"job_title": "Senior Technician"},
            "Promotion",
            "direct-service",
        )
        membership = await service.assign_member(
            manager.id,
            team.id,
            created.id,
            "MEMBER",
            "Assign platform support",
            "direct-service",
        )
        assert (
            await service.assign_member(
                manager.id,
                team.id,
                created.id,
                "MEMBER",
                "Idempotent retry",
                "direct-service",
            )
        ).id == membership.id
        changed = await service.assign_member(
            manager.id,
            team.id,
            created.id,
            "LEAD",
            "Promote team lead",
            "direct-service",
        )
        assert changed.id != membership.id
        await service.remove_member(
            manager.id,
            team.id,
            created.id,
            "Rotate coverage",
            "direct-service",
        )
        assert (
            await service.update_user_status(
                admin.id,
                created.id,
                UserStatus.ACTIVE,
                "Idempotent retry",
                "direct-service",
            )
        ).status == UserStatus.ACTIVE
        assert (
            await service.update_user_status(
                admin.id,
                created.id,
                UserStatus.DISABLED,
                "Leave of absence",
                "direct-service",
            )
        ).status == UserStatus.DISABLED
        assert (
            await service.update_user_status(
                admin.id,
                created.id,
                UserStatus.ACTIVE,
                "Return from leave",
                "direct-service",
            )
        ).status == UserStatus.ACTIVE
        await service.assign_member(
            manager.id,
            team.id,
            technician.id,
            "MEMBER",
            "Add responder",
            "direct-service",
        )
        retired = await service.update_team(
            manager.id,
            team.id,
            {"status": "INACTIVE"},
            "Retire team",
            "direct-service",
        )
        assert retired.status == "INACTIVE"

        for operation in (
            service.update_department(admin.id, uuid4(), {"name": "Missing"}, "Test", "x"),
            service.update_location(admin.id, uuid4(), {"name": "Missing"}, "Test", "x"),
            service.update_team(manager.id, uuid4(), {"name": "Missing"}, "Test", "x"),
            service.update_user(admin.id, uuid4(), {"display_name": "Missing"}, "Test", "x"),
            service.update_user_status(
                admin.id, uuid4(), UserStatus.DISABLED, "Test", "direct-service"
            ),
            service.assign_member(
                manager.id, uuid4(), technician.id, "MEMBER", "Test", "direct-service"
            ),
            service.remove_member(manager.id, uuid4(), technician.id, "Test", "direct-service"),
        ):
            with pytest.raises(HTTPException) as raised:
                await operation
            assert raised.value.status_code == 404
