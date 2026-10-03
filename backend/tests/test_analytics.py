from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.repository import AnalyticsAlert, AnalyticsDevice, AnalyticsTicket
from app.modules.analytics.service import AnalyticsService, percent, volume_points
from app.modules.assets.repository import AssetAccess
from app.modules.tickets.repository import TicketAccess

pytestmark = pytest.mark.anyio


def ticket_record(
    *,
    now: datetime,
    actor_id,
    status: str,
    priority: str = "HIGH",
    record_type: str = "REQUEST",
    resolved_after: int | None = None,
    responded_after: int | None = None,
    reopened: bool = False,
    sla_state: str = "COMPLETED",
    sla_breached: bool = False,
    assigned: bool = True,
) -> AnalyticsTicket:
    created = now - timedelta(days=2)
    resolved_at = created + timedelta(minutes=resolved_after) if resolved_after else None
    first_response_at = created + timedelta(minutes=responded_after) if responded_after else None
    ticket = SimpleNamespace(
        id=uuid4(),
        reference=f"INC-{uuid4().hex[:6]}",
        title="Recurring VPN interruption",
        status=status,
        priority=priority,
        record_type=record_type,
        assigned_technician_id=actor_id if assigned else None,
        asset_id=uuid4(),
        created_at=created,
        updated_at=now - timedelta(minutes=5),
        resolved_at=resolved_at,
        first_response_at=first_response_at,
        reopened_at=created + timedelta(minutes=90) if reopened else None,
    )
    sla = SimpleNamespace(
        state=sla_state,
        resolution_completed_at=resolved_at,
        resolution_breached_at=resolved_at if sla_breached else None,
        resolution_elapsed_seconds=(resolved_after or 30) * 60,
        resolution_target_seconds=180 * 60,
    )
    return AnalyticsTicket(
        ticket=ticket,
        sla=sla,
        category_name="Connectivity",
        subcategory_name="VPN",
        department_name="Engineering",
        technician_name="Taylor Technician" if assigned else None,
        asset_tag="LT-100",
    )


