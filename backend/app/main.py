from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
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
