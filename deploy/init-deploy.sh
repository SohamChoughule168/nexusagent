#!/usr/bin/env bash
# NexusAgent AI - initial deployment on a fresh AWS host
#
# Prerequisites (see docs/deployment/aws.md):
#   * user-data.sh has run (Docker installed, EBS mounted at /data).
#   * `.env.production` exists at the repo root with real values.
#
# What it does:
#   1. Verifies .env.production exists.
#   2. Ensures /data/nexusagent/uploads is present and owned by the backend
#      non-root user (uid/gid 1001).
#   3. Builds the backend + frontend images on the host (no registry needed).
#   4. Starts all services, applies DB migrations, waits for backend health.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.aws.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found." >&2
  echo "       Copy the template and fill in real values:" >&2
  echo "         cp env.production.example $ENV_FILE" >&2
  exit 1
fi

echo "==> Ensuring uploads directory on EBS volume (/data/nexusagent/uploads)"
sudo install -d -o 1001 -g 1001 /data/nexusagent/uploads

echo "==> Building images (backend + frontend) from source"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build

echo "==> Starting services"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

echo "==> Applying database migrations"
"$REPO_ROOT/deploy/db-migrate.sh"

echo "==> Waiting for backend health"
"$REPO_ROOT/deploy/healthcheck.sh" 15 5

echo "==> Initial deployment complete."
echo "    Open http://<your-ec2-public-dns>/ (or your domain once DNS/TLS are set)."
