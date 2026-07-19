# Phase 4 — Repository Audit

**Date:** 2026-07-19
**Branch:** `phase/3b-repository-health` → Phase 4 work
**Objective:** Confirm the repository is production-deployable from a clean clone
via a documented process. This audit inventories every deployment-relevant
subsystem and records the gaps closed during Phase 4.

> Legend: ✅ present & adequate · 🟡 present but improved this phase · 🔧 fixed
> this phase · ➕ added this phase

---

## 1. Backend

| Item | Status | Notes |
|------|--------|-------|
| FastAPI app (`app.main:app`) | ✅ | `uvicorn app.main:app`, 1 worker in image |
| Package layout | ✅ | `app` installed top-level via `[tool.setuptools] package-dir` |
| Health/version endpoints | 🟡 | `/health`, `/health/live`, `/health/ready`, `/health/startup` existed; ➕ added `/liveness`, `/ready`, `/health/db`, `/health/redis`, `/version` (Phase 4) |
| Config (`core/config.py`) | 🔧 | ➕ `TRUST_PROXY`, `DB_POOL_*`, `BUILD_*`; fixed comma-list env parsing for both `.env` and OS-env (was a container-startup crash) |
| Logging | ✅ | structlog JSON, request IDs, access logs, startup/shutdown, no-secret redaction; 🟡 error logs now carry `request_id` |
| DB engine | 🟡 | 🔧 `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_TIMEOUT` configurable (was fixed defaults) |
| Alembic | ✅ | single head `008_reconcile_schema_drift`; recent reconciliation migrations keep it aligned with ORM |
| Tests | ✅ | 27 test modules; pytest + pytest-asyncio |

## 2. Frontend

| Item | Status | Notes |
|------|--------|-------|
| Next.js 15 / React 19 | ✅ | `frontend/Dockerfile` multi-stage, non-root |
| Build | ✅ | `npm ci` + `next build`; deterministically copies public/ |
| Config | ✅ | `NEXT_PUBLIC_API_BASE_URL` inlined at build; `frontend/.env.example` present |
| Lint/type/test | ✅ | ESLint, `tsc --noEmit`, Vitest in `frontend-ci.yml` |

## 3. Docker Support

| Item | Status | Notes |
|------|--------|-------|
| `backend/Dockerfile` | ✅ | multi-stage, non-root, healthcheck, build-args for `BUILD_GIT_SHA/BUILD_TIMESTAMP` (➕) |
| `frontend/Dockerfile` | ✅ | multi-stage, non-root, build-args for provenance (➕) |
| `docker-compose.yml` | ✅ | production single-host: postgres, redis, backend, frontend, nginx; healthchecks, named volumes, networks, restart, hardening |
| `docker-compose.prod.yml` | ➕ | explicit production entrypoint (includes `docker-compose.yml`) |
| `docker-compose.dev.yml` | ➕ | dev overlay: source mounts, `--reload`, `next dev`, Adminer |
| `docker-compose.aws.yml` | ✅ | AWS single-instance (RDS/ElastiCache, EBS uploads, `read_only`, `TRUST_PROXY=true`) |
| `docker-compose.aws.tls.yml` | ✅ | TLS override |
| `.dockerignore` | ✅ | present for root + frontend |
| Validation | ✅ | `security.yml` (Trivy) + `docker-validation.yml` build the images |

## 4. Environment Variables

All variables audited against `backend/app/core/config.py`. Full matrix below.

| Variable | Class | Default | Notes |
|----------|-------|---------|-------|
| `POSTGRES_USER/PASSWORD/DB` | Required (secret) | — | compose `db` + `DATABASE_URL` |
| `DATABASE_URL` | Required | localhost | sync psycopg2 |
| `REDIS_URL` | Required | localhost | |
| `JWT_SECRET_KEY` / `JWT_REFRESH_SECRET_KEY` | Required (secret) | change-me | separate secrets |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | 30 | |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Optional | 7 | |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Secret (opt) | — | offline fallbacks if blank |
| `OPENROUTER_BASE_URL` | Optional | openrouter | |
| `EMBEDDINGS_PROVIDER` / `RAG_LLM_PROVIDER` / `RAG_LLM_MODEL` | Optional | local | |
| `BACKEND_CORS_ORIGINS` | Required | localhost list | comma or JSON; **parsing fixed** |
| `RATE_LIMIT_PER_MINUTE` | Optional | 100 | 0 disables |
| `MAX_UPLOAD_SIZE_MB` | Optional | 50 | matches nginx |
| `ALLOWED_EXTENSIONS` / `ALLOWED_MIME_TYPES` | Optional | pdf… | comma or JSON; **parsing fixed** |
| `UPLOAD_STORAGE_DIR` | Optional | ./storage/uploads | |
| `ENABLE_COST_TRACKING` | Optional | true | |
| `SECURITY_PASSWORD_SALT` | Required (secret) | change-me | |
| `SECURITY_FORCE_DEV_MODE` | Optional | false | |
| `ENABLE_WEBHOOK_TOOL` / `LEAD_CAPTURE_TOOL` / `HUMAN_ESCALATION_TOOL` | Optional | true | |
| `TOOL_EXECUTION_TIMEOUT_SECONDS` / `MAX_OUTPUT_CHARS` | Optional | 15 / 10000 | |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Optional | redis 1/2 | |
| `APP_NAME` / `APP_VERSION` | Optional | NexusAgent AI / 1.0.0 | |
| `DEBUG` | Optional | false | controls NullPool |
| `LOG_LEVEL` / `LOG_FORMAT` | Optional | INFO / json | |
| `LOG_FILE` / `ACCESS_LOG_FILE` / `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` | Optional | none | on-disk rotation |
| `LOG_ACCESS_ENABLED` | Optional | true | |
| `METRICS_ENABLED` / `PROMETHEUS_NAMESPACE` | Optional | true / nexusagent | |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | Optional | 5 / 10 / 30 | ➕ Phase 4 |
| `TRUST_PROXY` | Optional | false | ➕ Phase 4; true in AWS compose |
| `HEALTH_REQUIRE_REDIS` | Optional | false | |
| `BUILD_GIT_SHA` / `BUILD_TIMESTAMP` | Build | unknown | ➕ Phase 4 |
| `NEXT_PUBLIC_API_BASE_URL` | Required (build) | localhost:8000 | inlined to bundle |

