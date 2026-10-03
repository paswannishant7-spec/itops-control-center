from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.identity.rate_limit import LoginRateLimiter
from app.modules.identity.security import (
    PasswordPolicyError,
    PasswordService,
    TokenService,
    TokenValidationError,
)

SECRET = "test-secret-at-least-thirty-two-characters-long"


def test_passwords_are_argon2id_hashed_and_verified() -> None:
    service = PasswordService()
    password_hash = service.hash("Correct-Horse-7!")
    assert password_hash.startswith("$argon2id$")
    assert service.verify(password_hash, "Correct-Horse-7!") is True
    assert service.verify(password_hash, "wrong") is False
    assert service.verify(None, "wrong") is False


@pytest.mark.parametrize(
    "password",
    ["short", "alllowercase123!", "ALLUPPERCASE123!", "NoNumbersHere!", "NoSymbolsHere123"],
)
def test_password_policy_rejects_weak_values(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        PasswordService().hash(password)


def test_access_token_round_trip_and_wrong_type_rejection() -> None:
    service = TokenService(Settings(jwt_secret=SECRET))
    user_id, session_id = uuid4(), uuid4()
    token = service.create_access_token(user_id, session_id)
    assert service.decode_access_token(token) == (user_id, session_id)
    with pytest.raises(TokenValidationError):
        service.decode_access_token(token + "tampered")


def test_token_service_requires_nontrivial_secret() -> None:
    with pytest.raises(RuntimeError):
        TokenService(Settings(jwt_secret="too-short"))


def test_refresh_tokens_are_random_and_only_digest_is_stable() -> None:
    first = TokenService.new_refresh_token()
    second = TokenService.new_refresh_token()
    assert first.raw != second.raw
    assert first.digest == TokenService.hash_refresh_token(first.raw)
    assert first.raw not in first.digest


def test_login_rate_limiter_enforces_window() -> None:
    limiter = LoginRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client") is True
    assert limiter.allow("client") is True
    assert limiter.allow("client") is False
    limiter.reset()
    assert limiter.allow("client") is True
