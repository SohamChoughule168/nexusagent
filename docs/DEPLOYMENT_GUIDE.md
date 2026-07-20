# NexusAgent AI — Deployment Guide (Public HTTPS)

This guide takes NexusAgent from a local checkout to a **publicly accessible
HTTPS deployment**. It is produced for the deployment phase and covers the full
command set you must run.

> **Scope boundary:** This document stops at the exact point where a step
> requires *your* credentials or access to an external platform (Railway /
> Render / AWS / a domain registrar / Docker Hub / GitHub). I have **not**
> deployed anything — there is no live URL, and this guide makes no claim that a
> deployment succeeded. Every external action is marked **[YOU]** and must be
> performed by you.

---

## 0. TL;DR — Recommended target

**Railway** (priority 1 of Railway / Render / AWS EC2).

- Backend + frontend are already separate `Dockerfile`s → two Railway services.
- Railway managed **PostgreSQL** + **Redis** inject `DATABASE_URL` / `REDIS_URL`
  that the app already consumes.
- Railway provides **automatic HTTPS** → no nginx / certbot / EBS / security
  groups to manage.
- No Kubernetes, Terraform, or reverse proxy required.

Render is an equivalent alternative (see §9). The AWS EC2 path is fully
supported by the repo's existing `docker-compose.aws.yml` + `deploy/` scripts
(see §10) but is the heaviest option.

---

## 1. Prerequisites (local, on your machine)

```bash
# 1. Clone / be in the repo
cd nexusagent
git status                 # should be on the branch you intend to ship

# 2. Tools
docker --version           # only needed to validate images locally (optional)
railway --version          # Railway CLI  ->  https://docs.railway.com/quickstart
gh --version               # GitHub CLI   ->  https://cli.github.com
node --version             # >= 20 (frontend build)
python3 --version          # >= 3.11

# 3. Install the Railway CLI (one-time)  [YOU]
npm i -g @railway/cli
#   or:  brew install railway
railway login               # opens browser, authenticates you  [YOU]
```

---

## 2. Create the Railway project & managed services

```bash
# Link/initialize a Railway project  [YOU]
railway init                # choose "Empty project" and name it nexusagent

# Add managed PostgreSQL  (injects DATABASE_URL automatically)
railway add --service postgres

# Add managed Redis  (injects REDIS_URL automatically)
railway add --service redis
```