**Env templates:** `.env.example` (local, single source), `env.production.example`
(AWS), `frontend/.env.example`, `backend/.env.example` (➕ Phase 4). The AWS file
is a superset used by `docker-compose.aws.yml --env-file .env.production`; it is
kept separate (not "de-duplicated") because it is referenced by deploy scripts and
documents AWS-specific (RDS/ElastiCache/Domain) values.

## 5. Database

- Engine: PostgreSQL 16 (compose), Amazon RDS (AWS). Driver: `psycopg2` (sync).
- Migrations: Alembic, single head, runs `upgrade head` in prod/deploy.
- Tenant isolation: PostgreSQL RLS + app-layer tenant repository.
- Pool: `pool_pre_ping=True`; QueuePool sized via `DB_POOL_*` (DEBUG=false),
  NullPool (DEBUG=true).

## 6. Redis

- Image: `redis:7-alpine`, AOF enabled in compose. Used for Redis (cache),
  Celery broker/result (db 1/2). Healthchecked. Optional hard-dep via
  `HEALTH_REQUIRE_REDIS`.

## 7. Static Assets

- Frontend `public/` ensured at build; nginx serves `/_next/static` immutable.
- Brand assets in `brand/`. Demo PDFs in `demo/`.

## 8. Build & Deploy Scripts

| Script | Status | Purpose |
|--------|--------|---------|
| `run.sh` / `run.bat` | ✅ | one-command local stack + seed |
| `setup.sh` / `setup.bat` | ✅ | dependency install |
| `Makefile` | ✅ | `make dev` etc. |
| `deploy/init-deploy.sh` | ✅ | AWS first boot: build, up, migrate, health |
| `deploy/db-migrate.sh` | ✅ | `alembic upgrade head` in container |
| `deploy/compose.sh` | ✅ | shared compose-file resolution (TLS opt-in) |
| `deploy/healthcheck.sh` | ✅ | poll backend `/health` |
| `deploy/init-letsencrypt.sh` | ✅ | cert issuance + flip to TLS config |
| `deploy/backup.sh` / `restore.sh` | ✅ | RDS/PGBackRest-style |
| `deploy/rolling-restart.sh` | ✅ | zero-downtime restart |
| `monitoring/` | ✅ | Prometheus + Grafana compose |
| `nginx/` | ✅ | HTTP + TLS templates, security headers |

## 9. Secrets

- `.env*` git-ignored except templates. No real secrets in repo.
- CI uses least-privilege tokens; `security.yml` uploads SARIF (best-effort).
- AWS Secrets Manager documented as upgrade path.

## 10. Configuration

Documented in `docs/deployment/` (docker, aws, production, security-*, backups,
rollback, rate-limiting, observability, tls, secrets, github-actions, aws-iam,
PRODUCTION_CHECKLIST).

---

## Gaps closed in Phase 4

1. **Latent container-startup crash** — comma-separated `BACKEND_CORS_ORIGINS`
   (and `ALLOWED_*`) failed JSON-decoding via the OS-env source, so any image
   started from compose (no `.env` in image) would crash. Fixed by patching both
   the env and dotenv sources + adding validators.
2. **Missing canonical probes** — added `/liveness`, `/ready`, `/health/db`,
   `/health/redis`, `/version` (build metadata).
3. **No dev compose** — added `docker-compose.dev.yml` (hot reload) and explicit
   `docker-compose.prod.yml`.
4. **Trust proxy unconfigured** — added `TRUST_PROXY` + uvicorn
   `ProxyHeadersMiddleware`, enabled only in the AWS compose.
5. **DB pool not tunable** — added `DB_POOL_*` settings.
6. **CI used `create_all`, not Alembic** — new `deploy-validation` job runs
   `alembic upgrade head` → seed → smoke test the real app.
7. **`backend/.env.example` missing** — added; enriched all env templates with the
   full variable matrix.

See `PHASE_4_REPORT.md` for the consolidated change list and
`PHASE_4_SECURITY_REVIEW.md` for the security assessment.
