# Backup & Recovery

**Phase 5 — Step 7 deliverable**
**Scope:** Single-instance AWS deployment (Docker Compose + RDS + ElastiCache + EBS)
**Companion docs:** `docs/deployment/backups.md` (operational detail),
`docs/deployment/aws.md` (architecture), `PHASE_5_REPORT.md` (roll-up)

> This document is the operator runbook for backup, restore, and disaster recovery.
> It consolidates the scripts in `deploy/` (`backup.sh`, `restore.sh`) and the policy
> in `docs/deployment/backups.md` into one reference for on-call/ops.

---

## 1. What Is Backed Up

| Asset | Tool | On-disk artifact | Cadence |
|-------|------|------------------|---------|
| PostgreSQL (RDS) | `pg_dump --clean --if-exists` | `nexusagent-db-<ts>.sql.gz` | Nightly |
| Uploaded documents (`/data/nexusagent/uploads`) | `tar -czf` | `nexusagent-uploads-<ts>.tar.gz` | Nightly |
| Compose/env config | git + manual copy | repo + `.env.production` (S3) | On change |

**Redis is intentionally NOT backed up by the script.** It is a cache + Celery
broker/result store and is re-populated on restart. If Redis is ever promoted to a
system of record, snapshot it separately (`redis-cli SAVE` → copy the RDB, or enable
AOF).

---

## 2. The Backup Script

`deploy/backup.sh` (runs on the EC2 host as the `deploy` user):

```bash
# Defaults (override via env vars — never edit the script):
ENV_FILE=./.env.production
BACKUP_DIR=/data/nexusagent/backups
RETENTION_DAYS=7

# Run nightly via cron (see §6):
/opt/nexusagent/deploy/backup.sh
```

What it does:
1. Loads DB connection vars from `.env.production` (secret never printed).
2. `pg_dump -h $RDS_ENDPOINT -U $POSTGRES_USER -d $POSTGRES_DB --no-owner --clean --if-exists`
   piped to `gzip` → `nexusagent-db-<UTC-ts>.sql.gz`.
3. `tar -czf` of `/data/nexusagent/uploads` → `nexusagent-uploads-<ts>.tar.gz`.
4. Prunes local backups older than `RETENTION_DAYS`.
5. **Optional off-host copy:** if `BACKUP_S3_BUCKET` is set, syncs the backup dir to
   `s3://$BACKUP_S3_BUCKET/nexusagent-backups/`.

Override example (longer local retention + S3 target):

```bash
RETENTION_DAYS=30 BACKUP_S3_BUCKET=nexusagent-backups-prod \
  /opt/nexusagent/deploy/backup.sh
```

Requires `pg_dump` (installed by `user-data.sh` via `postgresql-client`) and network
reach from the host to RDS (security group `nexusagent-rds` allows 5432 from
`nexusagent-ec2`).

---

## 3. Restore

`deploy/restore.sh <ts>` is **destructive** — it overwrites the target database and
uploads and requires typing `RESTORE` at the prompt.

```bash
# List available backups:
ls -1 /data/nexusagent/backups/nexusagent-db-*.sql.gz

# Restore a backup set (DB + uploads):
/opt/nexusagent/deploy/restore.sh 20260718T123000Z
```

