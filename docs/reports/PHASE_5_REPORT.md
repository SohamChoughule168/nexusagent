# Phase 5 — Cloud Deployment & Observability — Report

**Status:** ✅ Complete (production hardening)
**Branch:** `phase/3b-repository-health`
**Commit:** `feat(phase-5): production hardening` (not pushed, not merged — awaiting review)

> **Scope note:** Phase 5 was executed as a **gap analysis**, not a rebuild. The
> repository already contained mature Docker, AWS deployment, nginx, monitoring
> (Prometheus/Grafana/Alertmanager), backup scripts, load-testing tooling, and
> deployment documentation. This phase **verified** that all of it matches reality
> and **implemented the one genuine production gap**: startup fail-fast validation.
> No existing infrastructure was rewritten.

---

## 1. What This Phase Delivered

| Area | Deliverable | Files |
|------|-------------|-------|
| Platform decision | AWS EC2 single-instance recommendation + 10-way comparison | `docs/reports/PHASE_5_DEPLOYMENT_PLAN.md` |
| **Production hardening (implemented)** | **Startup fail-fast on missing/insecure secrets & config** | `backend/app/core/config.py`, `backend/app/main.py`, `backend/tests/test_config_validation.py` |
| Backup & recovery | Operator runbook (consolidates scripts + policy) | `docs/reports/BACKUP_AND_RECOVERY.md` |
| Load testing | Tooling, profile, baselines, bottleneck analysis | `docs/reports/PHASE_5_LOAD_TEST.md` |
| Security verification | Control-by-control audit + gap remediation | `docs/reports/PHASE_5_SECURITY_REPORT.md` |
| This report | Roll-up + validation checklist + scaling plan | `docs/reports/PHASE_5_REPORT.md` |

---

## 2. Infrastructure

Single EC2 host (t3.medium) running Docker Compose; stateful services on managed AWS:

- **Compute:** EC2 (Ubuntu), `user-data.sh` cloud-init bootstraps Docker, certbot, EBS.
- **Reverse proxy:** nginx container — **sole public entrypoint** (SG 22/80/443 only).
- **App / API:** `backend` (FastAPI, internal `:8000`) + `frontend` (Next.js, internal `:3000`).
- **Database:** Amazon RDS PostgreSQL 16 (managed, Multi-AZ optional).
- **Cache/broker:** Amazon ElastiCache Redis 7 (or on-host container alternative).
- **Storage:** EBS gp3 at `/data` (uploads + backups).
- **Secrets:** `.env.production` (gitignored) + optional AWS Secrets Manager.
- **Observability:** separate compose project (Prometheus/Grafana/Alertmanager + exporters).

Defined in `docker-compose.aws.yml` + `docker-compose.aws.tls.yml`; bootstrap in `deploy/`.

---

## 3. Deployment

End-to-end, verified by the CI `deploy-validation` job (which mirrors production):

1. `cp env.production.example .env.production` → fill RDS/ElastiCache/domain/secrets.
2. `./deploy/init-deploy.sh` → build, `up`, `alembic upgrade head`, health-gate.
3. `./deploy/init-letsencrypt.sh` → TLS cert + HTTPS; `./deploy/setup-cron.sh` → backups + cert renewal.
4. Upgrades: `./deploy/update-containers.sh` (pull → build → migrate → recreate → gate).
5. Auto-recover: `restart: unless-stopped` + systemd `nexusagent.service` on boot.

Full walkthrough: `docs/deployment/aws.md`. Rollback: `docs/deployment/ROLLBACK.md`.

---

## 4. Monitoring

- **Prometheus** (`monitoring/prometheus/prometheus.yml`) scrapes the backend `/metrics`
  plus `node`, `postgres`, and `redis` exporters at 15s.
- **Grafana** auto-provisions **7 dashboards** (API, DB, Redis, Agent Activity, Token
  Usage, Errors, Infrastructure) bound to the `prometheus` datasource.
