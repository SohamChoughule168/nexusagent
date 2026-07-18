"""Health probes (Milestone 7, Phase 5).

Implements liveness, readiness and startup endpoints plus the individual
dependency checks (PostgreSQL, Redis, storage, LLM provider).

* **Liveness** — the process is up; safe to always return 200.
* **Readiness** — can the process accept traffic *now*? DB and storage are
  hard dependencies (``503`` if down); Redis and the LLM provider are
  reported but do not fail the probe by default (the app degrades gracefully
  without them — see ``Settings.HEALTH_REQUIRE_REDIS``).
* **Startup** — has the app finished its startup sequence (``lifespan``)?

LLM connectivity is **non-destructive**: it only issues a lightweight
``HEAD`` against the provider base URL (no token generation, no spend).
"""
from typing import Any, Dict, List

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Set to True at the end of the FastAPI lifespan startup sequence.
app_state: Dict[str, bool] = {"started": False}


async def check_database() -> Dict[str, Any]:
    """Verify PostgreSQL is reachable with a trivial query."""
    from sqlalchemy import text

    from app.core.database import get_sessionmaker

    try:
        session = get_sessionmaker()()
        try:
            session.execute(text("SELECT 1"))
            return {"name": "postgres", "status": "ok", "detail": "connected"}
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        return {"name": "postgres", "status": "down", "detail": str(exc)}


async def check_redis() -> Dict[str, Any]:
    """Verify Redis is reachable (reuses the cached client, else probes once)."""
    from app.core.redis import get_redis

    try:
        import redis.asyncio as aioredis
    except ImportError:  # redis client not installed
        return {"name": "redis", "status": "down", "detail": "redis package not installed"}

    client = get_redis()
    own = False
    if client is None:
        try:
            client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
            )
            own = True
        except Exception as exc:  # noqa: BLE001
            return {"name": "redis", "status": "down", "detail": str(exc)}

    try:
        await client.ping()
        return {"name": "redis", "status": "ok", "detail": "connected"}
    except Exception as exc:  # noqa: BLE001
        return {"name": "redis", "status": "down", "detail": str(exc)}
    finally:
        if own:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass


async def check_storage() -> Dict[str, Any]:
    """Verify the upload storage directory exists and is writable."""
    import os
    import tempfile

    path = settings.UPLOAD_STORAGE_DIR
    try:
        os.makedirs(path, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".health-", delete=True):
            pass
        return {"name": "storage", "status": "ok", "detail": path}
    except Exception as exc:  # noqa: BLE001
        return {"name": "storage", "status": "down", "detail": str(exc)}


async def check_llm() -> Dict[str, Any]:
    """Non-destructive LLM provider connectivity probe."""
    if not settings.OPENROUTER_API_KEY:
        return {
            "name": "llm",
            "status": "skipped",
            "detail": "no provider API key configured",
        }
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            resp = await client.head(settings.OPENROUTER_BASE_URL)
            auth_codes = (401, 403, 405)
            if resp.status_code >= 400 and resp.status_code not in auth_codes:
                return {
                    "name": "llm",
                    "status": "degraded",
                    "detail": f"provider returned HTTP {resp.status_code}",
                }
            return {
                "name": "llm",
                "status": "ok",
                "detail": f"reachable ({settings.OPENROUTER_BASE_URL})",
            }
    except Exception as exc:  # noqa: BLE001
        return {"name": "llm", "status": "degraded", "detail": str(exc)}


def liveness() -> Dict[str, Any]:
    """Liveness probe — always 200 while the process is running."""
    return {"status": "alive", "app": settings.APP_NAME, "version": settings.APP_VERSION}


def startup() -> Dict[str, Any]:
    """Startup probe — true once the lifespan startup has completed."""
    started = app_state.get("started", False)
    return {
        "status": "started" if started else "starting",
        "started": started,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


async def readiness() -> Dict[str, Any]:
    """Readiness probe — aggregate dependency health.

    Returns ``(payload, http_status)``. Required dependencies (postgres,
    storage) drive a ``503`` when down; redis/llm are optional and only
    move the overall status to ``degraded``.
    """
    checks: List[Dict[str, Any]] = [
        await check_database(),
        await check_storage(),
        await check_redis(),
        await check_llm(),
    ]
    by_name = {c["name"]: c for c in checks}
    required = [by_name["postgres"], by_name["storage"]]
    optional = [by_name["redis"], by_name["llm"]]

    required_down = [c for c in required if c["status"] == "down"]
    optional_down = [c for c in optional if c["status"] in ("down", "degraded")]

    if settings.HEALTH_REQUIRE_REDIS and by_name["redis"]["status"] == "down":
        required_down.append(by_name["redis"])

    if required_down:
        overall = "unavailable"
        http_status = 503
    elif optional_down:
        overall = "degraded"
        http_status = 200
    else:
        overall = "ok"
        http_status = 200

    return {
        "status": overall,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "checks": checks,
    }, http_status
