"""Idempotent database-polling SLA worker."""

import asyncio
import signal
from contextlib import suppress
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.db import models as _models  # noqa: F401 - register complete ORM metadata
from app.db.session import get_session_factory
from app.modules.sla.service import SlaService

log = structlog.get_logger()


async def run() -> None:
    settings = get_settings()
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for value in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(value, stopping.set)
    while not stopping.is_set():
        try:
            async with get_session_factory()() as session:
                inspected, changed = await SlaService(session).run_once(
                    limit=settings.sla_worker_batch_size
                )
            Path("/tmp/itops-sla-worker.heartbeat").touch()
            log.info("sla_worker_cycle", inspected=inspected, changed=changed)
        except Exception:
            log.exception("sla_worker_cycle_failed")
        try:
            await asyncio.wait_for(stopping.wait(), timeout=settings.sla_worker_interval_seconds)
        except TimeoutError:
            continue


if __name__ == "__main__":
    asyncio.run(run())
