from collections import defaultdict, deque
from hashlib import sha256
from math import ceil
from time import monotonic


class LoginRateLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        attempts = self._attempts[key]
        while attempts and attempts[0] <= now - self.window_seconds:
            attempts.popleft()
        if len(attempts) >= self.limit:
            return False
        attempts.append(now)
        return True

    def retry_after(self, key: str) -> int:
        attempts = self._attempts.get(key)
        if not attempts:
            return 0
        return max(0, ceil(attempts[0] + self.window_seconds - monotonic()))

    def reset(self) -> None:
        self._attempts.clear()


login_rate_limiter = LoginRateLimiter()
refresh_rate_limiter = LoginRateLimiter(limit=20)


def private_rate_limit_key(ip_address: str, credential: str) -> str:
    digest = sha256(credential.strip().lower().encode()).hexdigest()
    return f"{ip_address}:{digest}"
