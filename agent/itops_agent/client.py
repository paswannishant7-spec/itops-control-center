import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from itops_agent import __version__
from itops_agent.state import CredentialState


class AgentRequestError(RuntimeError):
    def __init__(self, status: int | None, retriable: bool) -> None:
        super().__init__("Agent request failed")
        self.status = status
        self.retriable = retriable


class AgentClient:
    def __init__(self, api_url: str, timeout_seconds: int) -> None:
        self.api_url = api_url
        self.timeout_seconds = timeout_seconds

    def _request(
        self, path: str, payload: dict[str, Any], state: CredentialState | None = None
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "User-Agent": f"itops-agent/{__version__}"}
        if state:
            headers["Authorization"] = f"Agent {state.agent_id}.{state.credential}"
        request = Request(
            f"{self.api_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return dict(json.loads(response.read().decode("utf-8")))
        except HTTPError as exc:
            raise AgentRequestError(exc.code, exc.code >= 500 or exc.code == 429) from None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise AgentRequestError(None, True) from None

    def enroll(self, token: str) -> CredentialState:
        value = self._request(
            "/monitoring/enroll",
            {"enrollment_token": token, "agent_version": __version__},
        )
        return CredentialState(
            agent_id=str(value["agent_id"]),
            device_id=str(value["device_id"]),
            credential=str(value["credential"]),
        )

    def send_heartbeat(self, state: CredentialState, payload: dict[str, Any]) -> None:
        self._request("/monitoring/agent/heartbeat", payload, state)

    def send_metrics(self, state: CredentialState, payload: dict[str, Any]) -> None:
        self._request("/monitoring/agent/metrics", payload, state)
