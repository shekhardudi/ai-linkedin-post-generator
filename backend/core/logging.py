"""Structured logging — JSON in production, pretty console in dev."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", pretty: bool = False) -> None:
    """Configure structlog + stdlib logging once at process start."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if pretty:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
