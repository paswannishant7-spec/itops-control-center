import logging
import signal
import threading

from itops_agent.client import AgentClient, AgentRequestError
from itops_agent.collector import heartbeat, metrics
from itops_agent.config import AgentConfig
from itops_agent.state import CredentialState, load_state, save_state

log = logging.getLogger("itops_agent")


def run(config: AgentConfig) -> None:
    stopping = threading.Event()
    for value in (signal.SIGINT, signal.SIGTERM):
        signal.signal(value, lambda *_: stopping.set())
    client = AgentClient(config.api_url, config.request_timeout_seconds)
    state: CredentialState | None = load_state(config.state_path)
    if state is None:
        if not config.enrollment_token:
            raise RuntimeError("No credential state or enrollment token is configured")
        state = client.enroll(config.enrollment_token)
        save_state(config.state_path, state)
        log.info("Agent enrollment completed for device %s", state.device_id)
    backoff = config.interval_seconds
    while not stopping.is_set():
        try:
            client.send_heartbeat(state, heartbeat())
            client.send_metrics(state, metrics())
            backoff = config.interval_seconds
        except AgentRequestError as exc:
            log.warning("Monitoring delivery failed (status=%s)", exc.status)
            if not exc.retriable:
                raise
            backoff = min(max(backoff * 2, 10), 300)
        stopping.wait(backoff)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(AgentConfig.from_environment())


if __name__ == "__main__":
    main()
