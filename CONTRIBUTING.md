# Contributing to NexusAgent

Thanks for contributing! This guide covers local setup, coding standards, the
branch/PR workflow, and testing.

## 1. Local setup

### Prerequisites
- Python 3.11+ (backend)
- Node.js 20+ (frontend)
- PostgreSQL 16 and Redis (local installs or Docker)

### Backend
```bash
# from repo root
pip install -e .                 # installs the `app` package (package-dir -> backend/)
pip install -e ".[dev]"          # adds pytest, pytest-asyncio, bandit

cp .env.example .env             # fill in secrets (JWT_*, DB password, salt)
# start Postgres + Redis (or: docker compose up db redis)
python -c "import app.models.all_models; from app.core.database import init_db; init_db()"
```

### Frontend
```bash
cd frontend
npm ci
cp .env.example .env.local       # set NEXT_PUBLIC_API_BASE_URL
npm run dev                      # http://localhost:3000
```

## 2. Coding standards

- **Backend**: Python, typed. Run `ruff check` (linter + formatter) before
  committing. `mypy` runs in CI as an **informational** gate today (the
  codebase is partially annotated); tighten locally as you touch code.
- **Frontend**: TypeScript strict, ESLint (`next lint`), Prettier-style
  formatting via the repo config. Prefer the shared `components/ui` primitives.
- **Secrets**: never commit real secrets. Use placeholders in `.env.example`;
  production secrets come from AWS Secrets Manager (see `docs/deployment/aws-secrets.md`).
- **Tenant isolation**: every data path must go through the tenant-scoped
  repository/services. Do not bypass `get_tenant_context`.
- **Migrations**: model changes require a new Alembic revision
  (`alembic revision --autogenerate -m "..."`), then verify it applies on a
  clean DB. Keep ORM models and migrations in sync.
- **Commits**: conventional-commit style used throughout the history
  (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `feat(deploy):`, …).

## 3. Branch strategy

- `main` is the stable, releasable branch. Every release is tagged `vX.Y.Z`.
- Create feature branches from `main` (e.g. `feat/api-keys-persist`,
  `fix/memory-rls`). Milestone work historically used `milestoneN-phaseM`
  branches/tags — keep `main` as the integration target.
- Keep branches short-lived and PR them back to `main`.

## 4. Pull requests

- Open a PR to `main` with a clear description and the linked issue/milestone.
- CI must pass: **backend tests** (pytest + coverage), **frontend tests**
  (vitest), **frontend lint + type-check**, **docker image validation**, and
  **security scanning** (dependency audit + Bandit). A failing required check
  blocks merge.
- Keep PRs focused; large changes should be split. Update docs
  (`ARCHITECTURE.md`, `OPERATIONS.md`, `CHANGELOG.md`) when behavior changes.
- Require review; squash-merge with a conventional-commit message.

## 5. Testing

### Backend
```bash
pytest                              # full suite (needs Postgres + Redis)
pytest backend/tests/test_api_keys.py   # a single file
pytest --cov=app --cov-report=xml  # with coverage (matches CI)
```
- The suite uses ephemeral fixtures; tests rely on `init_db()` to create the
  schema. Set `DATABASE_URL` (sync, e.g. `postgresql+psycopg2://…`),
  `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`. Redis is optional (degrades
  gracefully). See `.github/workflows/backend-ci.yml`.

### Frontend
```bash
cd frontend
npm run test            # vitest run
npm run test:watch     # vitest (watch)
npm run type-check      # tsc --noEmit
npm run lint            # next lint
npm run build           # production build (also type-checks)
```

### Before pushing
Ensure backend `pytest`, frontend `npm run test` + `type-check` + `lint`, and
`ruff check` all pass locally. This matches the CI gates and keeps `main` green.

## Release process (maintainers)
1. Bump `VERSION`, `pyproject.toml`, `frontend/package.json`, `APP_VERSION`,
   and env templates.
2. Update `CHANGELOG.md` and `RELEASE_NOTES_vX.Y.Z.md`.
3. Final validation gate (tests, lint, type-check, build, docker, docs links,
   clean `git status`).
4. Commit, push `main`, create an **annotated** tag `vX.Y.Z`, and publish the
   GitHub release notes.
