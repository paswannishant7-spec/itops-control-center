from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe


def new_secret() -> str:
    return token_urlsafe(48)


def secret_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def secret_matches(value: str, expected_hash: str) -> bool:
    return compare_digest(secret_hash(value), expected_hash)
