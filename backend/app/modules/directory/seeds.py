from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.access.models import RoleAssignmentEvent, UserRole
from app.modules.directory.models import (
    Department,
    DirectoryStatus,
    Location,
    Team,
    TeamMember,
    TeamMemberRole,
)
from app.modules.identity.models import User, UserStatus
from app.modules.identity.security import PasswordService


class UserSeed(NamedTuple):
    name: str
    email: str
    role: str
    department: str
    location: str
    job_title: str
    status: UserStatus = UserStatus.ACTIVE


DEPARTMENTS = (
    ("IT", "Information Technology", "Enterprise technology and service operations"),
    ("HR", "Human Resources", "People operations and employee experience"),
    ("FIN", "Finance", "Financial planning, accounting, and controls"),
    ("SALES", "Sales", "Customer acquisition and account growth"),
    ("MKTG", "Marketing", "Brand, communications, and demand generation"),
    ("OPS", "Operations", "Business operations and service delivery"),
    ("ADMIN", "Administration", "Corporate administration and facilities"),
    ("MGMT", "Management", "Executive leadership and strategy"),
)

LOCATIONS = (
    ("HQ", "Head Office", "Asia/Kolkata", "Bengaluru corporate campus"),
    ("NORTH", "North Office", "Asia/Kolkata", "New Delhi regional office"),
    ("SOUTH", "South Office", "Asia/Kolkata", "Chennai regional office"),
    ("REMOTE", "Remote", "UTC", "Distributed workforce"),
)

TEAMS = (
    ("SERVICE_DESK", "Service Desk", "Frontline IT support", "HQ"),
    ("DESKTOP_SUPPORT", "Desktop Support", "Endpoint and workplace support", "HQ"),
    ("NETWORK_OPS", "Network Operations", "Connectivity and network reliability", "SOUTH"),
    ("SYSTEMS_ADMIN", "Systems Administration", "Core platforms and identity", "SOUTH"),
    ("APPLICATION_SUPPORT", "Application Support", "Business application support", "REMOTE"),
    ("IT_OPERATIONS", "IT Operations", "Operational readiness and automation", "NORTH"),
)

