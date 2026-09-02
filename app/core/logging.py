import logging
import sys

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure structured logging once, at process startup.

    JSON output in non-local environments (log aggregator friendly), a readable
    console renderer locally. Called from app.main on startup and from the
    Celery worker entrypoint.
    """
    settings = get_settings()
    is_local = settings.app_env == "local"

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.debug else logging.INFO,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [structlog.dev.ConsoleRenderer() if is_local else structlog.processors.JSONRenderer()],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
