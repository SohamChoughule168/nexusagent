# Backups & Disaster Recovery

Operational backup, retention, restore-verification and DR procedures for a
production NexusAgent deployment. Companion to
[`observability.md`](./observability.md).

> Scope: single-instance AWS deployment (Milestone 7). No multi-region,
> no automated cross-region replication. See the
> [do-not-implement list](../README.md) — auto-scaling and multi-region are
> out of scope.

## What is backed up

| Asset | Tool | On-disk artifact |
|-------|------|------------------|
| PostgreSQL (RDS / local) | `pg_dump --clean --if-exists` | `nexusagent-db-<ts>.sql.gz` |
| Uploaded documents (`/data/nexusagent/uploads`) | `tar -czf` | `nexusagent-uploads-<ts>.tar.gz` |
| Compose/env config | manual copy (see DR) | git repo + `.env.production` (in S3) |

Redis is **not** backed up by the script — it is a cache/queue and is
re-populated on restart. If you use Redis as a system of record, snapshot it
separately (`redis-cli SAVE` → copy the RDB) or enable AOF.

The scripts live in [`../../deploy`](../../deploy): `backup.sh`, `restore.sh`.

## Schedule

```cron
# Nightly, 03:00 host time. Prunes, then syncs to S3 (if configured).
0 3 * * * /opt/nexusagent/deploy/backup.sh >> /data/nexusagent/backups/cron.log 2>&1
```

The dump is taken with `--clean --if-exists` so it can be piped straight into
`psql` for a restore.

## Retention policy

| Tier | Where | Default | Rationale |
|------|-------|---------|-----------|
| Hot (daily) | EBS `/data/nexusagent/backups` | **7 days** (`RETENTION_DAYS=7`) | Fast local restore for the most common "oops" window. |
| Warm (weekly) | S3 `s3://<bucket>/nexusagent-backups/` | **35 days** | Survives EBS loss / host replacement. |
| Cold (monthly) | S3 Glacier / lifecycle rule | **12 months** | Audit / long-term compliance. |

Apply the S3 lifecycle from `aws.md` (transition to Glacier after 35 days,
expire after 395 days). Monitor backup age with the
`DatabaseBackupAge` check described in `observability.md` (troubleshooting).

### Tuning

Override without editing the script:

```bash
RETENTION_DAYS=30 BACKUP_S3_BUCKET=my-co-backups \
  /opt/nexusagent/deploy/backup.sh
```

## Restore verification (do this *before* you need it)

A backup you have never restored is a hope, not a backup. Verify monthly.

### 1. Integrity check (every run, cheap)

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

### 2. Full dress rehearsal (monthly)

Restore into a **separate** RDS instance / database and point a staging backend
at it:

```bash
# 1. spin a scratch RDS or local Postgres
# 2. restore the DB
gunzip -c nexusagent-db-$TS.sql.gz | PGPASSWORD=... psql -h <scratch> -U ... -d nexusagent
# 3. restore uploads to a scratch dir
mkdir -p /tmp/restore-check && tar -xzf nexusagent-uploads-$TS.tar.gz -C /tmp/restore-check
# 4. boot a staging backend against <scratch>, run /health/ready, smoke-test chat
# 5. tear down scratch
```

Record the restore time. If it exceeds your RTO (see below), trim the dataset
or add parallelism (`pg_dump -j`).

## Disaster recovery checklist

Trigger when the primary host/RDS is unrecoverable.

- [ ] **Declare incident** — page on-call (see `observability.md` alert catalog).
- [ ] **Confirm blast radius** — is it the app host, RDS, ElastiCache, or EBS?
- [ ] **Provision replacement** — new EC2 (or reactivate the AMI from `aws.md`),
      attach a fresh EBS volume at `/data`.
- [ ] **Restore config** — clone repo at `/opt/nexusagent`, restore
      `.env.production` from S3 (`aws s3 cp s3://<bucket>/.env.production .`).
- [ ] **Restore data** — pull latest S3 backup locally, then
      `deploy/restore.sh <ts>` (type `RESTORE` at the prompt).
- [ ] **Bring up services** — `./deploy/init-deploy.sh` (build, migrate, gate).
- [ ] **Verify** — `/health/live` and `/health/ready` both `200`,
      dashboards show `nexusagent_db_up == 1`, login + one chat round-trip work.
- [ ] **Point DNS / re-issue TLS** if the public endpoint changed.
- [ ] **Notify stakeholders**, open a post-incident review, update this checklist
      with anything that was missing.

## RTO / RPO targets (suggested)

| Objective | Target | Notes |
|-----------|--------|-------|
| RPO (data loss) | ≤ 24 h | Nightly backup; intraday writes are lost on full restore. |
| RTO (recovery) | ≤ 4 h | Driven by host provisioning + EBS restore + migration time. |

Tighten RPO with RDS automated snapshots (e.g. 1 h) and Point-In-Time Recovery.

## Security

- Backups contain PII and document content. The S3 bucket uses least-privilege
  (see `aws-iam.md`) and should be encrypted (SSE-KMS).
- `.env.production` in S3 must be a **separate** object with its own KMS key and
  restricted to the deploy role — never bundled into the public backup set.
- Restore requires typing `RESTORE` and destroys the live DB — keep the script
  out of untrusted hands.
