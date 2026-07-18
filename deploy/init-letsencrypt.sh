#!/usr/bin/env bash
# NexusAgent AI - obtain a Let's Encrypt certificate and switch nginx to HTTPS.
#
# Prerequisites:
#   * init-deploy.sh has run; nginx is serving HTTP (port 80) from
#     ./nginx/nginx.conf, including the /.well-known/acme-challenge/ webroot.
#   * DNS A/AAAA for DOMAIN points at this instance's public IP, and the EC2
#     security group allows inbound 80 + 443.
#   * certbot is installed (deploy/user-data.sh installs it on Ubuntu).
#   * .env.production defines DOMAIN and LETSENCRYPT_EMAIL.
#
# What it does:
#   1. Ensures nginx is up (HTTP) so the ACME HTTP-01 challenge is reachable.
#   2. Runs `certbot certonly --webroot` to obtain the cert for DOMAIN.
#   3. Renders nginx/tls.conf from the template (deploy/render-nginx.sh).
#   4. Flips NGINX_CONF to ./nginx/tls.conf in .env.production and recreates
#      nginx with the TLS override (port 443 + mounted certs).
#
# Idempotent for re-runs: certbot is a no-op if the cert already exists and is
# not near expiry; nginx is recreated only to pick up the new config.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

source "$(dirname "$0")/compose.sh"

ENV_FILE="${ENV_FILE:-.env.production}"
[ -f "$ENV_FILE" ] && { set -a; . ./"$ENV_FILE"; set +a; }

DOMAIN="${DOMAIN:?DOMAIN is not set in .env.production}"
EMAIL="${LETSENCRYPT_EMAIL:?LETSENCRYPT_EMAIL is not set in .env.production}"
WEBROOT="${CERTBOT_WEBROOT:-/var/www/letsencrypt}"

echo "==> Ensuring nginx is up (HTTP) to serve the ACME challenge"
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" up -d --force-recreate nginx

echo "==> Requesting Let's Encrypt certificate for $DOMAIN"
sudo certbot certonly --webroot \
  -w "$WEBROOT" \
  -d "$DOMAIN" \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  --rsa-key-size 4096 \
  --non-interactive

echo "==> Rendering HTTPS nginx config"
"$REPO_ROOT/deploy/render-nginx.sh"

echo "==> Switching active config to HTTPS and recreating nginx (TLS)"
# Make the switch durable for future `update-containers.sh` / boot.
if grep -q '^NGINX_CONF=' "$ENV_FILE"; then
  sudo sed -i "s#^NGINX_CONF=.*#NGINX_CONF=./nginx/tls.conf#" "$ENV_FILE"
else
  printf 'NGINX_CONF=./nginx/tls.conf\n' >> "$ENV_FILE"
fi

export NGINX_CONF=./nginx/tls.conf
export ENABLE_TLS=true
docker compose "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" up -d --force-recreate nginx

echo "==> HTTPS is live. Verify: curl -fsS https://$DOMAIN/health"
echo "    Renewals are automated by deploy/renew-cert.sh (wire via deploy/setup-cron.sh)."