USERS = (
    UserSeed(
        "Nishant Paswan",
        "nishant.paswan@example.com",
        "ADMIN",
        "IT",
        "HQ",
        "Platform Administrator",
    ),
    UserSeed(
        "Priya Raman", "priya.raman@example.com", "ADMIN", "IT", "HQ", "Security Administrator"
    ),
    UserSeed(
        "Aisha Mehta",
        "aisha.mehta@example.com",
        "IT_MANAGER",
        "IT",
        "HQ",
        "Service Delivery Manager",
    ),
    UserSeed(
        "Marcus Reed",
        "marcus.reed@example.com",
        "IT_MANAGER",
        "IT",
        "NORTH",
        "Workplace Technology Manager",
    ),
    UserSeed(
        "Elena Vasquez",
        "elena.vasquez@example.com",
        "IT_MANAGER",
        "IT",
        "SOUTH",
        "Infrastructure Manager",
    ),
    UserSeed(
        "Helen Okafor",
        "helen.okafor@example.com",
        "IT_MANAGER",
        "IT",
        "REMOTE",
        "Business Systems Manager",
    ),
    UserSeed(
        "Maya Chen", "maya.chen@example.com", "TECHNICIAN", "IT", "HQ", "Service Desk Engineer"
    ),
    UserSeed(
        "Noah Williams",
        "noah.williams@example.com",
        "TECHNICIAN",
        "IT",
        "HQ",
        "Support Specialist",
    ),
    UserSeed(
        "Liam O'Connor",
        "liam.oconnor@example.com",
        "TECHNICIAN",
        "IT",
        "HQ",
        "Desktop Support Engineer",
    ),
    UserSeed(
        "Lucas Martin",
        "lucas.martin@example.com",
        "TECHNICIAN",
        "IT",
        "NORTH",
        "Endpoint Technician",
    ),
    UserSeed(
        "Arjun Nair", "arjun.nair@example.com", "TECHNICIAN", "IT", "SOUTH", "Network Engineer"
    ),
    UserSeed(
        "Ethan Clark",
        "ethan.clark@example.com",
        "TECHNICIAN",
        "IT",
        "SOUTH",
        "Network Operations Analyst",
    ),
    UserSeed(
        "Fatima Zahra",
        "fatima.zahra@example.com",
        "TECHNICIAN",
        "IT",
        "SOUTH",
        "Systems Administrator",
    ),
    UserSeed(
        "Sophia Kim",
        "sophia.kim@example.com",
        "TECHNICIAN",
        "IT",
        "REMOTE",
        "Application Support Engineer",
    ),
    UserSeed(
        "Grace Mensah",
        "grace.mensah@example.com",
        "TECHNICIAN",
        "IT",
        "NORTH",
        "IT Operations Engineer",
    ),
    UserSeed("Jordan Lee", "jordan.lee@example.com", "EMPLOYEE", "OPS", "HQ", "Operations Analyst"),
    UserSeed(
        "Amara Johnson",
        "amara.johnson@example.com",
        "EMPLOYEE",
        "HR",
        "HQ",
        "People Operations Partner",
    ),
    UserSeed(
        "Rahul Kapoor", "rahul.kapoor@example.com", "EMPLOYEE", "FIN", "HQ", "Financial Analyst"
    ),
    UserSeed(
        "Chloe Bennett",
        "chloe.bennett@example.com",
        "EMPLOYEE",
        "SALES",
        "NORTH",
        "Account Executive",
    ),
    UserSeed(
        "Ibrahim Diallo",
        "ibrahim.diallo@example.com",
        "EMPLOYEE",
        "MKTG",
        "REMOTE",
        "Growth Marketing Specialist",
    ),
    UserSeed(
        "Meera Iyer",
        "meera.iyer@example.com",
        "EMPLOYEE",
        "OPS",
        "SOUTH",
        "Service Operations Coordinator",
    ),
    UserSeed(
        "Oliver Grant",
        "oliver.grant@example.com",
        "EMPLOYEE",
        "ADMIN",
        "HQ",
        "Facilities Coordinator",
    ),
    UserSeed(
        "Zara Ahmed",
        "zara.ahmed@example.com",
        "EMPLOYEE",
        "MGMT",
        "HQ",
        "Executive Business Partner",
    ),
    UserSeed(
        "Diego Santos",
        "diego.santos@example.com",
        "EMPLOYEE",
        "SALES",
        "REMOTE",
        "Customer Success Manager",
    ),
    UserSeed(
        "Ananya Rao",
        "ananya.rao@example.com",
        "EMPLOYEE",
        "FIN",
        "SOUTH",
        "Accounts Payable Specialist",
    ),
    UserSeed(
        "Samuel Wright",
        "samuel.wright@example.com",
        "EMPLOYEE",
        "OPS",
        "NORTH",
        "Logistics Planner",
    ),
    UserSeed(
        "Nadia Petrova",
        "nadia.petrova@example.com",
        "EMPLOYEE",
        "MKTG",
        "REMOTE",
        "Content Strategist",
    ),
    UserSeed(
        "Kofi Asante",
        "kofi.asante@example.com",
        "EMPLOYEE",
        "HR",
        "NORTH",
        "Talent Acquisition Partner",
    ),
    UserSeed(
        "Emily Turner",
        "emily.turner@example.com",
        "EMPLOYEE",
        "ADMIN",
        "HQ",
        "Office Administrator",
    ),
    UserSeed(
        "Vikram Shah", "vikram.shah@example.com", "EMPLOYEE", "FIN", "HQ", "Procurement Analyst"
    ),
    UserSeed(
        "Camila Costa",
        "camila.costa@example.com",
        "EMPLOYEE",
        "SALES",
        "SOUTH",
        "Sales Operations Analyst",
    ),
    UserSeed(
        "Henry Walker",
        "henry.walker@example.com",
        "EMPLOYEE",
        "OPS",
        "REMOTE",
        "Quality Coordinator",
    ),
    UserSeed(
        "Sara Lindberg",
        "sara.lindberg@example.com",
        "EMPLOYEE",
        "MKTG",
        "NORTH",
        "Communications Manager",
    ),
    UserSeed(
        "Rohan Desai",
        "rohan.desai@example.com",
        "EMPLOYEE",
        "HR",
        "SOUTH",
        "Learning Specialist",
        UserStatus.DISABLED,
    ),
    UserSeed(
        "Amina Yusuf",
        "amina.yusuf@example.com",
        "EMPLOYEE",
        "SALES",
        "REMOTE",
        "Sales Development Representative",
        UserStatus.LOCKED,
    ),
)

