from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.base import Base

# Engine and sessionmaker are created lazily so importing this module never
# requires a database driver to be installed (e.g. during tests that only
# exercise non-DB endpoints). A real runtime still requires the DBAPI driver.
_engine = None
_SessionLocal = None


def _sync_database_url() -> str:
    """Return a synchronous DB URL (asyncpg is only for async drivers)."""
    return settings.DATABASE_URL.replace("+asyncpg", "")


def get_engine():
    global _engine
    if _engine is None:
        engine_kwargs: dict = {
            "pool_pre_ping": True,
            "future": True,
        }
        # DEBUG uses NullPool (fresh connection per request — friendly to
        # auto-reload and short-lived dev sessions). Production uses a bounded
        # QueuePool sized from configuration so a single worker cannot exhaust
        # Postgres connections under burst load.
        if not settings.DEBUG:
            engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
            engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
            engine_kwargs["pool_timeout"] = settings.DB_POOL_TIMEOUT
        _engine = create_engine(
            _sync_database_url(),
            poolclass=NullPool if settings.DEBUG else None,
            **engine_kwargs,
        )
    return _engine


def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
            future=True,
        )
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Iterator[Session]:
    """Context manager for standalone database sessions."""
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables declared on the shared Base (dev convenience)."""
    Base.metadata.create_all(bind=get_engine())
