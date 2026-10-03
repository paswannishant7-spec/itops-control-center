import json
import socket
from collections import namedtuple
from pathlib import Path
from urllib.error import HTTPError

import pytest

from itops_agent import collector
from itops_agent import main as agent_main
from itops_agent.client import AgentClient, AgentRequestError
from itops_agent.config import AgentConfig
from itops_agent.state import CredentialState, load_state, save_state


def test_collector_returns_only_bounded_operational_data(monkeypatch: pytest.MonkeyPatch) -> None:
    address = namedtuple("Address", "family address")
    memory = namedtuple("Memory", "percent used total")(40.0, 400, 1000)
    disk = namedtuple("Disk", "percent used total")(50.0, 500, 1000)
    network = namedtuple("Network", "bytes_sent bytes_recv")(100, 200)
    monkeypatch.setattr(
        collector.psutil,
        "net_if_addrs",
        lambda: {
            "ignored-name": [
                address(socket.AF_INET, "192.0.2.4"),
                address(socket.AF_INET, "127.0.0.1"),
            ]
        },
    )
    monkeypatch.setattr(collector.psutil, "boot_time", lambda: 1_700_000_000.0)
    monkeypatch.setattr(collector.psutil, "virtual_memory", lambda: memory)
    monkeypatch.setattr(collector.psutil, "disk_usage", lambda _: disk)
    monkeypatch.setattr(collector.psutil, "net_io_counters", lambda: network)
    monkeypatch.setattr(collector.psutil, "cpu_percent", lambda interval: 12.5)
    heartbeat = collector.heartbeat()
    metrics = collector.metrics()
    assert heartbeat["ip_addresses"] == ["192.0.2.4"]
    assert set(heartbeat) == {
        "observed_at",
        "available",
        "hostname",
        "operating_system",
        "ip_addresses",
        "boot_time",
        "collection_errors",
    }
    assert metrics["cpu_percent"] == 12.5
    assert "processes" not in metrics and "users" not in metrics


def test_state_round_trip_and_secure_url_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "agent-state.json"
    state = CredentialState("agent-id", "device-id", "unique-secret")
    assert load_state(path) is None
    save_state(path, state)
    assert load_state(path) == state
    path.write_text("not json", encoding="utf-8")
    assert load_state(path) is None
    monkeypatch.setenv("ITOPS_AGENT_API_URL", "http://insecure.example/api/v1")
    with pytest.raises(ValueError):
        AgentConfig.from_environment()
    monkeypatch.setenv("ITOPS_AGENT_API_URL", "https://itops.example/api/v1/")
    monkeypatch.setenv("ITOPS_AGENT_INTERVAL_SECONDS", "30")
    assert AgentConfig.from_environment().api_url == "https://itops.example/api/v1"


def test_client_enrolls_and_authenticates_without_logging_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "agent_id": "agent-id",
                    "device_id": "device-id",
                    "credential": "per-device-secret",
                }
            ).encode()

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr("itops_agent.client.urlopen", urlopen)
    client = AgentClient("https://itops.example/api/v1", 10)
    state = client.enroll("one-time-token")
    client.send_heartbeat(state, {"available": True})
    assert state.credential == "per-device-secret"
    assert requests[1][0].get_header("Authorization") == "Agent agent-id.per-device-secret"

    def rejected(request, timeout):
        raise HTTPError(request.full_url, 503, "unavailable", {}, None)

    monkeypatch.setattr("itops_agent.client.urlopen", rejected)
    with pytest.raises(AgentRequestError) as error:
        client.send_metrics(state, {})
    assert error.value.retriable is True
    assert "per-device-secret" not in str(error.value)


def test_runner_enrolls_retries_with_backoff_and_stops_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[int] = []
    saved: list[CredentialState] = []
    deliveries: list[str] = []

    class StopEvent:
        def is_set(self) -> bool:
            return len(waits) >= 2

        def set(self) -> None:
            waits.append(0)

        def wait(self, seconds: int) -> bool:
            waits.append(seconds)
            return self.is_set()

    class Client:
        def enroll(self, token: str) -> CredentialState:
            assert token == "single-use-token"
            return CredentialState("stable-agent", "device", "unique-credential")

        def send_heartbeat(self, state: CredentialState, payload: object) -> None:
            deliveries.append("heartbeat")
            if deliveries.count("heartbeat") == 1:
                raise AgentRequestError(503, True)

        def send_metrics(self, state: CredentialState, payload: object) -> None:
            deliveries.append("metrics")

    monkeypatch.setattr(agent_main.threading, "Event", StopEvent)
    monkeypatch.setattr(agent_main.signal, "signal", lambda *_: None)
    monkeypatch.setattr(agent_main, "AgentClient", lambda *_: Client())
    monkeypatch.setattr(agent_main, "load_state", lambda _: None)
    monkeypatch.setattr(agent_main, "save_state", lambda _, state: saved.append(state))
    monkeypatch.setattr(agent_main, "heartbeat", lambda: {})
    monkeypatch.setattr(agent_main, "metrics", lambda: {})
    agent_main.run(
        AgentConfig(
            api_url="https://itops.example/api/v1",
            state_path=tmp_path / "state.json",
            enrollment_token="single-use-token",
            interval_seconds=20,
            request_timeout_seconds=5,
        )
    )
    assert saved[0].agent_id == "stable-agent"
    assert waits == [40, 20]
    assert deliveries == ["heartbeat", "heartbeat", "metrics"]
