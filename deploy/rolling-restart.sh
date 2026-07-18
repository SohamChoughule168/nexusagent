#!/usr/bin/env bash
# NexusAgent AI - health-gated restart of a service (single-instance "rolling")
#
# On a single host we cannot run two backend copies, so a "rolling restart"
# means: stop the service, recreate it with the latest image/config, and wait
# for the health endpoint before declaring success. nginx keeps serving
# (returning 502 only during the brief backend gap), so the blast radius is
# limited to in-flight backend requests.
#
# Usage: deploy/rolling-restart.sh [service]
#   default service: backend
#
# For an application-only update that keeps the current image, this is enough.
# For a code update, run deploy/update-containers.sh instead (it rebuilds).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.aws.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
SVC="${1:-backend}"

echo "==> Health-gated restart of '$SVC'"

echo "    stopping '$SVC'"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" stop "$SVC"

echo "    recreating '$SVC' (latest image/config)"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
  up -d --no-deps --force-recreate "$SVC"

echo "    waiting for '$SVC' health"
"$REPO_ROOT/deploy/healthcheck.sh" 12 5

echo "==> '$SVC' restarted and healthy."
