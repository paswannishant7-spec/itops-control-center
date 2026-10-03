"""Phase 6 ticket workflow tests. PostgreSQL in CI; isolated SQLite locally."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import create_app
from app.modules.access.catalog import PERMISSIONS, ROLE_PERMISSIONS
from app.modules.access.models import Permission, Role, RolePermission, UserRole
from app.modules.alerts.models import (
    Alert,
    AlertEvent,
    AlertPolicy,
    AlertState,
    AutomationExecution,
    AutomationRule,
    Notification,
    NotificationPreference,
)
from app.modules.alerts.schemas import PolicyCreate, PolicyUpdate, RuleCreate, RuleUpdate
from app.modules.alerts.service import AlertService, NotificationService
from app.modules.assets.models import Asset, AssetAssignment, AssetEvent, AssetStatus
from app.modules.assets.schemas import AssetAssignmentCreate, AssetCreate, AssetUpdate
from app.modules.assets.service import AssetService
from app.modules.directory.models import Department, DirectoryStatus, Location, Team, TeamMember
from app.modules.identity.models import RefreshSession, User, UserStatus
from app.modules.identity.security import PasswordService, TokenService
from app.modules.monitoring.models import DeviceAgent, DeviceHeartbeat, DeviceMetric
from app.modules.monitoring.schemas import HeartbeatCreate, MetricCreate
from app.modules.monitoring.security import secret_hash
from app.modules.monitoring.service import MonitoringService
from app.modules.sla.models import (
    BusinessCalendar,
    BusinessWindow,
    SlaEvent,
    SlaInstance,
    SlaPause,
    SlaState,
)
from app.modules.sla.repository import CalendarBundle
from app.modules.sla.seeds import add_default_sla_configuration
from app.modules.sla.service import SlaService, business_seconds, elapsed_business_seconds
from app.modules.tickets.models import (
    CommentVisibility,
    Ticket,
    TicketAssignment,
    TicketCategory,
    TicketComment,
    TicketEvent,
    TicketStatus,
    TicketSubcategory,
    TicketType,
)
from app.modules.tickets.service import (
    LEGAL_TRANSITIONS,
    TicketService,
    calculate_priority,
    transition_permission,
)
from app.modules.tickets.storage import (
    AttachmentValidationError,
    LocalAttachmentStorage,
    validate_attachment,
)

pytestmark = pytest.mark.anyio
PASSWORD = "Correct-Horse-7!"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        jwt_secret="test-ticket-signing-key-at-least-32-characters",
        attachment_storage_path=tmp_path / "attachments",
        attachment_max_bytes=1024,
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
            if not await session.scalar(select(BusinessCalendar.id).limit(1)):
                add_default_sla_configuration(session)
            # Each test enables its own policies; migrations provide additional defaults.
            # The outer rollback restores those defaults after every test.
            await session.execute(update(AlertPolicy).values(enabled=False))
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


async def make_department(factory, code: str = "IT") -> Department:
    async with factory() as session:
        record = Department(
            id=uuid4(),
            code=code,
            name=f"{code} department",
            description=None,
            status=DirectoryStatus.ACTIVE,
        )
        session.add(record)
        await session.commit()
        return record


async def make_user(
    factory,
    settings: Settings,
    role: str | None,
    department_id: UUID | None,
    *,
    name: str,
) -> User:
    async with factory() as session:
        record = User(
            id=uuid4(),
            email=f"{name.lower().replace(' ', '.')}@example.com",
            display_name=name,
            department_id=department_id,
            location_id=None,
            employee_number=None,
            job_title=None,
            password_hash=PasswordService().hash(PASSWORD),
            status=UserStatus.ACTIVE,
            password_changed_at=datetime.now(UTC),
        )
        session_id = uuid4()
        session.add(record)
        await session.flush()
        session.add(
            RefreshSession(
                id=session_id,
                user_id=record.id,
                family_id=uuid4(),
                token_hash=uuid4().hex + uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        if role:
            session.add(UserRole(user_id=record.id, role_code=role))
        await session.commit()
        record.test_session_id = session_id
        record.test_settings = settings
        return record


def auth(user: User) -> dict[str, str]:
    token = TokenService(user.test_settings).create_access_token(user.id, user.test_session_id)
    return {"Authorization": f"Bearer {token}"}


async def make_team(factory, department_id: UUID, technician_id: UUID, code: str = "DESK") -> Team:
    async with factory() as session:
        team = Team(
            id=uuid4(),
            code=code,
            name=f"{code} team",
            description=None,
            status=DirectoryStatus.ACTIVE,
            department_id=department_id,
            location_id=None,
        )
        session.add(team)
        await session.flush()
        session.add(
            TeamMember(
                id=uuid4(),
                team_id=team.id,
                user_id=technician_id,
                member_role="MEMBER",
                started_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return team


async def create_ticket(client: httpx.AsyncClient, requester: User, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "title": "Unable to connect to corporate VPN",
        "description": "The VPN client reports that the gateway cannot be reached.",
        "impact": "HIGH",
        "urgency": "HIGH",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/tickets", headers=auth(requester), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def create_asset(
    client: httpx.AsyncClient, admin: User, **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "asset_tag": f"LT-{uuid4().hex[:8]}",
        "asset_type": "LAPTOP",
        "manufacturer": "Framework",
        "model": "Laptop 13",
        "reason": "Register corporate hardware",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/assets", headers=auth(admin), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_analytics_endpoint_permission_scope_and_window_validation(
    database, client, settings
):
    department = await make_department(database, "ANALYTICS")
    employee = await make_user(
        database, settings, "EMPLOYEE", department.id, name="Dashboard Employee"
    )
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Dashboard Technician"
    )
    manager = await make_user(
        database, settings, "IT_MANAGER", department.id, name="Dashboard Manager"
    )
    await make_team(database, department.id, technician.id, "ANALYTICS-DESK")

    denied = await client.get("/api/v1/analytics/dashboard", headers=auth(employee))
    invalid = await client.get("/api/v1/analytics/dashboard?window_days=366", headers=auth(manager))
    scoped = await client.get("/api/v1/analytics/dashboard?window_days=7", headers=auth(technician))
    organization = await client.get(
        "/api/v1/analytics/dashboard?window_days=30", headers=auth(manager)
    )

    assert denied.status_code == 403
    assert invalid.status_code == 422
    assert scoped.status_code == 200 and scoped.json()["scope"]["audience"] == "TEAM"
    assert organization.status_code == 200
    assert organization.json()["scope"]["audience"] == "ORGANIZATION"
    assert organization.json()["performance"]["mttr"] == {
        "minutes": None,
        "sample_size": 0,
    }


async def test_asset_inventory_scoping_assignment_history_and_ticket_links(
    database, client, settings
):
    it = await make_department(database, "ASSET_IT")
    finance = await make_department(database, "ASSET_FIN")
    owner = await make_user(database, settings, "EMPLOYEE", it.id, name="Asset Owner")
    stranger = await make_user(database, settings, "EMPLOYEE", it.id, name="Asset Stranger")
    technician = await make_user(database, settings, "TECHNICIAN", it.id, name="Asset Technician")
    other_technician = await make_user(
        database, settings, "TECHNICIAN", finance.id, name="Other Asset Technician"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Asset Administrator")
    await make_team(database, it.id, technician.id, "ASSET_DESK")
    await make_team(database, finance.id, other_technician.id, "OTHER_ASSET_DESK")

    created = await create_asset(
        client,
        admin,
        asset_tag="lt-0001",
        serial_number="SERIAL-0001",
        owner_id=str(owner.id),
        department_id=str(it.id),
        ip_address="192.0.2.8",
        mac_address="aa-bb-cc-dd-ee-ff",
    )
    asset_id = created["id"]
    assert created["asset_tag"] == "LT-0001"
    assert created["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert created["owner"]["id"] == str(owner.id)

    assert (await client.get("/api/v1/assets", headers=auth(owner))).json()["total"] == 1
    assert (await client.get("/api/v1/assets", headers=auth(stranger))).json()["total"] == 0
    assert (await client.get("/api/v1/assets", headers=auth(technician))).json()["total"] == 1
    assert (
        await client.get(f"/api/v1/assets/{asset_id}", headers=auth(other_technician))
    ).status_code == 404
    assert (await client.get("/api/v1/assets")).status_code == 401

    denied = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers=auth(technician),
        json={"hostname": "desk-01", "reason": "Attempt unauthorized change"},
    )
    assert denied.status_code == 403
    duplicate = await client.post(
        "/api/v1/assets",
        headers=auth(admin),
        json={
            "asset_tag": "LT-0001",
            "asset_type": "DESKTOP",
            "reason": "Exercise unique inventory identifier",
        },
    )
    assert duplicate.status_code == 409

    updated = await client.patch(
        f"/api/v1/assets/{asset_id}",
        headers=auth(admin),
        json={
            "hostname": "asset-owner-laptop",
            "health_status": "HEALTHY",
            "reason": "Record verified inventory details",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["hostname"] == "asset-owner-laptop"

    reassigned = await client.post(
        f"/api/v1/assets/{asset_id}/assignments",
        headers=auth(admin),
        json={
            "owner_id": str(stranger.id),
            "department_id": str(it.id),
            "reason": "Transfer custody to replacement employee",
        },
    )
    assert reassigned.status_code == 200
    assert reassigned.json()["owner"]["id"] == str(stranger.id)
    assert (await client.get("/api/v1/assets", headers=auth(owner))).json()["total"] == 0

    history = await client.get(f"/api/v1/assets/{asset_id}/history", headers=auth(admin))
    assert history.status_code == 200
    assert len(history.json()["assignments"]) == 2
    assert history.json()["assignments"][1]["ended_at"] is not None
    assert [event["action"] for event in history.json()["events"]] == [
        "asset.assigned",
        "asset.updated",
        "asset.created",
    ]

    ticket = await create_ticket(client, stranger, asset_id=asset_id)
    links = await client.get(f"/api/v1/assets/{asset_id}/tickets", headers=auth(stranger))
    assert links.status_code == 200
    assert links.json()[0]["id"] == ticket["id"]

    retired = await client.post(
        f"/api/v1/assets/{asset_id}/retire",
        headers=auth(admin),
        json={"reason": "Hardware reached the end of its service life"},
    )
    assert retired.status_code == 200
    assert retired.json()["status"] == "RETIRED"
    assert retired.json()["owner"] is None
    cannot_link = await create_asset(client, admin, asset_tag="ACTIVE-2", owner_id=str(stranger.id))
    response = await client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        headers=auth(admin),
        json={"asset_id": asset_id, "reason": "Try to link retired hardware"},
    )
    assert response.status_code == 409
    assert cannot_link["status"] == "ACTIVE"

    async with database() as session:
        assert len(list(await session.scalars(select(Asset)))) == 2
        assert len(list(await session.scalars(select(AssetAssignment)))) == 3
        assert len(list(await session.scalars(select(AssetEvent)))) >= 5


async def test_asset_validation_filters_clear_and_reference_errors(database, client, settings):
    department = await make_department(database, "ASSET_QA")
    admin = await make_user(database, settings, "ADMIN", None, name="Asset QA Admin")
    employee = await make_user(
        database, settings, "EMPLOYEE", department.id, name="Asset QA Employee"
    )
    invalid = await client.post(
        "/api/v1/assets",
        headers=auth(admin),
        json={
            "asset_tag": "QA-1",
            "asset_type": "LAPTOP",
            "ip_address": "not-an-ip",
            "reason": "Validate network identifiers",
        },
    )
    assert invalid.status_code == 422
    created = await create_asset(
        client,
        admin,
        asset_tag="QA-2",
        asset_type="SERVER",
        owner_id=str(employee.id),
        department_id=str(department.id),
    )
    filtered = await client.get(
        "/api/v1/assets",
        headers=auth(admin),
        params={"search": "qa-2", "asset_type": "SERVER", "status": "ACTIVE"},
    )
    assert filtered.status_code == 200 and filtered.json()["total"] == 1
    bad_reference = await client.post(
        f"/api/v1/assets/{created['id']}/assignments",
        headers=auth(admin),
        json={
            "owner_id": str(uuid4()),
            "reason": "Exercise assignment reference validation",
        },
    )
    assert bad_reference.status_code == 422
    cleared = await client.post(
        f"/api/v1/assets/{created['id']}/assignments",
        headers=auth(admin),
        json={"clear": True, "reason": "Return asset to unassigned inventory"},
    )
    assert cleared.status_code == 200 and cleared.json()["owner"] is None


async def test_asset_service_guards_and_schema_normalization(database, settings):
    department = await make_department(database, "ASSET_SERVICE")
    admin = await make_user(database, settings, "ADMIN", None, name="Asset Service Admin")
    employee = await make_user(
        database, settings, "EMPLOYEE", department.id, name="Asset Service Owner"
    )
    outsider = await make_user(database, settings, None, department.id, name="Asset No Role")
    async with database() as session:
        location = Location(
            id=uuid4(),
            code="ASSET_HQ",
            name="Asset headquarters",
            timezone="UTC",
            address=None,
            status=DirectoryStatus.ACTIVE,
        )
        session.add(location)
        await session.commit()
        service = AssetService(session)
        values = AssetCreate(
            asset_tag=" svc-100 ",
            asset_type="NETWORK_DEVICE",
            owner_id=employee.id,
            department_id=department.id,
            location_id=location.id,
            purchase_date=date(2026, 1, 1),
            warranty_end=date(2027, 1, 1),
            ip_address="2001:db8::1",
            mac_address="00-11-22-33-44-55",
            reason="Direct service lifecycle coverage",
        )
        assert values.asset_tag == "SVC-100"
        assert values.ip_address == "2001:db8::1"
        asset = await service.create_asset(
            admin.id,
            values.model_dump(exclude={"reason"}),
            values.reason,
            "request-direct-create",
        )
        record = await service.get_asset(employee.id, asset.id)
        assert record.asset.id == asset.id
        with pytest.raises(HTTPException) as denied:
            await service.list_assets(
                outsider.id,
                search=None,
                asset_type=None,
                status=None,
                health_status=None,
                owner_id=None,
                department_id=None,
                location_id=None,
                offset=0,
                limit=25,
            )
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as hidden:
            await service.get_asset(outsider.id, asset.id)
        assert hidden.value.status_code == 403
        with pytest.raises(HTTPException) as forbidden:
            await service.create_asset(
                employee.id,
                {"asset_tag": "NOPE", "asset_type": "LAPTOP"},
                "Unauthorized asset creation",
                "request-denied",
            )
        assert forbidden.value.status_code == 403
        with pytest.raises(HTTPException) as bad_dates:
            await service.update_asset(
                admin.id,
                asset.id,
                {"purchase_date": date(2028, 1, 1)},
                "Reject invalid warranty interval",
                "request-bad-date",
            )
        assert bad_dates.value.status_code == 422
        await service.assign(
            admin.id,
            asset.id,
            None,
            department.id,
            location.id,
            False,
            "Move custody to shared department inventory",
            "request-reassign",
        )
        assignments, events = await service.history(admin.id, asset.id)
        assert len(assignments) == 2 and len(events) == 2
        await service.retire(admin.id, asset.id, "Retire direct test hardware", "request-retire")
        assert await service.retire(admin.id, asset.id, "Repeat retirement", "request-repeat")
        with pytest.raises(HTTPException) as retired_edit:
            await service.update_asset(
                admin.id,
                asset.id,
                {"hostname": "blocked"},
                "Reject terminal edit",
                "request-terminal-edit",
            )
        assert retired_edit.value.status_code == 409
        with pytest.raises(HTTPException) as retired_assignment:
            await service.assign(
                admin.id,
                asset.id,
                employee.id,
                department.id,
                location.id,
                False,
                "Reject terminal assignment",
                "request-terminal-assign",
            )
        assert retired_assignment.value.status_code == 409

        asset.status = AssetStatus.DISPOSED
        await session.commit()
        with pytest.raises(HTTPException) as disposed_retire:
            await service.retire(
                admin.id, asset.id, "Reject disposed retirement", "request-disposed"
            )
        assert disposed_retire.value.status_code == 409

    with pytest.raises(ValueError):
        AssetCreate(
            asset_tag="BAD-IP",
            asset_type="LAPTOP",
            ip_address="invalid",
            reason="Reject invalid IP address",
        )
    with pytest.raises(ValueError):
        AssetCreate(
            asset_tag="BAD-MAC",
            asset_type="LAPTOP",
            mac_address="not-a-mac",
            reason="Reject invalid MAC address",
        )
    with pytest.raises(ValueError):
        AssetCreate(
            asset_tag="BAD-DATES",
            asset_type="LAPTOP",
            purchase_date=date(2027, 1, 1),
            warranty_end=date(2026, 1, 1),
            reason="Reject invalid dates",
        )
    with pytest.raises(ValueError):
        AssetUpdate(reason="Require a changed field")
    with pytest.raises(ValueError):
        AssetUpdate(status="RETIRED", reason="Require retirement endpoint")
    with pytest.raises(ValueError):
        AssetAssignmentCreate(reason="Require target or clear")
    with pytest.raises(ValueError):
        AssetAssignmentCreate(
            owner_id=employee.id,
            clear=True,
            reason="Do not combine target and clear",
        )


async def test_monitoring_enrollment_authentication(database, client, settings):
    department = await make_department(database, "MONITORING")
    other_department = await make_department(database, "MONITORING_OTHER")
    owner = await make_user(database, settings, "EMPLOYEE", department.id, name="Monitored Owner")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Monitoring Technician"
    )
    outsider = await make_user(
        database, settings, "TECHNICIAN", other_department.id, name="Remote Technician"
    )
    manager = await make_user(database, settings, "IT_MANAGER", None, name="Monitoring Manager")
    admin = await make_user(database, settings, "ADMIN", None, name="Monitoring Admin")
    await make_team(database, department.id, technician.id, "MONITOR_TEAM")
    await make_team(database, other_department.id, outsider.id, "REMOTE_MONITOR_TEAM")
    asset = await create_asset(
        client,
        admin,
        asset_tag="MON-100",
        asset_type="DESKTOP",
        owner_id=str(owner.id),
        department_id=str(department.id),
    )

    forbidden = await client.post(
        "/api/v1/monitoring/enrollments",
        headers=auth(manager),
        json={
            "asset_id": asset["id"],
            "reason": "Managers cannot issue agent credentials",
        },
    )
    assert forbidden.status_code == 403
    created = await client.post(
        "/api/v1/monitoring/enrollments",
        headers=auth(admin),
        json={
            "asset_id": asset["id"],
            "expires_in_minutes": 15,
            "reason": "Enroll managed workstation agent",
        },
    )
    assert created.status_code == 201, created.text
    enrollment = created.json()
    token = enrollment["enrollment_token"]
    assert len(token) >= 32
    async with database() as session:
        stored = await session.get(DeviceAgent, UUID(enrollment["agent_id"]))
        assert stored is not None
        assert stored.enrollment_token_hash == secret_hash(token)
        assert token != stored.enrollment_token_hash
        assert stored.credential_hash is None

    invalid = await client.post(
        "/api/v1/monitoring/enroll",
        json={"enrollment_token": "x" * 40, "agent_version": "0.1.0"},
    )
    assert invalid.status_code == 401
    enrolled = await client.post(
        "/api/v1/monitoring/enroll",
        json={"enrollment_token": token, "agent_version": "0.1.0"},
    )
    assert enrolled.status_code == 200, enrolled.text
    credential = enrolled.json()["credential"]
    agent_id = enrolled.json()["agent_id"]
    agent_headers = {"Authorization": f"Agent {agent_id}.{credential}"}
    assert agent_headers["Authorization"].startswith("Agent ")
    assert (
        await client.post(
            "/api/v1/monitoring/enroll",
            json={"enrollment_token": token, "agent_version": "0.1.0"},
        )
    ).status_code == 401


async def test_alert_configuration_and_enrollment_guards(database, client, settings):
    department = await make_department(database, "ALERTS")
    other_department = await make_department(database, "ALERTS_OTHER")
    owner = await make_user(database, settings, "EMPLOYEE", department.id, name="Alert Owner")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Alert Technician"
    )
    outsider = await make_user(
        database, settings, "TECHNICIAN", other_department.id, name="Other Alert Technician"
    )
    manager = await make_user(database, settings, "IT_MANAGER", None, name="Alert Manager")
    admin = await make_user(database, settings, "ADMIN", None, name="Alert Administrator")
    team = await make_team(database, department.id, technician.id, "ALERT_DESK")
    await make_team(database, other_department.id, outsider.id, "OTHER_ALERT_DESK")
    asset = await create_asset(
        client,
        admin,
        asset_tag="ALERT-100",
        owner_id=str(owner.id),
        department_id=str(department.id),
    )

    policy_payload = {
        "name": "Test critical CPU",
        "metric": "CPU_PERCENT",
        "operator": "GREATER_THAN",
        "threshold": 80,
        "severity": "CRITICAL",
        "enabled": True,
        "reason": "Exercise critical CPU alerting",
    }
    assert (
        await client.post("/api/v1/alerts/policies", headers=auth(manager), json=policy_payload)
    ).status_code == 403
    policy_response = await client.post(
        "/api/v1/alerts/policies", headers=auth(admin), json=policy_payload
    )
    assert policy_response.status_code == 201, policy_response.text
    policy = policy_response.json()
    assert policy["metric"] == "CPU_PERCENT"
    assert (
        await client.post("/api/v1/alerts/policies", headers=auth(admin), json=policy_payload)
    ).status_code == 409
    assert (
        await client.post(
            "/api/v1/alerts/policies",
            headers=auth(admin),
            json={**policy_payload, "name": "Invalid percent", "threshold": 101},
        )
    ).status_code == 422

    rule_response = await client.post(
        "/api/v1/automation/rules",
        headers=auth(admin),
        json={
            "name": "Critical endpoint incident",
            "minimum_severity": "CRITICAL",
            "create_incident": True,
            "notify_team": True,
            "assignment_team_id": str(team.id),
            "reason": "Create owned incidents for critical endpoint alerts",
        },
    )
    assert rule_response.status_code == 201, rule_response.text
    rule = rule_response.json()
    assert rule["create_incident"] is True

    enrollment = (
        await client.post(
            "/api/v1/monitoring/enrollments",
            headers=auth(admin),
            json={"asset_id": asset["id"], "reason": "Enroll alert test endpoint"},
        )
    ).json()
    enrolled = (
        await client.post(
            "/api/v1/monitoring/enroll",
            json={"enrollment_token": enrollment["enrollment_token"], "agent_version": "test"},
        )
    ).json()
    agent_headers = {"Authorization": f"Agent {enrolled['agent_id']}.{enrolled['credential']}"}
    assert agent_headers["Authorization"].startswith("Agent ")


async def test_alert_automation_incident_deduplication_and_notifications(
    database, client, settings, monkeypatch
):
    department = await make_department(database, "MONITORING_FLOW")
    other_department = await make_department(database, "MONITORING_FLOW_OTHER")
    owner = await make_user(
        database, settings, "EMPLOYEE", department.id, name="Monitoring Flow Owner"
    )
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Monitoring Flow Technician"
    )
    outsider = await make_user(
        database,
        settings,
        "TECHNICIAN",
        other_department.id,
        name="Monitoring Flow Outsider",
    )
    manager = await make_user(
        database, settings, "IT_MANAGER", None, name="Monitoring Flow Manager"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Monitoring Flow Admin")
    team = await make_team(database, department.id, technician.id, "MONITORING_FLOW_DESK")
    await make_team(database, other_department.id, outsider.id, "MONITORING_OTHER_DESK")
    asset = await create_asset(
        client,
        admin,
        asset_tag="MON-FLOW",
        owner_id=str(owner.id),
        department_id=str(department.id),
    )
    policy = (
        await client.post(
            "/api/v1/alerts/policies",
            headers=auth(admin),
            json={
                "name": "Flow critical CPU",
                "metric": "CPU_PERCENT",
                "operator": "GREATER_THAN",
                "threshold": 80,
                "severity": "CRITICAL",
                "reason": "Exercise alert automation flow",
            },
        )
    ).json()
    rule = (
        await client.post(
            "/api/v1/automation/rules",
            headers=auth(admin),
            json={
                "name": "Flow critical incident",
                "minimum_severity": "CRITICAL",
                "create_incident": True,
                "notify_team": True,
                "assignment_team_id": str(team.id),
                "reason": "Create and notify for flow alerts",
            },
        )
    ).json()
    enrollment = (
        await client.post(
            "/api/v1/monitoring/enrollments",
            headers=auth(admin),
            json={"asset_id": asset["id"], "reason": "Enroll monitoring flow endpoint"},
        )
    ).json()
    enrolled = (
        await client.post(
            "/api/v1/monitoring/enroll",
            json={"enrollment_token": enrollment["enrollment_token"], "agent_version": "test"},
        )
    ).json()
    agent_id = enrolled["agent_id"]
    agent_headers = {"Authorization": f"Agent {agent_id}.{enrolled['credential']}"}
    now = datetime.now(UTC)
    heartbeat_payload = {
        "observed_at": now.isoformat(),
        "hostname": "alert-device",
        "operating_system": "Test OS",
        "boot_time": (now - timedelta(days=1)).isoformat(),
    }
    assert (
        await client.post(
            "/api/v1/monitoring/agent/heartbeat",
            headers=agent_headers,
            json=heartbeat_payload,
        )
    ).status_code == 200

    def metric(cpu: float) -> dict[str, object]:
        return {
            "sampled_at": datetime.now(UTC).isoformat(),
            "cpu_percent": cpu,
            "memory_percent": 20,
            "memory_used_bytes": 20,
            "memory_total_bytes": 100,
            "disk_percent": 30,
            "disk_used_bytes": 30,
            "disk_total_bytes": 100,
            "network_bytes_sent": 1,
            "network_bytes_received": 2,
        }

    high = await client.post(
        "/api/v1/monitoring/agent/metrics", headers=agent_headers, json=metric(95)
    )
    assert high.status_code == 200 and high.json()["accepted"] is True
    visible = await client.get("/api/v1/alerts", headers=auth(technician))
    assert visible.status_code == 200 and visible.json()["total"] == 1
    assert (await client.get("/api/v1/alerts", headers=auth(outsider))).json()["total"] == 0
    assert (await client.get("/api/v1/alerts", headers=auth(owner))).status_code == 403
    alert = visible.json()["items"][0]
    assert alert["metric"] == "CPU_PERCENT" and alert["incident_reference"].startswith("INC-")

    incident = await client.get(
        f"/api/v1/tickets/{alert['incident_ticket_id']}", headers=auth(technician)
    )
    assert incident.status_code == 200
    assert incident.json()["record_type"] == "INCIDENT"
    assert incident.json()["source"] == "AUTOMATION"
    assert incident.json()["assignment_team"]["id"] == str(team.id)
    assert incident.json()["sla_state"] == "ON_TRACK"

    notifications = await client.get("/api/v1/notifications", headers=auth(technician))
    assert notifications.status_code == 200
    assert notifications.json()["total"] == 1 and notifications.json()["unread"] == 1
    notification_id = notifications.json()["items"][0]["id"]
    read = await client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=auth(technician)
    )
    assert read.status_code == 200 and read.json()["read_at"] is not None
    assert (
        await client.post(f"/api/v1/notifications/{notification_id}/read", headers=auth(outsider))
    ).status_code == 404
    executions = await client.get("/api/v1/automation/executions", headers=auth(admin))
    assert executions.status_code == 200 and executions.json()["total"] == 1
    assert executions.json()["items"][0]["status"] == "SUCCEEDED"

    async with database() as session:
        agent = await session.get(DeviceAgent, UUID(enrolled["agent_id"]))
        assert agent is not None
        agent.last_metric_at = datetime.now(UTC) - timedelta(minutes=2)
        await session.commit()
    assert (
        await client.post(
            "/api/v1/monitoring/agent/metrics", headers=agent_headers, json=metric(99)
        )
    ).json()["accepted"] is True
    assert (await client.get("/api/v1/alerts", headers=auth(admin))).json()["total"] == 1
    assert (await client.get("/api/v1/automation/executions", headers=auth(admin))).json()[
        "total"
    ] == 1
    assert (await client.get("/api/v1/notifications", headers=auth(technician))).json()[
        "total"
    ] == 1

    acknowledged = await client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge",
        headers=auth(technician),
        json={"reason": "Technician is investigating"},
    )
    assert acknowledged.status_code == 200 and acknowledged.json()["state"] == "ACKNOWLEDGED"
    assert (
        await client.post(
            f"/api/v1/alerts/{alert['id']}/suppress",
            headers=auth(technician),
            json={"reason": "Technician cannot suppress alerts"},
        )
    ).status_code == 403
    suppressed = await client.post(
        f"/api/v1/alerts/{alert['id']}/suppress",
        headers=auth(admin),
        json={"reason": "Suppress while maintenance is performed"},
    )
    assert suppressed.status_code == 200 and suppressed.json()["state"] == "SUPPRESSED"

    async with database() as session:
        agent = await session.get(DeviceAgent, UUID(enrolled["agent_id"]))
        assert agent is not None
        agent.last_metric_at = datetime.now(UTC) - timedelta(minutes=2)
        await session.commit()
    assert (
        await client.post(
            "/api/v1/monitoring/agent/metrics", headers=agent_headers, json=metric(20)
        )
    ).status_code == 200
    resolved = await client.get(f"/api/v1/alerts/{alert['id']}", headers=auth(manager))
    assert resolved.status_code == 200 and resolved.json()["state"] == "RESOLVED"

    preferences = await client.get("/api/v1/notifications/preferences/me", headers=auth(technician))
    assert preferences.status_code == 200 and preferences.json()["in_app_enabled"] is True
    updated_preferences = await client.put(
        "/api/v1/notifications/preferences/me",
        headers=auth(technician),
        json={"in_app_enabled": True, "minimum_alert_severity": "INFO"},
    )
    assert updated_preferences.status_code == 200
    async with database() as session:
        agent = await session.get(DeviceAgent, UUID(enrolled["agent_id"]))
        assert agent is not None
        direct_metric = DeviceMetric(
            agent_id=agent.id,
            sampled_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            cpu_percent=97,
            memory_percent=20,
            memory_used_bytes=20,
            memory_total_bytes=100,
            disk_percent=30,
            disk_used_bytes=30,
            disk_total_bytes=100,
            network_bytes_sent=3,
            network_bytes_received=4,
        )
        direct_service = AlertService(session)
        await direct_service.evaluate_metric(agent, direct_metric)
        await session.commit()
        direct_alert = await session.scalar(
            select(Alert)
            .where(Alert.state == "TRIGGERED")
            .order_by(Alert.triggered_at.desc(), Alert.id.desc())
        )
        assert direct_alert is not None
        await direct_service.transition(
            technician.id,
            direct_alert.id,
            AlertState.ACKNOWLEDGED,
            "Direct technician acknowledgement",
            "direct-alert-acknowledge",
        )
        failing_rule = await direct_service.create_rule(
            admin.id,
            RuleCreate(
                name="Failing incident rule",
                minimum_severity="CRITICAL",
                create_incident=True,
                assignment_team_id=team.id,
                reason="Exercise bounded automation failure",
            ),
            "failing-incident-rule",
        )

        async def reject_incident(*_args):
            raise HTTPException(422, "Synthetic incident action failure")

        monkeypatch.setattr(AlertService, "_incident", reject_incident)
        await direct_service._automate(direct_alert)
        await session.commit()
        failed_execution = await session.scalar(
            select(AutomationExecution).where(
                AutomationExecution.rule_id == failing_rule.id,
                AutomationExecution.alert_id == direct_alert.id,
            )
        )
        assert failed_execution is not None
        assert failed_execution.status == "FAILED"
        assert failed_execution.error_code == "ACTION_FAILED"
        assert failed_execution.incident_ticket_id is None
    assert (await client.get("/api/v1/alerts", headers=auth(admin))).json()["total"] == 2
    assert (await client.get("/api/v1/automation/executions", headers=auth(admin))).json()[
        "total"
    ] == 3
    assert (await client.get("/api/v1/notifications", headers=auth(technician))).json()[
        "total"
    ] == 2
    disabled_preferences = await client.put(
        "/api/v1/notifications/preferences/me",
        headers=auth(technician),
        json={"in_app_enabled": False, "minimum_alert_severity": "CRITICAL"},
    )
    assert disabled_preferences.status_code == 200
    update_rule = await client.patch(
        f"/api/v1/automation/rules/{rule['id']}",
        headers=auth(admin),
        json={"enabled": False, "reason": "Pause automated incident creation"},
    )
    assert update_rule.status_code == 200 and update_rule.json()["enabled"] is False
    update_policy = await client.patch(
        f"/api/v1/alerts/policies/{policy['id']}",
        headers=auth(admin),
        json={"enabled": False, "reason": "Disable completed test policy"},
    )
    assert update_policy.status_code == 200 and update_policy.json()["enabled"] is False


async def test_alert_services_validation_and_persistence(database, client, settings):
    department = await make_department(database, "ALERT_DIRECT")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Direct Alert Technician"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Direct Alert Admin")
    team = await make_team(database, department.id, technician.id, "DIRECT_ALERT_DESK")
    async with database() as session:
        service = AlertService(session)
        policy = await service.create_policy(
            admin.id,
            PolicyCreate(
                name="Direct disk policy",
                metric="DISK_PERCENT",
                operator="AT_LEAST",
                threshold=85,
                severity="HIGH",
                reason="Create direct service policy",
            ),
            "direct-policy",
        )
        policy = await service.update_policy(
            admin.id,
            policy.id,
            PolicyUpdate(threshold=90, reason="Raise direct threshold"),
            "direct-policy-update",
        )
        assert policy.threshold == 90
        rule = await service.create_rule(
            admin.id,
            RuleCreate(
                name="Direct notification rule",
                minimum_severity="HIGH",
                notify_team=True,
                assignment_team_id=team.id,
                reason="Notify direct test team",
            ),
            "direct-rule",
        )
        rule = await service.update_rule(
            admin.id,
            rule.id,
            RuleUpdate(minimum_severity="CRITICAL", reason="Narrow direct rule"),
            "direct-rule-update",
        )
        assert rule.minimum_severity == "CRITICAL"
        with pytest.raises(HTTPException) as no_actions:
            await service.update_rule(
                admin.id,
                rule.id,
                RuleUpdate(
                    create_incident=False,
                    notify_team=False,
                    reason="Reject rule without actions",
                ),
                "invalid-rule",
            )
        assert no_actions.value.status_code == 422
        with pytest.raises(HTTPException) as missing_policy:
            await service.update_policy(
                admin.id,
                uuid4(),
                PolicyUpdate(enabled=False, reason="Missing policy"),
                "missing-policy",
            )
        assert missing_policy.value.status_code == 404
        with pytest.raises(HTTPException) as missing_rule:
            await service.update_rule(
                admin.id,
                uuid4(),
                RuleUpdate(enabled=False, reason="Missing rule"),
                "missing-rule",
            )
        assert missing_rule.value.status_code == 404

        preference_service = NotificationService(session)
        preference = await preference_service.update_preference(technician.id, True, "HIGH")
        assert preference.minimum_alert_severity == "HIGH"
        values, total, unread = await preference_service.list(technician.id, True, 0, 10)
        assert values == [] and total == 0 and unread == 0
        with pytest.raises(HTTPException) as missing_notification:
            await preference_service.mark_read(technician.id, uuid4())
        assert missing_notification.value.status_code == 404

    with pytest.raises(ValueError):
        PolicyCreate(
            name="Invalid offline threshold",
            metric="DEVICE_OFFLINE",
            operator="AT_LEAST",
            threshold=2,
            severity="HIGH",
            reason="Reject invalid offline threshold",
        )
    with pytest.raises(ValueError):
        RuleCreate(
            name="No action",
            minimum_severity="WARNING",
            reason="Reject actionless rule",
        )

    async with database() as session:
        assert await session.get(AlertPolicy, policy.id) is not None
        assert len(list(await session.scalars(select(AutomationRule)))) == 1
        assert len(list(await session.scalars(select(NotificationPreference)))) == 1
        assert len(list(await session.scalars(select(AlertEvent)))) == 4
        assert len(list(await session.scalars(select(Alert)))) == 0
        assert len(list(await session.scalars(select(AutomationExecution)))) == 0
        assert len(list(await session.scalars(select(Notification)))) == 0
        assert (
            len(
                list(
                    await session.scalars(
                        select(Ticket).where(Ticket.record_type == TicketType.INCIDENT)
                    )
                )
            )
            == 0
        )


async def test_offline_and_missed_heartbeat_alerts_deduplicate_and_recover(
    database, client, settings
):
    department = await make_department(database, "ALERT_OFFLINE")
    owner = await make_user(
        database, settings, "EMPLOYEE", department.id, name="Offline Alert Owner"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Offline Alert Admin")
    asset = await create_asset(
        client,
        admin,
        asset_tag="ALERT-OFFLINE-100",
        owner_id=str(owner.id),
        department_id=str(department.id),
    )
    enrollment = (
        await client.post(
            "/api/v1/monitoring/enrollments",
            headers=auth(admin),
            json={"asset_id": asset["id"], "reason": "Enroll offline alert endpoint"},
        )
    ).json()
    enrolled = (
        await client.post(
            "/api/v1/monitoring/enroll",
            json={"enrollment_token": enrollment["enrollment_token"], "agent_version": "test"},
        )
    ).json()
    current = datetime.now(UTC).replace(microsecond=0)
    async with database() as session:
        alert_service = AlertService(session)
        offline_policy = await alert_service.create_policy(
            admin.id,
            PolicyCreate(
                name="Direct device offline",
                metric="DEVICE_OFFLINE",
                operator="AT_LEAST",
                threshold=1,
                severity="HIGH",
                reason="Detect unavailable direct test device",
            ),
            "offline-policy",
        )
        await alert_service.create_policy(
            admin.id,
            PolicyCreate(
                name="Direct missed heartbeats",
                metric="HEARTBEAT_MISSED",
                operator="AT_LEAST",
                threshold=3,
                severity="CRITICAL",
                reason="Detect repeated missed direct heartbeats",
            ),
            "missed-policy",
        )
        agent = await session.get(DeviceAgent, UUID(enrolled["agent_id"]))
        assert agent is not None
        agent.status = "ONLINE"
        agent.last_heartbeat_at = current - timedelta(minutes=10)
        await session.commit()
        assert (await MonitoringService(session, settings).reconcile(current))[0] == 1
        assert (await MonitoringService(session, settings).reconcile(current))[0] == 1
        active = list(
            await session.scalars(
                select(Alert).where(Alert.state.in_(("TRIGGERED", "ACKNOWLEDGED")))
            )
        )
        assert len(active) == 2
        assert {value.metric for value in active} == {
            "DEVICE_OFFLINE",
            "HEARTBEAT_MISSED",
        }

        await alert_service.update_policy(
            admin.id,
            offline_policy.id,
            PolicyUpdate(enabled=False, reason="Disable offline policy during maintenance"),
            "disable-offline-policy",
        )
        agent = await session.get(DeviceAgent, UUID(enrolled["agent_id"]))
        assert agent is not None
        agent.status = "ONLINE"
        agent.missed_heartbeat_count = 0
        await alert_service.evaluate_device(agent, current)
        await session.commit()
        await MonitoringService(session, settings).heartbeat(
            agent,
            HeartbeatCreate(
                observed_at=current,
                hostname="recovered-device",
                operating_system="Test OS",
                boot_time=current - timedelta(days=1),
            ),
        )
        alerts = list(await session.scalars(select(Alert)))
        assert len(alerts) == 2 and {value.state for value in alerts} == {"RESOLVED"}


async def test_monitoring_heartbeat_metrics_and_scope(database, client, settings):
    department = await make_department(database, "MONITORING_CONTINUED")
    other_department = await make_department(database, "MONITORING_CONTINUED_OTHER")
    owner = await make_user(
        database, settings, "EMPLOYEE", department.id, name="Continued Monitor Owner"
    )
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Continued Monitor Technician"
    )
    outsider = await make_user(
        database,
        settings,
        "TECHNICIAN",
        other_department.id,
        name="Continued Monitor Outsider",
    )
    manager = await make_user(
        database, settings, "IT_MANAGER", None, name="Continued Monitor Manager"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Continued Monitor Admin")
    await make_team(database, department.id, technician.id, "CONTINUED_MONITOR_DESK")
    await make_team(database, other_department.id, outsider.id, "CONTINUED_OTHER_DESK")
    asset = await create_asset(
        client,
        admin,
        asset_tag="MON-CONTINUED",
        owner_id=str(owner.id),
        department_id=str(department.id),
    )
    enrollment = (
        await client.post(
            "/api/v1/monitoring/enrollments",
            headers=auth(admin),
            json={"asset_id": asset["id"], "reason": "Enroll continued monitoring endpoint"},
        )
    ).json()
    enrolled = (
        await client.post(
            "/api/v1/monitoring/enroll",
            json={"enrollment_token": enrollment["enrollment_token"], "agent_version": "test"},
        )
    ).json()
    agent_id = enrolled["agent_id"]
    agent_headers = {"Authorization": f"Agent {agent_id}.{enrolled['credential']}"}
    now = datetime.now(UTC)
    heartbeat = await client.post(
        "/api/v1/monitoring/agent/heartbeat",
        headers=agent_headers,
        json={
            "observed_at": now.isoformat(),
            "available": True,
            "hostname": "monitored-workstation",
            "operating_system": "Windows 11 Enterprise",
            "ip_addresses": ["192.0.2.20", "192.0.2.20"],
            "boot_time": (now - timedelta(days=2)).isoformat(),
            "collection_errors": [],
        },
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["status"] == "ONLINE"
    assert heartbeat.json()["accepted"] is True

    metric_payload = {
        "sampled_at": now.isoformat(),
        "cpu_percent": 17.5,
        "memory_percent": 42.0,
        "memory_used_bytes": 4_200,
        "memory_total_bytes": 10_000,
        "disk_percent": 55.0,
        "disk_used_bytes": 55_000,
        "disk_total_bytes": 100_000,
        "network_bytes_sent": 123_456,
        "network_bytes_received": 654_321,
    }
    first_metric = await client.post(
        "/api/v1/monitoring/agent/metrics", headers=agent_headers, json=metric_payload
    )
    assert first_metric.status_code == 200 and first_metric.json()["accepted"] is True
    sampled = await client.post(
        "/api/v1/monitoring/agent/metrics", headers=agent_headers, json=metric_payload
    )
    assert sampled.status_code == 200 and sampled.json()["accepted"] is False
    assert (
        await client.post(
            "/api/v1/monitoring/agent/metrics",
            headers={"Authorization": f"Agent {agent_id}.wrong-secret"},
            json=metric_payload,
        )
    ).status_code == 401

    visible = await client.get("/api/v1/monitoring/agents", headers=auth(technician))
    assert visible.status_code == 200 and visible.json()["total"] == 1
    assert (await client.get("/api/v1/monitoring/agents", headers=auth(outsider))).json()[
        "total"
    ] == 0
    assert (await client.get("/api/v1/monitoring/agents", headers=auth(owner))).status_code == 403
    detail = await client.get(f"/api/v1/monitoring/agents/{agent_id}", headers=auth(manager))
    assert detail.status_code == 200
    assert detail.json()["hostname"] == "monitored-workstation"
    metrics = await client.get(
        f"/api/v1/monitoring/agents/{agent_id}/metrics", headers=auth(technician)
    )
    assert metrics.status_code == 200 and metrics.json()["total"] == 1
    assert metrics.json()["items"][0]["cpu_percent"] == 17.5

    degraded = await client.post(
        "/api/v1/monitoring/agent/heartbeat",
        headers=agent_headers,
        json={
            "observed_at": datetime.now(UTC).isoformat(),
            "available": False,
            "hostname": "monitored-workstation",
            "operating_system": "Windows 11 Enterprise",
            "ip_addresses": [],
            "boot_time": (now - timedelta(days=2)).isoformat(),
            "collection_errors": ["disk_collection_failed"],
        },
    )
    assert degraded.status_code == 200 and degraded.json()["status"] == "DEGRADED"

    disabled = await client.post(
        f"/api/v1/monitoring/agents/{agent_id}/disable",
        headers=auth(admin),
        json={"reason": "Device was removed from managed monitoring"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["credential_status"] == "REVOKED"
    assert (
        await client.post(
            "/api/v1/monitoring/agent/heartbeat",
            headers=agent_headers,
            json={
                "observed_at": now.isoformat(),
                "hostname": "disabled",
                "operating_system": "disabled",
                "boot_time": (now - timedelta(days=1)).isoformat(),
            },
        )
    ).status_code == 401


async def test_monitoring_reconciliation_retention_and_validation(database, client, settings):
    department = await make_department(database, "MONITOR_RECONCILE")
    admin = await make_user(database, settings, "ADMIN", None, name="Reconcile Admin")
    owner = await make_user(database, settings, "EMPLOYEE", department.id, name="Reconcile Owner")
    asset = await create_asset(
        client,
        admin,
        asset_tag="MON-OLD",
        owner_id=str(owner.id),
        department_id=str(department.id),
    )
    enrollment = (
        await client.post(
            "/api/v1/monitoring/enrollments",
            headers=auth(admin),
            json={"asset_id": asset["id"], "reason": "Enroll retention test device"},
        )
    ).json()
    enrolled = (
        await client.post(
            "/api/v1/monitoring/enroll",
            json={
                "enrollment_token": enrollment["enrollment_token"],
                "agent_version": "0.1.0",
            },
        )
    ).json()
    old = datetime.now(UTC) - timedelta(days=settings.monitoring_retention_days + 1)
    async with database() as session:
        agent = await session.get(DeviceAgent, UUID(enrolled["agent_id"]))
        assert agent is not None
        agent.status = "ONLINE"
        agent.last_heartbeat_at = old
        session.add(
            DeviceHeartbeat(
                agent_id=agent.id,
                received_at=old,
                observed_at=old,
                available=True,
                resulting_status="ONLINE",
                hostname="old-device",
                operating_system="Test OS",
                ip_addresses=[],
                boot_time=old - timedelta(days=1),
                collection_errors=[],
            )
        )
        session.add(
            DeviceMetric(
                agent_id=agent.id,
                sampled_at=old,
                received_at=old,
                cpu_percent=1,
                memory_percent=1,
                memory_used_bytes=1,
                memory_total_bytes=10,
                disk_percent=1,
                disk_used_bytes=1,
                disk_total_bytes=10,
                network_bytes_sent=1,
                network_bytes_received=1,
            )
        )
        await session.commit()
        offline, pruned_metrics, pruned_heartbeats = await MonitoringService(
            session, settings
        ).reconcile()
        assert (offline, pruned_metrics, pruned_heartbeats) == (1, 1, 1)
        await session.refresh(agent)
        assert agent.status == "OFFLINE" and agent.missed_heartbeat_count > 0

    invalid_metric = {
        "sampled_at": datetime.now(UTC).isoformat(),
        "cpu_percent": 101,
        "memory_percent": 10,
        "memory_used_bytes": 1,
        "memory_total_bytes": 10,
        "disk_percent": 10,
        "disk_used_bytes": 1,
        "disk_total_bytes": 10,
        "network_bytes_sent": 0,
        "network_bytes_received": 0,
    }
    headers = {"Authorization": f"Agent {enrolled['agent_id']}.{enrolled['credential']}"}
    assert (
        await client.post("/api/v1/monitoring/agent/metrics", headers=headers, json=invalid_metric)
    ).status_code == 422


async def test_monitoring_service_direct_lifecycle_and_error_guards(database, client, settings):
    department = await make_department(database, "MONITOR_DIRECT")
    admin = await make_user(database, settings, "ADMIN", None, name="Direct Monitor Admin")
    owner = await make_user(
        database, settings, "EMPLOYEE", department.id, name="Direct Monitor Owner"
    )
    asset_data = await create_asset(
        client,
        admin,
        asset_tag="MON-DIRECT",
        owner_id=str(owner.id),
        department_id=str(department.id),
    )
    now = datetime.now(UTC)
    async with database() as session:
        service = MonitoringService(session, settings)
        agent, token = await service.create_enrollment(
            admin.id,
            UUID(asset_data["id"]),
            10,
            "Exercise the direct monitoring lifecycle",
            "direct-enrollment",
        )
        with pytest.raises(HTTPException) as bad_token:
            await service.enroll("z" * 48, "test")
        assert bad_token.value.status_code == 401
        agent, credential = await service.enroll(token, "test")
        assert credential and agent.status == "OFFLINE"

        base_heartbeat = {
            "observed_at": now,
            "hostname": "direct-device",
            "operating_system": "Test OS",
            "ip_addresses": ["2001:0db8::1", "2001:db8::1"],
            "boot_time": now - timedelta(hours=1),
            "collection_errors": [],
        }
        with pytest.raises(HTTPException) as stale_heartbeat:
            await service.heartbeat(
                agent,
                HeartbeatCreate(**{**base_heartbeat, "observed_at": now - timedelta(days=2)}),
            )
        assert stale_heartbeat.value.status_code == 422
        with pytest.raises(HTTPException) as invalid_boot:
            await service.heartbeat(
                agent,
                HeartbeatCreate(**{**base_heartbeat, "boot_time": now + timedelta(minutes=1)}),
            )
        assert invalid_boot.value.status_code == 422
        agent = await service.heartbeat(agent, HeartbeatCreate(**base_heartbeat))
        assert agent.status == "ONLINE"

        metric_data = {
            "sampled_at": now,
            "cpu_percent": 5,
            "memory_percent": 20,
            "memory_used_bytes": 20,
            "memory_total_bytes": 100,
            "disk_percent": 30,
            "disk_used_bytes": 30,
            "disk_total_bytes": 100,
            "network_bytes_sent": 40,
            "network_bytes_received": 50,
        }
        with pytest.raises(HTTPException) as stale_metric:
            await service.metric(
                agent,
                MetricCreate(**{**metric_data, "sampled_at": now - timedelta(days=2)}),
            )
        assert stale_metric.value.status_code == 422
        accepted, agent = await service.metric(agent, MetricCreate(**metric_data))
        assert accepted is True
        accepted, _ = await service.metric(agent, MetricCreate(**metric_data))
        assert accepted is False
        records, total = await service.list_agents(admin.id, "ONLINE", 0, 10)
        assert total == 1 and records[0].agent.id == agent.id
        samples, total = await service.metrics(admin.id, agent.id, 0, 10)
        assert total == 1 and samples[0].cpu_percent == 5
        with pytest.raises(HTTPException) as missing:
            await service.visible_agent(admin.id, uuid4())
        assert missing.value.status_code == 404

        rotated, rotated_token = await service.create_enrollment(
            admin.id,
            agent.asset_id,
            10,
            "Rotate the direct lifecycle credential",
            "direct-rotation",
        )
        assert rotated.id == agent.id and rotated.credential_hash is None
        rotated, new_credential = await service.enroll(rotated_token, "test-rotated")
        assert new_credential != credential and rotated.credential_hash == secret_hash(
            new_credential
        )
        disabled = await service.disable(
            admin.id, rotated.id, "Complete direct lifecycle test", "direct-disable"
        )
        assert disabled.status == "DISABLED"

        asset = await session.get(Asset, UUID(asset_data["id"]))
        assert asset is not None
        asset.status = AssetStatus.RETIRED
        await session.commit()
        with pytest.raises(HTTPException) as terminal:
            await service.create_enrollment(
                admin.id,
                asset.id,
                10,
                "Reject terminal asset enrollment",
                "terminal-enrollment",
            )
        assert terminal.value.status_code == 409

    with pytest.raises(ValueError):
        HeartbeatCreate(
            observed_at=now,
            hostname="bad-ip",
            operating_system="Test OS",
            ip_addresses=["not-an-ip"],
            boot_time=now - timedelta(hours=1),
        )
    with pytest.raises(ValueError):
        MetricCreate(**{**metric_data, "memory_used_bytes": 101})

    heartbeat_url = "/api/v1/monitoring/agent/heartbeat"
    minimal_heartbeat = {
        "observed_at": now.isoformat(),
        "hostname": "unauthorized",
        "operating_system": "Test OS",
        "boot_time": (now - timedelta(hours=1)).isoformat(),
    }
    assert (await client.post(heartbeat_url, json=minimal_heartbeat)).status_code == 401
    assert (
        await client.post(
            heartbeat_url,
            headers={"Authorization": "Bearer irrelevant"},
            json=minimal_heartbeat,
        )
    ).status_code == 401
    assert (
        await client.post(
            heartbeat_url,
            headers={"Authorization": "Agent not-a-uuid.secret"},
            json=minimal_heartbeat,
        )
    ).status_code == 401


async def test_ticket_intake_visibility_filters_and_non_disclosure(database, client, settings):
    it = await make_department(database)
    finance = await make_department(database, "FIN")
    employee = await make_user(database, settings, "EMPLOYEE", it.id, name="Request Owner")
    stranger = await make_user(database, settings, "EMPLOYEE", it.id, name="Private Stranger")
    technician = await make_user(database, settings, "TECHNICIAN", it.id, name="Desk Technician")
    other_technician = await make_user(
        database, settings, "TECHNICIAN", finance.id, name="Finance Technician"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Ticket Administrator")
    await make_team(database, it.id, technician.id)
    await make_team(database, finance.id, other_technician.id, "FIN_DESK")

    created = await create_ticket(client, employee)
    assert created["priority"] == "CRITICAL"
    assert created["status"] == "NEW"
    assert created["requester"]["id"] == str(employee.id)
    assert created["department"]["id"] == str(it.id)
    assert created["reference"].startswith("IT-")

    own = await client.get("/api/v1/tickets", headers=auth(employee))
    assert own.status_code == 200
    assert own.json()["total"] == 1
    assert (
        await client.get(f"/api/v1/tickets/{created['id']}", headers=auth(employee))
    ).status_code == 200

    assert (await client.get("/api/v1/tickets", headers=auth(stranger))).json()["total"] == 0
    assert (
        await client.get(f"/api/v1/tickets/{created['id']}", headers=auth(stranger))
    ).status_code == 404
    assert (await client.get("/api/v1/tickets", headers=auth(technician))).json()["total"] == 1
    assert (await client.get("/api/v1/tickets", headers=auth(other_technician))).json()[
        "total"
    ] == 0

    filtered = await client.get(
        "/api/v1/tickets",
        headers=auth(admin),
        params={"search": "vpn", "status": "NEW", "priority": "CRITICAL", "limit": 1},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    sla_filtered = await client.get(
        "/api/v1/tickets", headers=auth(admin), params={"sla_state": "ON_TRACK"}
    )
    assert sla_filtered.status_code == 200 and sla_filtered.json()["total"] == 1
    assert (await client.get("/api/v1/tickets")).status_code == 401
    assert (await client.get("/api/v1/tickets/categories", headers=auth(employee))).json() == []


async def test_complete_assignment_transition_and_event_workflow(database, client, settings):
    department = await make_department(database)
    employee = await make_user(database, settings, "EMPLOYEE", department.id, name="Workflow Owner")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Workflow Technician"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Workflow Administrator")
    team = await make_team(database, department.id, technician.id)
    ticket = await create_ticket(client, employee, impact="LOW", urgency="LOW")
    ticket_url = f"/api/v1/tickets/{ticket['id']}"

    denied = await client.put(
        f"{ticket_url}/assignment",
        headers=auth(employee),
        json={"team_id": str(team.id), "reason": "Self assignment is prohibited"},
    )
    assert denied.status_code == 403
    assigned = await client.put(
        f"{ticket_url}/assignment",
        headers=auth(technician),
        json={
            "team_id": str(team.id),
            "technician_id": str(technician.id),
            "reason": "Claim eligible regional ticket",
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_technician"]["id"] == str(technician.id)

    illegal = await client.post(
        f"{ticket_url}/transitions",
        headers=auth(technician),
        json={"status": "IN_PROGRESS", "reason": "Skip required open state"},
    )
    assert illegal.status_code == 409
    for target in (
        "OPEN",
        "IN_PROGRESS",
        "PENDING_USER",
        "IN_PROGRESS",
        "ESCALATED",
        "IN_PROGRESS",
    ):
        response = await client.post(
            f"{ticket_url}/transitions",
            headers=auth(technician),
            json={"status": target, "reason": f"Move workflow to {target}"},
        )
        assert response.status_code == 200, response.text

    missing_resolution = await client.post(
        f"{ticket_url}/transitions",
        headers=auth(technician),
        json={"status": "RESOLVED", "reason": "Missing required resolution"},
    )
    assert missing_resolution.status_code == 422
    resolved = await client.post(
        f"{ticket_url}/transitions",
        headers=auth(technician),
        json={
            "status": "RESOLVED",
            "reason": "VPN profile repaired",
            "resolution_summary": "Reissued the user VPN profile and verified connectivity.",
            "resolution_code": "CONFIGURATION_REPAIRED",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None

    reopened = await client.post(
        f"{ticket_url}/transitions",
        headers=auth(employee),
        json={"status": "OPEN", "reason": "Problem returned after reconnect"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolution_summary"] is None
    for target in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
        payload = {"status": target, "reason": f"Complete workflow at {target}"}
        if target == "RESOLVED":
            payload.update(
                resolution_summary="Reinstalled VPN client and verified stable connectivity.",
                resolution_code="SOFTWARE_REINSTALLED",
            )
        response = await client.post(
            f"{ticket_url}/transitions", headers=auth(technician), json=payload
        )
        assert response.status_code == 200, response.text
    assert response.json()["closed_at"] is not None

    events = await client.get(f"{ticket_url}/events", headers=auth(employee))
    assert events.status_code == 200
    event_types = [item["event_type"] for item in events.json()["items"]]
    assert event_types[0] == "ticket.created"
    assert "ticket.assigned" in event_types
    assert event_types.count("ticket.status_changed") == 11
    async with database() as session:
        assignments = list(
            await session.scalars(
                select(TicketAssignment).where(TicketAssignment.ticket_id == UUID(ticket["id"]))
            )
        )
        assert len(assignments) == 1 and assignments[0].ended_at is None
        assert await session.scalar(
            select(TicketEvent).where(TicketEvent.ticket_id == UUID(ticket["id"]))
        )
        assert await session.get(Ticket, UUID(ticket["id"]))

    assert (
        await client.patch(
            ticket_url,
            headers=auth(admin),
            json={"title": "Cannot edit closed ticket", "reason": "Exercise terminal guard"},
        )
    ).status_code == 409
    assert (
        await client.post(
            f"{ticket_url}/attachments",
            headers={**auth(technician), "Content-Type": "text/plain"},
            params={"filename": "late-note.txt"},
            content=b"A closed ticket must reject this upload.",
        )
    ).status_code == 409


async def test_public_and_internal_comments_and_first_response(database, client, settings):
    department = await make_department(database)
    employee = await make_user(database, settings, "EMPLOYEE", department.id, name="Comment Owner")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Comment Technician"
    )
    team = await make_team(database, department.id, technician.id)
    ticket = await create_ticket(client, employee)
    ticket_url = f"/api/v1/tickets/{ticket['id']}"
    await client.put(
        f"{ticket_url}/assignment",
        headers=auth(technician),
        json={"team_id": str(team.id), "reason": "Take ownership for response"},
    )

    public = await client.post(
        f"{ticket_url}/comments",
        headers=auth(employee),
        json={"body": "The issue also occurs on mobile.", "visibility": "PUBLIC"},
    )
    assert public.status_code == 201
    denied = await client.post(
        f"{ticket_url}/comments",
        headers=auth(employee),
        json={"body": "Attempted private note", "visibility": "INTERNAL"},
    )
    assert denied.status_code == 403
    internal = await client.post(
        f"{ticket_url}/comments",
        headers=auth(technician),
        json={"body": "Suspect an expired device certificate.", "visibility": "INTERNAL"},
    )
    assert internal.status_code == 201
    async with database() as session:
        stored = await session.get(Ticket, UUID(ticket["id"]))
        assert stored is not None and stored.first_response_at is None
    technician_public = await client.post(
        f"{ticket_url}/comments",
        headers=auth(technician),
        json={"body": "We are investigating the certificate issue.", "visibility": "PUBLIC"},
    )
    assert technician_public.status_code == 201
    visible_to_employee = await client.get(f"{ticket_url}/comments", headers=auth(employee))
    visible_to_technician = await client.get(
        f"{ticket_url}/comments", headers=auth(technician), params={"limit": 1}
    )
    assert visible_to_employee.json()["total"] == 2
    assert visible_to_technician.json()["total"] == 3
    assert len(visible_to_technician.json()["items"]) == 1
    async with database() as session:
        stored = await session.get(Ticket, UUID(ticket["id"]))
        assert stored.first_response_at is not None
        assert len(list(await session.scalars(select(TicketComment)))) == 3


async def test_private_attachment_validation_download_and_limits(database, client, settings):
    department = await make_department(database)
    owner = await make_user(database, settings, "EMPLOYEE", department.id, name="File Owner")
    stranger = await make_user(database, settings, "EMPLOYEE", department.id, name="File Stranger")
    ticket = await create_ticket(client, owner)
    ticket_url = f"/api/v1/tickets/{ticket['id']}"

    uploaded = await client.post(
        f"{ticket_url}/attachments",
        headers={**auth(owner), "Content-Type": "text/plain"},
        params={"filename": "diagnostics.log"},
        content=b"VPN client error code 412",
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]
    listing = await client.get(f"{ticket_url}/attachments", headers=auth(owner))
    assert listing.json()[0]["size_bytes"] == 25
    download = await client.get(f"{ticket_url}/attachments/{attachment_id}", headers=auth(owner))
    assert download.status_code == 200
    assert download.content == b"VPN client error code 412"
    assert "diagnostics.log" in download.headers["content-disposition"]
    assert (
        await client.get(f"{ticket_url}/attachments/{attachment_id}", headers=auth(stranger))
    ).status_code == 404

    mismatch = await client.post(
        f"{ticket_url}/attachments",
        headers={**auth(owner), "Content-Type": "application/pdf"},
        params={"filename": "fake.pdf"},
        content=b"not a PDF",
    )
    assert mismatch.status_code == 422
    oversized = await client.post(
        f"{ticket_url}/attachments",
        headers={**auth(owner), "Content-Type": "text/plain"},
        params={"filename": "huge.txt"},
        content=b"x" * 1025,
    )
    assert oversized.status_code == 413


async def test_categories_updates_reassignment_and_authorization(database, client, settings):
    department = await make_department(database)
    employee = await make_user(database, settings, "EMPLOYEE", department.id, name="Category Owner")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Category Technician"
    )
    second = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Second Technician"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Category Administrator")
    team = await make_team(database, department.id, technician.id)
    second_team = await make_team(database, department.id, second.id, "ESCALATION")
    async with database() as session:
        category = TicketCategory(id=uuid4(), code="NETWORK", name="Network", is_active=True)
        session.add(category)
        await session.flush()
        subcategory = TicketSubcategory(
            id=uuid4(),
            category_id=category.id,
            code="VPN",
            name="Virtual private network",
            is_active=True,
        )
        session.add(subcategory)
        await session.commit()

    catalog = await client.get("/api/v1/tickets/categories", headers=auth(employee))
    assert catalog.status_code == 200
    assert catalog.json()[0]["subcategories"][0]["id"] == str(subcategory.id)
    invalid = await client.post(
        "/api/v1/tickets",
        headers=auth(employee),
        json={
            "title": "Invalid standalone subcategory",
            "description": "This request deliberately omits its parent category.",
            "subcategory_id": str(subcategory.id),
        },
    )
    assert invalid.status_code == 422
    ticket = await create_ticket(
        client,
        employee,
        category_id=str(category.id),
        subcategory_id=str(subcategory.id),
        impact="LOW",
        urgency="LOW",
    )
    ticket_url = f"/api/v1/tickets/{ticket['id']}"
    assert (
        await client.patch(
            ticket_url,
            headers=auth(employee),
            json={"impact": "HIGH", "reason": "Employee cannot reprioritize"},
        )
    ).status_code == 403
    updated = await client.patch(
        ticket_url,
        headers=auth(admin),
        json={"impact": "HIGH", "urgency": "MEDIUM", "reason": "Reflect broader outage"},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == "HIGH"
    await client.put(
        f"{ticket_url}/assignment",
        headers=auth(technician),
        json={"team_id": str(team.id), "reason": "Initial team assignment"},
    )
    reassigned = await client.put(
        f"{ticket_url}/assignment",
        headers=auth(admin),
        json={
            "team_id": str(second_team.id),
            "technician_id": str(second.id),
            "reason": "Escalate to specialist queue",
        },
    )
    assert reassigned.status_code == 200
    async with database() as session:
        history = list(
            await session.scalars(
                select(TicketAssignment)
                .where(TicketAssignment.ticket_id == UUID(ticket["id"]))
                .order_by(TicketAssignment.started_at)
            )
        )
        assert len(history) == 2
        assert history[0].ended_at is not None and history[1].ended_at is None

    assert (
        await client.get(
            "/api/v1/tickets",
            headers=auth(admin),
            params={"created_from": "2026-01-01T00:00:00"},
        )
    ).status_code == 422


async def test_policy_and_attachment_units_cover_edge_cases():
    assert calculate_priority("HIGH", "HIGH") == "CRITICAL"
    assert calculate_priority("HIGH", "MEDIUM") == "HIGH"
    assert calculate_priority("LOW", "MEDIUM") == "MEDIUM"
    assert calculate_priority("LOW", "LOW") == "LOW"
    assert transition_permission("IN_PROGRESS", "ESCALATED") == "ticket:escalate"
    assert transition_permission("IN_PROGRESS", "RESOLVED") == "ticket:resolve"
    assert transition_permission("RESOLVED", "CLOSED") == "ticket:close"
    assert transition_permission("RESOLVED", "OPEN") == "ticket:reopen"
    assert transition_permission("OPEN", "IN_PROGRESS") == "ticket:update"
    assert LEGAL_TRANSITIONS["CLOSED"] == frozenset()
    assert (
        validate_attachment("screen.png", "image/png", b"\x89PNG\r\n\x1a\nbody", 100)
        == "screen.png"
    )
    assert validate_attachment("photo.jpg", "image/jpeg", b"\xff\xd8\xffbody", 100) == "photo.jpg"
    assert validate_attachment("image.gif", "image/gif", b"GIF89abody", 100) == "image.gif"
    assert validate_attachment("report.pdf", "application/pdf", b"%PDF-1.7", 100) == "report.pdf"
    with pytest.raises(AttachmentValidationError):
        validate_attachment("bad.exe", "application/octet-stream", b"MZ", 100)
    with pytest.raises(AttachmentValidationError):
        validate_attachment("empty.txt", "text/plain", b"", 100)
    with pytest.raises(AttachmentValidationError):
        validate_attachment("binary.txt", "text/plain", b"a\x00b", 100)
    with pytest.raises(AttachmentValidationError):
        validate_attachment("invalid.txt", "text/plain", b"\xff", 100)


async def test_direct_service_layer_complete_transaction_path(database, settings, tmp_path):
    department = await make_department(database)
    employee = await make_user(database, settings, "EMPLOYEE", department.id, name="Direct Owner")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="Direct Technician"
    )
    admin = await make_user(database, settings, "ADMIN", None, name="Direct Administrator")
    no_role = await make_user(database, settings, None, department.id, name="No Grant User")
    team = await make_team(database, department.id, technician.id, "DIRECT_DESK")
    async with database() as session:
        service = TicketService(session)
        with pytest.raises(HTTPException):
            await service.list_tickets(
                no_role.id,
                search=None,
                status=None,
                priority=None,
                team_id=None,
                technician_id=None,
                department_id=None,
                asset_id=None,
                created_from=None,
                created_to=None,
                offset=0,
                limit=10,
            )
        ticket = await service.create_ticket(
            employee,
            {
                "title": "Direct service ticket creation",
                "description": "Exercise service transactions without the HTTP transport.",
                "impact": "MEDIUM",
                "urgency": "MEDIUM",
                "category_id": None,
                "subcategory_id": None,
                "asset_id": None,
            },
            "direct-create",
        )
        record = await service.get_ticket(employee.id, ticket.id)
        assert record.ticket.id == ticket.id
        values, total = await service.list_tickets(
            admin.id,
            search="Direct service",
            status="NEW",
            priority="MEDIUM",
            team_id=None,
            technician_id=None,
            department_id=department.id,
            asset_id=None,
            created_from=datetime.now(UTC) - timedelta(days=1),
            created_to=datetime.now(UTC) + timedelta(days=1),
            offset=0,
            limit=10,
        )
        assert total == 1 and values[0].ticket.id == ticket.id
        updated = await service.update_ticket(
            admin.id,
            ticket.id,
            {"title": "Direct service ticket updated", "impact": "HIGH"},
            "Clarify direct test case",
            "direct-update",
        )
        assert updated.priority == "HIGH"
        assigned = await service.assign_ticket(
            technician.id,
            ticket.id,
            team.id,
            technician.id,
            "Claim direct service ticket",
            "direct-assignment",
        )
        assert assigned.assigned_technician_id == technician.id
        assert (
            await service.assign_ticket(
                technician.id,
                ticket.id,
                team.id,
                technician.id,
                "Idempotent assignment",
                "direct-assignment-noop",
            )
        ).id == ticket.id
        for target in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS):
            await service.transition(
                technician.id,
                ticket.id,
                target,
                f"Move to {target}",
                "direct-transition",
                None,
                None,
            )
        await service.add_comment(
            employee.id,
            ticket.id,
            "Requester public response",
            CommentVisibility.PUBLIC,
            "direct-comment-public",
        )
        await service.add_comment(
            technician.id,
            ticket.id,
            "Technician private investigation",
            CommentVisibility.INTERNAL,
            "direct-comment-internal",
        )
        employee_comments, employee_total = await service.list_comments(
            employee.id, ticket.id, 0, 100
        )
        technician_comments, technician_total = await service.list_comments(
            technician.id, ticket.id, 0, 100
        )
        assert employee_total == len(employee_comments) == 1
        assert technician_total == len(technician_comments) == 2
        storage = LocalAttachmentStorage(tmp_path / "direct-storage")
        attachment = await service.add_attachment(
            employee.id,
            ticket.id,
            "direct.txt",
            "text/plain; charset=utf-8",
            b"direct diagnostic output",
            storage,
            1024,
            "direct-attachment",
        )
        assert (await service.download_attachment(employee.id, ticket.id, attachment.id)).sha256
        assert len(await service.list_attachments(employee.id, ticket.id)) == 1
        events, event_total = await service.list_events(employee.id, ticket.id, 0, 100)
        assert event_total == len(events)
        assert {event.event.event_type for event in events} >= {
            "ticket.created",
            "ticket.updated",
            "ticket.assigned",
            "ticket.comment_added",
            "ticket.attachment_added",
        }
        with pytest.raises(HTTPException):
            await service.transition(
                technician.id,
                ticket.id,
                TicketStatus.CLOSED,
                "Illegal early closure",
                "direct-invalid-transition",
                None,
                None,
            )


def test_business_time_weekend_holiday_overnight_timezone_and_pause():
    calendar = BusinessCalendar(name="Office", timezone="Asia/Kolkata", is_active=True)
    weekdays = [
        BusinessWindow(calendar_id=calendar.id, weekday=day, start_minute=540, end_minute=1020)
        for day in range(5)
    ]
    bundle = CalendarBundle(calendar, weekdays, frozenset())
    start = datetime(2026, 1, 9, 10, 30, tzinfo=UTC)  # Friday 16:00 IST
    end = datetime(2026, 1, 12, 4, 30, tzinfo=UTC)  # Monday 10:00 IST
    assert business_seconds(bundle, start, end) == 2 * 60 * 60
    holiday = CalendarBundle(calendar, weekdays, frozenset({date(2026, 1, 12)}))
    assert business_seconds(holiday, start, end) == 60 * 60

    overnight = CalendarBundle(
        calendar,
        [BusinessWindow(calendar_id=calendar.id, weekday=0, start_minute=1320, end_minute=1560)],
        frozenset(),
    )
    overnight_start = datetime(2026, 1, 5, 16, 30, tzinfo=UTC)
    overnight_end = datetime(2026, 1, 5, 20, 30, tzinfo=UTC)
    assert business_seconds(overnight, overnight_start, overnight_end) == 4 * 60 * 60
    pause = SlaPause(
        instance_id=uuid4(),
        reason="PENDING_USER",
        started_at=overnight_start + timedelta(hours=1),
        ended_at=overnight_start + timedelta(hours=2),
    )
    assert elapsed_business_seconds(overnight, overnight_start, overnight_end, [pause]) == 10800
    assert business_seconds(bundle, end, start) == 0
    overlapping = CalendarBundle(
        calendar,
        [
            BusinessWindow(calendar_id=calendar.id, weekday=0, start_minute=540, end_minute=720),
            BusinessWindow(calendar_id=calendar.id, weekday=0, start_minute=660, end_minute=1020),
        ],
        frozenset(),
    )
    monday_open = datetime(2026, 1, 5, 3, 30, tzinfo=UTC)
    monday_close = datetime(2026, 1, 5, 11, 30, tzinfo=UTC)
    assert business_seconds(overlapping, monday_open, monday_close) == 28800


async def test_sla_configuration_api_permissions_and_validation(database, client, settings):
    employee = await make_user(database, settings, "EMPLOYEE", None, name="SLA Employee")
    technician = await make_user(database, settings, "TECHNICIAN", None, name="SLA Viewer")
    admin = await make_user(database, settings, "ADMIN", None, name="SLA Administrator")
    assert (
        await client.get("/api/v1/sla/priority-matrix", headers=auth(employee))
    ).status_code == 403
    matrix = await client.get("/api/v1/sla/priority-matrix", headers=auth(technician))
    assert matrix.status_code == 200 and len(matrix.json()) == 9
    updated = await client.put(
        "/api/v1/sla/priority-matrix/LOW/HIGH",
        headers=auth(admin),
        json={"priority": "HIGH"},
    )
    assert updated.status_code == 200 and updated.json()["priority"] == "HIGH"
    invalid = await client.post(
        "/api/v1/sla/calendars",
        headers=auth(admin),
        json={
            "name": "Invalid zone",
            "timezone": "Mars/Olympus",
            "windows": [{"weekday": 0, "start_minute": 540, "end_minute": 1020}],
        },
    )
    assert invalid.status_code == 422
    payload = {
        "name": "India service desk",
        "timezone": "Asia/Kolkata",
        "windows": [{"weekday": day, "start_minute": 540, "end_minute": 1020} for day in range(5)],
        "holidays": [{"holiday_date": "2026-01-26", "name": "Republic Day"}],
    }
    calendar = await client.post("/api/v1/sla/calendars", headers=auth(admin), json=payload)
    assert calendar.status_code == 201, calendar.text
    calendar_id = calendar.json()["id"]
    assert calendar.json()["holidays"][0]["name"] == "Republic Day"
    listing = await client.get("/api/v1/sla/calendars", headers=auth(technician))
    assert listing.status_code == 200 and len(listing.json()) == 2
    missing = await client.put(
        f"/api/v1/sla/calendars/{uuid4()}", headers=auth(admin), json=payload
    )
    assert missing.status_code == 404
    bad_policy = await client.post(
        "/api/v1/sla/policies",
        headers=auth(admin),
        json={
            "name": "Bad calendar",
            "priority": "LOW",
            "calendar_id": str(uuid4()),
            "response_target_minutes": 5,
            "resolution_target_minutes": 10,
        },
    )
    assert bad_policy.status_code == 422
    invalid_targets = await client.post(
        "/api/v1/sla/policies",
        headers=auth(admin),
        json={
            "name": "Invalid targets",
            "priority": "LOW",
            "calendar_id": calendar_id,
            "response_target_minutes": 60,
            "resolution_target_minutes": 30,
        },
    )
    assert invalid_targets.status_code == 422
    policy_payload = {
        "name": "India P4",
        "priority": "LOW",
        "calendar_id": calendar_id,
        "response_target_minutes": 30,
        "resolution_target_minutes": 240,
        "at_risk_percent": 75,
    }
    policy = await client.post("/api/v1/sla/policies", headers=auth(admin), json=policy_payload)
    assert policy.status_code == 201, policy.text
    policies = await client.get("/api/v1/sla/policies", headers=auth(technician))
    assert policies.status_code == 200 and len(policies.json()) == 5
    policy_payload["response_target_minutes"] = 45
    replaced = await client.put(
        f"/api/v1/sla/policies/{policy.json()['id']}",
        headers=auth(admin),
        json=policy_payload,
    )
    assert replaced.status_code == 200 and replaced.json()["response_target_minutes"] == 45
    malformed = {**payload, "windows": [{"weekday": 0, "start_minute": 10, "end_minute": 10}]}
    assert (
        await client.post("/api/v1/sla/calendars", headers=auth(admin), json=malformed)
    ).status_code == 422


async def test_ticket_sla_pause_resume_response_and_policy_change(database, client, settings):
    department = await make_department(database, "SLA")
    employee = await make_user(database, settings, "EMPLOYEE", department.id, name="SLA Owner")
    technician = await make_user(
        database, settings, "TECHNICIAN", department.id, name="SLA Technician"
    )
    stranger = await make_user(database, settings, "EMPLOYEE", department.id, name="SLA Stranger")
    team = await make_team(database, department.id, technician.id, "SLAT")
    ticket = await create_ticket(client, employee, impact="MEDIUM", urgency="MEDIUM")
    ticket_url = f"/api/v1/tickets/{ticket['id']}"
    sla_url = f"/api/v1/sla/tickets/{ticket['id']}"
    own_sla = await client.get(sla_url, headers=auth(employee))
    assert own_sla.status_code == 200 and own_sla.json()["policy_name"] == "P3 Medium"
    assert (await client.get(sla_url, headers=auth(stranger))).status_code == 404
    assigned = await client.put(
        f"{ticket_url}/assignment",
        headers=auth(technician),
        json={"team_id": str(team.id), "reason": "Own SLA queue"},
    )
    assert assigned.status_code == 200
    for target in ("OPEN", "IN_PROGRESS", "PENDING_USER"):
        response = await client.post(
            f"{ticket_url}/transitions",
            headers=auth(technician),
            json={"status": target, "reason": f"Move to {target}"},
        )
        assert response.status_code == 200
    paused = await client.get(sla_url, headers=auth(employee))
    assert paused.json()["state"] == "PAUSED" and paused.json()["is_paused"] is True
    resumed = await client.post(
        f"{ticket_url}/transitions",
        headers=auth(technician),
        json={"status": "IN_PROGRESS", "reason": "Requester answered"},
    )
    assert resumed.status_code == 200
    reply = await client.post(
        f"{ticket_url}/comments",
        headers=auth(technician),
        json={"body": "We are working on your request.", "visibility": "PUBLIC"},
    )
    assert reply.status_code == 201
    assert (await client.get(sla_url, headers=auth(employee))).json()[
        "active_target"
    ] == "RESOLUTION"
    update_response = await client.patch(
        ticket_url,
        headers=auth(technician),
        json={"impact": "HIGH", "urgency": "HIGH", "reason": "Wider impact confirmed"},
    )
    assert update_response.status_code == 200 and update_response.json()["priority"] == "CRITICAL"
    assert (await client.get(sla_url, headers=auth(employee))).json()[
        "policy_name"
    ] == "P1 Critical"
    async with database() as session:
        pauses = list(await session.scalars(select(SlaPause)))
        assert len(pauses) == 1 and pauses[0].ended_at is not None


async def test_sla_worker_breach_escalation_completion_and_retry(database, client, settings):
    employee = await make_user(database, settings, "EMPLOYEE", None, name="Worker Owner")
    ticket = await create_ticket(client, employee, impact="HIGH", urgency="HIGH")
    now = datetime.now(UTC).replace(microsecond=0)
    async with database() as session:
        record = await session.get(Ticket, UUID(ticket["id"]))
        assert record is not None
        record.created_at = now - timedelta(minutes=20)
        await session.commit()
    async with database() as session:
        assert await SlaService(session).run_once(now=now) == (1, 1)
    async with database() as session:
        instance = await session.scalar(select(SlaInstance))
        assert instance is not None and instance.state == SlaState.BREACHED
        assert instance.response_breached_at is not None
        assert instance.response_breached_at.replace(tzinfo=UTC) == now
        first_count = len(list(await session.scalars(select(SlaEvent))))
    async with database() as session:
        assert await SlaService(session).run_once(now=now) == (1, 0)
        assert len(list(await session.scalars(select(SlaEvent)))) == first_count
    async with database() as session:
        record = await session.get(Ticket, UUID(ticket["id"]))
        instance = await session.scalar(select(SlaInstance))
        assert record is not None and instance is not None
        record.created_at = now - timedelta(hours=3)
        record.first_response_at = now - timedelta(hours=2, minutes=50)
        instance.response_completed_at = record.first_response_at
        await session.commit()
    async with database() as session:
        await SlaService(session).run_once(now=now)
        instance = await session.scalar(select(SlaInstance))
        assert instance is not None
        assert instance.resolution_breached_at is not None and instance.escalated_at is not None
        assert instance.resolution_breached_at.replace(tzinfo=UTC) == now
        assert instance.escalated_at.replace(tzinfo=UTC) == now
        notifications = list(
            await session.scalars(select(SlaEvent).where(SlaEvent.notification_required.is_(True)))
        )
        assert {item.event_type for item in notifications} == {"sla.breached", "sla.escalated"}
    async with database() as session:
        record = await session.get(Ticket, UUID(ticket["id"]))
        assert record is not None
        record.status = TicketStatus.RESOLVED
        record.resolved_at = now
        await session.commit()
    async with database() as session:
        await SlaService(session).run_once(now=now)
        instance = await session.scalar(select(SlaInstance))
        assert instance is not None and instance.state == SlaState.COMPLETED


async def test_sla_missing_configuration_and_calendar_replace(database):
    async with database() as session:
        await session.execute(text("DELETE FROM sla_instances"))
        await session.execute(text("DELETE FROM sla_policies"))
        await session.execute(text("DELETE FROM priority_matrix"))
        await session.commit()
        with pytest.raises(HTTPException) as missing_matrix:
            await SlaService(session).resolve_priority("LOW", "LOW")
        assert missing_matrix.value.status_code == 503
        service = SlaService(session)
        created_rule = await service.set_matrix("LOW", "LOW", "LOW")
        assert created_rule.priority == "LOW"
        detached = Ticket(
            id=uuid4(),
            reference="IT-DETACHED",
            title="Detached SLA test ticket",
            description="This ticket has no service-level instance.",
            requester_id=uuid4(),
            impact="LOW",
            urgency="LOW",
            priority="LOW",
            status=TicketStatus.NEW,
            source="PORTAL",
        )
        assert await service.snapshot(detached) is None
        await service.on_transition(
            detached.id, TicketStatus.NEW, TicketStatus.OPEN, datetime.now(UTC)
        )
        values = {
            "name": "Replace me",
            "timezone": "UTC",
            "is_active": True,
            "is_default": False,
            "windows": [{"weekday": 0, "start_minute": 60, "end_minute": 120}],
            "holidays": [{"holiday_date": date(2026, 1, 1), "name": "New Year"}],
        }
        calendar = await service.save_calendar(values)
        replacement = {
            "name": "Replaced calendar",
            "timezone": "UTC",
            "is_active": True,
            "is_default": True,
            "windows": [{"weekday": 1, "start_minute": 120, "end_minute": 180}],
            "holidays": [],
        }
        await service.save_calendar(replacement, calendar.id)
        bundle = await service.repository.calendar_bundle(calendar.id)
        assert bundle is not None and bundle.calendar.name == "Replaced calendar"
        assert len(bundle.windows) == 1 and bundle.windows[0].weekday == 1
