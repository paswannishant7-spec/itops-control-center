import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    api_url: str
    state_path: Path
    enrollment_token: str | None
    interval_seconds: int
    request_timeout_seconds: int

    @classmethod
    def from_environment(cls) -> "AgentConfig":
        api_url = os.getenv("ITOPS_AGENT_API_URL", "http://localhost:8000/api/v1").rstrip("/")
        state_path = Path(
            os.getenv("ITOPS_AGENT_STATE_PATH", str(Path.home() / ".itops-agent.json"))
        )
        interval = int(os.getenv("ITOPS_AGENT_INTERVAL_SECONDS", "60"))
        timeout = int(os.getenv("ITOPS_AGENT_REQUEST_TIMEOUT_SECONDS", "10"))
        if not api_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("Agent API URL must use HTTPS outside local development")
        if not 10 <= interval <= 3600 or not 1 <= timeout <= 120:
            raise ValueError("Agent interval or timeout is outside the supported range")
        return cls(
            api_url=api_url,
            state_path=state_path,
            enrollment_token=os.getenv("ITOPS_AGENT_ENROLLMENT_TOKEN") or None,
            interval_seconds=interval,
            request_timeout_seconds=timeout,
        )
