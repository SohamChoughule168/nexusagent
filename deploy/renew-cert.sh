#!/usr/bin/env bash
# NexusAgent AI - renew Let's Encrypt certificates and reload nginx on change.
#
# Intended to run from cron (see deploy/setup-cron.sh), twice daily. certbot
# only actually renews when a cert is within its renewal window (<=30 days to
# expiry), so running it often is safe. The --deploy-hook reloads nginx only
# when a certificate was genuinely renewed.
#
# nginx is run by docker compose; the deploy-hook sends SIGHUP to the nginx
# container, which reloads its config and certificates gracefully (no dropped
# connections).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source "$(dirname "$0")/compose.sh"

ENV_FILE="${ENV_FILE:-.env.production}"
[ -f "$ENV_FILE" ] && { set -a; . ./"$ENV_FILE"; set +a; }

WEBROOT="${CERTBOT_WEBROOT:-/var/www/letsencrypt}"

# The deploy-hook runs in certbot's own shell, so it must be self-contained
# (no inherited vars). It sends SIGHUP to the nginx container to reload certs
# with zero downtime. Both compose files are listed so the project/container
# name resolves whether or not TLS is currently active.
NGINX_HUP_HOOK='cd /opt/nexusagent && docker compose -f docker-compose.aws.yml -f docker-compose.aws.tls.yml --env-file .env.production kill -s HUP nginx'

echo "==> Renewing certificates (webroot=$WEBROOT)"
sudo certbot renew --webroot -w "$WEBROOT" \
  --quiet \
  --deploy-hook "$NGINX_HUP_HOOK"

echo "==> Renewal check complete."
