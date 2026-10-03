import platform
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil


def iso_timestamp(value: float | None = None) -> str:
    return (
        datetime.fromtimestamp(value, UTC).isoformat() if value else datetime.now(UTC).isoformat()
    )


def heartbeat() -> dict[str, Any]:
    errors: list[str] = []
    addresses: list[str] = []
    try:
        for records in psutil.net_if_addrs().values():
            for record in records:
                if record.family in {socket.AF_INET, socket.AF_INET6}:
                    address = record.address.split("%", 1)[0]
                    if not address.startswith(("127.", "::1")):
                        addresses.append(address)
    except (OSError, RuntimeError):
        errors.append("ip_collection_failed")
    try:
        boot_time = iso_timestamp(psutil.boot_time())
    except (OSError, RuntimeError):
        boot_time = iso_timestamp()
        errors.append("boot_time_collection_failed")
    return {
        "observed_at": iso_timestamp(),
        "available": True,
        "hostname": socket.gethostname()[:255],
        "operating_system": f"{platform.system()} {platform.release()}"[:160],
        "ip_addresses": list(dict.fromkeys(addresses))[:16],
        "boot_time": boot_time,
        "collection_errors": errors,
    }


def metrics() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    root = Path.home().anchor or "/"
    disk = psutil.disk_usage(root)
    network = psutil.net_io_counters()
    return {
        "sampled_at": iso_timestamp(),
        "cpu_percent": psutil.cpu_percent(interval=0.25),
        "memory_percent": memory.percent,
        "memory_used_bytes": memory.used,
        "memory_total_bytes": memory.total,
        "disk_percent": disk.percent,
        "disk_used_bytes": disk.used,
        "disk_total_bytes": disk.total,
        "network_bytes_sent": network.bytes_sent,
        "network_bytes_received": network.bytes_recv,
    }
