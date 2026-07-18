"""Observability middleware (Milestone 7, Phase 5).

Three small ``BaseHTTPMiddleware`` components, added in this (inner→outer)
order in :mod:`app.main` (with ``RequestIDMiddleware`` outermost so it sets
``request.state.request_id`` *before* these read it):

1. ``MetricsMiddleware``     — HTTP request count, latency, error count, in-flight.
2. ``AccessLogMiddleware``   — one structured access-log line per request.
3. ``RequestContextMiddleware`` — binds ``request_id`` (+ tenant, if known) into
   the structlog context so every log during the request carries correlation.

``RequestIDMiddleware`` (in :mod:`app.core.middleware`) remains the outermost
layer so it establishes ``request.state.request_id`` and echoes ``X-Request-ID``
before these read it.
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    get_access_logger,
    get_logger,
)
from app.core.metrics import (
    HTTP_ERROR_COUNT,
    HTTP_IN_PROGRESS,
    HTTP_REQUEST_COUNT,
    HTTP_REQUEST_LATENCY,
)

logger = get_logger(__name__)
access_logger = get_access_logger()

# Endpoints that should not pollute HTTP metrics / access logs.
_SKIP_METRICS = frozenset(
    {
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


def _endpoint_label(request: Request) -> str:
    """Return a low-cardinality endpoint label for the request.

    Prefers the matched route's templated path (e.g.
    ``/api/v1/conversations/{conversation_id}``) so per-request IDs in the
    raw path do not explode metric cardinality.
    """
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path or "/"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record HTTP request count, latency, and error count."""

    async def dispatch(self, request: Request, call_next):
        if not settings.METRICS_ENABLED or request.url.path in _SKIP_METRICS:
            return await call_next(request)

        method = request.method
        start = time.perf_counter()
        HTTP_IN_PROGRESS.inc()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            HTTP_IN_PROGRESS.dec()
            duration = max(time.perf_counter() - start, 0.0)
            endpoint = _endpoint_label(request)
            HTTP_REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status_code).inc()
            HTTP_REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
            if status_code >= 400:
                HTTP_ERROR_COUNT.labels(
                    method=method, endpoint=endpoint, status=status_code
                ).inc()


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured access-log line per request."""

    async def dispatch(self, request: Request, call_next):
        if not settings.LOG_ACCESS_ENABLED:
            return await call_next(request)

        method = request.method
        path = request.url.path
        start = time.perf_counter()
        request_id = getattr(request.state, "request_id", "unknown")
        try:
            response = await call_next(request)
            status_code = response.status_code
            size = response.headers.get("content-length")
        except Exception:
            status_code = 500
            size = None
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            access_logger.info(
                "request",
                request_id=request_id,
                method=method,
                path=path,
                status=status_code,
                duration_ms=duration_ms,
                bytes=int(size) if size and size.isdigit() else None,
                user_agent=request.headers.get("user-agent"),
            )
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind request-scoped fields into the structlog context for correlation."""

    async def dispatch(self, request: Request, call_next):
        request_id = getattr(request.state, "request_id", None) or request.headers.get(
            "X-Request-ID"
        ) or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        bind_request_context(request_id)
        try:
            return await call_next(request)
        finally:
            clear_request_context()
