# Rollback Procedure — NexusAgent AI

Covers rolling back a bad deploy in the AWS single-instance production
environment. Two distinct rollback types: **code** (redeploy last-good commit)
and **data** (restore a pre-deploy database/upload backup). Read the whole
document before acting — the wrong order can lose data.

Companion: [`aws.md`](aws.md) §7–§8, [`PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md).

---

## 0. Triage first

| Symptom | Likely scope | First action |
|---------|--------------|--------------|
| New code shipped, backend unhealthy, **no** migration ran (or migration succeeded but app broken) | Code only | Roll back **code** (§1). Do **not** touch the DB. |
| Migration failed / partial | Code + data | Stop. Restore **DB backup** (§2) **then** redeploy old code (§1). |
| Migration succeeded but is **not backward-compatible** with old code | Code + data | Restore **DB backup** (§2) **then** redeploy old code (§1). |
| Only config/secret changed (no new code) | Config | `deploy/rolling-restart.sh backend` after fixing `.env.production`. |

**Golden rule:** migrations run against *shared* RDS. If a migration is not
backward-compatible, you MUST restore the pre-deploy DB backup *before*
redeploying old code, or the old code will crash on the new schema.

---

## 1. Roll back code (last-good commit)

Images are built from git, so a code rollback is a redeploy of the last-good
commit.

```bash
cd /opt/nexusagent
git fetch --all

# Identify the last-good SHA (from your deploy log / release notes).
LAST_GOOD=<sha-from-previous-release>
git checkout "$LAST_GOOD"        # or: git pull; git reset --hard <sha>

# Rebuild + migrate + recreate, then health-gate.
./deploy/update-containers.sh
```

`update-containers.sh` runs `alembic upgrade head`, which is a **no-op forward**
if the old commit's head matches the restored DB — safe to run after a restore.

If you only need to revert the *running* image without a git reset (e.g. the
commit is fine but the build is bad), checkout the known-good tag/SHA and
rebuild as above.

## 2. Restore a database + uploads backup

Always back up **before** `update-containers.sh` (see checklist §7). To restore:

```bash
cd /opt/nexusagent

# List available backups to pick the timestamp
ls -1 /data/nexusagent/backups/nexusagent-db-*.sql.gz

# DESTRUCTIVE: overwrites the live DB + uploads. Type RESTORE to confirm.
./deploy/restore.sh 20260718T123000Z

# Reload the backend to pick up restored data
./deploy/rolling-restart.sh backend
```

`restore.sh` requires an explicit `RESTORE` confirmation and restores both the
`pg_dump` SQL and the uploads tarball (if present). Afterward, redeploy the
matching last-good code (§1) so app and schema agree.

### Off-host (S3) backups
If `BACKUP_S3_BUCKET` was set, pull the backup set first:

```bash
aws s3 sync "s3://$BACKUP_S3_BUCKET/nexusagent-backups/" /data/nexusagent/backups/
```

---

## 3. Rollback decision tree

```
Deploy went bad?
│
├─ Was a database migration part of this deploy?
│   ├─ No ─────────────────────────► §1 (redeploy last-good commit). Done.
│   └─ Yes
│       ├─ Migration applied cleanly AND is backward-compatible?
│       │     └─ Yes ► §1 (redeploy last-good commit). DB is fine.
│       └─ Migration failed OR not backward-compatible?
│             └─ §2 (restore pre-deploy DB+uploads backup)
│                THEN §1 (redeploy last-good commit).
│
└─ Only config/secret changed?
      └─ Fix .env.production, then `deploy/rolling-restart.sh backend`.
```

---

## 4. TLS / certificate rollback

If a TLS change breaks HTTPS (bad cert path, expired cert, HSTS lockout):

1. Temporarily serve HTTP: set `NGINX_CONF=./nginx/nginx.conf` in
   `.env.production` and recreate nginx:
   ```bash
   ./deploy/rolling-restart.sh nginx   # or: ENABLE_TLS=false ./deploy/update-containers.sh
   ```
2. Re-issue with `./deploy/init-letsencrypt.sh` (see `tls.md`) once the cause
   is fixed.
3. **HSTS note:** if `Strict-Transport-Security` was served with `max-age`,
   browsers cache it. During a TLS rollback to HTTP, affected clients may refuse
   HTTP for the cached duration. Communicate a maintenance window or use a
   short `max-age` during early rollout.

---

## 5. Post-rollback verification

- [ ] `curl -fsS http://<host>/health` (or `https://` once TLS restored)
      returns `{"status":"healthy"}`.
- [ ] `docker compose -f docker-compose.aws.yml --env-file .env.production ps`
      shows all services `healthy`.
- [ ] Frontend loads; chat/agent flows work end-to-end.
- [ ] `docker compose ... exec -T backend alembic current` matches the expected
      revision for the restored code.
- [ ] Backups resume normally on the next cron run.

---

## 6. Prevention

- Tag every production release (`git tag -a vX.Y.Z`) so rollbacks target a known
  SHA, not ad-hoc commits.
- Always `./deploy/backup.sh` before a code update; store the timestamp with the
  release note.
- Review each migration's downgrade path; prefer additive (backward-compatible)
  migrations in hotfixes.
- Dry-run certificate renewal (`sudo certbot renew --dry-run`) before relying on
  auto-renewal.
