#!/usr/bin/env bash
# NexusAgent AI - backend health probe
#
# Polls the backend's /health endpoint (over the internal docker network) and
# exits 0 once healthy, or 1 after ATTEMPTS failures. Used by the deploy
# scripts to gate on backend readiness without exposing the port publicly.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.aws.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
ATTEMPTS="${1:-10}"
SLEEP="${2:-5}"

echo "==> Probing backend /health (max $ATTEMPTS attempts, ${SLEEP}s apart)"
for i in $(seq 1 "$ATTEMPTS"); do
  if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
      exec -T backend curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "==> backend healthy"
    exit 0
  fi
  echo "    attempt $i/$ATTEMPTS not ready; sleeping ${SLEEP}s"
  sleep "$SLEEP"
done

echo "ERROR: backend did not become healthy" >&2
exit 1