> Railway variables `DATABASE_URL` (postgresql://…) and `REDIS_URL`
> (redis://…) are injected into every service in the project. The app's
> `Settings` uses the **psycopg2** driver by default, and SQLAlchemy maps a
> bare `postgresql://` URL to psycopg2 automatically — so **no rewrite is
> required**. Confirmed against `backend/app/core/config.py:102`.

---

## 3. Backend service

Railway builds the backend from the **repo root** (the `Dockerfile` copies the
root `pyproject.toml` + `backend/`). Use these settings in the Railway
dashboard **or** the `railway.toml` in §8:

- **Source:** the repository
- **Root directory:** `.` (repo root)
- **Dockerfile path:** `backend/Dockerfile`
- **Healthcheck path:** `/health`
- **Public networking:** on (Railway gives `https://<backend>.up.railway.app`)

Set the following **service variables** for the backend (`railway variables` or
dashboard → Variables):

```bash
# --- Core ---
DEBUG=false
DOCS_ENABLED=false
LOG_LEVEL=INFO
LOG_FORMAT=json
TRUST_PROXY=true            # Railway is the trusted edge proxy (backend not directly exposed pre-auth)
PORT=8000                   # Railway overrides at runtime; container CMD honours $PORT

# --- JWT secrets (GENERATE, never reuse)  [YOU] ---
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_REFRESH_SECRET_KEY=$(openssl rand -hex 32)
SECURITY_PASSWORD_SALT=$(openssl rand -hex 16)
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# --- CORS: the frontend's public origin (set after frontend URL is known) ---
BACKEND_CORS_ORIGINS=https://<frontend>.up.railway.app

# --- LLM providers (optional; leave blank for offline/local fallback) ---
OPENROUTER_API_KEY=        # [YOU] paste a real key to enable cloud LLMs
EMBEDDINGS_PROVIDER=local
RAG_LLM_PROVIDER=local
RAG_LLM_MODEL=openai/gpt-4o-mini

# --- Limits / features ---
RATE_LIMIT_PER_MINUTE=100
MAX_UPLOAD_SIZE_MB=50
ENABLE_COST_TRACKING=true
ENABLE_WEBHOOK_TOOL=true
ENABLE_LEAD_CAPTURE_TOOL=true
ENABLE_HUMAN_ESCALATION_TOOL=true
TOOL_EXECUTION_TIMEOUT_SECONDS=15.0
TOOL_EXECUTION_MAX_OUTPUT_CHARS=10000
HEALTH_REQUIRE_REDIS=false
```

> `DATABASE_URL` / `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
> come from Railway's Postgres/Redis plugins — **do not** override them unless
> you are using an external DB.

Apply them from the shell:

```bash
railway variables set DEBUG=false DOCS_ENABLED=false TRUST_PROXY=true \
  JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  JWT_REFRESH_SECRET_KEY="$(openssl rand -hex 32)" \
  SECURITY_PASSWORD_SALT="$(openssl rand -hex 16)" \
  BACKEND_CORS_ORIGINS="https://<frontend>.up.railway.app"
```

---

## 4. Frontend service

- **Root directory:** `frontend`
- **Dockerfile path:** `frontend/Dockerfile`
- **Healthcheck path:** `/` (the image healthcheck probes its own `/`)
- **Public networking:** on (`https://<frontend>.up.railway.app`)

The frontend **inlines** the API base URL at build time, so set this **build
variable** (it must be present *when the image builds*):

```bash
# Build-time variable (inlined into the client bundle):
NEXT_PUBLIC_API_BASE_URL=https://<backend>.up.railway.app/api/v1

# Runtime variable:
NEXT_TELEMETRY_DISABLED=1
```

```bash
railway variables set --service frontend \
  NEXT_PUBLIC_API_BASE_URL="https://<backend>.up.railway.app/api/v1" \
  NEXT_TELEMETRY_DISABLED=1
```

> ⚠️ If you change `NEXT_PUBLIC_API_BASE_URL` later, you must **redeploy the
> frontend** (it is baked into the build, not read at runtime).

---

## 5. Database & Redis setup

Railway's Postgres/Redis plugins auto-provision the databases and inject the
connection strings. No manual DB creation is needed. The app creates its schema
via Alembic (next step).

```bash
# Confirm the injected URLs (values are masked by the CLI, that's expected)
railway variables get DATABASE_URL
railway variables get REDIS_URL
```

If you prefer an **external** Postgres/Redis, override `DATABASE_URL` /
`REDIS_URL` as service variables with the `postgresql+psycopg2://…` and
`redis://…` forms respectively.

---

## 6. Apply database migrations (Alembic)

Migrations are **not** run at container startup (by design — shared DB). Run
`alembic upgrade head` once the backend is deployed and the DB is reachable.

**Option A — `railway run` from your local clone (simplest, recommended):**

```bash
# From the repo root, with the backend's dependencies + alembic installed locally.
# NOTE: alembic is NOT in the pyproject [dev] extra, so install it explicitly
# (matches the version pinned in backend/Dockerfile).
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                 # installs the `app` package + runtime deps
pip install "alembic==1.13.1"    # matches backend/Dockerfile

railway link                     # attach the local project to Railway
railway service connect backend  # select the backend service
railway run alembic upgrade head # runs locally with the service's env injected
```

**Option B — exec into the running container (if `railway exec` is available):**

```bash
railway exec --service backend "alembic upgrade head"
```

> The backend image installs `alembic==1.13.1` and bundles `backend/alembic`;
> `backend/alembic/env.py` reads the project `Settings` (so it targets the same
> `DATABASE_URL` the app uses). Confirm the head applied:

```bash
railway run alembic current     # should report the latest revision
```

---

## 7. Deploy & verify (manual)

```bash
# Deploy both services (builds the images on Railway's builders)
railway up

# Watch logs
railway logs --service backend
railway logs --service frontend
```

**Verification commands** (replace `<backend>` / `<frontend>` with the real
subdomains Railway assigned — shown in the dashboard):

```bash
# Health (backend)
curl -fsS https://<backend>.up.railway.app/health
# -> {"status":"healthy"}

# Readiness (DB + Redis aggregate)
curl -fsS https://<backend>.up.railway.app/ready
# -> {"status":"ok", ...}  (503 if a dependency is down)

# Version / build metadata
curl -fsS https://<backend>.up.railway.app/version
# -> {"app_name":"NexusAgent AI","version":"1.0.0","git_sha":..., ...}

# Frontend UI
curl -fsS -o /dev/null -w "%{http_code}\n" https://<frontend>.up.railway.app/
# -> 200
```

All three probe endpoints (`/health`, `/ready`, `/version`) are implemented in
`backend/app/main.py`. ✅

---

## 8. Machine-readable config (`railway.toml`)

Place this at the repo root so the two services deploy deterministically.
Commit it — it documents the topology and lets `railway up` build both.

```toml
# railway.toml — NexusAgent AI (Railway, multi-service)
[backend]
rootDirectory = "."
dockerfilePath = "backend/Dockerfile"
healthcheckPath = "/health"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3

[backend.variables]
DEBUG = "false"
DOCS_ENABLED = "false"
TRUST_PROXY = "true"
LOG_LEVEL = "INFO"
LOG_FORMAT = "json"
# JWT_* / SECURITY_PASSWORD_SALT must be set as *secret* variables in the
# dashboard (they are intentionally NOT committed here).
BACKEND_CORS_ORIGINS = "https://nexusagent-frontend.up.railway.app"

[frontend]
rootDirectory = "frontend"
dockerfilePath = "frontend/Dockerfile"
healthcheckPath = "/"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3

[frontend.variables]
NEXT_TELEMETRY_DISABLED = "1"
NEXT_PUBLIC_API_BASE_URL = "https://nexusagent-backend.up.railway.app/api/v1"
```

> Replace the `up.railway.app` subdomains with the ones Railway actually
> assigns, and move `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`,
> `SECURITY_PASSWORD_SALT` into the **secret** variable UI (or a Railway
> project secret) rather than this file.

---

## 9. Alternative: Render (equivalent)

Render uses a `render.yaml` blueprint. No nginx; same env model. Create
`render.yaml` at the repo root:

```yaml
# render.yaml — NexusAgent AI (Render, multi-service)
services:
  - type: web
    name: nexusagent-backend
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    rootDir: .
    plan: starter
    healthCheckPath: /health
    envVars:
      - key: DEBUG
        value: "false"
      - key: DOCS_ENABLED
        value: "false"
      - key: TRUST_PROXY
        value: "true"
      - key: DATABASE_URL
        fromDatabase:
          name: nexusagent-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: nexusagent-redis
          property: connectionString
      - key: JWT_SECRET_KEY
        sync: false
      - key: JWT_REFRESH_SECRET_KEY
        sync: false
      - key: SECURITY_PASSWORD_SALT
        sync: false
      - key: BACKEND_CORS_ORIGINS
        value: "https://nexusagent-frontend.onrender.com"

  - type: web
    name: nexusagent-frontend
    runtime: docker
    dockerfilePath: ./frontend/Dockerfile
    rootDir: frontend
    plan: starter
    healthCheckPath: /
    envVars:
      - key: NEXT_TELEMETRY_DISABLED
        value: "1"
      - key: NEXT_PUBLIC_API_BASE_URL
        value: "https://nexusagent-backend.onrender.com/api/v1"

databases:
  - name: nexusagent-db
    databaseName: nexusagent
    plan: free

  - name: nexusagent-redis
    plan: free
    ipAllowList: []
```

Render's Postgres `connectionString` is `postgresql://…` → works with psycopg2
as noted in §2. Run migrations after first deploy via the Render shell /
`render run "alembic upgrade head"`.

---

## 10. Alternative: AWS EC2 (heaviest, fully supported by repo)

The repository already contains a complete AWS single-instance path — use it
only if you need VPC-level control:

- `docker-compose.aws.yml` (RDS + ElastiCache, no bundled db/redis)
- `deploy/user-data.sh`, `deploy/init-deploy.sh`, `deploy/db-migrate.sh`,
  `deploy/healthcheck.sh`
- `deploy/iam-policy.json`, `deploy/nexusagent.service`
- `nginx/tls.conf.example` + `deploy/init-letsencrypt.sh` (Let's Encrypt)
- `env.production.example` + `docs/deployment/aws.md`, `tls.md`, `PRODUCTION_CHECKLIST.md`

---

## 11. CI/CD (automatic deploy on push to `main`)

A GitHub Actions workflow is provided at
`.github/workflows/deploy.yml`. It triggers a Railway deploy on every push to
`main`.

**Secret you must add** (GitHub → Settings → Secrets → Actions):

- `RAILWAY_TOKEN` — a Railway project access token
  (`railway whoami` → dashboard → Account → Tokens)  **[YOU]**

Once the secret exists, pushes to `main` deploy automatically. See the
workflow file header for the exact trigger and the manual fallback
(`railway up`).

---

## 12. STOP — remaining steps require your credentials

The following are **not** performed here and require your accounts/access:

- [ ] **[YOU]** `railway login` and `railway init` (§2).
- [ ] **[YOU]** Generate + paste `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`,
      `SECURITY_PASSWORD_SALT` (§3).
- [ ] **[YOU]** Set `OPENROUTER_API_KEY` (or other LLM key) if cloud LLMs are
      wanted (§3).
- [ ] **[YOU]** `railway up` to actually build + publish the images (§7).
- [ ] **[YOU]** Run `alembic upgrade head` against the live DB (§6).
- [ ] **[YOU]** Add GitHub secret `RAILWAY_TOKEN` to enable auto-deploy (§11).
- [ ] **[YOU — optional]** Custom domain + TLS in Railway's dashboard
      (Settings → Domains), then update `BACKEND_CORS_ORIGINS` and
      `NEXT_PUBLIC_API_BASE_URL` to the `https://` custom origin and redeploy
      the frontend.

No live URL exists yet. Deployment is **not** complete until you run the
**[YOU]** steps above.
