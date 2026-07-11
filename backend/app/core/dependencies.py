from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db as _get_db
from app.core.redis import get_redis


def get_settings():
    """FastAPI dependency exposing application settings."""
    return settings


def get_db_session() -> Session:
    """FastAPI dependency yielding a database session."""
    return _get_db()


def get_request_id(request: Request) -> str:
    """FastAPI dependency returning the request correlation ID."""
    return getattr(request.state, "request_id", "unknown")


def get_redis_client() -> Optional[object]:
    """FastAPI dependency returning the Redis client (may be ``None``)."""
    return get_redis()
