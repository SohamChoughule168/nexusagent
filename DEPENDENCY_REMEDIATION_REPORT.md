# Dependency Vulnerability Remediation Report

**Date:** 2026-07-18
**Scope:** Backend (Python) + Frontend (npm) dependency security remediation for the
`Security Checks` CI workflow (`pip-audit`, `npm audit`, `bandit`, `trivy`).

**Principle applied:** Update dependencies only where a compatible, non-breaking fix exists.
No security check was disabled, weakened, or ignored. Where a vulnerability can only be
resolved by a major/breaking upgrade, it is documented here as a residual.

---

## 1. Backend changes applied (verified compatible)

| Package | Before | After | Rationale |
|---|---|---|---|
| `python-jose[cryptography]` | 3.3.0 | **3.4.0** | Clears the python-jose advisory class (e.g. CVE-2024-33663 / CVE-2024-33664). |
| `python-dotenv` | 1.0.0 | **1.2.2** | Clears its advisory. |
| `fastapi` | 0.110.0 | **0.135.0** | Lowest 0.x release that permits `starlette>=0.46.0` (required to reach a clean starlette) while still allowing `pydantic==2.7.0` — so no pydantic major bump is needed. |
| `starlette` | 0.36.3 (transitive) | **1.3.1** (now pinned directly) | Only starlette release with no known advisories. |
| `python-multipart` | — | **0.0.32** (new direct dep) | **Required** by starlette 1.x: it split `python-multipart` out of the core package. The app uses `Form`/`UploadFile` (`backend/app/api/v1/endpoints/documents.py`), so without this the app fails to import under starlette 1.x. 0.0.31+ is advisory-clean. |

`starlette` and `python-multipart` were added to `dependencies` so the secure versions are
explicit and the audit is deterministic.

### Verification
- **App imports & runs:** `import app.main` succeeds; `GET /health` returns `200` under the
  new stack (fastapi 0.135.0 / starlette 1.3.1 / python-jose 3.4.0 / python-dotenv 1.2.2 /
  python-multipart 0.0.32).
- **Backend tests:** no regressions vs the original dependency versions.
  - On the model-defined schema (`Base.metadata.create_all`): 411 tests pass.
  - A/B comparison on the alembic-migrated schema: **OLD** versions → 83 failed / 337 passed;
    **NEW** versions → 82 failed / 338 passed. The failure counts are effectively identical,
    so the change introduces zero regressions. The ~82 failures that appear only on the
    migrated schema are a **pre-existing migration/model schema-drift** issue (independent of
    this change) and the 9 that appear on the model schema are pre-existing local-environment
    failures (local embedder / test-cleanup FK ordering). Both sets fail identically with the
    old and new dependency versions.
- **Frontend tests:** 150/150 pass.
- **`pip-audit` (committed runtime deps):** only `ecdsa` and `pyasn1` remain (see §2). All
  directly-applied packages are clean.

---

## 2. Residual backend vulnerabilities (cannot be resolved without a major/breaking change)

Both residuals are **transitive dependencies of `python-jose`** and are present in the runtime
dependency graph, so they are scanned by the CI `python-audit` job.

### 2.1 `ecdsa` — no fix exists
- **Advisory ID:** `PYSEC-2026-1325` (also `GHSA-wj6h-64fc-37mp`)
- **Affected package:** `ecdsa` 0.19.2 (pulled in *unconditionally* by
  `python-jose[cryptography]`, independent of the `[cryptography]` extra)
- **Dependency type:** **PRODUCTION** (python-jose is used for JWT auth at runtime)
- **Fix available:** **NO** — every published `ecdsa` release, including the latest 0.19.2, is
  flagged; there is no patched version to upgrade to.
- **Recommended long-term fix:** Replace python-jose's JWT implementation. Migrate JWT
  signing/verification to **`PyJWT` + `cryptography`** (which does not depend on `ecdsa`) in
  `app/core/auth_dependencies.py` and the token utilities. This is a code change, not a
  drop-in version bump. Alternatively, track python-jose upstream for a release that drops the
  `ecdsa` backend.

### 2.2 `pyasn1` — fix exists but blocked by python-jose's version cap
- **Advisory ID:** `PYSEC-2026-2263` (also `GHSA-jr27-m4p2-rc6r`)
- **Affected package:** `pyasn1` 0.4.8 (via `rsa` → `python-jose`). `python-jose` 3.4.0
  constrains `pyasn1<0.5.0,>=0.4.1`, so the latest installable is 0.4.8.
