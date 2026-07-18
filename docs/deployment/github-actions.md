# GitHub Actions CI/CD

Continuous Integration for NexusAgent AI. These pipelines **validate** every
pull request and every push to `main` — they do **not** deploy (no AWS,
Kubernetes, Nginx, or production release). Deployment is intentionally out of
scope for this milestone.

---

## Workflow Overview

| Workflow | File | Purpose | Jobs |
| --- | --- | --- | --- |
| **Backend CI** | `.github/workflows/backend-ci.yml` | Lint, type-check, and test the Python (FastAPI) backend with coverage. | `lint`, `test` |
| **Frontend CI** | `.github/workflows/frontend-ci.yml` | Lint, type-check, unit-test, and production-build the Next.js frontend. | `lint`, `test`, `build` |
| **Docker Validation** | `.github/workflows/docker-validation.yml` | Validate `docker-compose.yml` and build both container images. | `validate` |
| **Security Checks** | `.github/workflows/security.yml` | Scan dependencies for known vulnerabilities. | `python-audit`, `npm-audit`, `dependency-review` |

All four workflows run **in parallel** because they are triggered by the same
events independently. Within a workflow, jobs are also parallel where it is safe
(`frontend-ci` makes `build` depend on `lint` + `test` so we never build a
known-broken app).

### What each step does

**Backend CI — `lint`**
- `ruff check backend/app backend/tests` — blocking linter (config in
  `pyproject.toml` → `[tool.ruff]`). Fails the build on any violation.
