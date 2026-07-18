#!/usr/bin/env bash
# NexusAgent AI - shared compose file resolution for deploy scripts.
#
# Source this (after the script has cd'd into REPO_ROOT). It populates the
# COMPOSE_FILES array used by every deploy script:
#
#   COMPOSE_FILES=(-f docker-compose.aws.yml)
#
# TLS is opt-in via `ENABLE_TLS=true` (default off). When set, the
# docker-compose.aws.tls.yml override is added, which opens port 443 and mounts
# the Let's Encrypt certificate directory into nginx. Enable it once
# init-letsencrypt.sh has issued a certificate (it also flips NGINX_CONF in
# .env.production so the active config becomes ./nginx/tls.conf).
#
# Usage inside a deploy script:
#   source "$(dirname "$0")/compose.sh"
#   docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" up -d

COMPOSE_BASE="${COMPOSE_BASE:-docker-compose.aws.yml}"
COMPOSE_FILES=(-f "$COMPOSE_BASE")
if [ "${ENABLE_TLS:-false}" = "true" ]; then
  COMPOSE_FILES+=(-f docker-compose.aws.tls.yml)
fi