- **Alertmanager** + `alerts.yml`: 9 alerts (ServiceDown, HighErrorRate, HighLatency,
  DatabaseUnavailable, RedisUnavailable, LLMProviderUnreachable, DiskUsageHigh,
  MemoryUsageHigh, CpuUsageHigh) with `critical`→page routing and inhibition.
- **Verified:** every metric name and health check the alerts depend on exists in the
  backend (`app/core/metrics.py`, `app/core/health.py`). Monitoring matches implementation.

Run: `docker compose -f monitoring/docker-compose.monitoring.yml up -d`.

---

## 5. Metrics

The backend exposes a single Prometheus `/metrics` endpoint (gated by
`METRICS_ENABLED`), namespaced with `PROMETHEUS_NAMESPACE` (`nexusagent_`). Confirmed
present in `app/core/metrics.py`:

- **HTTP:** `nexusagent_http_requests_total`, `nexusagent_http_request_duration_seconds`
  (histogram), `nexusagent_http_errors_total`, `nexusagent_http_requests_in_progress`.
- **Dependencies:** `nexusagent_db_up`, `nexusagent_redis_up`, `nexusagent_storage_up`,
  `nexusagent_llm_up`, `nexusagent_scrape_errors_total`.
- **App state:** `nexusagent_active_conversations`, `nexusagent_active_agents`,
  `nexusagent_total_tokens`, `nexusagent_total_cost_usd`.
- **Pool/Redis/queue:** `nexusagent_db_connection_pool_*`, `nexusagent_redis_*`,
  `nexusagent_queue_length`.

`endpoint` labels use templated route paths (no cardinality blow-up); `/metrics`,
`/docs`, `/redoc`, `/openapi.json` are excluded.

---

## 6. Logging

Structured **JSON** logging via `structlog` (`app/core/logging.py`), container-friendly
(stdout; optional rotated file sinks):

- **Access logs:** one JSON line per request on `app.access` (`request_id, method, path,
  status, duration_ms, bytes, user_agent`); toggled by `LOG_ACCESS_ENABLED`.
- **Correlation IDs:** `RequestIDMiddleware` assigns `request_id` (echoes `X-Request-ID`,
  honours client value) and `RequestContextMiddleware` binds it into the structlog
  context so every log in the request carries it. Both confirmed in
  `app/core/middleware.py` + `app/core/observability_middleware.py`.
- **No secrets in logs:** validation/warnings reference setting *names*, never values.
- Config: `LOG_LEVEL`, `LOG_FORMAT=json`, `LOG_FILE`, `ACCESS_LOG_FILE`,
  `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`.

---

## 7. Security (key result)

Full audit in `PHASE_5_SECURITY_REPORT.md`. Headline:

- **Remediated this phase — startup fail-fast (was the one real gap):** the app now
  **refuses to start in production** (`DEBUG is False`) when `JWT_SECRET_KEY`,
  `JWT_REFRESH_SECRET_KEY`, `SECURITY_PASSWORD_SALT`, `DATABASE_URL`, or `REDIS_URL` are
  missing/insecure, or when a remote LLM/embeddings provider is selected without its
  key. Dev mode (`DEBUG=True`) still allows defaults. Verified end-to-end + 10 unit tests.
