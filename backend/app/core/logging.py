import logging
import structlog
from logging.handlers import RotatingFileHandler
from structlog.stdlib import LoggerFactory, PositionalArgumentsFormatter
from structlog.processors import TimeStamper, JSONRenderer, UnicodeDecoder
from structlog.contextvars import bind_contextvars, clear_contextvars
from typing import Any, Optional

from app.core.config import settings

# Guard so repeated (re)imports / explicit calls to configure_logging() never
# stack duplicate handlers onto the root logger.
_configured = False


def configure_logging() -> None:
    """Configure structured logging for the application.

    Behaviour:
      * Application logs are emitted as JSON (configurable via ``LOG_FORMAT``)
        to stdout by default — the container-friendly convention.
      * When ``LOG_FILE`` is set, a size-capped, rotating ``RotatingFileHandler``
        is attached to the ``app`` logger so application logs are also persisted
        to disk with automatic rotation (see ``LOG_MAX_BYTES`` / ``LOG_BACKUP_COUNT``).
      * Access logs (one structured line per HTTP request) go to a dedicated
        ``app.access`` logger. When ``ACCESS_LOG_FILE`` is set they *additionally*
        write to their own rotating file, keeping access records separate from
        application logs on disk.
    """
    global _configured
    if _configured:
        return

    # Standard library logging setup (structlog's stdlib LoggerFactory routes
    # through this). ConsoleRenderer/JSONRenderer are applied by structlog.
    logging.basicConfig(
        format="%(message)s",
        stream=None,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )

    # Apply optional on-disk rotation for application logs.
    if settings.LOG_FILE:
        _attach_rotating_file(
            logging.getLogger("app"),
            settings.LOG_FILE,
            settings.LOG_MAX_BYTES,
            settings.LOG_BACKUP_COUNT,
        )
    # Apply optional on-disk rotation for the access log (separate file).
    if settings.ACCESS_LOG_FILE:
        _attach_rotating_file(
            logging.getLogger("app.access"),
            settings.ACCESS_LOG_FILE,
            settings.LOG_MAX_BYTES,
            settings.LOG_BACKUP_COUNT,
        )

    structlog.configure(
        processors=[
            TimeStamper(fmt="iso"),
            UnicodeDecoder(),
            PositionalArgumentsFormatter(),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Merge any request-scoped contextvars (e.g. request_id) into the event.
            structlog.contextvars.merge_contextvars,
            JSONRenderer() if settings.LOG_FORMAT == "json" else structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _configured = True


def _attach_rotating_file(logger: logging.Logger, path: str, max_bytes: int, backup_count: int) -> None:
    """Attach a size-capped rotating file handler to a logger (idempotent)."""
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", None) == _norm(path):
            return
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    # Do not propagate to root (avoids double emission to stdout for the file logger).
    logger.propagate = False


def _norm(path: str) -> str:
    import os

    return os.path.abspath(os.path.normpath(path))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured application logger bound with the app name."""
    return structlog.get_logger(name).bind(app_name=settings.APP_NAME)


def get_access_logger() -> structlog.stdlib.BoundLogger:
    """Get the dedicated structured access logger (one line per HTTP request)."""
    return structlog.get_logger("app.access").bind(app_name=settings.APP_NAME, log_type="access")


def bind_request_context(request_id: str, **kwargs: Any) -> None:
    """Bind request-scoped fields (e.g. request_id) into the structlog context.

    Every subsequent log within the same context (async task) carries these
    fields automatically, giving correlation across the whole request lifetime.
    """
    bind_contextvars(request_id=request_id, **kwargs)


def clear_request_context() -> None:
    """Clear request-scoped contextvars at the end of a request."""
    clear_contextvars()


class RequestIDMiddleware:
    """Middleware to add request IDs for tracing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            import uuid

            scope["request_id"] = str(uuid.uuid4())[:8]

        await self.app(scope, receive, send)


# Initialize logging on import.
configure_logging()
logger = get_logger(__name__)
