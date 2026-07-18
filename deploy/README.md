# NexusAgent AI - AWS Deployment Scripts

These shell scripts drive the single-instance AWS deployment described in
[`../docs/deployment/aws.md`](../docs/deployment/aws.md). All scripts run on
the EC2 host as the `deploy` user (created by `user-data.sh`) and assume the
repo is cloned at `/opt/nexusagent` with a real `.env.production` at the root.

They resolve the repo root from their own location, so they work from anywhere:

```bash
cd /opt/nexusagent
./deploy/init-deploy.sh
```

## Scripts

| Script                  | Purpose                                                      |
|-------------------------|--------------------------------------------------------------|
| `user-data.sh`          | EC2 cloud-init bootstrap: Docker, certbot, EBS mount, deploy user, systemd unit. |
| `init-deploy.sh`        | First-time deploy: build, start, migrate, health-gate.      |
| `update-containers.sh`  | Routine code update: pull, build, migrate, recreate, gate.  |
| `rolling-restart.sh`    | Health-gated restart of one service (default: `backend`).   |
| `db-migrate.sh`         | Run `alembic upgrade head` against RDS.                     |
| `healthcheck.sh`        | Poll backend `/health` over the internal network.           |
| `backup.sh`             | `pg_dump` of RDS + tar of uploads; prune old backups.       |
| `restore.sh`            | Restore a backup set (DB + uploads). Destructive.           |
| `compose.sh`            | Sourced helper: resolves `COMPOSE_FILES` (adds TLS override when `ENABLE_TLS=true`). |
| `render-nginx.sh`       | Render `nginx/tls.conf` from `tls.conf.template` (`DOMAIN`/`WEBROOT`). |
| `init-letsencrypt.sh`   | Issue a Let's Encrypt cert (webroot) and switch nginx to HTTPS. |
| `renew-cert.sh`         | Renew certs from cron; reload nginx only on actual renewal.  |
| `setup-cron.sh`         | Install nightly backup + twice-daily certbot renewal cron.  |
| `fetch-secrets.sh`      | Render `.env.production` from an AWS Secrets Manager JSON secret. |
| `nexusagent.service`    | systemd unit (installed by user-data.sh) to start the stack on host boot. |

See [`../docs/deployment/backups.md`](../docs/deployment/backups.md) for the
retention policy, monthly restore-verification procedure and the full disaster
recovery checklist.

## Security

Milestone 7, Phase 6 hardening is documented under
[`../docs/deployment/`](../docs/deployment/):

| Doc | Covers |
|-----|--------|
| [`secrets.md`](../docs/deployment/secrets.md) | Secret generation, rotation, storage, backup, recovery, AWS Secrets Manager, local dev. |
| [`security-checklist.md`](../docs/deployment/security-checklist.md) | Pre/post-deploy, incident-response, key-rotation checklists. |
| [`security-scanning.md`](../docs/deployment/security-scanning.md) | Bandit, Trivy, pip-audit, npm audit (CI + local). |
| [`security-headers.md`](../docs/deployment/security-headers.md) | CSP, HSTS, frame/referrer/permissions headers, nginx integration. |
| [`rate-limiting.md`](../docs/deployment/rate-limiting.md) | In-memory rate limiter behavior and limits. |
| `iam-policy.json`      | Least-privilege instance-role policy (SSM, optional S3/ECR).|

## Overridable env vars

Each script honors these (defaults shown):

| Var          | Default                  | Meaning                                  |
|--------------|--------------------------|------------------------------------------|
| `COMPOSE_FILE` | `docker-compose.aws.yml` | Compose file used.                     |
| `ENV_FILE`   | `.env.production`        | Env file loaded by compose.             |
| `BRANCH`     | `main`                   | Branch pulled by `update-containers.sh`.|
| `BACKUP_DIR` | `/data/nexusagent/backups` | Backup target on the EBS volume.      |
| `RETENTION_DAYS` | `7`                 | Backups older than this are pruned.     |
| `BACKUP_S3_BUCKET` | _(unset)_         | If set, `backup.sh` syncs to this S3 bucket. |

## Typical workflows

```bash
# First deploy on a fresh host
cp env.production.example .env.production   # then edit with real values
./deploy/init-deploy.sh

# Enable HTTPS (after DNS + security group allow 80/443)
./deploy/init-letsencrypt.sh
./deploy/setup-cron.sh          # nightly backup + certbot renewal

# (Optional) pull secrets from AWS Secrets Manager instead of hand-editing
AWS_SECRETS_MANAGER_SECRET_NAME=nexusagent/prod ./deploy/fetch-secrets.sh

# Ship a new version (keeps serving HTTPS if NGINX_CONF=./nginx/tls.conf)
./deploy/update-containers.sh

# Restart just the backend (e.g. after a config tweak) without rebuilding
./deploy/rolling-restart.sh backend

# Restore from a backup
./deploy/restore.sh 20260718T123000Z
```

## TLS / HTTPS

`init-letsencrypt.sh` issues a Let's Encrypt certificate via certbot's webroot
plugin (nginx serves the ACME challenge over port 80), renders
`nginx/tls.conf`, and flips `NGINX_CONF` in `.env.production` so the stack serves
HTTPS. Renewal is automated by `renew-cert.sh` via `setup-cron.sh`. Full
procedure and troubleshooting: [`../docs/deployment/tls.md`](../docs/deployment/tls.md).

## Automatic restart on boot

`user-data.sh` installs `deploy/nexusagent.service` and enables it, so a host
reboot brings the whole stack back up (containers additionally use
`restart: unless-stopped` for in-place crashes). To run with the TLS override at
boot, edit the unit's `ExecStart`/`ExecStop` to append
`-f /opt/nexusagent/docker-compose.aws.tls.yml` (see the unit file header).

## Prerequisites

- `user-data.sh` has run (Docker + Compose plugin + certbot installed, EBS at `/data`).
- `postgresql-client` present (installed by `user-data.sh`) for `pg_dump`/`psql`.
- `.env.production` exists with real RDS/ElastiCache endpoints and secrets.
- EC2 security group allows the host to reach RDS (5432) and ElastiCache (6379).

See [`../docs/deployment/aws.md`](../docs/deployment/aws.md) for the full
walkthrough, AWS resources, cost estimate, health/rollback, and troubleshooting.
See [`../docs/deployment/PRODUCTION_CHECKLIST.md`](../docs/deployment/PRODUCTION_CHECKLIST.md)
and [`../docs/deployment/ROLLBACK.md`](../docs/deployment/ROLLBACK.md) for the
deploy/rollback runbooks.
