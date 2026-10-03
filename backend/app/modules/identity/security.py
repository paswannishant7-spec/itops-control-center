from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings


class PasswordPolicyError(ValueError):
    pass


class TokenValidationError(ValueError):
    pass


class PasswordService:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash("dummy-password-never-accepted")

    def validate(self, password: str) -> None:
        if not 12 <= len(password) <= 128:
            raise PasswordPolicyError("Password must contain between 12 and 128 characters")
        requirements = (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
        if not all(requirements):
            raise PasswordPolicyError(
                "Password must include upper, lower, number, and symbol characters"
            )

    def hash(self, password: str) -> str:
        self.validate(password)
        return self._hasher.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        candidate = password_hash or self._dummy_hash
        try:
            valid = self._hasher.verify(candidate, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
        return bool(valid and password_hash is not None)


@dataclass(frozen=True)
class RefreshToken:
    raw: str
    digest: str


class TokenService:
    def __init__(self, settings: Settings) -> None:
        if settings.jwt_secret is None or len(settings.jwt_secret.get_secret_value()) < 32:
            raise RuntimeError("ITOPS_JWT_SECRET must contain at least 32 characters")
        self.settings = settings
        self._secret = settings.jwt_secret.get_secret_value()

    def create_access_token(self, user_id: UUID, session_id: UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid4()),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=self.settings.access_token_minutes),
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def decode_access_token(self, token: str) -> tuple[UUID, UUID]:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
                options={"require": ["exp", "iat", "sub", "sid", "type"]},
            )
            if payload["type"] != "access":
                raise TokenValidationError("Invalid token type")
            return UUID(payload["sub"]), UUID(payload["sid"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise TokenValidationError("Invalid access token") from exc

    @staticmethod
    def new_refresh_token() -> RefreshToken:
        raw = token_urlsafe(48)
        return RefreshToken(raw=raw, digest=TokenService.hash_refresh_token(raw))

    @staticmethod
    def hash_refresh_token(raw: str) -> str:
        return sha256(raw.encode("utf-8")).hexdigest()
