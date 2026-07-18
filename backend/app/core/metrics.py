"""Prometheus metrics for NexusAgent (Milestone 7, Phase 5).

Defines every application/infrastructure metric and a lightweight collector that
refreshes the database- and Redis-backed gauges when ``/metrics`` is scraped.

All metrics are namespaced (``nexusagent_*``) via ``Settings.PROMETHEUS_NAMESPACE``
so they are unambiguous inside a shared Prometheus instance.

Event-driven metrics (HTTP request count, latency, errors) are updated by the
observability middleware on each request. Stateful metrics (active conversations,
active agents, token usage, DB pool, Redis/cache) are refreshed by
:func:`refresh_metrics`, called once per scrape of ``/metrics``.
"""
from typing import Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

NS = settings.PROMETHEUS_NAMESPACE

# --------------------------------------------------------------------------- #
# HTTP (event-driven — updated by the metrics middleware)
# --------------------------------------------------------------------------- #
HTTP_REQUEST_COUNT = Counter(
    f"{NS}_http_requests_total",
    "Total HTTP requests handled, by method, endpoint and status.",
    ["method", "endpoint", "status"],
)
HTTP_REQUEST_LATENCY = Histogram(
    f"{NS}_http_request_duration_seconds",
    "HTTP request latency in seconds, by method and endpoint.",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
HTTP_ERROR_COUNT = Counter(
    f"{NS}_http_errors_total",
    "Total HTTP errors (4xx/5xx), by method, endpoint and status.",
    ["method", "endpoint", "status"],
)
HTTP_IN_PROGRESS = Gauge(
    f"{NS}_http_requests_in_progress",
    "HTTP requests currently being processed.",
)

# --------------------------------------------------------------------------- #
# Dependency availability (refreshed by the collector; used by alerting)
# --------------------------------------------------------------------------- #
DB_UP = Gauge(f"{NS}_db_up", "PostgreSQL reachable (1) or not (0).")
REDIS_UP = Gauge(f"{NS}_redis_up", "Redis reachable (1) or not (0).")
STORAGE_UP = Gauge(f"{NS}_storage_up", "Upload storage directory writable (1) or not (0).")
LLM_UP = Gauge(f"{NS}_llm_up", "LLM provider reachable (1) or not (0).")
SCRAPE_ERRORS = Counter(
    f"{NS}_scrape_errors_total",
    "Errors encountered while refreshing stateful metrics.",
)

# --------------------------------------------------------------------------- #
# Application state (refreshed from the database)
# --------------------------------------------------------------------------- #
ACTIVE_CONVERSATIONS = Gauge(
    f"{NS}_active_conversations",
    "Number of conversations in the 'active' state.",
)
ACTIVE_AGENTS = Gauge(
    f"{NS}_active_agents",
    "Number of agents in the 'active' state.",
)
TOTAL_TOKENS = Gauge(
    f"{NS}_total_tokens",
    "Cumulative LLM tokens consumed across all usage events.",
)
TOTAL_COST_USD = Gauge(
    f"{NS}_total_cost_usd",
    "Cumulative LLM cost in USD across all usage events.",
)

# --------------------------------------------------------------------------- #
# Queue length (if a broker/queue is configured)
# --------------------------------------------------------------------------- #
QUEUE_LENGTH = Gauge(
    f"{NS}_queue_length",
    "Length of the background task queue (Celery/Redis), if available.",
)

# --------------------------------------------------------------------------- #
# Database connection pool
# --------------------------------------------------------------------------- #
DB_POOL_SIZE = Gauge(f"{NS}_db_connection_pool_size", "Configured DB connection pool size.")
DB_POOL_IN_USE = Gauge(f"{NS}_db_connections_in_use", "DB connections currently checked out.")
DB_POOL_IDLE = Gauge(f"{NS}_db_connections_idle", "Idle DB connections in the pool.")
DB_POOL_OVERFLOW = Gauge(f"{NS}_db_connections_overflow", "DB connections overflowing the pool.")

# --------------------------------------------------------------------------- #
# Redis / cache statistics
# --------------------------------------------------------------------------- #
REDIS_MEMORY_USED_BYTES = Gauge(f"{NS}_redis_memory_used_bytes", "Redis resident memory usage in bytes.")
REDIS_CONNECTED_CLIENTS = Gauge(f"{NS}_redis_connected_clients", "Number of connected Redis clients.")
REDIS_KEYSPACE_HITS = Gauge(f"{NS}_redis_keyspace_hits", "Cumulative Redis keyspace hits.")
REDIS_KEYSPACE_MISSES = Gauge(f"{NS}_redis_keyspace_misses", "Cumulative Redis keyspace misses.")
REDIS_EXPIRED_KEYS = Gauge(f"{NS}_redis_expired_keys", "Cumulative Redis expired keys.")
REDIS_EVICTED_KEYS = Gauge(f"{NS}_redis_evicted_keys", "Cumulative Redis evicted keys.")
REDIS_UPTIME_SECONDS = Gauge(f"{NS}_redis_uptime_seconds", "Redis uptime in seconds.")


# Re-export so the endpoint handler has a single import surface.
CONTENT_TYPE = CONTENT_TYPE_LATEST


def _safe(label: str) -> str:
    """Normalise a route/path label so it is a valid Prometheus label value."""
    return (label or "unknown").replace(" ", "_") or "unknown"


async def refresh_metrics() -> None:
    """Refresh DB-/Redis-backed gauges. Called once per ``/metrics`` scrape.

    Never raises: individual subsystems are isolated so a failure in one (e.g.
    Redis down) does not break the entire scrape or zero out unrelated metrics.
    """
    await _refresh_database()
    await _refresh_redis()
    await _refresh_storage()
    await _refresh_llm()


async def _refresh_database() -> None:
    """Refresh DB pool stats and application-state gauges from PostgreSQL."""
    from sqlalchemy import func, select, text

    from app.core.database import get_engine
    from app.core.database import get_sessionmaker
    from app.models.all_models import Agent, Conversation, UsageEvent

    try:
        # Connection-pool statistics (only meaningful for a pooling engine;
        # NullPool, used in DEBUG mode, has no pool to report).
        engine = get_engine()
        pool = engine.pool
        if hasattr(pool, "size"):
            DB_POOL_SIZE.set(pool.size())
            DB_POOL_IN_USE.set(pool.checkedout())
            DB_POOL_IDLE.set(pool.checkedin())
            DB_POOL_OVERFLOW.set(int(getattr(pool, "overflow", 0) or 0))

        session = get_sessionmaker()()
        try:
            active_conv = session.scalar(
                select(func.count()).select_from(Conversation).where(Conversation.status == "active")
            )
            active_agents = session.scalar(
                select(func.count()).select_from(Agent).where(Agent.status == "active")
            )
            token_row = session.execute(
                select(
                    func.coalesce(func.sum(UsageEvent.total_tokens), 0),
                    func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
                )
            ).first()
            ACTIVE_CONVERSATIONS.set(int(active_conv or 0))
            ACTIVE_AGENTS.set(int(active_agents or 0))
            TOTAL_TOKENS.set(int(token_row[0] or 0))
            TOTAL_COST_USD.set(float(token_row[1] or 0.0))
        finally:
            session.close()
        DB_UP.set(1)
    except Exception as exc:  # noqa: BLE001 - isolation per subsystem
        logger.warning("metrics_db_refresh_failed", error=str(exc))
        SCRAPE_ERRORS.inc()
        DB_UP.set(0)


async def _refresh_redis() -> None:
    """Refresh Redis connectivity and cache statistics from ``INFO``."""
    from app.core.redis import get_redis

    try:
        import redis.asyncio as aioredis
    except ImportError:  # redis client not installed
        REDIS_UP.set(0)
        return

    client = get_redis()
    own_client = False
    if client is None:
        # No cached client (e.g. lifespan did not run). Probe once, then close.
        try:
            client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
            )
            own_client = True
        except Exception:  # noqa: BLE001
            client = None

    if client is None:
        REDIS_UP.set(0)
        return
    try:
        info = await client.info("all")
        REDIS_UP.set(1)
        stats = info.get("stats", {})
        REDIS_KEYSPACE_HITS.set(float(stats.get("keyspace_hits", 0) or 0))
        REDIS_KEYSPACE_MISSES.set(float(stats.get("keyspace_misses", 0) or 0))
        REDIS_EXPIRED_KEYS.set(float(stats.get("expired_keys", 0) or 0))
        REDIS_EVICTED_KEYS.set(float(stats.get("evicted_keys", 0) or 0))
        REDIS_MEMORY_USED_BYTES.set(float(info.get("memory", {}).get("used_memory", 0) or 0))
        REDIS_CONNECTED_CLIENTS.set(float(info.get("clients", {}).get("connected_clients", 0) or 0))
        REDIS_UPTIME_SECONDS.set(float(info.get("uptime_in_seconds", 0) or 0))

        # Queue length: default Celery queue ("celery") on the configured broker.
        try:
            broker = settings.CELERY_BROKER_URL
            if broker and broker.startswith("redis"):
                qlen = await client.llen("celery")
                QUEUE_LENGTH.set(int(qlen or 0))
            else:
                QUEUE_LENGTH.set(0)
        except Exception:  # noqa: BLE001
            QUEUE_LENGTH.set(0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics_redis_refresh_failed", error=str(exc))
        SCRAPE_ERRORS.inc()
        REDIS_UP.set(0)
    finally:
        if own_client and client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass


async def _refresh_storage() -> None:
    """Verify the upload storage directory is present and writable."""
    import os
    import tempfile

    path = settings.UPLOAD_STORAGE_DIR
    try:
        os.makedirs(path, exist_ok=True)
        # Probe write/delete of a tiny temp file.
        with tempfile.NamedTemporaryFile(dir=path, prefix=".health-", delete=True):
            pass
        STORAGE_UP.set(1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics_storage_refresh_failed", error=str(exc))
        SCRAPE_ERRORS.inc()
        STORAGE_UP.set(0)


async def _refresh_llm() -> None:
    """Non-destructive LLM connectivity probe (network reachability only).

    Does not generate tokens or spend credits — it only performs a lightweight
    HTTP ``GET`` against the configured provider base URL to confirm routing /
    DNS / TLS reachability. With no provider key configured the check is skipped
    (left at previous value, default 0) and surfaced by alerting as 'unknown'.
    """
    if not settings.OPENROUTER_API_KEY:
        return
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            # HEAD is non-destructive; falls back to GET on method-not-allowed.
            resp = await client.head(settings.OPENROUTER_BASE_URL)
            auth_codes = (401, 403, 405)
            if resp.status_code >= 400 and resp.status_code not in auth_codes:
                LLM_UP.set(0)
                return
            LLM_UP.set(1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics_llm_refresh_failed", error=str(exc))
        LLM_UP.set(0)


def render_metrics() -> bytes:
    """Generate the current Prometheus exposition text (default registry)."""
    return generate_latest()
