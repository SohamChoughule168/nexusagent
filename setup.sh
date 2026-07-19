#!/usr/bin/env bash
# NexusAgent — environment setup (install backend + frontend dependencies).
#
# Prepares env files and installs:
#   - the Python backend as an editable package (+ dev tools: pytest, bandit)
#   - the Node frontend (npm ci, using the committed lockfile)
#
# Run this once after cloning, before `./run.sh` (Docker) or the manual
# non-Docker workflow. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "==> Creating .env from .env.example"; cp .env.example .env; }
[ -f frontend/.env.local ] || { echo "==> Creating frontend/.env.local from example"; cp frontend/.env.example frontend/.env.local; }

echo "==> Installing backend (editable) + dev tools..."
python -m pip install --upgrade pip
pip install -e ".[dev]"

echo "==> Installing frontend dependencies (npm ci)..."
cd frontend
npm ci

echo ""
echo "==> Setup complete."
echo "    Docker users:        ./run.sh"
echo "    Non-Docker users:    see docs/user-guide/quickstart.md"
