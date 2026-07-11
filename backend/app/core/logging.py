import logging
import structlog
from structlog.stdlib import LoggerFactory, PositionalArgumentsFormatter
from structlog.processors import TimeStamper, JSONRenderer, UnicodeDecoder
from typing import Any

from app.core.config import settings


def configure_logging():
    """Configure structured logging for the application."""
    # Standard library logging setup
    logging.basicConfig(
        format="%(message)s",
        stream=None,
        level=getattr(logging, settings.LOG_LEVEL.upper()),
    )

    structlog.configure(
        processors=[
            TimeStamper(fmt="iso"),
            UnicodeDecoder(),
            PositionalArgumentsFormatter(),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            JSONRenderer() if settings.LOG_FORMAT == "json" else structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name).bind(app_name=settings.APP_NAME)


class RequestIDMiddleware:
    """Middleware to add request IDs for tracing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            # Generate request ID
            import uuid
            scope["request_id"] = str(uuid.uuid4())[:8]

        await self.app(scope, receive, send)


# Initialize logging on import
configure_logging()
logger = get_logger(__name__)