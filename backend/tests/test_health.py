from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.main import create_app


def test_liveness_returns_service_identity() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ITOps Control Center API",
        "version": "0.1.0",
    }
    assert response.headers["x-request-id"]


def test_readiness_reports_database_ready(monkeypatch: MonkeyPatch) -> None:
    async def ready() -> bool:
        return True

    monkeypatch.setattr("app.api.routes.health.database_is_ready", ready)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_fails_when_database_is_unavailable(monkeypatch: MonkeyPatch) -> None:
    async def unavailable() -> bool:
        return False

    monkeypatch.setattr("app.api.routes.health.database_is_ready", unavailable)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
