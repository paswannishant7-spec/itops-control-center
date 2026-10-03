from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.modules.identity.dependencies import get_auth_service, get_current_user
from app.modules.identity.models import User, UserStatus
from app.modules.identity.rate_limit import login_rate_limiter
from app.modules.identity.service import AuthenticationError, AuthResult

SETTINGS = Settings(jwt_secret="test-secret-at-least-thirty-two-characters-long")
USER = User(
    id=uuid4(),
    email="operator@example.com",
    display_name="Operator",
    password_hash="not-returned",
    status=UserStatus.ACTIVE,
    password_changed_at=datetime.now(UTC),
)


class StubService:
    async def login(
        self, email: str, password: str, user_agent: str | None, ip_address: str | None
    ) -> AuthResult:
        if password == "wrong":
            raise AuthenticationError("internal detail")
        return AuthResult("access-token", "refresh-token", 600, USER)

    async def refresh(
        self, raw_token: str, user_agent: str | None, ip_address: str | None
    ) -> AuthResult:
        if raw_token != "refresh-token":
            raise AuthenticationError("invalid")
        return AuthResult("rotated-access", "rotated-refresh", 600, USER)

    async def logout(self, raw_token: str | None) -> None:
        return None


def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_auth_service] = StubService
    app.dependency_overrides[get_current_user] = lambda: USER
    login_rate_limiter.reset()
    return TestClient(app)


def test_login_sets_http_only_refresh_cookie() -> None:
    with client() as test_client:
        response = test_client.post(
            "/api/v1/auth/login", json={"email": USER.email, "password": "valid"}
        )
    assert response.status_code == 200
    assert response.json()["access_token"] == "access-token"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "refresh-token" not in response.text


def test_login_error_is_generic() -> None:
    with client() as test_client:
        response = test_client.post(
            "/api/v1/auth/login", json={"email": USER.email, "password": "wrong"}
        )
    assert response.status_code == 401
    assert response.json()["title"] == "Invalid email or password"
    assert response.json()["code"] == "http_error"


def test_refresh_rotates_cookie_and_logout_clears_it() -> None:
    with client() as test_client:
        test_client.cookies.set("itops_refresh", "refresh-token")
        refreshed = test_client.post("/api/v1/auth/refresh")
        logged_out = test_client.post("/api/v1/auth/logout")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] == "rotated-access"
    assert "rotated-refresh" in refreshed.headers["set-cookie"]
    assert logged_out.status_code == 200
    assert "Max-Age=0" in logged_out.headers["set-cookie"]


def test_me_is_protected_and_returns_safe_profile() -> None:
    with client() as test_client:
        response = test_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer access"})
    assert response.status_code == 200
    assert response.json()["email"] == USER.email
    assert "password_hash" not in response.text
