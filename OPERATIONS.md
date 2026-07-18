# NexusAgent — Operations

Operational guidance for running NexusAgent v1.0.0 in production. For
step-by-step deployment, see `docs/deployment/` (especially `production.md`,
`aws.md`, `backups.md`, `observability.md`, `security-checklist.md`). The
helper scripts live in `deploy/`.

## 1. Deployment

### Prerequisites
- PostgreSQL 16 (RDS or container) and Redis (ElastiCache or container).
- Docker + Docker Compose on the host (or use the CI-built images).
- All secrets from `env.production.example` filled in — **required** secrets
  have no defaults and the app fails fast if omitted. Never commit `.env.production`.

### Local / single-host (compose)
```bash
cp .env.example .env          # fill in secrets
docker compose up -d          # db, redis, backend, frontend
```

### AWS single-instance
```bash
# 1. Launch EC2 with deploy/user-data.sh as cloud-init (Docker, EBS, deploy user)
# 2. On the host:
cd /opt/nexusagent
cp env.production.example .env.production   # fill in secrets
./deploy/init-deploy.sh        # build, start, migrate (alembic), health-gate
```

### Database migrations
Run Alembic against the target database before/with each deploy:
```bash
./deploy/db-migrate.sh         # -> alembic upgrade head
```

### Routine code update
```bash
./deploy/update-containers.sh  # pull, build, migrate, recreate, health-gate
./deploy/rolling-restart.sh    # health-gated restart of one service (default backend)
```

### Container image build (CI also validates this)
```bash
docker compose build           # backend + frontend images
```

## 2. Monitoring

- **Metrics**: backend exposes Prometheus exposition at `GET /metrics`
  (scrape interval ~15–30s). Stack: `monitoring/docker-compose.monitoring.yml`
  (Prometheus + Grafana). Dashboards in `monitoring/grafana/`.
- **Health probes** (Kubernetes-style, also used by compose healthchecks):
  - `GET /health/live` — process liveness.
  - `GET /health/ready` — dependency health aggregate (DB, Redis optional).
  - `GET /health/startup` — true once lifespan startup completed.
  - `GET /health` — backward-compatible aggregate.
- **Logs**: structured JSON to stdout by default (`LOG_FORMAT=json`); optional
  rotating file logs (`LOG_FILE`, `ACCESS_LOG_FILE`).
- **Rate limiting**: `RATE_LIMIT_PER_MINUTE` (keys off `X-Forwarded-For` set by
  nginx; exempts `/health` and `/metrics`). Disable by setting `0`.
- **Tracing context**: every request carries a `X-Request-ID`; it is logged and
  returned in the response header.

See `docs/deployment/observability.md` and `docs/deployment/rate-limiting.md`.

## 3. Backup

`deploy/backup.sh` produces timestamped, gzipped archives on the EBS volume
(`/data/nexusagent/backups` by default):
- `nexusagent-db-<ts>.sql.gz` — `pg_dump` of the database.
- `nexusagent-uploads-<ts>.tar.gz` — tar of `/data/nexusagent/uploads`.

Old backups beyond `RETENTION_DAYS` are pruned.

```bash
./deploy/backup.sh
```

Schedule it (e.g. nightly via cron/systemd timer). Backups include both the
database and uploaded documents (which are not in the database).

## 4. Restore

`deploy/restore.sh <ts>` restores a backup set. **Destructive to the live
database and uploads** — run during a maintenance window.

```bash
./deploy/restore.sh 20260718T123000Z
```

Monthly restore-verification is recommended; see `docs/deployment/backups.md`
for the retention policy and full disaster-recovery checklist.

## 5. Incident response

1. **Check the health gate**: `./deploy/healthcheck.sh` (polls `/health`
   internally). If not healthy, inspect container logs.
2. **Rotate compromised secrets** (JWT keys, DB password, API keys) by updating
   `.env.production` and restarting the backend: `./deploy/rolling-restart.sh`.
   - JWT key rotation invalidates all existing tokens (users re-login).
3. **Roll back a bad deploy**: re-run `./deploy/update-containers.sh` after
   checking out the previous tag, or pull the prior image tag.
4. **Database issues**: never restore over a live DB without a fresh backup
   first. Use `deploy/restore.sh` from a verified set.
5. **Escalate** with: request ID(s) from the failing request, the last deploy
   tag (`git describe`), backend logs around the timestamp, and Prometheus
   signals (error rate, p95 latency).

## 6. Maintenance

- **Secrets**: store production secrets in AWS Secrets Manager (see
  `docs/deployment/aws-secrets.md`) and export into the env at deploy time.
  Rotate JWT secrets periodically; rotate DB/API keys on suspected compromise.
- **Upgrades**: change `VERSION`/`APP_VERSION`, bump images, run migrations,
  and deploy behind a health-gate. Tag releases and keep the changelog current.
- **Capacity**: backend runs one Uvicorn worker per container — scale out
  (more containers) rather than up. Budget ~100 MB RSS per worker plus headroom.
- **Logs/metrics retention**: configure Prometheus/Grafana retention; archive
  JSON logs if required for compliance.
- **Security hygiene**: keep dependencies patched (CI runs `pip-audit` +
  Bandit); re-run the `docs/deployment/security-checklist.md` before each
  release.

## Quick reference — deploy scripts
| Script | Purpose |
| --- | --- |
| `deploy/user-data.sh` | EC2 cloud-init: Docker, EBS mount, deploy user |
| `deploy/init-deploy.sh` | First deploy: build, start, migrate, health-gate |
| `deploy/update-containers.sh` | Routine update: pull, build, migrate, recreate |
| `deploy/rolling-restart.sh` | Health-gated restart of one service |
| `deploy/db-migrate.sh` | `alembic upgrade head` |
| `deploy/healthcheck.sh` | Poll `/health` over internal network |
| `deploy/backup.sh` | pg_dump + uploads archive, prune old |
| `deploy/restore.sh` | Restore a backup set (destructive) |
