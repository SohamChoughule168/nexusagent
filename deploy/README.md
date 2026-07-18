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

| Script                 | Purpose                                                      |
|------------------------|--------------------------------------------------------------|
| `user-data.sh`         | EC2 cloud-init bootstrap: Docker, EBS mount, deploy user.    |
| `init-deploy.sh`       | First-time deploy: build, start, migrate, health-gate.      |
| `update-containers.sh` | Routine code update: pull, build, migrate, recreate, gate.  |
| `rolling-restart.sh`   | Health-gated restart of one service (default: `backend`).   |
| `db-migrate.sh`        | Run `alembic upgrade head` against RDS.                     |
| `healthcheck.sh`       | Poll backend `/health` over the internal network.           |
| `backup.sh`            | `pg_dump` of RDS + tar of uploads; prune old backups.       |
| `restore.sh`           | Restore a backup set (DB + uploads). Destructive.           |

See [`../docs/deployment/backups.md`](../docs/deployment/backups.md) for the
retention policy, monthly restore-verification procedure and the full disaster
recovery checklist.
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

# Ship a new version
./deploy/update-containers.sh

# Restart just the backend (e.g. after a config tweak) without rebuilding
./deploy/rolling-restart.sh backend

# Nightly backup (wire into cron)
0 3 * * * /opt/nexusagent/deploy/backup.sh >> /data/nexusagent/backups/cron.log 2>&1

# Restore from a backup
./deploy/restore.sh 20260718T123000Z
```

## Prerequisites

- `user-data.sh` has run (Docker + Compose plugin installed, EBS at `/data`).
- `postgresql-client` present (installed by `user-data.sh`) for `pg_dump`/`psql`.
- `.env.production` exists with real RDS/ElastiCache endpoints and secrets.
- EC2 security group allows the host to reach RDS (5432) and ElastiCache (6379).

See [`../docs/deployment/aws.md`](../docs/deployment/aws.md) for the full
walkthrough, AWS resources, cost estimate, health/rollback, and troubleshooting.
