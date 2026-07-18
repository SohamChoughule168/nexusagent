#!/usr/bin/env bash
# NexusAgent AI - apply database migrations (Alembic)
#
# Runs `alembic upgrade head` inside the running backend container. Alembic
# reads the project Settings, so it targets the RDS endpoint configured via
# DATABASE_URL in .env.production. The asyncpg driver is auto-normalized to
# psycopg2 by alembic/env.py, so no manual URL change is needed.
#
# For a zero-downtime workflow, run this BEFORE recreating the backend on
# upgrades (migrations are applied to shared RDS, not the container).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.aws.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

echo "==> Running: alembic upgrade head"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend alembic upgrade head
echo "==> Migrations applied."
