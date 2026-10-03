from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.middleware import SecurityHeadersMiddleware
from app.modules.audit.immutability import AuditMutationError, reject_audit_mutation
from app.modules.audit.schemas import AuditSource
from app.modules.audit.service import AuditService, sanitize_state
from app.modules.identity.rate_limit import LoginRateLimiter, private_rate_limit_key
from app.modules.tickets.storage import (
    AttachmentMalwareDetected,
    AttachmentScanError,
    ClamAVScanner,
)


def event(**values: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "actor_id": uuid4(),
        "action": "entity.updated",
        "entity_type": "ENTITY",
        "entity_id": uuid4(),
        "before_state": {"password": "never expose", "name": "before"},
        "after_state": {"api_key": "never expose", "name": "after"},
        "reason": "Controlled change",
        "request_id": "request-18",
        "created_at": datetime(2026, 9, 15, tzinfo=UTC),
        "ticket_id": uuid4(),
        "instance_id": uuid4(),
        "article_id": uuid4(),
        "asset_id": uuid4(),
        "event_type": "entity.updated",
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_audit_normalization_covers_every_source_without_sensitive_ai_text() -> None:
    role = event(user_id=uuid4(), before_roles=["EMPLOYEE"], after_roles=["ADMIN"])
    assert AuditService._normalize(AuditSource.ACCESS, role).entity_type == "USER"
    assert AuditService._normalize(AuditSource.DIRECTORY, event()).entity_type == "ENTITY"
    assert AuditService._normalize(AuditSource.TICKET, event()).entity_type == "TICKET"
    sla = AuditService._normalize(
        AuditSource.SLA, event(payload={"deadline": "soon", "refresh_token": "hidden"})
    )
    assert sla.actor_id is None and sla.after_state == {
        "deadline": "soon",
        "refresh_token": "[REDACTED]",
    }
    assert (
        AuditService._normalize(AuditSource.KNOWLEDGE, event()).entity_type == "KNOWLEDGE_ARTICLE"
    )
    assert AuditService._normalize(AuditSource.ASSET, event()).entity_type == "ASSET"
    assert AuditService._normalize(AuditSource.ALERT, event()).entity_type == "ENTITY"
    ai = AuditService._normalize(
        AuditSource.AI,
        event(
            action="EDITED",
            output_type="RESPONSE_DRAFT",
            confidence=0.81,
            feedback_text="private",
            edited_content="private",
        ),
    )
    assert ai.action == "ai.feedback.edited"
    assert ai.after_state == {"output_type": "RESPONSE_DRAFT", "confidence": 0.81}
    assert "private" not in ai.model_dump_json()
    assert sanitize_state([{"secret_value": "x"}]) == [{"secret_value": "[REDACTED]"}]


@pytest.mark.anyio
async def test_audit_page_filters_counts_orders_and_validates_dates() -> None:
    row = event(action="directory.updated")
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 1
    session.scalars.return_value = [row]
    service = AuditService(session)
    result = await service.page(
        source=AuditSource.DIRECTORY,
        action="directory.updated",
        entity_id=row.entity_id,
        actor_id=row.actor_id,
        created_from=row.created_at - timedelta(minutes=1),
        created_to=row.created_at + timedelta(minutes=1),
        offset=0,
        limit=20,
    )
    assert result.total == 1 and result.items[0].id == row.id
    with pytest.raises(HTTPException):
        await service.page(
            source=None,
            action=None,
            entity_id=None,
            actor_id=None,
            created_from=row.created_at,
            created_to=row.created_at - timedelta(seconds=1),
            offset=0,
            limit=20,
        )


def test_audit_mutation_guard_rejects_updates_and_deletes() -> None:
    from app.modules.access.models import RoleAssignmentEvent

    record = RoleAssignmentEvent()
    with pytest.raises(AuditMutationError, match="updated"):
        reject_audit_mutation(SimpleNamespace(dirty=[record], deleted=[]))
    with pytest.raises(AuditMutationError, match="deleted"):
        reject_audit_mutation(SimpleNamespace(dirty=[], deleted=[record]))
    reject_audit_mutation(SimpleNamespace(dirty=[], deleted=[]))


def test_security_headers_and_strict_cors_configuration() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, production=True)

    @app.get("/api/v1/example")
    async def example() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/api/v1/example")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["strict-transport-security"].startswith("max-age=")
    with pytest.raises(ValidationError):
        Settings(cors_origins=["https://example.com/path"])
    with pytest.raises(ValidationError):
        Settings(cors_origins=["https://example.com", "https://EXAMPLE.com/"])
    with pytest.raises(ValidationError):
        Settings(attachment_scan_required=True)


def test_production_configuration_fails_closed() -> None:
    valid = {
        "environment": "production",
        "database_url": "postgresql+psycopg://itops:test-only@database:5432/itops",
        "jwt_secret": "test-only-production-secret-at-least-32-characters",
        "secure_cookies": True,
        "cors_origins": ["https://support.example.com"],
        "attachment_scan_required": True,
        "attachment_clamav_host": "clamav.internal",
    }
    Settings(**valid)
    for unsafe in (
        {"database_url": "postgresql+psycopg://itops:replace-with-password@localhost:5432/itops"},
        {"jwt_secret": None},
        {"secure_cookies": False},
        {"cors_origins": ["http://support.example.com"]},
        {"attachment_scan_required": False},
        {"enterprise_seed_password": "test-only-demo-password"},
    ):
        with pytest.raises(ValidationError):
            Settings(**(valid | unsafe))


def test_embedding_dimensions_parse_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITOPS_AI_EMBEDDING_DIMENSIONS", "1536")
    assert Settings().ai_embedding_dimensions == 1536
    monkeypatch.setenv("ITOPS_AI_EMBEDDING_DIMENSIONS", "3072")
    with pytest.raises(ValidationError):
        Settings()


def test_rate_limit_keys_hide_credentials_and_retry_after_is_bounded() -> None:
    key = private_rate_limit_key("127.0.0.1", "Admin@Example.com")
    assert "admin@example.com" not in key
    limiter = LoginRateLimiter(limit=1, window_seconds=60)
    assert limiter.retry_after("missing") == 0
    assert limiter.allow(key) and not limiter.allow(key)
    assert 1 <= limiter.retry_after(key) <= 60


class FakeSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = bytearray()

    def __enter__(self) -> "FakeSocket":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def settimeout(self, _: int) -> None:
        return None

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def recv(self, _: int) -> bytes:
        return self.response


@pytest.mark.anyio
async def test_clamav_streaming_accepts_clean_and_fails_closed(monkeypatch) -> None:
    clean = FakeSocket(b"stream: OK\0")
    monkeypatch.setattr("socket.create_connection", lambda *_: clean)
    await ClamAVScanner("scanner").scan(b"safe")
    assert clean.sent.startswith(b"zINSTREAM\0")

    monkeypatch.setattr("socket.create_connection", lambda *_: FakeSocket(b"stream: Virus FOUND\0"))
    with pytest.raises(AttachmentMalwareDetected):
        await ClamAVScanner("scanner").scan(b"unsafe")
    monkeypatch.setattr("socket.create_connection", lambda *_: FakeSocket(b"stream: ERROR\0"))
    with pytest.raises(AttachmentScanError):
        await ClamAVScanner("scanner").scan(b"unknown")

    def unavailable(*_: object) -> None:
        raise OSError("offline")

    monkeypatch.setattr("socket.create_connection", unavailable)
    with pytest.raises(AttachmentScanError, match="unavailable"):
        await ClamAVScanner("scanner").scan(b"unknown")
