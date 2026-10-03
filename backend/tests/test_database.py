from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import CheckConstraint, Column, Integer, Table

from app.core.config import Settings
from app.db import models as database_models
from app.db.base import Base
from app.db.seeds import run_seeds, seed_registry
from app.db.session import create_engine, database_is_ready


def test_metadata_uses_predictable_constraint_names() -> None:
    assert {
        "AIFeedback",
        "Alert",
        "AlertEvent",
        "AlertPolicy",
        "AutomationExecution",
        "AutomationRule",
        "Notification",
        "NotificationPreference",
        "PasswordResetToken",
        "RefreshSession",
        "RealtimeCursor",
        "RealtimeEvent",
        "User",
        "Role",
        "Permission",
        "UserRole",
        "Department",
        "DeviceAgent",
        "DeviceHeartbeat",
        "DeviceMetric",
        "Location",
        "Team",
        "TeamMember",
        "DirectoryEvent",
        "KnowledgeArticle",
        "KnowledgeArticleVersion",
        "KnowledgeCategory",
        "KnowledgeEvent",
        "AIInteraction",
        "AIRecommendation",
        "Asset",
        "AssetAssignment",
        "AssetEvent",
        "KnowledgeChunk",
        "KnowledgeEmbedding",
        "TicketEmbedding",
        "BusinessCalendar",
        "BusinessHoliday",
        "BusinessWindow",
        "PriorityMatrix",
        "SlaEvent",
        "SlaInstance",
        "SlaPause",
        "SlaPolicy",
        "Ticket",
        "TicketAssignment",
        "TicketAttachment",
        "TicketCategory",
        "TicketComment",
        "TicketEvent",
        "TicketSubcategory",
    } <= set(database_models.__all__)
    table = Table(
        "naming_example",
        Base.metadata,
        Column("value", Integer, nullable=False),
        CheckConstraint("value > 0", name="value_positive"),
    )
    constraint = next(item for item in table.constraints if isinstance(item, CheckConstraint))
    assert constraint.name == "ck_naming_example_value_positive"
    Base.metadata.remove(table)


def test_database_url_is_secret_and_engine_uses_postgresql() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:secret@localhost:5432/app")
    assert "user:secret" not in repr(settings)
    engine = create_engine(settings)
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.password == "secret"


@pytest.mark.anyio
async def test_seed_registry_is_safe_without_bootstrap_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    settings = Settings(
        initial_admin_email="", initial_admin_password="", enterprise_seed_password=""
    )
    monkeypatch.setattr("app.modules.identity.seeds.get_settings", lambda: settings)
    monkeypatch.setattr("app.modules.directory.seeds.get_settings", lambda: settings)
    assert len(seed_registry()) == 2
    await run_seeds(session)
    session.add.assert_not_called()


@pytest.mark.anyio
async def test_database_probe_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = MagicMock()
    engine.connect.side_effect = OSError("database unavailable")
    monkeypatch.setattr("app.db.session.get_engine", lambda: engine)
    assert await database_is_ready() is False
