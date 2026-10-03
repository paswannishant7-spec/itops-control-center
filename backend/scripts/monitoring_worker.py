"""Heartbeat reconciliation and bounded telemetry-retention worker."""

import asyncio
import signal
from contextlib import suppress

import structlog

from app.core.config import get_settings
from app.db import models as _models  # noqa: F401 - register complete ORM metadata
from app.db.session import get_session_factory
from app.modules.monitoring.service import MonitoringService

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
                offline, metrics, heartbeats = await MonitoringService(
                    session, settings
                ).reconcile()
            log.info(
                "monitoring_worker_cycle",
                agents_marked_offline=offline,
                metrics_pruned=metrics,
                heartbeats_pruned=heartbeats,
            )
        except Exception:
            log.exception("monitoring_worker_cycle_failed")
        try:
            await asyncio.wait_for(
                stopping.wait(), timeout=settings.monitoring_worker_interval_seconds
            )
        except TimeoutError:
            continue


if __name__ == "__main__":
    asyncio.run(run())
