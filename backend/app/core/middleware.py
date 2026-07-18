import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a correlation ID to every request and echo it in the response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline security headers to every response.

    This is defense-in-depth for when the backend is reached directly (e.g. the
    local compose publishes port 8000). In the production deployment nginx is
    the edge and owns the same header set (see nginx/nginx.conf), which strips
    these upstream copies to avoid duplicate headers. The policies are kept in
    sync deliberately.
    """

    # Same CSP as nginx so direct-to-backend responses are equally constrained.
    CSP = (
        "default-src 'self'; img-src 'self' data:; font-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' "
        "'unsafe-eval'; connect-src 'self'; frame-ancestors 'self'; "
        "base-uri 'self'; form-action 'self'"
    )

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = self.CSP
        return response
