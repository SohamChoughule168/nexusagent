from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging import bind_request_context, clear_request_context, get_logger

logger = get_logger(__name__)


class NexusAgentError(Exception):
    """Base class for application-specific errors."""

    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, message: str | None = None):
        self.message = message or self.detail
        super().__init__(self.message)


class ConfigurationError(NexusAgentError):
    status_code = 500
    detail = "Configuration error"


class ResourceNotFoundError(NexusAgentError):
    status_code = 404
    detail = "Resource not found"


class BusinessError(NexusAgentError):
    status_code = 400
    detail = "Business error"


def register_exception_handlers(app) -> None:
    """Register centralized exception handlers on the FastAPI app."""

    def _request_id(request: Request) -> str:
        return getattr(request.state, "request_id", "unknown")

    @app.exception_handler(NexusAgentError)
    async def handle_nexus_error(request: Request, exc: NexusAgentError):
        # Bind the request_id into the structlog context so the error line
        # carries the same correlation id as the access log for that request.
        bind_request_context(_request_id(request))
        logger.error(
            "nexus_error",
            error=str(exc),
            exc_type=type(exc).__name__,
            path=request.url.path,
            request_id=_request_id(request),
        )
        clear_request_context()
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "type": type(exc).__name__},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        bind_request_context(_request_id(request))
        logger.error(
            "unexpected_error",
            error=str(exc),
            exc_type=type(exc).__name__,
            path=request.url.path,
            request_id=_request_id(request),
        )
        clear_request_context()
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )
