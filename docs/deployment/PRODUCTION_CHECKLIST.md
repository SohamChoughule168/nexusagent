# Production Deployment Checklist — NexusAgent AI

Use this checklist for every deploy to the AWS single-instance production
environment. It pairs with [`aws.md`](aws.md), [`tls.md`](tls.md), and
[`ROLLBACK.md`](ROLLBACK.md). Each box should be ticked (or explicitly N/A'd)
before a deploy is declared complete.

---

## 1. Pre-flight (one-time, per environment)

- [ ] AWS account + IAM instance role attached (policy in `deploy/iam-policy.json`).
- [ ] VPC + subnet; security groups `nexusagent-ec2` (22/80/443), `nexusagent-rds`
      (5432 from ec2), `nexusagent-redis` (6379 from ec2) created.
- [ ] EC2 instance launched (t3.medium) with `user-data.sh` as cloud-init; it
      installed Docker, certbot, gettext-base, mounted EBS at `/data`, cloned
      the repo to `/opt/nexusagent`, and enabled the `nexusagent` systemd unit.
- [ ] RDS PostgreSQL 16 (`db.t4g.micro`, gp3 20 GiB) created; `nexusagent`
      user/db provisioned; automated snapshots enabled (≥7 days).
- [ ] ElastiCache Redis 7 (`cache.t4g.micro`) created; SG allows only ec2.
- [ ] Domain registered; Route 53 hosted zone; A/AAAA record points at the
      instance Elastic IP.
- [ ] Elastic IP attached (stable public IP across reboots).
- [ ] SSH key / SSM Session Manager access confirmed for the `deploy` user.

## 2. Secrets & environment

- [ ] `.env.production` created at the repo root (`cp env.production.example
      .env.production`) and all `replace-with-*` values replaced.
- [ ] All **required** secrets present (no compose config failure):
      `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`,
      `SECURITY_PASSWORD_SALT`, `BACKEND_CORS_ORIGINS`.
- [ ] `DOMAIN` and `LETSENCRYPT_EMAIL` set.
- [ ] `BACKEND_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` use the real
      `https://` origin (after TLS) — or the http origin for the very first
      bring-up.
- [ ] `.env.production` is `chmod 600`, owned by `deploy`, and **gitignored**.
- [ ] Secrets Manager option: `AWS_SECRETS_MANAGER_SECRET_NAME` set and
      `deploy/fetch-secrets.sh` verified to render `.env.production`
      (preferred for production; keeps plaintext off the host between deploys).
- [ ] `docker compose -f docker-compose.aws.yml --env-file .env.production
      config` validates with no errors.

## 3. First deploy

- [ ] `./deploy/init-deploy.sh` completes: images build, containers start,
      `alembic upgrade head` applies, backend `/health` returns healthy.
- [ ] `curl -fsS http://<host>/health` returns `{"status":"healthy"}`.
- [ ] Frontend loads at `http://<host>/`.
- [ ] Note the current commit SHA (`git rev-parse HEAD`) for rollback.

## 4. TLS / HTTPS (`docs/deployment/tls.md`)

- [ ] DNS A/AAAA for `DOMAIN` resolves to the instance; SG allows 80+443.
- [ ] `./deploy/init-letsencrypt.sh` issued the certificate (HTTP→HTTPS
      redirect active; HSTS present).
- [ ] `curl -fsS https://<DOMAIN>/health` succeeds with a valid cert.
- [ ] `NGINX_CONF=./nginx/tls.conf` persisted in `.env.production`.
- [ ] `curl -I http://<DOMAIN>/` returns `301` to `https://`.
- [ ] `./deploy/setup-cron.sh` installed nightly backup + certbot renewal.
- [ ] `crontab -l` shows the `nexusagent-backup` and `nexusagent-certbot` jobs.

## 5. Post-deploy verification

- [ ] `docker compose -f docker-compose.aws.yml --env-file .env.production ps`
      shows all services `healthy`.
- [ ] Backend API reachable: `curl -fsS https://<DOMAIN>/api/v1/...` (or the
      health/version endpoint) returns 200/expected body.
- [ ] WebSocket upgrade works (chat UI connects without errors).
- [ ] Uploads persist: upload a file, confirm it lands in
      `/data/nexusagent/uploads` and survives a container recreate.
- [ ] Security headers present: `curl -I https://<DOMAIN>/` shows
      `Strict-Transport-Security`, `X-Content-Type-Options`, `Content-Security-
      Policy`, etc.
- [ ] Backups: `./deploy/backup.sh` produces a DB dump + uploads tarball;
      verify with a test restore in a scratch RDS or `pg_restore --list`.
- [ ] `deploy/nexusagent.service` is enabled (`systemctl is-enabled nexusagent`)
      so the stack restarts after a host reboot.

## 6. Ongoing operations

- [ ] Nightly backups confirmed present in `/data/nexusagent/backups` (and S3 if
      `BACKUP_S3_BUCKET` is set).
- [ ] Certificate renewal verified: `sudo certbot renew --dry-run`.
- [ ] Monitoring/Grafana reachable (see `monitoring/`) and scraping.
- [ ] Log rotation in place (json-file `max-size`/`max-file` set per service).
- [ ] Patch cadence: `apt-get upgrade` on the host on a schedule; rebuild images
      on dependency bumps.

## 7. Before every code update

- [ ] `./deploy/backup.sh` taken (DB + uploads) and the timestamp recorded.
- [ ] Current commit SHA recorded (`git rev-parse HEAD`).
- [ ] Migration backward-compatibility reviewed (shared RDS — see ROLLBACK.md).
- [ ] Maintenance window noted if JWT/secret rotation or breaking migration.

---

### Emergency contacts / escalation
- Host unreachable: check EC2 status, SG, and `systemctl status nexusagent`.
- DB unhealthy: see `aws.md` §7 (failure recovery) and `ROLLBACK.md`.
- TLS broken: see `tls.md` (re-issue / fallback to HTTP) and `ROLLBACK.md`.
