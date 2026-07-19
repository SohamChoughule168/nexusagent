# NexusAgent — Release Engineering

This document defines the release process for NexusAgent. It covers semantic
versioning, how the version is embedded into every artifact, the git tag
strategy, the release checklist, the release-notes template, and how to verify
the running image's version at any time.

**Current release line:** `1.0.0` (tagged `v1.0.0`). This public beta is the
external rollout of the already-tagged `1.0.0`; see
[§7 Known limitations & beta framing](#7-known-limitations--beta-framing).

---

## 1. Semantic versioning

NexusAgent follows [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html):
`MAJOR.MINOR.PATCH` (`X.Y.Z`).

| Bump      | When                                                                 |
|-----------|----------------------------------------------------------------------|
| `MAJOR`   | Breaking API/contract changes, tenant-data migration that is *not* backward-compatible, or a security posture change that requires consumer action. |
| `MINOR`   | New backward-compatible features (new endpoints, new agent/Tool capabilities, new providers). |
| `PATCH`   | Backward-compatible fixes, dependency bumps that preserve behavior, docs, and operational hardening. |

Pre-release identifiers use the SemVer suffix when needed:

- `X.Y.Z-beta.N` — public-beta builds distributed for field testing.
- `X.Y.Z-rc.N` — release candidates gated behind the final validation gate.

The `1.0.0` line is treated as stable; the *public beta* is a distribution
channel for that line, not a separate version number (see §7).

---

## 2. Application version embedding

The version is declared **once per artifact kind** and surfaced consistently so
operators can confirm "deployed code == documented release" without shelling
into a container.

| Artifact | Location | Source of truth |
|----------|----------|-----------------|
| Repo version file | `VERSION` | single-line `1.0.0` |
| Python package | `pyproject.toml` → `version` | `1.0.0` |
| Runtime config | `backend/app/core/config.py` → `APP_VERSION` | `"1.0.0"` |
| Frontend package | `frontend/package.json` → `version` | `1.0.0` |
| Build metadata | Docker `BUILD_GIT_SHA` / `BUILD_TIMESTAMP` (injected at build) | `git rev-parse` / UTC timestamp |
| Running image | `GET /version` endpoint | aggregates the above |

The `/version` endpoint (`backend/app/main.py`) returns
`app.core.build_info.get_build_info()`, which reports:

```json
{
  "app_name": "NexusAgent AI",
  "version": "1.0.0",
  "app_version": "1.0.0",
  "build_git_sha": "a1b2c3d",
  "build_timestamp": "2026-07-19T12:00:00Z",
  "python_version": "3.11.x",
  "package_version": "1.0.0"
}
```

`version` is read from the repo `VERSION` file (fallbacks to `APP_VERSION`),
`build_git_sha` / `build_timestamp` are `"unknown"` for local/dev builds that
were not built with those args (see §4).

The FastAPI app is also constructed with `version=settings.APP_VERSION`, so the
OpenAPI document (`GET /openapi.json`, `GET /docs`) carries the version too.

---

## 3. Bumping the version (single source-of-truth list)

When cutting a new `X.Y.Z`, update **all** of the following (kept in sync by
convention; CI does not auto-bump):

1. `VERSION`
2. `pyproject.toml` → `version`
3. `backend/app/core/config.py` → `APP_VERSION`
4. `frontend/package.json` → `version`
5. `.env.example` / `env.production.example` (any `APP_VERSION`-style value)

Then regenerate the changelog and release notes (§6).

---

## 4. Git tag strategy

- **Release tags are annotated** and follow `vX.Y.Z`
  (`git tag -a v1.0.0 -m "NexusAgent v1.0.0"`). Annotated tags carry the
  tagger, date, and message, and are what the rollback runbook targets.
- **Milestone tags** (`milestoneN-phaseM`) are lightweight historical markers
  used during development; do not confuse them with release tags.
- **Beta/RC tags** use the full pre-release suffix: `v1.0.0-beta.1`,
  `v1.0.0-rc.1`.
- **Never** delete or move a published release tag. If a release is bad, cut a
  new `PATCH` and document the supersession in the changelog.
- **Branch model:** `main` is the stable, releasable branch. Feature work lives
  on short-lived branches PR'd back to `main`; every release is tagged on
  `main`.

Build args in `docker-compose*.yml` forward `BUILD_GIT_SHA` /
`BUILD_TIMESTAMP` (defaulting to `unknown`) into the images, and
`.github/workflows/docker-validation.yml` injects `${GITHUB_SHA::7}` + a UTC
timestamp at CI build time, so production images are self-identifying.

---

## 5. Release checklist

Run this gate before tagging. Each item must be ticked (or explicitly N/A'd).

### Pre-tag
- [ ] All target PRs merged to `main`; `main` is green in CI.
- [ ] Version bumped across all five locations in §3.
- [ ] `CHANGELOG.md` updated (new `## [X.Y.Z]` section, Keep a Changelog format).
- [ ] `RELEASE_NOTES_vX.Y.Z.md` written from the template (§6).
- [ ] Docs reviewed: `README.md`, `ARCHITECTURE.md`, `OPERATIONS.md`,
      `CONTRIBUTING.md`, `docs/user-guide/*`, `docs/deployment/*`.

### Validation gate
- [ ] Backend tests pass: `pytest` (or `make test-backend`).
- [ ] Frontend tests pass: `cd frontend && npm run test`.
- [ ] Frontend type-check + lint: `npm run type-check && npm run lint`.
- [ ] `ruff check` clean on the backend.
- [ ] Docker images build: `docker compose build` (or CI `docker-validation`).
- [ ] `mypy` informational error count unchanged or reduced.
- [ ] Fresh clone builds and runs via `./run.sh` (doc-driven happy path).
- [ ] Migration applies cleanly: `alembic upgrade head` on a clean DB.
- [ ] Seed works: `python backend/scripts/seed_demo.py --init-db`.
- [ ] `/health` returns `{"status":"healthy"}`; `/version` returns the new `version`.
- [ ] `/docs` and `/openapi.json` are reachable and reflect the new version.
- [ ] `git status` clean (no stray artifacts, caches, or secrets).

### Tag & publish
- [ ] Create annotated tag: `git tag -a vX.Y.Z -m "NexusAgent vX.Y.Z"`.
- [ ] Push tag: `git push origin vX.Y.Z`.
- [ ] Publish GitHub release notes from `RELEASE_NOTES_vX.Y.Z.md`.
- [ ] Record the released commit SHA in the deploy runbook / release notes.
- [ ] (Production) deploy via `deploy/update-containers.sh` behind a health-gate.

---

## 6. Release-notes template

Copy to `RELEASE_NOTES_vX.Y.Z.md` and fill in. Keep the structure stable so
customers and operators can scan quickly.

```markdown
# NexusAgent vX.Y.Z — Release Notes

**Release date:** YYYY-MM-DD
**Tag:** `vX.Y.Z`

<One-paragraph positioning: what NexusAgent is and what this release delivers.>

---

## Features
- <Grouped by area: Multi-tenancy & auth, AI agents, Knowledge bases & RAG,
  Conversations & memory, Tools & orchestration, Frontend, Operations.>

## Improvements
- <Notable non-feature changes: performance, UX, docs, dependency hygiene.>

## Security
- <Auth, RLS, headers, rate limiting, secrets handling, scanning. Link the
  security checklist where relevant.>

## Known limitations
- <Honest list of what is NOT supported yet (formats, offline fallbacks,
  scaling ceilings, non-blocking gates).>

## Upgrade notes
- <For first release: fresh-deploy steps. For upgrades: migration/breaking
  notes and rollback pointers.>
```

The `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/):
group under `## [X.Y.Z] — YYYY-MM-DD` with `Added / Fixed / Changed /
Removed` subsections.

---

## 7. Known limitations & beta framing

NexusAgent `1.0.0` is labeled "first production release" and is tagged
`v1.0.0`. For the purposes of **public beta** distribution, the beta is the
external rollout of this same `1.0.0` line — **no version number changes** are
made for the beta. Beta-specific expectations and constraints are documented in
[`docs/reports/PHASE_6_REPORT.md`](reports/PHASE_6_REPORT.md) and the beta
readiness checklists under `docs/deployment/`.

If a true pre-release cut is ever needed, use the `X.Y.Z-beta.N` / `X.Y.Z-rc.N`
scheme (§1, §4) rather than downgrading the stable `1.0.0` label.

---

## 8. Version endpoint verification (runbook)

Confirm the running image's version at any time without redeploying:

```bash
# Public beta (local compose)
curl -fsS http://localhost:8000/version | python -m json.tool

# Production (through nginx)
curl -fsS https://<DOMAIN>/version | python -m json.tool

# Health probes
curl -fsS http://localhost:8000/health        # {"status":"healthy"}
curl -fsS http://localhost:8000/health/ready  # dependency aggregate
```

Expected: `version` == `app_version` == the repo `VERSION` file, and
`build_git_sha` matches `git rev-parse --short HEAD` for CI-built images (or
`unknown` for local builds). A mismatch between `version` and the deployed tag
means the image was built from a different commit than the one tagged — rebuild
from the tagged SHA before trusting it in production.
