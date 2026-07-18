# NexusAgent AI - Backend production image
# Multi-stage build: install deps, then run as a non-root user.

# ---- Stage 1: dependencies ----
FROM python:3.11-slim AS deps

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy only the dependency manifest first for better layer caching.
COPY pyproject.toml ./
# Install runtime dependencies declared in pyproject.toml.
# --no-deps is intentionally NOT used; the pinned [project].dependencies are
# exactly what the production runtime needs.
RUN pip install --upgrade pip && \
    pip install . && \
    # Alembic is required to run database migrations in production.
    pip install alembic==1.13.1

# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000

# Install runtime libs used by psycopg2 (none needed for -binary) and a
# healthcheck client. curl is used by the container healthcheck.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system --gid 1001 appuser && \
    useradd --system --uid 1001 --gid appuser --create-home appuser

WORKDIR /app

# Bring in the installed dependencies from the deps stage.
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source. The backend/ host directory holds the `app`
# package, so its contents are copied into /app so that `app.main:app`
# resolves correctly.
COPY backend/ /app/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

# Persist uploaded documents (created on demand by the app).
RUN mkdir -p /app/storage/uploads && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# uvicorn is on PATH from the deps stage. The app module is at app.main:app
# (working dir is /app, which contains the backend/ package via COPY backend/).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