async def test_dashboard_formulas_scope_attention_and_empty_helpers(monkeypatch) -> None:
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    actor_id = uuid4()
    active_risk = ticket_record(
        now=now,
        actor_id=actor_id,
        status="IN_PROGRESS",
        priority="CRITICAL",
        record_type="INCIDENT",
        sla_state="AT_RISK",
    )
    active_breach = ticket_record(
        now=now,
        actor_id=actor_id,
        status="ESCALATED",
        priority="CRITICAL",
        record_type="INCIDENT",
        sla_state="BREACHED",
        assigned=False,
    )
    resolved_fast = ticket_record(
        now=now,
        actor_id=actor_id,
        status="RESOLVED",
        resolved_after=120,
        responded_after=30,
    )
    resolved_reopened = ticket_record(
        now=now,
        actor_id=actor_id,
        status="RESOLVED",
        resolved_after=240,
        responded_after=60,
        reopened=True,
        sla_breached=True,
    )
    online_asset = SimpleNamespace(
        id=uuid4(), asset_tag="LT-100", hostname="alpha", health_status="HEALTHY"
    )
    offline_asset = SimpleNamespace(
        id=uuid4(), asset_tag="LT-200", hostname="beta", health_status="OFFLINE"
    )
    degraded_asset = SimpleNamespace(
        id=uuid4(), asset_tag="LT-300", hostname=None, health_status="WARNING"
    )
    devices = [
        AnalyticsDevice(SimpleNamespace(id=uuid4(), status="ONLINE"), online_asset),
        AnalyticsDevice(SimpleNamespace(id=uuid4(), status="OFFLINE"), offline_asset),
        AnalyticsDevice(SimpleNamespace(id=uuid4(), status="DEGRADED"), degraded_asset),
    ]
    alerts = [
        AnalyticsAlert(
            SimpleNamespace(
                id=uuid4(),
                asset_id=offline_asset.id,
                severity="CRITICAL",
                metric="DEVICE_OFFLINE",
                state="TRIGGERED",
                triggered_at=now - timedelta(minutes=10),
            ),
            offline_asset,
        ),
        AnalyticsAlert(
            SimpleNamespace(
                id=uuid4(),
                asset_id=degraded_asset.id,
                severity="HIGH",
                metric="MEMORY_PERCENT",
                state="ACKNOWLEDGED",
                triggered_at=now - timedelta(minutes=20),
            ),
            degraded_asset,
        ),
    ]
    ticket_access = TicketAccess(
        actor_id,
        frozenset({"analytics:view", "ticket:view_team"}),
        frozenset(),
        frozenset(),
    )
    asset_access = AssetAccess(
        actor_id,
        frozenset({"analytics:view", "asset:view_team"}),
        frozenset(),
    )
    monkeypatch.setattr(
        "app.modules.analytics.service.TicketService.access",
        AsyncMock(return_value=ticket_access),
    )
    monkeypatch.setattr(
        "app.modules.analytics.service.AssetService.access",
        AsyncMock(return_value=asset_access),
    )
    service = AnalyticsService(AsyncMock(spec=AsyncSession))
    service.repository.tickets = AsyncMock(
        return_value=[active_risk, active_breach, resolved_fast, resolved_reopened]
    )
    service.repository.devices = AsyncMock(return_value=devices)
    service.repository.alerts = AsyncMock(return_value=alerts)
    service.repository.feedback_actions = AsyncMock(
        return_value=["ACCEPTED", "EDITED", "REJECTED", "REGENERATED"]
    )

    result = await service.dashboard(actor_id, 30, now)

    assert result.scope.audience == "TEAM"
    assert result.summary.open_tickets == 2
    assert result.summary.assigned_to_me == 1 and result.summary.unassigned_tickets == 1
    assert result.summary.critical_incidents == 2
    assert result.summary.sla_at_risk == result.summary.sla_breached == 1
    assert result.summary.online_devices == result.summary.offline_devices == 1
    assert result.summary.unhealthy_devices == 2 and result.summary.critical_alerts == 1
    assert result.performance.mttr.minutes == 180
    assert result.performance.mtta.minutes == 45
    assert result.performance.sla_compliance.percent == 50
    assert result.performance.first_contact_resolution_proxy.percent == 50
    assert result.performance.reopen_rate.percent == 50
    assert result.ai_assistance.acceptance_rate == pytest.approx(33.3)
    assert result.recurring_issues[0].ticket_count == 4
    assert result.technician_workload[0].assigned_open == 1
    assert result.technician_workload[0].resolved_in_window == 2
    assert result.attention.urgent_tickets[0].sla_state == "BREACHED"
    assert result.attention.device_health_issues[0].status == "OFFLINE"
    assert result.attention.critical_alerts[0].asset_tag == "LT-200"
    assert len(result.ticket_volume.daily) == 30
    assert sum(point.created for point in result.ticket_volume.daily) == 4
    assert sum(point.resolved for point in result.ticket_volume.weekly) == 2
    assert percent(1, 0) is None
    assert volume_points([], now - timedelta(days=7), now, "month")


async def test_organization_scope_and_no_samples_are_explicit(monkeypatch) -> None:
    actor_id = uuid4()
    ticket_access = TicketAccess(
        actor_id,
        frozenset({"analytics:view", "ticket:view_all"}),
        frozenset(),
        frozenset(),
    )
    asset_access = AssetAccess(
        actor_id,
        frozenset({"analytics:view", "asset:view_all"}),
        frozenset(),
    )
    monkeypatch.setattr(
        "app.modules.analytics.service.TicketService.access",
        AsyncMock(return_value=ticket_access),
    )
    monkeypatch.setattr(
        "app.modules.analytics.service.AssetService.access",
        AsyncMock(return_value=asset_access),
    )
    service = AnalyticsService(AsyncMock(spec=AsyncSession))
    service.repository.tickets = AsyncMock(return_value=[])
    service.repository.devices = AsyncMock(return_value=[])
    service.repository.alerts = AsyncMock(return_value=[])
    service.repository.feedback_actions = AsyncMock(return_value=[])

    result = await service.dashboard(actor_id, 7)

    assert result.scope.audience == "ORGANIZATION"
    assert result.performance.mttr.minutes is None
    assert result.performance.sla_compliance.percent is None
    assert result.ai_assistance.acceptance_rate is None
    assert result.summary.open_tickets == 0
