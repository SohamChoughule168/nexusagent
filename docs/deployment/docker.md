# Deployment with Docker

This guide covers building and running NexusAgent AI locally using Docker and
Docker Compose. It targets a **single-host, local production** deployment:
Frontend (Next.js), Backend (FastAPI), PostgreSQL, and Redis.

> Out of scope for this phase (later milestones): Kubernetes, AWS, CI/CD,
> Nginx, monitoring, HTTPS, and load balancing.

## Architecture

```
┌-------------------------┐      ┌--------------------------------┐
│  Browser                │      │  nexusagent-net (bridge)       │
│  http://localhost:3000  │─────▶│  frontend  (Next.js :3000)     │
└-------------------------┘      │      │ depends_on (healthy)     │
                                │      ▼                           │
                                │  backend   (FastAPI :8000)      │
                                │      │ depends_on (healthy)     │
                                │      ├──▶ db      (Postgres :5432)
                                │      └──▶ redis   (Redis   :6379)
                                └--------------------------------┘
```

- The **browser calls the backend directly** (`http://localhost:8000/api/v1`).
  `NEXT_PUBLIC_API_BASE_URL` is baked into the client bundle at build time.
- Inter-service traffic (backend → db/redis) uses the compose service names
  (`db`, `redis`) on the `nexusagent-net` bridge network.

## Prerequisites

- Docker Engine **24.0+**
- Docker Compose **v2** (`docker compose` plugin)
- ~2 GB free disk for images

## 1. Environment variables

Copy the template and edit it. **`.env` is gitignored — never commit secrets.**

```bash
cp .env.example .env
# then edit .env and replace every placeholder with a real value
```

Key variables (all documented in `.env.example`):

| Variable | Used by | Notes |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `db` + backend `DATABASE_URL` | Compose builds `DATABASE_URL` from these. |
| `DATABASE_URL` | backend | Overridden in compose to `postgresql+psycopg2://…@db:5432/…`. |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | backend | Overridden in compose to the `redis` service. |
| `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY` | backend | **Required in production.** `openssl rand -hex 32`. |
| `SECURITY_PASSWORD_SALT` | backend | **Required in production.** `openssl rand -hex 16`. |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | backend | Leave blank to use offline/local fallbacks. |
| `BACKEND_CORS_ORIGINS` | backend | Comma-separated, no spaces (e.g. `http://localhost:3000`). |
| `NEXT_PUBLIC_API_BASE_URL` | frontend (build) | Inlined at build time. Browser → backend origin. |

Every variable has a safe **local default** in `docker-compose.yml`, so the
stack also runs with an empty `.env` for a quick localhost demo.

## 2. Build

Build all images (or just one):

```bash
# All services
docker compose build

# Single service
docker compose build backend
docker compose build frontend
```

The backend image is a multi-stage build: dependencies install into a `deps`
stage, then a minimal `runtime` stage runs as a non-root `appuser` (uid 1001).
The frontend image builds Next.js in a `builder` stage, then a `runner` stage
runs `next start` as a non-root `nextjs` user (uid 1001).

## 3. Run

```bash
# Start everything in the background
docker compose up -d

# Follow logs
docker compose logs -f

# Check health
docker compose ps
```

Expected healthy services:

```
NAME                STATUS                    PORTS
nexusagent-db       Up (healthy)              0.0.0.0:5432->5432/tcp
nexusagent-redis    Up (healthy)              0.0.0.0:6379->6379/tcp
nexusagent-backend  Up (healthy)              0.0.0.0:8000->8000/tcp
nexusagent-frontend Up (healthy)              0.0.0.0:3000->3000/tcp
```

Access the UI at **http://localhost:3000** and the API at
**http://localhost:8000** (health: `http://localhost:8000/health`).

### Database migrations

The backend image ships Alembic, but migrations are **not** auto-applied at
startup. Run them once against the running container:

```bash
docker compose exec backend alembic upgrade head
```

### Stopping

```bash
docker compose down            # stop, keep volumes
docker compose down -v         # stop AND remove volumes (deletes data)
```

## 4. Images & services

| Image | Service | Port | User |
| --- | --- | --- | --- |
| `nexusagent-backend:latest` | backend | 8000 | appuser (1001) |
| `nexusagent-frontend:latest` | frontend | 3000 | nextjs (1001) |
| `postgres:16-alpine` | db | 5432 | (image default) |
| `redis:7-alpine` | redis | 6379 | (image default) |

### Health checks

- **db** — `pg_isready`
- **redis** — `redis-cli ping`
- **backend** — `GET /health` (curl)
- **frontend** — `GET /` via node `fetch`

### Networks, volumes, restart

- Network: `nexusagent-net` (bridge) shared by all four services.
- Volumes: `postgres_data` (DB), `redis_data` (Redis AOF).
- Restart policy: `unless-stopped` on every service.
- Ordering: `backend` waits for `db`+`redis` healthy; `frontend` waits for
  `backend` healthy (`depends_on` with `condition: service_healthy`).

## 5. Troubleshooting

**`docker compose config` fails with "invalid interpolation"**
The compose file uses `${VAR:-default}` substitution. Ensure a `.env` exists
(next to `docker-compose.yml`); `cp .env.example .env` resolves it. Variable
names must be alphanumerics/underscores.

**Backend container unhealthy / exits**
- Check logs: `docker compose logs backend`.
- Confirm `JWT_SECRET_KEY` and `JWT_REFRESH_SECRET_KEY` are set (not the
  `change-me-in-production` default) in production.
- Confirm the `db` is healthy: `docker compose ps db`. The backend waits for it.

**CORS errors in the browser**
- `BACKEND_CORS_ORIGINS` must include the exact origin you load the UI from
  (e.g. `http://localhost:3000`), comma-separated, **no spaces**.
- It is read at backend startup; restart the backend after changing it.

**Frontend cannot reach the backend**
- `NEXT_PUBLIC_API_BASE_URL` is **baked at build time**. Rebuild the frontend
  after changing it: `docker compose up -d --build frontend`.
- The browser calls `localhost:8000` directly — ensure port `8000` is published
  and not firewalled.

**Database connection refused**
- The backend `DATABASE_URL` in compose must use the service name `db`, not
  `localhost`. Do not override `DATABASE_URL` in `.env` with a `localhost` value
  when running via compose.

**Stale builds**
- Force a clean rebuild: `docker compose build --no-cache` or
  `docker compose up -d --build --force-recreate`.

## 6. Production notes

- This stack is intended for **local / single-host** production-like runs. For
  multi-host, autoscaling, ingress TLS, or managed databases, use a later
  phase (Kubernetes / cloud / reverse proxy).
- **Secrets:** set strong `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`,
  `SECURITY_PASSWORD_SALT`, and a unique `POSTGRES_PASSWORD`. Do not use the
  placeholder defaults.
- **Data:** Postgres and Redis data live in named volumes (`postgres_data`,
  `redis_data`). Back them up; `docker compose down -v` destroys them.
- **TLS / HTTPS:** not configured here. Terminate TLS at a later reverse proxy
  or load balancer phase.
- **Scaling:** `docker compose up -d --scale backend=N` works for stateless
  replicas behind a future proxy; the DB and Redis remain single instances.
- **Images:** pin to specific digests/tags in a locked-down environment rather
  than `:latest` for reproducible deployments.
