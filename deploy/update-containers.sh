#!/usr/bin/env bash
# NexusAgent AI - update the deployment to the latest code
#
# Pulls the latest source, rebuilds images, applies migrations, and recreates
# all containers. This is the routine "ship a new version" path.
#
# Usage: deploy/update-containers.sh [branch]
#   default branch: main
#
# What it does:
#   1. git pull --ff-only
#   2. docker compose build (backend + frontend)
#   3. alembic upgrade head (against RDS)
#   4. docker compose up -d --force-recreate (all services)
#   5. wait for backend health

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.aws.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
BRANCH="${1:-main}"

echo "==> Pulling latest source (branch=$BRANCH)"
git pull --ff-only "origin" "$BRANCH"

echo "==> Rebuilding images"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build

echo "==> Applying migrations"
"$REPO_ROOT/deploy/db-migrate.sh"

echo "==> Recreating containers"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --force-recreate

echo "==> Waiting for backend health"
"$REPO_ROOT/deploy/healthcheck.sh" 15 5

echo "==> Update complete."
