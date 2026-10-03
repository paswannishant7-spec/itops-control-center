from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.modules.identity.models import RefreshSession, User, UserStatus
from app.modules.identity.security import PasswordService, TokenService
from app.modules.identity.service import AuthenticationError, AuthService

SECRET = "test-secret-at-least-thirty-two-characters-long"
PASSWORD = "Correct-Horse-7!"


class FakeRepository:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.refreshes: dict[str, RefreshSession] = {}
        self.commits = 0

    async def user_by_email(self, email: str) -> User | None:
        return self.user if self.user and self.user.email == email else None

    async def user_by_id(self, user_id: UUID) -> User | None:
        return self.user if self.user and self.user.id == user_id else None

    async def refresh_by_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshSession | None:
        return self.refreshes.get(token_hash)

    def add_refresh(self, refresh: RefreshSession) -> None:
        self.refreshes[refresh.token_hash] = refresh

    async def revoke_family(self, family_id: UUID, revoked_at: datetime) -> None:
        for refresh in self.refreshes.values():
            if refresh.family_id == family_id and refresh.revoked_at is None:
                refresh.revoked_at = revoked_at

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        for refresh in self.refreshes.values():
            if refresh.id is None:
                refresh.id = uuid4()


def make_user(status: UserStatus = UserStatus.ACTIVE) -> User:
    return User(
        id=uuid4(),
        email="operator@example.com",
        display_name="Operator",
        password_hash=PasswordService().hash(PASSWORD),
        status=status,
        password_changed_at=datetime.now(UTC),
    )


def make_service(repository: FakeRepository) -> AuthService:
    return AuthService(repository, Settings(jwt_secret=SECRET))  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_login_and_refresh_rotate_session() -> None:
    repository = FakeRepository(make_user())
    service = make_service(repository)
    login = await service.login("operator@example.com", PASSWORD, "browser", "127.0.0.1")
    original_digest = TokenService.hash_refresh_token(login.refresh_token)
    original = repository.refreshes[original_digest]
    refreshed = await service.refresh(login.refresh_token, "browser", "127.0.0.1")
    assert refreshed.refresh_token != login.refresh_token
    assert original.revoked_at is not None
    assert original.replaced_by_id is not None


@pytest.mark.anyio
async def test_reusing_rotated_token_revokes_family() -> None:
    repository = FakeRepository(make_user())
    service = make_service(repository)
    login = await service.login("operator@example.com", PASSWORD, None, None)
    await service.refresh(login.refresh_token, None, None)
    with pytest.raises(AuthenticationError):
        await service.refresh(login.refresh_token, None, None)
    assert all(item.revoked_at is not None for item in repository.refreshes.values())


@pytest.mark.anyio
async def test_login_is_generic_for_missing_wrong_and_disabled_users() -> None:
    for repository, password in (
        (FakeRepository(None), PASSWORD),
        (FakeRepository(make_user()), "wrong"),
        (FakeRepository(make_user(UserStatus.DISABLED)), PASSWORD),
    ):
        with pytest.raises(AuthenticationError, match="Invalid email or password"):
            await make_service(repository).login("operator@example.com", password, None, None)


@pytest.mark.anyio
async def test_expired_refresh_is_revoked() -> None:
    repository = FakeRepository(make_user())
    service = make_service(repository)
    token = TokenService.new_refresh_token()
    refresh = RefreshSession(
        id=uuid4(),
        user_id=repository.user.id,
        family_id=uuid4(),
        token_hash=token.digest,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )  # type: ignore[union-attr]
    repository.add_refresh(refresh)
    with pytest.raises(AuthenticationError, match="Session expired"):
        await service.refresh(token.raw, None, None)
    assert refresh.revoked_at is not None


@pytest.mark.anyio
async def test_logout_revokes_known_token_and_ignores_missing_token() -> None:
    repository = FakeRepository(make_user())
    service = make_service(repository)
    login = await service.login("operator@example.com", PASSWORD, None, None)
    await service.logout(login.refresh_token)
    assert (
        repository.refreshes[TokenService.hash_refresh_token(login.refresh_token)].revoked_at
        is not None
    )
    await service.logout(None)
