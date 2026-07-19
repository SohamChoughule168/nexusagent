# Quickstart

Get NexusAgent running locally and seed the demo workspace in a few minutes.

## 1. Prerequisites

- **Docker + Docker Compose** — runs the local stack (Postgres, Redis, backend,
  frontend, nginx). This is the recommended path.
- **Python 3.11+** (verified on 3.11, 3.12, and 3.13) — only needed for the
  non-Docker path or to run the seed script locally.
- **Node.js 20+** — only if you want to run the frontend separately.

> The dependency pins are kept in sync with current Python/Node releases. On
> Python 3.13 the pinned `pydantic`, `sqlalchemy`, and `psycopg2-binary`
> versions all ship prebuilt wheels, so `pip install` works without a Rust/MSVC
> toolchain. See `pyproject.toml` for the exact pins.

## 2. One-command launch (recommended)

From the repository root, run the launcher for your platform:

```bash
./run.sh          # macOS / Linux
make dev          # macOS / Linux (same as run.sh)
run.bat           # Windows
```

This will:

1. Copy `.env` / `frontend/.env.local` from the examples if they are missing.
2. `docker compose up -d --build` — start Postgres, Redis, the backend
   (port 8000), the frontend (port 3000), and nginx (port 80).
3. Wait for the backend health probe to go green.
4. Seed the **Brightpath** demo workspace (org + help-center KB + Aria agent +
   sample chats) inside the backend container.

> The stack does **not** seed automatically — the launcher (or the manual step
> below) runs the seed explicitly. This keeps the DB init/seed step
> visible and idempotent.

## 3. Seed manually (alternative)

If you started the stack another way, seed the demo workspace yourself:

```bash
# Inside the backend container (no local Python toolchain needed):
docker compose run --rm backend python backend/scripts/seed_demo.py --init-db

# Or, from your host after installing the backend:
pip install -e .
python backend/scripts/seed_demo.py --init-db   # --init-db creates tables for a fresh DB
```

`--init-db` builds the schema with `Base.metadata.create_all` (matching the
local dev path). For a production-faithful schema that also applies Row-Level
Security policies, run `docker compose run --rm backend alembic upgrade head`
instead and then seed **without** `--init-db`.

The script prints the demo credentials and a demo API key when it finishes.

## 4. Open the app

- Landing page: <http://localhost:3000/>
- Live demo: <http://localhost:3000/demo>
- Pricing: <http://localhost:3000/pricing>
- Dashboard (sign in with the demo credentials): <http://localhost:3000/login>

## 5. Talk to the demo agent

Open the [live demo](http://localhost:3000/demo) and click **Launch live demo**.
You are signed into the Brightpath demo workspace as the demo user. Ask Aria
about inviting a team, pricing, or SSO and watch it cite the help center.

## Default demo credentials

| Field    | Value                |
|----------|----------------------|
| Email    | `demo@nexusagent.dev` |
| Password | `nexusagent-demo`     |

Override any of these with environment variables before seeding:
`DEMO_ORG_NAME`, `DEMO_ORG_SLUG`, `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`.

## Non-Docker local setup

If you cannot use Docker, run the services natively:

```bash
./setup.sh                       # install backend + frontend deps (or setup.bat)
# 1. Start PostgreSQL + Redis and point DATABASE_URL / REDIS_URL at them in .env
pip install -e .                 # ensure the `app` package is importable
python backend/scripts/seed_demo.py --init-db
uvicorn app.main:app --reload --port 8000        # terminal 1 (backend)
cd frontend && npm run dev                        # terminal 2 (frontend)
```

The app **degrades gracefully** without Redis: rate limiting falls back to an
in-process limiter and health reports `degraded` (not `unhealthy`). Postgres is
required.

## Troubleshooting

- **Backend unreachable from the demo page:** the frontend calls the backend at
  `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000/api/v1`). Make sure
  the backend container is healthy (`curl http://localhost:8000/health`).
- **Empty answers from the agent:** the knowledge base may not be embedded.
  Re-run the seed script, or check the document status in the knowledge-base UI.
- **No LLM responses (offline):** without an embeddings/LLM key the pipeline
  still retrieves chunks but answers with the offline composer. Set
  `OPENROUTER_API_KEY` (and `RAG_LLM_PROVIDER`/`EMBEDDINGS_PROVIDER`) for full
  generated answers.
- **`pip install` fails building a wheel (Rust/MSVC):** you are on a Python
  version newer than the pinned deps were built for. Upgrade pip and use a
  supported Python (3.11–3.13); the current pins ship prebuilt wheels for all
  three.
