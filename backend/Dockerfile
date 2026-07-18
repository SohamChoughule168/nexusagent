# NexusAgent AI - Backend production image
# Multi-stage build: install deps (incl. the `app` package via `pip install .`),
# then run as a non-root user.
#
# Build context: the REPOSITORY ROOT. The Dockerfile expects pyproject.toml and
# backend/ at the root of the build context (see docker-compose.yml
# `backend.build` and .github/workflows/docker-validation.yml). The `app`
# package is installed as a normal top-level package, so no PYTHONPATH is set.

# ---- Stage 1: dependencies + installable package ----
FROM python:3.11-slim AS deps

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# pyproject.toml drives both dependency installation and discovery of the
# `app` package (which lives under backend/ via [tool.setuptools].package-dir).
COPY pyproject.toml ./
# The application source is required so `pip install .` can build/install the
# `app` package (package-dir maps "" -> backend/, so backend/app -> `app`).
COPY backend/app ./backend/app
# README is referenced by pyproject's `readme` field.
COPY README.md ./

# Install runtime deps + the `app` package. The package is installed into
# site-packages as a normal top-level import, so the runtime needs no
# PYTHONPATH. Alembic is required to run database migrations in production.
RUN pip install --upgrade pip && \
    pip install . && \
    pip install alembic==1.13.1

# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Runtime healthcheck client. curl is used by the container healthcheck.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system --gid 1001 appuser && \
    useradd --system --uid 1001 --gid appuser --create-home appuser

WORKDIR /app

# Bring in the installed dependencies (incl. the `app` package) from the deps
# stage. `app.main:app` now resolves as an installed top-level package.
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Alembic migration scripts + config. (The `app` code itself is already
# installed in site-packages from the deps stage, so it is not copied here.)
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini

# Persist uploaded documents (created on demand by the app).
RUN mkdir -p /app/storage/uploads && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# uvicorn is on PATH from the deps stage. The `app` package is installed
# top-level, so `app.main:app` resolves without any PYTHONPATH manipulation.
#
# `exec` replaces the shell with uvicorn as PID 1 so it receives SIGTERM
# directly and shuts down gracefully (draining in-flight requests) when the
# container is stopped. Without `exec`, the shell would be PID 1 and swallow
# the signal, forcing Docker's SIGKILL after the stop grace period.
#
# The container runs as the non-root `appuser` (uid 1001) and, in production
# compose, with `read_only: true` + a tmpfs `/tmp` (uploads live on a mounted
# volume). Dropped Linux capabilities: see docker-compose*.yml (`cap_drop`).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
