from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.v1.router import api_router
from app.core.config import ConfigurationError, settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import RateLimitMiddleware
# Proxy-header handling ships with uvicorn (starlette has no equivalent module).
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.core.observability_middleware import (
    AccessLogMiddleware,
    MetricsMiddleware,
    RequestContextMiddleware,
)
from app.core.redis import close_redis, init_redis

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup_begin", version=settings.APP_VERSION)

    # Fail fast on invalid production configuration. Under pytest we downgrade
    # to a warning so the existing test suite can run with development defaults
    # (mirrors the rate-limiter's pytest guard in this module).
    try:
        settings.validate()
    except ConfigurationError as exc:
        if _under_pytest():
            logger.warning("startup_config_invalid", detail=str(exc))
        else:
            logger.error("startup_config_invalid", detail=str(exc))
            raise

    await init_redis()
    # Mark startup complete so the /health/startup probe flips to "started".
    from app.core import health as health_module

    health_module.app_state["started"] = True
    logger.info("startup_complete", version=settings.APP_VERSION)
    yield
    await close_redis()
    health_module.app_state["started"] = False
    logger.info("shutdown_complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Trusted reverse proxy. When TRUST_PROXY is enabled (production compose, where
# nginx is the sole public entrypoint and the backend publishes no host port),
# honour X-Forwarded-* so request.client reports the real client IP and
# url_for()/redirects build the public scheme/host. See Settings.TRUST_PROXY for
# the security rationale — never enable this while the backend port is exposed.
if settings.TRUST_PROXY:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Middleware order: first added is OUTERMOST. RequestIDMiddleware stays last so
# it assigns ``request.state.request_id`` *before* the observability middleware
# (Metrics -> AccessLog -> RequestContext) reads it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting runs just inside the CORS layer so unauthenticated clients are
# throttled before they reach any business logic. Health/metrics are exempt.
# It is registered only when enabled (RATE_LIMIT_PER_MINUTE > 0) and skipped
# under pytest so the test suite — which shares one client IP — is never
# throttled. In production compose it is active at the configured budget and
# keys off X-Forwarded-For / X-Real-IP set by nginx.
def _under_pytest() -> bool:
    import os

    return bool(os.environ.get("PYTEST_VERSION") or os.environ.get("PYTEST_CURRENT_TEST"))


if settings.RATE_LIMIT_PER_MINUTE > 0 and not _under_pytest():
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.RATE_LIMIT_PER_MINUTE,
        exempt_paths=("/health", "/metrics", "/health/live", "/health/ready", "/health/startup"),
    )
app.add_middleware(MetricsMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(RequestIDMiddleware)

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")


# --------------------------------------------------------------------------- #
# Observability endpoints (root-namespaced for Prometheus / k8s probes)
# --------------------------------------------------------------------------- #
@app.get("/metrics", tags=["observability"], include_in_schema=settings.METRICS_ENABLED)
async def metrics() -> Response:
    """Prometheus exposition endpoint. Refreshes stateful gauges per scrape."""
    if not settings.METRICS_ENABLED:
        return JSONResponse(status_code=404, content={"detail": "metrics disabled"})
    from app.core import metrics as metrics_module

    try:
        await metrics_module.refresh_metrics()
    except Exception as exc:  # noqa: BLE001 - never fail the scrape on refresh errors
        logger.warning("metrics_refresh_failed", error=str(exc))
    return Response(
        content=metrics_module.render_metrics(),
        media_type=metrics_module.CONTENT_TYPE,
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    # Backward-compatible aggregate endpoint (kept stable for existing probes).
    return {"status": "healthy"}


@app.get("/health/live", tags=["health"])
async def health_live() -> dict:
    """Liveness probe — process is alive."""
    from app.core import health as health_module

    return health_module.liveness()


@app.get("/health/ready", tags=["health"])
async def health_ready() -> JSONResponse:
    """Readiness probe — dependency health aggregate."""
    from app.core import health as health_module

    payload, status_code = await health_module.readiness()
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/health/startup", tags=["health"])
async def health_startup() -> dict:
    """Startup probe — true once the lifespan startup has completed."""
    from app.core import health as health_module

    return health_module.startup()


@app.get("/", tags=["root"])
async def root() -> dict:
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION}


# --------------------------------------------------------------------------- #
# Canonical probe aliases (Phase 4)
#
# Kubernetes / cloud load-balancers commonly expect /liveness and /ready by
# those exact names. They mirror the /health/live and /health/ready probes so
# existing and conventional probe paths both work.
# --------------------------------------------------------------------------- #
@app.get("/liveness", tags=["health"])
async def liveness_alias() -> dict:
    """Liveness probe alias — process is alive."""
    from app.core import health as health_module

    return health_module.liveness()


@app.get("/ready", tags=["health"])
async def ready_alias() -> JSONResponse:
    """Readiness probe alias — dependency health aggregate."""
    from app.core import health as health_module

    payload, status_code = await health_module.readiness()
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/health/db", tags=["health"])
async def health_db() -> JSONResponse:
    """Standalone PostgreSQL dependency check."""
    from app.core import health as health_module

    result = await health_module.check_database()
    status_code = 200 if result["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=result)


@app.get("/health/redis", tags=["health"])
async def health_redis() -> JSONResponse:
    """Standalone Redis dependency check."""
    from app.core import health as health_module

    result = await health_module.check_redis()
    status_code = 200 if result["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=result)


@app.get("/version", tags=["meta"])
async def version() -> dict:
    """Build / version metadata for the running image (Phase 4)."""
    from app.core.build_info import get_build_info

    return get_build_info()
