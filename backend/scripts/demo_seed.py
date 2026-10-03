"""Opt-in, fictional portfolio data. Run only against a disposable development database."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.modules.alerts.models import Alert, AlertState
from app.modules.alerts.service import AlertService
from app.modules.assets.models import Asset
from app.modules.assets.service import AssetService
from app.modules.directory.models import Department, Location, Team
from app.modules.identity.models import User
from app.modules.knowledge.models import ArticleStatus, KnowledgeArticle, KnowledgeCategory
from app.modules.knowledge.service import KnowledgeService
from app.modules.monitoring.models import DeviceAgent
from app.modules.monitoring.schemas import HeartbeatCreate, MetricCreate
from app.modules.monitoring.service import MonitoringService
from app.modules.sla.models import SlaInstance
from app.modules.sla.service import SlaService
from app.modules.tickets.models import CommentVisibility, Ticket, TicketCategory, TicketStatus
from app.modules.tickets.service import TicketService

SOURCE = "step6-fictional-demo"


@dataclass(frozen=True)
class Scenario:
    title: str
    description: str
    requester: str
    team: str | None
    technician: str | None
    status: TicketStatus
    age_hours: int
    impact: str = "MEDIUM"
    urgency: str = "MEDIUM"
    category: str = "WORKPLACE"
    asset: str | None = None
    conversation: tuple[str, str, str] | None = None


SCENARIOS = (
    Scenario(
        "VPN sign-in stalls after MFA approval",
        "The VPN client accepts MFA but never completes the connection from my home network.",
        "amara.johnson@example.com",
        "SERVICE_DESK",
        "maya.chen@example.com",
        TicketStatus.PENDING_USER,
        31,
        "HIGH",
        "MEDIUM",
        "ACCESS",
        "YM-LT-1042",
        (
            "The issue started after yesterday's laptop restart.",
            "I have cleared the stale VPN profile. Please try a fresh connection and confirm.",
            "Check conditional-access device compliance if the new profile still hangs.",
        ),
    ),
    Scenario(
        "Intermittent Wi-Fi on south office floor",
        "Calls drop when moving between the south office meeting rooms and desk area.",
        "meera.iyer@example.com",
        "NETWORK_OPS",
        "arjun.nair@example.com",
        TicketStatus.IN_PROGRESS,
        27,
        "HIGH",
        "HIGH",
        "NETWORK",
    ),
    Scenario(
        "MFA recovery for finance reporting",
        "The authenticator was replaced and finance reporting now prompts "
        "for an unavailable factor.",
        "rahul.kapoor@example.com",
        "SYSTEMS_ADMIN",
        "fatima.zahra@example.com",
        TicketStatus.OPEN,
        8,
        "MEDIUM",
        "HIGH",
        "ACCESS",
    ),
    Scenario(
        "Laptop battery drains during client visits",
        "The assigned laptop loses most of its charge before a two-hour off-site meeting ends.",
        "chloe.bennett@example.com",
        "DESKTOP_SUPPORT",
        "liam.oconnor@example.com",
        TicketStatus.ESCALATED,
        69,
        "HIGH",
        "MEDIUM",
        "HARDWARE",
        "YM-LT-1068",
    ),
    Scenario(
        "Reception printer awaiting replacement roller",
        "The front-desk printer repeatedly jams while processing visitor badges.",
        "oliver.grant@example.com",
        "DESKTOP_SUPPORT",
        "lucas.martin@example.com",
        TicketStatus.PENDING_VENDOR,
        74,
        "LOW",
        "MEDIUM",
        "HARDWARE",
    ),
    Scenario(
        "Email sync delayed on mobile device",
        "New messages arrive on the desktop but the mobile mail client is hours behind.",
        "ibrahim.diallo@example.com",
        "SERVICE_DESK",
        "noah.williams@example.com",
        TicketStatus.RESOLVED,
        96,
        "MEDIUM",
        "MEDIUM",
        "APPLICATION",
        None,
        (
            "The delay seems limited to my phone.",
            "I renewed the mobile mail account and verified a new message arrived.",
            "Confirm the device policy sync completed; no mailbox-wide issue observed.",
        ),
    ),
    Scenario(
        "Procurement portal access for new approver",
        "A new approver cannot open the purchase-order review queue despite manager approval.",
        "vikram.shah@example.com",
        "APPLICATION_SUPPORT",
        "sophia.kim@example.com",
        TicketStatus.CLOSED,
        240,
        "MEDIUM",
        "LOW",
        "APPLICATION",
    ),
    Scenario(
        "New starter laptop and account checklist",
        "Please prepare a laptop and standard collaboration access for Monday's new starter.",
        "kofi.asante@example.com",
        None,
        None,
        TicketStatus.NEW,
        2,
        "MEDIUM",
        "LOW",
        "ONBOARDING",
    ),
    Scenario(
        "Suspicious attachment reported by sales",
        "A customer-facing mailbox received an unexpected archive attachment "
        "claiming to be an invoice.",
        "diego.santos@example.com",
        "SERVICE_DESK",
        "maya.chen@example.com",
        TicketStatus.IN_PROGRESS,
        4,
        "HIGH",
        "HIGH",
        "SECURITY",
    ),
    Scenario(
        "VPN access restored after profile refresh",
        "Remote finance access failed following a managed device certificate rotation.",
        "ananya.rao@example.com",
        "SERVICE_DESK",
        "maya.chen@example.com",
        TicketStatus.RESOLVED,
        168,
        "MEDIUM",
        "MEDIUM",
        "ACCESS",
    ),
    Scenario(
        "Install approved design software",
        "Marketing needs the approved design package on a managed workstation "
        "for campaign production.",
        "nadia.petrova@example.com",
        "APPLICATION_SUPPORT",
        "sophia.kim@example.com",
        TicketStatus.OPEN,
        11,
        "LOW",
        "MEDIUM",
        "APPLICATION",
    ),
    Scenario(
        "Docking station drops external display",
        "The external monitor disconnects several times each afternoon when "
        "connected through the desk dock.",
        "jordan.lee@example.com",
        "DESKTOP_SUPPORT",
        "liam.oconnor@example.com",
        TicketStatus.IN_PROGRESS,
        6,
        "MEDIUM",
        "MEDIUM",
        "HARDWARE",
        "YM-LT-1081",
    ),
    Scenario(
        "Core switch CPU sustained above threshold",
        "Network operations observed sustained control-plane CPU above the "
        "configured alert threshold.",
        "nishant.paswan@example.com",
        "IT_OPERATIONS",
        "grace.mensah@example.com",
        TicketStatus.IN_PROGRESS,
        7,
        "HIGH",
        "HIGH",
        "NETWORK",
        "YM-NW-3010",
    ),
    Scenario(
        "Shared mailbox permissions corrected",
        "Sales operations needed delegated access to the regional shared mailbox.",
        "camila.costa@example.com",
        "SYSTEMS_ADMIN",
        "fatima.zahra@example.com",
        TicketStatus.CLOSED,
        336,
        "LOW",
        "MEDIUM",
        "ACCESS",
    ),
    Scenario(
        "Packet loss to north office",
        "The north office reports intermittent latency to the finance application "
        "during peak hours.",
        "samuel.wright@example.com",
        "NETWORK_OPS",
        "ethan.clark@example.com",
        TicketStatus.ESCALATED,
        52,
        "HIGH",
        "MEDIUM",
        "NETWORK",
    ),
    Scenario(
        "Windows update requires a restart window",
        "The managed laptop has a pending security update but restarts during scheduled training.",
        "emily.turner@example.com",
        "DESKTOP_SUPPORT",
        "lucas.martin@example.com",
        TicketStatus.PENDING_USER,
        44,
        "MEDIUM",
        "LOW",
        "WORKPLACE",
    ),
    Scenario(
        "New laptop configured for people operations",
        "The replacement laptop needs the standard HR application set and encrypted drive policy.",
        "amara.johnson@example.com",
        "DESKTOP_SUPPORT",
        "liam.oconnor@example.com",
        TicketStatus.RESOLVED,
        192,
        "MEDIUM",
        "MEDIUM",
        "ONBOARDING",
        "YM-LT-1042",
    ),
    Scenario(
        "Request access to regional sales dashboard",
        "The sales dashboard shows an access-denied message for a newly transferred team member.",
        "chloe.bennett@example.com",
        None,
        None,
        TicketStatus.NEW,
        1,
        "LOW",
        "MEDIUM",
        "APPLICATION",
    ),
    Scenario(
        "Remote printer discovery fails",
        "The remote office printer is not discoverable after reconnecting to the company VPN.",
        "sara.lindberg@example.com",
        "SERVICE_DESK",
        "noah.williams@example.com",
        TicketStatus.OPEN,
        13,
        "MEDIUM",
        "LOW",
        "HARDWARE",
    ),
    Scenario(
        "Single sign-on loop for executive workspace",
        "The executive workspace returns to the login screen after a successful MFA prompt.",
        "zara.ahmed@example.com",
        "SYSTEMS_ADMIN",
        "fatima.zahra@example.com",
        TicketStatus.IN_PROGRESS,
        23,
        "HIGH",
        "MEDIUM",
        "ACCESS",
    ),
)

ASSETS = (
    ("YM-LT-1042", "LAPTOP", "Dell", "Latitude 7450", "amara.johnson@example.com", "HQ"),
    ("YM-LT-1068", "LAPTOP", "Lenovo", "ThinkPad T14 Gen 5", "chloe.bennett@example.com", "NORTH"),
    ("YM-LT-1081", "LAPTOP", "Lenovo", "ThinkPad X1 Carbon", "jordan.lee@example.com", "HQ"),
    ("YM-DT-2004", "DESKTOP", "HP", "EliteDesk 800 G9", "oliver.grant@example.com", "HQ"),
    ("YM-PR-2011", "PRINTER", "HP", "LaserJet Enterprise M610", None, "HQ"),
    ("YM-PR-2032", "PRINTER", "Brother", "MFC-L6915DW", None, "NORTH"),
    ("YM-MN-2120", "MONITOR", "Dell", "P2425H", "rahul.kapoor@example.com", "HQ"),
    ("YM-NW-3010", "NETWORK_DEVICE", "Cisco", "Catalyst 9300", None, "SOUTH"),
    ("YM-SV-4002", "SERVER", "Dell", "PowerEdge R760", None, "HQ"),
    ("YM-LT-1097", "LAPTOP", "HP", "EliteBook 840 G11", "meera.iyer@example.com", "SOUTH"),
)

ARTICLES = (
    (
        "ACCOUNT",
        "Reset a forgotten password",
        "Use the self-service recovery flow before contacting the desk.",
        "Confirm your work email and complete the approved identity challenge. "
        "Choose a unique passphrase and sign in again. If recovery is unavailable, "
        "contact the service desk; never share a one-time code in a ticket.",
        ("password", "identity"),
    ),
    (
        "ACCOUNT",
        "Recover MFA access after replacing a phone",
        "Restore a registered factor without bypassing identity checks.",
        "Use a previously registered factor or approved recovery method. If neither "
        "is available, ask the service desk for an identity-verified reset. Re-register "
        "the new device and remove the lost one from your security settings.",
        ("mfa", "recovery"),
    ),
    (
        "CONNECTIVITY",
        "Troubleshoot a VPN connection",
        "Check common client, profile, and network causes.",
        "Confirm local internet access, then reconnect the approved VPN client. Note "
        "the exact error and time. Restart the client and retry once; if MFA succeeds "
        "but the tunnel stalls, attach a redacted diagnostic and contact the service "
        "desk. Never paste credentials or tokens into the ticket.",
        ("vpn", "remote-work"),
    ),
    (
        "CONNECTIVITY",
        "Improve office Wi-Fi stability",
        "Collect useful details for roaming and signal issues.",
        "Check the approved corporate SSID and forget outdated guest networks. Record "
        "the floor, approximate time, and whether other devices are affected. Reconnect "
        "once; if calls still drop, send those details to Network Operations.",
        ("wifi", "network"),
    ),
    (
        "WORKPLACE",
        "Clear a recurring printer jam",
        "Safe checks before a printer service visit.",
        "Pause the print job, follow the device display to remove accessible paper, and "
        "avoid forcing internal rollers. Check tray guides and paper stock. If the jam "
        "repeats, record the printer asset tag and contact Desktop Support.",
        ("printer", "hardware"),
    ),
    (
        "WORKPLACE",
        "Prepare a replacement Windows laptop",
        "Standard handover and sign-in checklist.",
        "Confirm the assigned asset tag, encryption state, operating-system updates, "
        "and approved application bundle. Sign in with the employee account, verify "
        "MFA, and test network and collaboration tools before handing over the device.",
        ("windows", "onboarding"),
    ),
    (
        "APPLICATION",
        "Restore mobile email sync",
        "Check whether delayed messages are device-specific.",
        "Compare delivery in the web mailbox and mobile app. Confirm connectivity and "
        "approved device policy, then refresh the managed mail account. If only the "
        "mobile app is delayed, send the device type and last successful sync time.",
        ("email", "mobile"),
    ),
    (
        "APPLICATION",
        "Request approved software installation",
        "Provide details needed for a managed installation.",
        "Include the approved software name, business purpose, device asset tag, and "
        "required date. Do not download an unapproved installer. Application Support "
        "will confirm licensing and deployment status in the ticket.",
        ("software", "installation"),
    ),
)


async def seed_demo(session: AsyncSession, settings: Settings) -> dict[str, int]:
    if settings.environment.lower() not in {"development", "test"}:
        raise RuntimeError("Fictional demo data is restricted to development/test databases")
    users = {user.email: user for user in (await session.scalars(select(User))).all()}
    if len(users) < 35 or "nishant.paswan@example.com" not in users:
        raise RuntimeError("Run the existing enterprise directory seed before demo data")
    teams = {team.code: team for team in (await session.scalars(select(Team))).all()}
    departments = {value.id: value for value in (await session.scalars(select(Department))).all()}
    admin = users["nishant.paswan@example.com"]
    counts = {"categories": 0, "articles": 0, "assets": 0, "tickets": 0, "agents": 0}

    categories: dict[str, TicketCategory] = {}
    for code, name in (
        ("ACCESS", "Accounts & access"),
        ("NETWORK", "Network & connectivity"),
        ("HARDWARE", "Hardware & devices"),
        ("APPLICATION", "Applications & email"),
        ("ONBOARDING", "Onboarding"),
        ("SECURITY", "Security reports"),
        ("WORKPLACE", "Workplace support"),
    ):
        category = await session.scalar(select(TicketCategory).where(TicketCategory.code == code))
        if category is None:
            category = TicketCategory(code=code, name=name, is_active=True)
            session.add(category)
            await session.commit()
            counts["categories"] += 1
        categories[code] = category

    knowledge = KnowledgeService(session)
    knowledge_categories: dict[str, KnowledgeCategory] = {}
    for code, name in (
        ("ACCOUNT", "Account & identity"),
        ("CONNECTIVITY", "Connectivity"),
        ("WORKPLACE", "Workplace devices"),
        ("APPLICATION", "Business applications"),
    ):
        kb_category = await session.scalar(
            select(KnowledgeCategory).where(KnowledgeCategory.code == code)
        )
        if kb_category is None:
            kb_category = await knowledge.save_category(
                {
                    "code": code,
                    "name": name,
                    "description": "Fictional enterprise support guidance",
                    "is_active": True,
                }
            )
        knowledge_categories[code] = kb_category
    for code, title, summary, content, tags in ARTICLES:
        slug = title.lower().replace(" ", "-")
        if await session.scalar(select(KnowledgeArticle.id).where(KnowledgeArticle.slug == slug)):
            continue
        article_id = await knowledge.create_article(
            admin.id,
            {
                "slug": slug,
                "category_id": knowledge_categories[code].id,
                "tags": list(tags),
                "title": title,
                "summary": summary,
                "content": content,
                "change_summary": "Initial fictional support guide",
            },
            SOURCE,
        )
        await knowledge.transition(
            admin.id, article_id, ArticleStatus.IN_REVIEW, "Submit verified demo guidance", SOURCE
        )
        await knowledge.transition(
            admin.id,
            article_id,
            ArticleStatus.PUBLISHED,
            "Publish fictional support guidance",
            SOURCE,
        )
        counts["articles"] += 1

    asset_service = AssetService(session)
    assets: dict[str, Asset] = {}
    locations = {
        location.code: location for location in (await session.scalars(select(Location))).all()
    }
    for tag, kind, manufacturer, model, owner_email, location_code in ASSETS:
        asset = await session.scalar(select(Asset).where(Asset.asset_tag == tag))
        if asset is None:
            owner = users[owner_email] if owner_email else None
            department = departments[owner.department_id] if owner and owner.department_id else None
            location = locations[location_code]
            asset = await asset_service.create_asset(
                admin.id,
                {
                    "asset_tag": tag,
                    "hostname": tag.lower(),
                    "asset_type": kind,
                    "manufacturer": manufacturer,
                    "model": model,
                    "owner_id": owner.id if owner else None,
                    "department_id": department.id
                    if department
                    else teams["IT_OPERATIONS"].department_id,
                    "location_id": location.id,
                    "status": "ACTIVE",
                    "health_status": "UNKNOWN",
                },
                "Register fictional managed asset",
                SOURCE,
            )
            counts["assets"] += 1
        assets[tag] = asset

    ticket_service = TicketService(session)
    now = datetime.now(UTC)
    for index, scenario in enumerate(SCENARIOS):
        if await session.scalar(select(Ticket.id).where(Ticket.title == scenario.title)):
            continue
        first = now - timedelta(hours=scenario.age_hours, minutes=index * 3)
        requester = users[scenario.requester]
        with patch("app.modules.tickets.service.utc_now", return_value=first):
            ticket = await ticket_service.create_ticket(
                requester,
                {
                    "title": scenario.title,
                    "description": scenario.description,
                    "impact": scenario.impact,
                    "urgency": scenario.urgency,
                    "category_id": categories[scenario.category].id,
                    "subcategory_id": None,
                    "asset_id": assets[scenario.asset].id if scenario.asset else None,
                },
                SOURCE,
            )
        ticket.created_at = first
        instance = await session.scalar(
            select(SlaInstance).where(SlaInstance.ticket_id == ticket.id)
        )
        if instance is not None:
            instance.created_at = first
        await session.commit()
        moment = first + timedelta(minutes=12)
        technician = users[scenario.technician] if scenario.technician else None
        if scenario.team and technician:
            with patch("app.modules.tickets.service.utc_now", return_value=moment):
                await ticket_service.assign_ticket(
                    admin.id,
                    ticket.id,
                    teams[scenario.team].id,
                    technician.id,
                    "Route to the responsible support team",
                    SOURCE,
                )
            moment += timedelta(minutes=8)
        path = {
            TicketStatus.NEW: (),
            TicketStatus.OPEN: ("OPEN",),
            TicketStatus.IN_PROGRESS: ("OPEN", "IN_PROGRESS"),
            TicketStatus.PENDING_USER: ("OPEN", "IN_PROGRESS", "PENDING_USER"),
            TicketStatus.PENDING_VENDOR: ("OPEN", "IN_PROGRESS", "PENDING_VENDOR"),
            TicketStatus.ESCALATED: ("OPEN", "IN_PROGRESS", "ESCALATED"),
            TicketStatus.RESOLVED: ("OPEN", "IN_PROGRESS", "RESOLVED"),
            TicketStatus.CLOSED: ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"),
        }[scenario.status]
        conversation = scenario.conversation
        for state in path:
            if state in {"PENDING_USER", "PENDING_VENDOR", "RESOLVED", "CLOSED"} and conversation:
                for author, body, visibility in (
                    (requester, conversation[0], CommentVisibility.PUBLIC),
                    (technician, conversation[1], CommentVisibility.PUBLIC),
                    (technician, conversation[2], CommentVisibility.INTERNAL),
                ):
                    assert author is not None
                    with patch("app.modules.tickets.service.utc_now", return_value=moment):
                        comment = await ticket_service.add_comment(
                            author.id, ticket.id, body, visibility, SOURCE
                        )
                    comment.created_at = moment
                    await session.commit()
                    moment += timedelta(minutes=4)
                conversation = None
            with patch("app.modules.tickets.service.utc_now", return_value=moment):
                await ticket_service.transition(
                    technician.id if technician else admin.id,
                    ticket.id,
                    TicketStatus(state),
                    f"Support workflow advanced to {state.lower().replace('_', ' ')}",
                    SOURCE,
                    "Service restored and confirmed with the requester."
                    if state == "RESOLVED"
                    else None,
                    "CONFIGURATION_REPAIRED" if state == "RESOLVED" else None,
                )
            moment += timedelta(minutes=7)
        ticket.updated_at = moment
        await session.commit()
        if instance is not None:
            await SlaService(session).evaluate(instance, ticket, min(moment, now))
            await session.commit()
        counts["tickets"] += 1

    monitoring = MonitoringService(session, settings)
    for tag, cpu, memory, disk, offline in (
        ("YM-NW-3010", 94.0, 61.0, 44.0, False),
        ("YM-SV-4002", 38.0, 57.0, 92.0, False),
        ("YM-PR-2011", 13.0, 34.0, 68.0, True),
    ):
        existing = await session.scalar(
            select(DeviceAgent).where(DeviceAgent.asset_id == assets[tag].id)
        )
        if existing is not None and offline:
            continue
        if existing is None:
            agent, enrollment_token = await monitoring.create_enrollment(
                admin.id, assets[tag].id, 30, "Register fictional demo telemetry source", SOURCE
            )
            agent, credential = await monitoring.enroll(enrollment_token, "fictional-demo")
            del credential  # Only a hash persists; no usable agent credential is retained.
            counts["agents"] += 1
        else:
            agent = existing
        sample_time = datetime.now(UTC)
        heartbeat = HeartbeatCreate(
            observed_at=sample_time,
            available=True,
            hostname=tag.lower(),
            operating_system="Managed device (fictional)",
            ip_addresses=[],
            boot_time=sample_time - timedelta(days=3),
        )
        await monitoring.heartbeat(agent, heartbeat)
        await monitoring.metric(
            agent,
            MetricCreate(
                sampled_at=sample_time,
                cpu_percent=cpu,
                memory_percent=memory,
                memory_used_bytes=int(memory * 1_000_000),
                memory_total_bytes=100_000_000,
                disk_percent=disk,
                disk_used_bytes=int(disk * 1_000_000),
                disk_total_bytes=100_000_000,
                network_bytes_sent=120_000,
                network_bytes_received=240_000,
            ),
        )
        if offline:
            agent.last_heartbeat_at = sample_time - timedelta(hours=2)
            await session.commit()
            await monitoring.reconcile(sample_time, 100)
    alerts = list(
        (
            await session.scalars(
                select(Alert)
                .where(Alert.state == AlertState.TRIGGERED)
                .order_by(Alert.created_at, Alert.id)
            )
        ).all()
    )
    if alerts and counts["agents"]:
        await AlertService(session).transition(
            admin.id,
            alerts[0].id,
            AlertState.ACKNOWLEDGED,
            "Operations is investigating the fictional signal",
            SOURCE,
        )
    return counts


async def main() -> None:
    settings = get_settings()
    async with get_session_factory()() as session:
        counts = await seed_demo(session, settings)
    print("Fictional demo data created:", counts)


if __name__ == "__main__":
    asyncio.run(main())
