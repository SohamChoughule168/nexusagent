from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    import redis.asyncio as aioredis

    _REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover - redis optional at import time
    aioredis = None
    _REDIS_AVAILABLE = False

_redis_client: Optional["aioredis.Redis"] = None


async def init_redis() -> Optional["aioredis.Redis"]:
    """Initialize the Redis client with safe startup handling.

    Returns ``None`` if Redis is unreachable so the application can still
    start without it (features depending on Redis degrade gracefully).
    """
    global _redis_client
    if not _REDIS_AVAILABLE:
        logger.warning("redis_unavailable", reason="redis package not installed")
        return None

    try:
        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
        )
        await client.ping()
        _redis_client = client
        logger.info("redis_connected", url=settings.REDIS_URL)
        return client
    except Exception as exc:  # noqa: BLE001 - never crash startup on Redis failure
        logger.warning("redis_connection_failed", error=str(exc))
        _redis_client = None
        return None


async def close_redis() -> None:
    """Close the Redis client on shutdown."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_close_failed", error=str(exc))
        finally:
            _redis_client = None


def get_redis() -> Optional["aioredis.Redis"]:
    """Return the active Redis client (may be ``None``)."""
    return _redis_client
