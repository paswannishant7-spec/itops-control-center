import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CredentialState:
    agent_id: str
    device_id: str
    credential: str


def load_state(path: Path) -> CredentialState | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return CredentialState(
            agent_id=str(value["agent_id"]),
            device_id=str(value["device_id"]),
            credential=str(value["credential"]),
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_state(path: Path, state: CredentialState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(asdict(state)), encoding="utf-8")
    with __import__("contextlib").suppress(OSError):
        os.chmod(temporary, 0o600)
    temporary.replace(path)
