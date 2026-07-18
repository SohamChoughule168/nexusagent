# TLS / HTTPS with Let's Encrypt (certbot) — NexusAgent AI

This document covers enabling HTTPS in the AWS single-instance deployment using
**Let's Encrypt** certificates obtained and renewed by **certbot** in
`--webroot` mode. It is the production path referenced from
[`aws.md`](aws.md) §3.4. (ACM + an Application Load Balancer is an alternative,
out of scope here.)

The design keeps nginx as the sole TLS terminator: certbot writes challenge
files to a host webroot (`/var/www/letsencrypt`) that nginx serves over port 80;
nginx then terminates TLS using the issued certificate mounted from
`/etc/letsencrypt`. Renewal runs from cron and reloads nginx only when a cert
actually renews.

---

## 1. Prerequisites

- The stack is already deployed (`./deploy/init-deploy.sh`) and serving HTTP on
  port 80 via `./nginx/nginx.conf`, which already includes the
  `/.well-known/acme-challenge/` location and the webroot volume.
- `certbot` and `gettext-base` are installed on the host — `user-data.sh`
  installs both on Ubuntu. Verify: `certbot --version`, `envsubst --version`.
- A **public domain** (`DOMAIN`) whose A/AAAA record points at the instance's
  Elastic IP, and the EC2 security group allows inbound **80 and 443**.
- `.env.production` defines:
  - `DOMAIN=nexusagent.example.com`
  - `LETSENCRYPT_EMAIL=ops@example.com`
  - `CERTBOT_WEBROOT=/var/www/letsencrypt` (default)
  - `NGINX_CONF=./nginx/nginx.conf` (the initial value)

---

## 2. Issue the certificate (one-time)

```bash
cd /opt/nexusagent
./deploy/init-letsencrypt.sh
```

What it does:

1. Ensures nginx is up (HTTP) so the ACME HTTP-01 challenge is reachable.
2. Runs `certbot certonly --webroot -w /var/www/letsencrypt -d $DOMAIN ...`
   to obtain the cert (RSA 4096). Certs land at
   `/etc/letsencrypt/live/$DOMAIN/`.
3. Renders `nginx/tls.conf` from `nginx/tls.conf.template` (substituting
   `DOMAIN`/`WEBROOT`) via `deploy/render-nginx.sh`.
4. Flips `NGINX_CONF=./nginx/tls.conf` in `.env.production` and recreates nginx
   with the TLS override (`docker-compose.aws.tls.yml`: opens 443, mounts
   `/etc/letsencrypt` read-only).

Verify:

```bash
curl -fsS https://$DOMAIN/health                 # valid cert, healthy
curl -I   http://$DOMAIN/                        # 301 -> https://
sudo certbot certificates                         # shows $DOMAIN, not expiring
```

`nginx/tls.conf` adds: HTTP→HTTPS 301 redirect, `Strict-Transport-Security`,
modern TLS ciphers/protocols, OCSP stapling, and WebSocket-aware `/api/`
proxying — same routing as the HTTP config.

---

## 3. Automate renewal

```bash
./deploy/setup-cron.sh
```

Installs two cron jobs (idempotent — safe to re-run):

| Schedule | Job | Purpose |
|----------|-----|---------|
| `0 3 * * *` | `deploy/backup.sh` | Nightly DB + uploads backup (prune + optional S3). |
| `23 2,14 * * *` | `deploy/renew-cert.sh` | Twice-daily Let's Encrypt renewal check. |

`renew-cert.sh` runs `certbot renew --webroot` with a `--deploy-hook` that sends
`SIGUSR1`/`HUP` to the nginx container **only when a cert was renewed**, so nginx
picks up the new certificate with no downtime.

Dry-run to confirm renewal works:

```bash
sudo certbot renew --dry-run
```

---

## 4. How it fits the compose files

| File | Role |
|------|------|
| `docker-compose.aws.yml` | Base. nginx mounts `${NGINX_CONF:-./nginx/nginx.conf}` and the webroot volume; publishes only port 80. |
| `docker-compose.aws.tls.yml` | Override (applied when `ENABLE_TLS=true`). Opens 443 and mounts `/etc/letsencrypt:/etc/nginx/certs:ro`. |
| `nginx/nginx.conf` | HTTP config (active by default); serves ACME challenge. |
| `nginx/tls.conf.template` | HTTPS template; rendered to `nginx/tls.conf` by `render-nginx.sh`. |
| `nginx/tls.conf` | The rendered, active HTTPS config (generated; not committed). |

The deploy scripts (`init-deploy.sh`, `update-containers.sh`,
`rolling-restart.sh`, `healthcheck.sh`, `db-migrate.sh`) source
`deploy/compose.sh`, which adds the TLS override automatically when
`ENABLE_TLS=true`. After `init-letsencrypt.sh`, `NGINX_CONF` is persisted in
`.env.production`, so plain `./deploy/update-containers.sh` keeps serving HTTPS.

---

## 5. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| certbot: `Failed authorization: Connection refused` | SG blocks 80, or nginx down, or DNS not pointed | Open 80, ensure `nginx` healthy, confirm DNS A record. |
| certbot: `too many certificates` | Rate-limited (duplicate issuances) | Use staging first: add `--staging` to `init-letsencrypt.sh` for tests. |
| nginx: `SSL_CTX: no certificate` on 443 | `NGINX_CONF` not switched / certs not mounted | Confirm `NGINX_CONF=./nginx/tls.conf` and TLS override applied. |
| Renewal didn't reload nginx | deploy-hook failed | Check cron log `/data/nexusagent/backups/cron.log`; run `renew-cert.sh` manually. |
| Browser refuses HTTP after HSTS | HSTS cached | Use a maintenance window; see `ROLLBACK.md` §4. |

To temporarily fall back to HTTP (e.g. while fixing a cert), set
`NGINX_CONF=./nginx/nginx.conf` and recreate nginx (see `ROLLBACK.md` §4).

---

## 6. Alternative: AWS ACM + ALB (not used here)

If you prefer AWS-managed certificates, terminate TLS at an Application Load
Balancer with an ACM cert and point it at the EC2 instance's port 80 (nginx
stays HTTP). That removes certbot/cron from the host but introduces an ALB and
a public subnet/health-check config — a larger change, intentionally out of
scope for this single-instance phase.