MEMBERSHIPS = (
    ("SERVICE_DESK", "aisha.mehta@example.com", TeamMemberRole.LEAD),
    ("SERVICE_DESK", "maya.chen@example.com", TeamMemberRole.MEMBER),
    ("SERVICE_DESK", "noah.williams@example.com", TeamMemberRole.MEMBER),
    ("DESKTOP_SUPPORT", "marcus.reed@example.com", TeamMemberRole.LEAD),
    ("DESKTOP_SUPPORT", "liam.oconnor@example.com", TeamMemberRole.MEMBER),
    ("DESKTOP_SUPPORT", "lucas.martin@example.com", TeamMemberRole.MEMBER),
    ("NETWORK_OPS", "elena.vasquez@example.com", TeamMemberRole.LEAD),
    ("NETWORK_OPS", "arjun.nair@example.com", TeamMemberRole.MEMBER),
    ("NETWORK_OPS", "ethan.clark@example.com", TeamMemberRole.MEMBER),
    ("SYSTEMS_ADMIN", "elena.vasquez@example.com", TeamMemberRole.LEAD),
    ("SYSTEMS_ADMIN", "fatima.zahra@example.com", TeamMemberRole.MEMBER),
    ("APPLICATION_SUPPORT", "helen.okafor@example.com", TeamMemberRole.LEAD),
    ("APPLICATION_SUPPORT", "sophia.kim@example.com", TeamMemberRole.MEMBER),
    ("IT_OPERATIONS", "marcus.reed@example.com", TeamMemberRole.LEAD),
    ("IT_OPERATIONS", "grace.mensah@example.com", TeamMemberRole.MEMBER),
)


async def seed_enterprise_directory(session: AsyncSession) -> None:
    """Seed a local-only, repeatable organization for demos and integration testing."""
    settings = get_settings()
    if (
        settings.enterprise_seed_password is None
        or not settings.enterprise_seed_password.get_secret_value()
    ):
        return
    if settings.environment.lower() not in {"development", "test"}:
        raise RuntimeError("Enterprise demo accounts can only be seeded in development or test")

    departments: dict[str, Department] = {}
    for code, name, description in DEPARTMENTS:
        department = await session.scalar(
            select(Department).where(func.lower(Department.code) == code.lower())
        )
        if department is None:
            department = Department(
                code=code, name=name, description=description, status=DirectoryStatus.ACTIVE
            )
            session.add(department)
            await session.flush()
        departments[code] = department

    locations: dict[str, Location] = {}
    for code, name, timezone, address in LOCATIONS:
        location = await session.scalar(
            select(Location).where(func.lower(Location.code) == code.lower())
        )
        if location is None:
            location = Location(
                code=code,
                name=name,
                timezone=timezone,
                address=address,
                status=DirectoryStatus.ACTIVE,
            )
            session.add(location)
            await session.flush()
        locations[code] = location

    teams: dict[str, Team] = {}
    for code, name, description, location_code in TEAMS:
        team = await session.scalar(select(Team).where(func.lower(Team.code) == code.lower()))
        if team is None:
            team = Team(
                code=code,
                name=name,
                description=description,
                status=DirectoryStatus.ACTIVE,
                department_id=departments["IT"].id,
                location_id=locations[location_code].id,
            )
            session.add(team)
            await session.flush()
        teams[code] = team

    password = settings.enterprise_seed_password.get_secret_value()
    password_service = PasswordService()
    users: dict[str, User] = {}
    newly_created: set[str] = set()
    changed_at = datetime.now(UTC)
    for number, spec in enumerate(USERS, start=1001):
        user = await session.scalar(
            select(User).where(func.lower(User.email) == spec.email.lower())
        )
        if user is None:
            newly_created.add(spec.email)
            user = User(
                email=spec.email,
                display_name=spec.name,
                employee_number=f"EMP-{number}",
                job_title=spec.job_title,
                department_id=departments[spec.department].id,
                location_id=locations[spec.location].id,
                password_hash=password_service.hash(password),
                status=spec.status,
                password_changed_at=changed_at,
            )
            session.add(user)
            await session.flush()
        elif spec.email == "nishant.paswan@example.com":
            user.display_name = spec.name
            user.employee_number = user.employee_number or f"EMP-{number}"
            user.job_title = user.job_title or spec.job_title
            user.department_id = user.department_id or departments[spec.department].id
            user.location_id = user.location_id or locations[spec.location].id
        users[spec.email] = user

    actor = users["nishant.paswan@example.com"]
    for spec in USERS:
        if spec.email not in newly_created:
            continue
        user = users[spec.email]
        existing_roles = list(
            await session.scalars(select(UserRole.role_code).where(UserRole.user_id == user.id))
        )
        if spec.role not in existing_roles:
            session.add(UserRole(user_id=user.id, role_code=spec.role))
            session.add(
                RoleAssignmentEvent(
                    actor_id=actor.id,
                    user_id=user.id,
                    before_roles=sorted(existing_roles),
                    after_roles=sorted([*existing_roles, spec.role]),
                    reason="Development enterprise dataset seed",
                    request_id="seed-enterprise-directory",
                )
            )

    for team_code, email, member_role in MEMBERSHIPS:
        team, user = teams[team_code], users[email]
        exists = await session.scalar(
            select(TeamMember.id).where(
                TeamMember.team_id == team.id,
                TeamMember.user_id == user.id,
                TeamMember.ended_at.is_(None),
            )
        )
        if exists is None:
            session.add(TeamMember(team_id=team.id, user_id=user.id, member_role=member_role))
