"""Alembic environment script.

Standard, production-compatible Alembic environment for the NexusAgent
backend. Uses the project's real Settings configuration for the database URL
and the synchronous PostgreSQL driver for Alembic's synchronous execution.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context

# ---------------------------------------------------------------------------
# Ensure the backend package is importable regardless of the current directory.
# env.py lives at <backend>/alembic/env.py -> backend dir is one level up.
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
# Load the project's real Settings configuration.
# ---------------------------------------------------------------------------
from app.core.config import Settings  # noqa: E402

config = context.config

# Emit loggers from alembic.ini if present (does not print credentials).
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        # Logging is best-effort; never let it leak credentials or abort.
        pass

# ---------------------------------------------------------------------------
# Resolve the database URL source for Alembic's synchronous execution.
# 1. Prefer an externally configured sqlalchemy.url (e.g. set by a test runner
#    with Config.set_main_option). 2. Otherwise fall back to Settings().
#    DATABASE_URL. In both cases only the driver scheme is normalized
#    (asyncpg -> psycopg2) so the synchronous Alembic engine never receives an
#    async driver. The .env and the application's async URL are never modified.
# ---------------------------------------------------------------------------
external_url = config.get_main_option("sqlalchemy.url")
source_url = external_url if external_url else Settings().DATABASE_URL

if source_url.startswith("postgresql+asyncpg://"):
    alembic_url = source_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://", 1
    )
else:
    alembic_url = source_url

# Provide the synchronous URL to Alembic's engine config unconditionally.
config.set_main_option("sqlalchemy.url", alembic_url)

# ---------------------------------------------------------------------------
# Import all mapped model modules so every table is registered on the
# metadata before target_metadata is used. Existing project modules only.
# ---------------------------------------------------------------------------
from app.models.base import Base  # noqa: E402,F401
import app.models.user  # noqa: E402,F401
import app.models.organization  # noqa: E402,F401
import app.models.all_models  # noqa: E402,F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DB connection)."""
    context.configure(
        url=alembic_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a synchronous engine."""
    from sqlalchemy import engine_from_config
    from sqlalchemy import pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