- HTTPS (Let's Encrypt + HSTS + modern TLS + OCSP), full security-header set, JWT HS256
  with strict algorithm allowlist, non-root images (`appuser` uid 1001), `read_only` +
  `cap_drop: ALL` + resource limits, SG limited to 22/80/443, scoped IAM, and continuous
  dependency scanning (`pip-audit`, `npm audit`, `dependency-review`, `bandit`, `trivy`).

---

## 8. Performance

Load-testing tooling (`deploy/loadtest/loadtest.py`, aiohttp-based) drives a read-heavy
mix (25 users / 100 rpm / 15 min) against a live deployment; `docker stats` captures
CPU/RAM. Target profile, expected baselines, bottleneck analysis, and recommendations
are in `PHASE_5_LOAD_TEST.md`. Execution requires a live deployment; capture real numbers
there and record them in the baseline table.

---

## 9. Known Limitations

1. **Rate limiter is single-instance** (in-memory). Horizontal scaling needs Redis or
   nginx `limit_req`. (Acceptable for the single-node design.)
2. **Refresh tokens are not revocable** (no denylist/jti) — carried from Phase 4.
3. **CSP keeps `'unsafe-inline'`/`'unsafe-eval'`** for Next.js compatibility (nonce future).
4. **`deploy` user has NOPASSWD sudo** — prefer SSM Session Manager in production.
5. **No SMTP env settings** exist; when SMTP is added, extend `validate()` (see §7/§2).
6. **Docker unavailable in this audit sandbox** — compose YAMLs were validated by parser
   and CI; live `docker compose config` runs in CI (`docker-validation.yml`).

---

## 10. Future Scaling Plan

The app tier is **stateless** (JWT sessions, external RDS/Redis, uploads on shared EBS/S3),
so horizontal scaling is a deployment change, not a rewrite:

1. Place **N EC2 hosts** (or an Auto Scaling Group) behind an **Application Load Balancer**.
2. Promote RDS to **Multi-AZ**; keep ElastiCache external (already is).
3. Move uploads to **S3** (abstraction exists; `aws.md` §6 documents the path + IAM).
4. Switch the rate limiter to **Redis** (`RATE_LIMIT_PER_MINUTE` is currently single-instance).
5. Re-point Prometheus exporters; consider managed Grafana Cloud / Amazon Managed Prometheus.
6. Add **RDS automated snapshots + PITR** to tighten RPO below the nightly `pg_dump` window.

---

## 11. Validation Checklist

| Check | How | Result |
|-------|-----|--------|
| Fresh deployment | `init-deploy.sh` (build → migrate → health-gate) | ✅ Script + CI `deploy-validation` |
| Backend | `/health`, `/liveness`, `/ready` | ✅ Endpoints present; CI smoke-tests |
| Frontend | `/` serves Next.js | ✅ Compose + healthcheck |
| Database | RDS reachable; `/health/db` | ✅ Health check + alert |
| Redis | ElastiCache reachable; `/health/redis` | ✅ Health check + alert |
| HTTPS | `tls.conf` + certbot | ✅ Config present; operator issues cert |
| Health endpoints | `/health`, `/ready`, `/liveness`, `/version`, `/health/db`, `/health/redis` | ✅ All implemented |
| Metrics endpoint | `GET /metrics` (Prometheus) | ✅ Implemented; names match alerts |
| Monitoring | Prometheus + Grafana + 7 dashboards + 9 alerts | ✅ Stack + config present; names verified |
| Load test | `deploy/loadtest/loadtest.py` + `docker stats` | ✅ Tooling + runbook (run live) |
| Recovery procedure | `deploy/restore.sh` + DR checklist | ✅ Scripts + `BACKUP_AND_RECOVERY.md` |
| **Startup fail-fast** | insecure/missing prod secrets → refuse to boot | ✅ **Implemented & verified this phase** |

---

## 12. Files Changed (this commit)

**Modified**
- `backend/app/core/config.py` — `Settings.validate()` now enforces in production (raises
  `ConfigurationError` on missing/insecure secrets, missing DB/Redis, or remote provider
  without a key); dev mode warns only.
- `backend/app/main.py` — lifespan calls `settings.validate()` before dependency init;
  pytest guard downgrades to a warning so the test suite is unaffected.

**Added**
- `backend/tests/test_config_validation.py` — 10 tests covering the fail-fast policy.

**Added (reports)**
- `docs/reports/PHASE_5_DEPLOYMENT_PLAN.md`
- `docs/reports/BACKUP_AND_RECOVERY.md`
- `docs/reports/PHASE_5_LOAD_TEST.md`
- `docs/reports/PHASE_5_SECURITY_REPORT.md`
- `docs/reports/PHASE_5_REPORT.md`

No deployment infrastructure, CI, monitoring config, or existing docs were modified.