- `mypy backend/app` — **non-blocking / informational** type check (see
  [Caveats](#caveats–known-gaps)). The backend is only partially annotated, so
  mypy is run with `continue-on-error: true` and is configured to become a hard
  gate once the codebase is annotated.

**Backend CI — `test`**
- Provisions ephemeral **Postgres 16** and **Redis 7** service containers.
- Installs the project with `pip install -e ".[dev]"` + `pytest-cov`.
- Creates the schema via `init_db()` (equivalent to `Base.metadata.create_all`),
  then runs `pytest` with coverage (`xml` + `html`) and a JUnit report.

**Frontend CI**
- `npm ci` (reproducible install from the lockfile).
- `npm run lint` (ESLint via `next lint`).
- `npm run type-check` (`tsc --noEmit`).
- `npm test` (Vitest) emitting a JUnit report.
- `npm run build` (Next.js production build; fails on any build error).

**Docker Validation**
1. `docker compose config` — validates the compose file (variable interpolation
   and service shape) without building.
2. Builds the **backend** image from the **repository root** context.
3. Builds the **frontend** image from the `frontend/` context.

**Security Checks**
- `python-audit` — `pip-audit` over the installed Python dependency tree.
- `npm-audit` — `npm audit --audit-level=moderate` over the frontend lockfile.
- `dependency-review` — GitHub Dependency Review on pull requests only
  (`fail-on-severity: high`).

---

## Trigger Conditions

Every workflow triggers on:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

- **Push to `main`** → all four workflows run (post-merge validation).
- **Pull request into `main`** → all four workflows run (pre-merge gate).
  `dependency-review` is further guarded with `if: github.event_name ==
  'pull_request'`.

`concurrency` groups cancel superseded runs on the same ref to save minutes.

### Suggested branch-protection required checks

To make these the enforced gate for `main`, mark the following as **required
status checks** in *Settings → Branches*:

- `Backend CI / Lint & Type Check`
- `Backend CI / Test & Coverage`
- `Frontend CI / Lint & Type Check`
- `Frontend CI / Unit Tests`
- `Frontend CI / Production Build`
- `Docker Validation / Compose Config & Image Builds`
- `Security Checks / Python Dependency Audit`
- `Security Checks / Frontend Dependency Audit`
- `Security Checks / Dependency Review` (PRs only)

---

## Required GitHub Secrets

**None.** The validation-only pipelines need no secrets — tests use fixed,
non-sensitive values injected via `env:` (e.g. `JWT_SECRET_KEY=ci-test-secret`),
and images are built but never pushed.

If you later extend these workflows to **push images to a registry** or deploy,
add the relevant secrets then (e.g. `REGISTRY_TOKEN`, `DEPLOY_SSH_KEY`) and
reference them with `${{ secrets.* }}`. Keep them out of the validation scope for
now.

---

## Artifact Outputs

Uploaded via `actions/upload-artifact@v4` and available for 90 days on each run.

| Workflow | Artifact name | Contents | When |
| --- | --- | --- | --- |
| Backend CI | `backend-coverage` | `coverage.xml`, `htmlcov/` | always |
| Backend CI | `backend-test-results` | `test-results/junit.xml` | always |
| Frontend CI | `frontend-test-results` | `frontend/test-results/junit.xml` | always |

> The Docker job intentionally does **not** push or publish images, so it
> produces no artifacts. Add an upload step only if/when a registry push is
> introduced in a later milestone.

---

## Caching Strategy

- **Python** — `actions/setup-python@v5` with `cache: pip` keyed on
  `pyproject.toml`. Speeds up `pip install` of the backend dependency tree.
- **Node** — `actions/setup-node@v4` with `cache: npm` keyed on
  `frontend/package-lock.json`. Speeds up `npm ci`.

---

## Troubleshooting

### Ruff fails on a new PR
The project's ruff config lives in `pyproject.toml` (`[tool.ruff]` /
`[tool.ruff.lint]`). Run the same check locally:

```bash
python -m pip install ruff==0.6.9
ruff check backend/app backend/tests
```

### Mypy is reported but the job still passes
Type checking is intentionally **non-blocking** while the backend is
incrementally annotated. It is configured in `pyproject.toml` (`[tool.mypy]`)
with `ignore_missing_imports = true` and untyped-def checks disabled. To make
it a hard gate later, remove `continue-on-error: true` from the `lint` job's
mypy step and tighten the `[tool.mypy]` options.

### Backend tests fail with "relation does not exist"
The `test` job creates tables with `init_db()` (i.e.
`Base.metadata.create_all`) **after** importing `app.models.all_models`, rather
than running Alembic migrations. If a model is not registered in
`app.models.all_models`, its table will be missing — add it to the aggregate
module.

### Docker Validation: `docker compose config` passes but `docker compose build` would not
`docker compose config` only validates structure, so it succeeds. The compose
file sets the backend `build.context: ./backend`, but `backend/Dockerfile`
copies root-level paths (`pyproject.toml`, `backend/`, `alembic/`,
`alembic.ini`). The two are inconsistent. The CI workflow therefore builds the
backend image **directly** from the repository root (`docker build -f
backend/Dockerfile -t … .`) rather than via `docker compose build`. Reconciling
the compose `context` with the Dockerfile is a follow-up cleanup item and is
outside the scope of this milestone.

### Docker backend build fails on `pip install .`
The backend `Dockerfile` runs `pip install .` while `pyproject.toml` declares
`packages = ["app", "api", …]` — package directories that live under
`backend/`, not at the repository root the build context provides. If the image
build fails for this reason, the packaging/`Dockerfile` split needs to be
reconciled (also a pre-existing item, not addressed here so as not to modify the
shipped Dockerfile).

### `npm ci` fails
Ensure `frontend/package-lock.json` is committed and in sync with
`package.json`. `npm ci` refuses to run if they diverge.

### Dependency-review job is skipped
It is guarded to run only on `pull_request` events, so it is correctly skipped
on direct pushes to `main`.

---

## Pinned Action Versions

All third-party actions are pinned to a major version (no floating `@main`):

- `actions/checkout@v4`
- `actions/setup-python@v5`
- `actions/setup-node@v4`
- `actions/upload-artifact@v4`
- `docker/setup-buildx-action@v3`
- `actions/dependency-review-action@v4`

Tooling installed inside steps is also pinned (e.g. `ruff==0.6.9`,
`mypy==1.11.2`, `pytest-cov==5.0.0`, `pip-audit==2.7.3`, `node:20`,
`postgres:16-alpine`, `redis:7-alpine`).
