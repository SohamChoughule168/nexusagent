# NexusAgent — GA Release Checklist

**Target release:** `1.0.0` (tagged `v1.0.0`)
**Purpose:** the consolidated pre-General-Availability gate. Run every section
before promoting the public beta to GA. Each item must be ticked or explicitly
marked N/A with a reason.

This document is the operator's single source of truth for the GA cut. It draws
on [`docs/deployment/PRODUCTION_CHECKLIST.md`](../docs/deployment/PRODUCTION_CHECKLIST.md),
[`docs/deployment/ROLLBACK.md`](../docs/deployment/ROLLBACK.md),
[`docs/deployment/BACKUP_AND_RECOVERY.md`](../docs/deployment/BACKUP_AND_RECOVERY.md),
[`docs/deployment/security-checklist.md`](../docs/deployment/security-checklist.md),
and [`docs/BETA_READINESS.md`](../docs/BETA_READINESS.md).

---

## 1. Deployment

- [ ] **Image built & tagged** — `v1.0.0` image built; `BUILD_GIT_SHA` /
      `BUILD_TIMESTAMP` injected and visible via `GET /version`.
- [ ] **Migrations** — `alembic current` matches the release; migrations are
      additive (no destructive/backward-incompatible change in the GA hotfix).
- [ ] **Single-host / AWS compose verified** — `docker compose -f docker-compose.prod.yml up -d --build`
      (or `docker-compose.aws.yml`) starts all services `healthy`.
- [ ] **nginx** — TLS live; HTTP→HTTPS redirect + HSTS; `/api` routing; no route
      to `/docs`, `/redoc`, `/openapi.json` (docs disabled in prod).
- [ ] **Env sourced from secrets** — `env.production` (or Secrets Manager) sets
      every `replace-with-*`; no `change-me-*` defaults; `DOCS_ENABLED=false`.
- [ ] **Resource limits** — `mem_limit` / `cpus` / `pids_limit` set on all
      services; backend + frontend run `read_only` + `tmpfs: /tmp` with
      `cap_drop: [ALL]`.
- [ ] **Fresh-clone smoke** — a clean `git clone` + the documented one-command
      launch brings up backend, frontend, db, redis, nginx.

## 2. Monitoring

- [ ] **Health probes** — `/health`, `/health/ready`, `/health/startup` return
      green; aliases `/liveness`, `/ready` work; `/health/db`, `/health/redis`
      report dependency status.
- [ ] **Metrics** — `/metrics` scraped by Prometheus; Grafana dashboards load
      (endpoint not proxied by nginx — internal only).
- [ ] **Logs** — structured JSON logs shipping to the aggregation target; every
      request carries `X-Request-ID` and echoes it in the response.
- [ ] **Alerts** — error-rate / p95 / 5xx alerts configured and a test alert
      fired.
- [ ] **Version first** — support confirms a reporter's `GET /version`
      `build_git_sha` before debugging (catches stale images).

## 3. Backups

- [ ] **DB backups** — nightly `deploy/backup.sh`; S3 (off-host) copy configured.
- [ ] **Upload volume** — backed up with the DB or snapshotted independently.
- [ ] **Restore rehearsed** — a test restore from the latest backup succeeds
      (monthly cadence).
- [ ] **Restore authority** — only on-call may run `deploy/restore.sh`
      (destructive; requires typed `RESTORE`).

## 4. Security

- [ ] **Secrets** — `JWT_SECRET_KEY` / `JWT_REFRESH_SECRET_KEY` distinct 32-byte
      values; `SECURITY_PASSWORD_SALT` set; DB password strong & unique.
- [ ] **Config validation** — production boot (DEBUG=false) refuses insecure
      defaults (`config.validate()` passes).
- [ ] **CORS** — `BACKEND_CORS_ORIGINS` = real production origin(s) only.
- [ ] **Security headers** — CSP, `X-Content-Type-Options: nosniff`,
      `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`,
      `Permissions-Policy` set (nginx edge; mirrored by the backend middleware).
