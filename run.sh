#!/usr/bin/env bash
# NexusAgent — one-command local development launcher.
#
# What it does (Docker path, recommended):
#   1. Copies .env / frontend/.env.local from the examples if missing.
#   2. `docker compose up -d --build` (Postgres, Redis, backend, frontend, nginx).
#   3. Waits for the backend health probe to go green.
#   4. Seeds the Brightpath demo workspace (org + KB + Aria agent + sample chats).
#
# If Docker is not available it prints the manual (non-Docker) workflow instead
# of failing silently. The non-Docker path is documented in
# docs/user-guide/quickstart.md.
set -euo pipefail
cd "$(dirname "$0")"

# --- 1. Ensure env files exist ------------------------------------------------
[ -f .env ] || { echo "==> Creating .env from .env.example"; cp .env.example .env; }
[ -f frontend/.env.local ] || { echo "==> Creating frontend/.env.local from example"; cp frontend/.env.example frontend/.env.local; }

# --- 2. Docker available? ------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "==> Docker detected — launching full stack (db, redis, backend, frontend, nginx)"
  docker compose up -d --build

  echo "==> Waiting for backend health (http://localhost:8000/health)..."
  for _ in $(seq 1 60); do
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
      echo "==> Backend is healthy."
      break
    fi
    sleep 2
  done

  echo "==> Seeding demo workspace (Brightpath org + Aria agent)..."
  # Runs inside the backend container so no local Python toolchain is needed.
  # DATABASE_URL is supplied by compose, so it points at the `db` service.
  docker compose run --rm backend python backend/scripts/seed_demo.py --init-db || \
    echo "   (seed skipped or failed — re-run with: docker compose run --rm backend python backend/scripts/seed_demo.py --init-db)"

  echo ""
  echo "NexusAgent is up:"
  echo "  Landing : http://localhost:3000/"
  echo "  Demo    : http://localhost:3000/demo"
  echo "  Sign in : http://localhost:3000/login  (demo@nexusagent.dev / nexusagent-demo)"
  echo ""
  echo "Stop the stack later with:  docker compose down"
  exit 0
fi

# --- 3. No Docker: print the manual workflow ----------------------------------
cat <<'EOF'
Docker was not found. Use the non-Docker local workflow:

  1. Start PostgreSQL + Redis (e.g. `docker compose up -d db redis`, or install
     them locally and point DATABASE_URL / REDIS_URL at them in .env).
  2. ./setup.sh                         # install backend + frontend deps
  3. pip install -e .                    # ensure the `app` package is importable
  4. python backend/scripts/seed_demo.py --init-db   # create schema + demo data
  5. uvicorn app.main:app --reload --port 8000        # terminal 1 (backend)
  6. cd frontend && npm run dev                        # terminal 2 (frontend)

Then open http://localhost:3000/  (demo: http://localhost:3000/demo)
See docs/user-guide/quickstart.md for the full guide.
EOF
exit 1
