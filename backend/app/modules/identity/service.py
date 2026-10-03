from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import Settings
from app.modules.identity.models import RefreshSession, User, UserStatus
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.security import PasswordService, TokenService


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class AuthResult:
    access_token: str
    refresh_token: str
    access_expires_in: int
    user: User


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_expired(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= now


class AuthService:
    def __init__(self, repository: IdentityRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self.passwords = PasswordService()
        self.tokens = TokenService(settings)

    async def login(
        self, email: str, password: str, user_agent: str | None, ip_address: str | None
    ) -> AuthResult:
        user = await self.repository.user_by_email(email.lower())
        if not self.passwords.verify(user.password_hash if user else None, password):
            raise AuthenticationError("Invalid email or password")
        if user is None or user.status != UserStatus.ACTIVE:
            raise AuthenticationError("Invalid email or password")

        now = utc_now()
        refresh_token = self.tokens.new_refresh_token()
        session = RefreshSession(
            user_id=user.id,
            family_id=uuid4(),
            token_hash=refresh_token.digest,
            expires_at=now + timedelta(days=self.settings.refresh_token_days),
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address,
        )
        self.repository.add_refresh(session)
        user.last_login_at = now
        await self.repository.flush()
        await self.repository.commit()
        return self._result(user, session.id, refresh_token.raw)

    async def refresh(
        self, raw_token: str, user_agent: str | None, ip_address: str | None
    ) -> AuthResult:
        now = utc_now()
        current = await self.repository.refresh_by_hash(
            self.tokens.hash_refresh_token(raw_token), for_update=True
        )
        if current is None:
            raise AuthenticationError("Invalid session")
        if current.revoked_at is not None:
            await self.repository.revoke_family(current.family_id, now)
            await self.repository.commit()
            raise AuthenticationError("Invalid session")
        if is_expired(current.expires_at, now):
            current.revoked_at = now
            await self.repository.commit()
            raise AuthenticationError("Session expired")

        user = await self.repository.user_by_id(current.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            await self.repository.revoke_family(current.family_id, now)
            await self.repository.commit()
            raise AuthenticationError("Invalid session")

        token = self.tokens.new_refresh_token()
        replacement = RefreshSession(
            user_id=user.id,
            family_id=current.family_id,
            token_hash=token.digest,
            expires_at=now + timedelta(days=self.settings.refresh_token_days),
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address,
        )
        self.repository.add_refresh(replacement)
        await self.repository.flush()
        current.revoked_at = now
        current.replaced_by_id = replacement.id
        await self.repository.commit()
        return self._result(user, replacement.id, token.raw)

    async def logout(self, raw_token: str | None) -> None:
        if raw_token:
            current = await self.repository.refresh_by_hash(
                self.tokens.hash_refresh_token(raw_token), for_update=True
            )
            if current is not None and current.revoked_at is None:
                current.revoked_at = utc_now()
                await self.repository.commit()

    def _result(self, user: User, session_id: UUID, refresh_token: str) -> AuthResult:
        return AuthResult(
            access_token=self.tokens.create_access_token(user.id, session_id),
            refresh_token=refresh_token,
            access_expires_in=self.settings.access_token_minutes * 60,
            user=user,
        )