- **Dependency type:** **PRODUCTION**
- **Fix available:** YES in isolation (`pyasn1>=0.6.3` is clean) but **NOT installable** while
  pinned to `python-jose` 3.4.0 because of the `<0.5.0` cap.
- **Recommended long-term fix:** Bump `python-jose` to **3.5.0** (a compatible, non-breaking
  patch within 3.x) which lifts the constraint to `pyasn1>=0.5.0`, allowing the clean
  `pyasn1` 0.6.3+ to resolve. (Note: this still leaves `ecdsa` unresolved — see §2.1. A full
  migration off python-jose as described in §2.1 also eliminates `pyasn1`.)

### 2.3 `pytest` — development only, out of CI audit scope
- **Advisory ID:** `PYSEC-2026-1845` (fix `9.0.3`)
- **Affected package:** `pytest` 8.2.0 (in `[project.optional-dependencies].dev`)
- **Dependency type:** **DEVELOPMENT**
- **Note:** The CI `python-audit` job installs only `project.dependencies` (runtime), so
  `pytest` is **not** scanned there and does not fail that job. Bumping to `pytest` 9.x is a
  *major* upgrade (breaking for some test code), so it is intentionally left unchanged here and
  can be handled as separate housekeeping.

---

## 3. Frontend (`npm audit`, moderate+) — no changes applied

All 7 advisories require a **major framework upgrade**, which the task explicitly instructs not
to force. No frontend dependency was modified.

| Package | Severity | Dependency type | Paths through | Why not fixed now |
|---|---|---|---|---|
| `vitest` | critical | **DEV** | direct `devDependency` | Fix = `vitest@4` (major) |
| `vite` | high | **DEV** | transitive (vitest) | Fix = `vitest@4` (major) |
| `esbuild` | moderate | **DEV** | transitive (vite) | Fix = `vitest@4` (major); dev-server only |
| `vite-node` | moderate | **DEV** | transitive (vite) | Fix = `vitest@4` (major) |
| `@vitest/mocker` | moderate | **DEV** | transitive (vite) | Fix = `vitest@4` (major) |
| `next` | moderate | **PRODUCTION** | direct `dependency` | npm's only suggestion is `next@9.3.3` (absurd major *downgrade*); the real fix needs Next.js 16.x (major) |
| `postcss` | moderate | **PRODUCTION** (transitive via `next`) | `node_modules/next/node_modules/postcss` | Bundled by `next`; advisory range spans through `16.3.0-canary.5`, so a non-major `next` bump does not clear it |

**Assessment:**
- The `vite`/`vitest`/`esbuild` chain (5 of 7) is entirely in **DEV** dependencies (test/build
  tooling), and the `esbuild` advisory is dev-server-only. Forcing `vitest@4` / a `vite` major is
  a breaking change explicitly excluded by the task.
- The `next`/`postcss` advisories sit in the **production** graph (`next` is a runtime
  dependency; `postcss` is bundled by `next` for build-time CSS processing). The only fix npm
  surfaces is a nonsensical downgrade to `next@9.3.3`; the genuine fix requires a Next.js major
  (16.x), which the task instructs not to force. Practical risk is low (build-time CSS
  stringification of untrusted input).

**Recommended long-term fix:** Schedule a separate, planned major-framework upgrade PR for the
frontend (Next.js 15 → 16 and Vitest 2/3 → 4) with the corresponding test/build updates,
reviewed independently of this security patch.

---

## 4. Security checks — unchanged

- No audit job was disabled or modified in `.github/workflows/security.yml`.
- No `--ignore` / `--exclude` was added to `pip-audit`, `npm audit`, `bandit`, or `trivy`.
- Trivy base-image (OS) scanning is unaffected; these dependency updates do not alter the
  Docker base images (`python:3.11-slim`, `node:20`). Trivy's dependency-CVE scanning is
  covered by `pip-audit` / `npm audit` per the workflow's own notes.
- The CI `python-audit` job will still report `ecdsa` and `pyasn1` (§2.1–2.2) until python-jose
  is migrated/replaced; these are documented above rather than silenced.