- [ ] **Auth** — `/auth/change-password` requires a Bearer session (target user
      derived from the token, not the request body — K1 resolved). Invalid token
      → 401; missing/invalid tenant membership → 403.
- [ ] **API docs disabled** — `curl -fsS https://<domain>/docs` → 404
      (`DOCS_ENABLED=false`).
- [ ] **Rate limiting** — `RATE_LIMIT_PER_MINUTE` set; burst returns 429 with
      `Retry-After`.
- [ ] **Dependency scans** — `pip-audit`, `npm audit`, `bandit`, `trivy` green
      (residuals `ecdsa`/`pyasn1` via python-jose and dev-only frontend advisories
      are documented in `DEPENDENCY_REMEDIATION_REPORT.md`; no scan disabled).
- [ ] **Firewall / Security Group** — only 22 (or SSM), 80, 443 open; backend /
      frontend ports on the internal bridge only.

## 5. Testing

- [ ] **Backend suite green** — ~440 tests pass in CI (auth, tenant isolation,
      RAG/chat, memory, tools, routing, rate limiting, API keys).
- [ ] **New GA tests added** — `tests/test_change_password.py` (session-required
      change-password) and `tests/test_registration.py` (duplicate-slug → 409)
      pass.
- [ ] **Frontend** — `tsc --noEmit`, `next lint`, and `vitest run` green.
- [ ] **Critical E2E paths** — register → login → create KB → upload PDF → chat
      with citations; agent builder; demo workspace all verified.
- [ ] **Docker validation** — `docker-validation.yml` passes (image builds,
      healthchecks, non-root).

## 6. Documentation

- [ ] **README / User Guide / FAQ** — consistent; FAQ published
      (`docs/FAQ.md`); points a new user clone → run → talk to the demo agent.
- [ ] **API docs accuracy** — `docs/user-guide/api-examples.md` matches the
      running endpoints (docs endpoint itself is prod-disabled).
- [ ] **Known issues** — `docs/BETA_READINESS.md` updated with GA classification
      (§3.1); K1/K4/K6 fixed, K2/K3/K5 accepted for GA.
- [ ] **Deployment + ops docs** — `OPERATIONS.md`, `ARCHITECTURE.md`,
      `docs/deployment/*` current; troubleshooting consolidated.
- [ ] **Version numbers** — `VERSION`, `pyproject.toml`, `APP_VERSION`,
      `frontend/package.json`, `.env.example` all `1.0.0`.

## 7. Rollback

- [ ] **Runbook rehearsed** — `docs/deployment/ROLLBACK.md` walked once.
- [ ] **Last-good tag identified** — `git describe` / previous `v1.0.0` image
      pinned for code rollback.
- [ ] **Data rollback plan** — if a migration ran, backup-then-redeploy order is
      understood (restore pre-deploy DB *then* redeploy last-good code).
- [ ] **Verify post-rollback** — `/health` healthy; chat/agent flows work;
      `alembic current` matches restored code.

## 8. Support readiness

- [ ] **Triage queue** — issue tracker / shared inbox monitored during GA hours.
- [ ] **Repro path** — sign into the Brightpath demo workspace
      (`demo@nexusagent.dev` / `nexusagent-demo`) to reproduce chat/KB issues.
- [ ] **Log correlation** — ask reporters for `X-Request-ID`; grep logs / Grafana.
- [ ] **Escalation** — request ID(s), last deploy tag, backend logs around the
      timestamp, Prometheus signals (error rate, p95).
- [ ] **Known-issues pointer** — link `docs/BETA_READINESS.md` §3 before filing
      new bugs.
- [ ] **Rollback authority** — only on-call runs `deploy/restore.sh`.

---

### GA go / no-go

- **No Critical or High issues open** (K1 resolved; see `docs/BETA_READINESS.md` §3.1).
- **All sections above ticked or N/A** → promote beta → GA.
- **Release recommendation:** see `docs/reports/MILESTONE_A_GA_REPORT.md`.
