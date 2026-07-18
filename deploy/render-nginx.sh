#!/usr/bin/env bash
# NexusAgent AI - render the active HTTPS nginx config from its template.
#
# Substitutes ${DOMAIN} and ${WEBROOT} (from the environment / .env.production)
# into nginx/tls.conf.template and writes nginx/tls.conf. Fails if any
# placeholder remains unreplaced so a half-rendered config is never deployed.
#
# Usage: deploy/render-nginx.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
[ -f "$ENV_FILE" ] && { set -a; . ./"$ENV_FILE"; set +a; }

DOMAIN="${DOMAIN:?DOMAIN is not set (add it to .env.production)}"
WEBROOT="${CERTBOT_WEBROOT:-/var/www/letsencrypt}"

export DOMAIN WEBROOT

SRC="nginx/tls.conf.template"
OUT="nginx/tls.conf"

if [ ! -f "$SRC" ]; then
  echo "ERROR: $SRC missing" >&2
  exit 1
fi

# Render only the two known variables (avoids clobbering shell $vars by name).
envsubst '${DOMAIN} ${WEBROOT}' < "$SRC" > "$OUT"

# Guard: fail if any placeholder survived.
if grep -Eq '\$\{(DOMAIN|WEBROOT)\}' "$OUT"; then
  echo "ERROR: unreplaced placeholder in $OUT" >&2
  grep -En '\$\{(DOMAIN|WEBROOT)\}' "$OUT" >&2
  exit 1
fi

echo "==> Rendered $OUT for domain '$DOMAIN' (webroot $WEBROOT)."
