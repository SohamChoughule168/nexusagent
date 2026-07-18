"""Lightweight in-memory rate limiter (Milestone 7, Phase 6).

A fixed-window per-client-IP limiter built only on the existing FastAPI /
Starlette stack (no external framework). It is intentionally simple and is
designed for the project's **single-instance** deployment model:

* State is held in a process-local dict. It is *not* shared across multiple
  backend replicas — for a horizontally-scaled / multi-host deployment this
  must be replaced with a shared store (e.g. Redis) or enforced at the reverse
  proxy (nginx ``limit_req``).
* The window is 60 seconds; the request budget comes from
  ``Settings.RATE_LIMIT_PER_MINUTE``.
* Health/readiness/metrics endpoints are exempt so probes and scrapes never
  trip the limiter.

The limiter only inspects the request line and trusted proxy headers
(``X-Forwarded-For`` / ``X-Real-IP`` set by nginx) — it never reads the
request body, so it is safe to run in front of file-upload endpoints.

Registration is conditional (see ``app/main.py``): it is skipped when
``RATE_LIMIT_PER_MINUTE <= 0`` or while running under pytest, so the test
suite — which shares a single client IP — is never throttled.
"""
from collections import defaultdict
from time import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Paths that must never be rate-limited (liveness/readiness probes, the
# aggregate health endpoint, and the Prometheus scrape endpoint).
DEFAULT_EXEMPT_PREFIXES = ("/health", "/metrics")


def _client_ip(request: Request) -> str:
    """Best-effort client IP behind the nginx reverse proxy.

    nginx sets ``X-Forwarded-For`` (leftmost = original client) and
    ``X-Real-IP``. We trust those over ``request.client.host`` because the
    backend is only reachable from nginx on the internal bridge network;
    ``request.client.host`` would otherwise always be the proxy's address.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For may be a comma-separated chain; the first entry is
        # the originating client.
        return forwarded.split(",", 1)[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window (per-minute) rate limiter keyed by client IP."""

    def __init__(self, app, limit_per_minute: int = 100, exempt_paths=None) -> None:
        super().__init__(app)
        # `limit_per_minute <= 0` disables the limiter entirely (used in CI).
        self.limit = int(limit_per_minute)
        self.window_seconds = 60.0
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._exempt = frozenset(exempt_paths or ())

    def _is_exempt(self, path: str) -> bool:
        if path in self._exempt:
            return True
        return any(path.startswith(prefix) for prefix in DEFAULT_EXEMPT_PREFIXES)

    def _prune(self, timestamps: list[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

    async def dispatch(self, request: Request, call_next):
        # Disabled (limit <= 0) or an exempt probe/scrape path: pass through.
        if self.limit <= 0 or self._is_exempt(request.url.path):
            return await call_next(request)

        ip = _client_ip(request)
        now = time()
        bucket = self._buckets[ip]
        self._prune(bucket, now)

        if len(bucket) >= self.limit:
            # Seconds until the oldest request in the window ages out.
            retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and retry later."},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)