What it does:
1. Resolves `nexusagent-db-<ts>.sql.gz` + `nexusagent-uploads-<ts>.tar.gz`.
2. Confirms the `RESTORE` word interactively.
3. `gunzip -c db.sql.gz | PGPASSWORD=... psql -h $RDS_ENDPOINT -U $POSTGRES_USER -d $POSTGRES_DB`.
4. Restores uploads tarball to `/data/nexusagent`, re-chowning to uid/gid 1001
   (the backend's non-root user).
5. Prints the rolling-restart command to reload the backend.

After restore: `./deploy/rolling-restart.sh backend` so the app picks up the new
schema/data.

> **Migrations matter.** Backups are logical `pg_dump` snapshots of *whatever schema
> is live*. Restoring an old backup under new code can desync from Alembic. When
> rolling back a deploy, restore the DB **first**, then deploy the matching old
> commit (see `docs/deployment/aws.md` §7).

---

## 4. Redis Persistence

Redis is **not** part of the backup set. Two cases:

- **ElastiCache (recommended):** managed service; durability is the provider's
  concern. Restart re-populates the cache from RDS on first access. Scheduled jobs /
  in-flight Celery tasks queued in Redis (`db 1`/`db 2`) are lost on failover — they
  are retryable by design.
- **On-host Redis container:** if you run Redis in a container (see `aws.md` §5,
  Option B), mount a volume and rely on RDB/AOF for local durability. Add an explicit
  `SAVE` + copy step if you need point-in-time Redis backups.

---

## 5. Disaster Recovery (DR)

Trigger when the primary host and/or RDS is unrecoverable.

### DR checklist

- [ ] **Declare incident** — page on-call (`ServiceDown` / `DatabaseUnavailable`
      critical alerts).
- [ ] **Confirm blast radius** — app host, RDS, ElastiCache, or EBS?
- [ ] **Provision replacement** — new EC2 (or reactivate the AMI), attach a fresh EBS
      at `/data`.
- [ ] **Restore config** — clone repo at `/opt/nexusagent`; restore `.env.production`
      from S3 (`aws s3 cp s3://<bucket>/.env.production .`) if not on the host.
- [ ] **Restore data** — `aws s3 sync` latest S3 backup locally, then
      `deploy/restore.sh <ts>` (type `RESTORE`).
- [ ] **Bring up services** — `./deploy/init-deploy.sh` (build, migrate, health-gate).
- [ ] **Verify** — `/health/live` and `/health/ready` both `200`;
      `nexusagent_db_up == 1` on `nx-db`; login + one chat round-trip succeed.
- [ ] **Repoint DNS / re-issue TLS** if the public endpoint changed.
- [ ] **Notify stakeholders**, open a post-incident review, update this checklist.

### RTO / RPO targets (suggested)

| Objective | Target | Notes |
|-----------|--------|-------|
| **RPO** (data loss) | ≤ 24 h | Nightly backup; intraday writes lost on full restore. Tighten with RDS automated snapshots (1 h) + PITR. |
| **RTO** (recovery) | ≤ 4 h | Host provisioning + EBS restore + migration + smoke test. |

Tighten RPO further with **RDS automated snapshots** (e.g. 1-hour) and **Point-In-Time
Recovery** — these are managed by RDS and complement (do not replace) the logical
`pg_dump` backups, which remain the portable, cross-cloud restore path.

---

## 6. Retention Policy

| Tier | Where | Default | Rationale |
|------|-------|---------|-----------|
| Hot (daily) | EBS `/data/nexusagent/backups` | **7 days** (`RETENTION_DAYS=7`) | Fast local restore for the common "oops" window. |
| Warm (weekly) | S3 `s3://<bucket>/nexusagent-backups/` | **35 days** | Survives EBS loss / host replacement. |
| Cold (monthly) | S3 Glacier via lifecycle rule | **12 months** | Audit / long-term compliance. |

Cron (installed by `deploy/setup-cron.sh`):

```cron
# Nightly 03:00 host time; prunes then syncs to S3 if configured.
0 3 * * * /opt/nexusagent/deploy/backup.sh >> /data/nexusagent/backups/cron.log 2>&1
```

Apply the S3 → Glacier lifecycle transition (after 35 days, expire after ~395 days).
Monitor backup freshness via the `DatabaseBackupAge` check described in
`docs/deployment/observability.md`.

---

## 7. Restore Verification (do this BEFORE you need it)

A backup you have never restored is a hope, not a backup. Verify **monthly**.

### 7.1 Integrity check (cheap, every run)

```bash
TS=20260718T030000Z
# gzip must decompress without error
gunzip -t /data/nexusagent/backups/nexusagent-db-$TS.sql.gz
# SQL must be syntactically loadable — dry-run into a throwaway DB
PGPASSWORD=test psql -h localhost -U test -d postgres -c "DROP DATABASE IF EXISTS restore_check;"
PGPASSWORD=test psql -h localhost -U test -c "CREATE DATABASE restore_check;"
gunzip -c /data/nexusagent/backups/nexusagent-db-$TS.sql.gz \
  | PGPASSWORD=test psql -h localhost -U test -d restore_check >/dev/null \
  && echo "DB RESTORE_OK"
# uploads tarball lists cleanly
tar -tzf /data/nexusagent/backups/nexusagent-uploads-$TS.tar.gz >/dev/null \
  && echo "UPLOADS_RESTORE_OK"
```

### 7.2 Full dress rehearsal (monthly)

1. Spin a scratch RDS or local Postgres.
2. Restore the DB: `gunzip -c nexusagent-db-$TS.sql.gz | PGPASSWORD=... psql -h <scratch> -U ... -d nexusagent`.
3. Restore uploads to a scratch dir: `mkdir -p /tmp/restore-check && tar -xzf nexusagent-uploads-$TS.tar.gz -C /tmp/restore-check`.
4. Boot a staging backend against `<scratch>`, run `/health/ready`, smoke-test chat.
5. Tear down scratch.

Record the restore time. If it exceeds RTO, trim the dataset or add `pg_dump -j`
parallelism.

---

## 8. Security of Backups

- Backups contain **PII and document content**. The S3 bucket uses least-privilege
  (`deploy/iam-policy.json` → `S3Uploads*`) and should be **SSE-KMS encrypted**.
- `.env.production` in S3 must be a **separate** object under its own KMS key,
  restricted to the deploy role — never bundled into the public backup set.
- `restore.sh` destroys the live DB and requires typing `RESTORE`; keep the script
  out of untrusted hands.

---

## 9. Quick Reference

| Task | Command |
|------|---------|
| Ad-hoc backup | `deploy/backup.sh` |
| List backups | `ls -1 /data/nexusagent/backups/nexusagent-db-*.sql.gz` |
| Restore | `deploy/restore.sh <ts>` (types `RESTORE`) |
| Reload after restore | `deploy/rolling-restart.sh backend` |
| Verify backup | see §7.1 |
| DR bring-up | `deploy/init-deploy.sh` after restoring config + data |
