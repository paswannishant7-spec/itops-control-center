import logging

import structlog


def configure_logging(level: str, json_logs: bool) -> None:
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
    )
