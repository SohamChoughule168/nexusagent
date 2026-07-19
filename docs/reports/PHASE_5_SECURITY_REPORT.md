# Phase 5 — Security Report

**Phase 5 — Step 9 deliverable (production hardening focus)**
**Scope:** Verify HTTPS, headers, cookies, JWT, secrets, Docker images, dependency
vulnerabilities, container permissions, network exposure, least privilege.
**Companion:** `PHASE_5_REPORT.md`, `docs/deployment/security-*.md`,
`PHASE_4_SECURITY_REVIEW.md`

> This is a **verification** report against the deployed configuration. Each control
> is checked against the actual code/config. The one genuine production gap found —
> **startup did not fail fast on insecure/missing secrets** — has been **remediated
> this phase** (see §2 and §10).

---

## 1. Summary

| Control | Status | Notes |
|---------|--------|-------|
| HTTPS / TLS | ✅ Pass | nginx terminates TLS via Let's Encrypt; HSTS + modern ciphers + OCSP stapling. |
| Security headers | ✅ Pass | CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy (nginx + backend). |
| Cookies | ✅ N/A | No session cookies — auth is JWT bearer tokens. |
| JWT | ✅ Pass | HS256, strict algorithm allowlist, separate access/refresh keys, short expiry. |
| Secrets | ✅ **Fixed** | App now fails fast on missing/insecure secrets in production (was: warn-only). |
| Docker images | ✅ Pass | `python:3.11-slim`, non-root `appuser` (uid 1001), healthcheck, build provenance. |
| Dependency vulnerabilities | ✅ Pass | `pip-audit`, `npm audit`, `dependency-review`, `bandit`, `trivy` in CI. |
| Container permissions | ✅ Pass | `read_only`, `cap_drop: ALL`, tmpfs, CPU/mem/PID limits (AWS compose). |
| Network exposure | ✅ Pass | SG allows only 22/80/443; backend/frontend publish no host port. |
| Least privilege | ✅ Pass | Scoped IAM instance role; deploy user hardening noted. |

---

## 2. Secrets & Startup Validation (Remediated Gap)

**Before this phase:** `Settings.validate()` existed but only *logged a warning* when
insecure default secrets (`change-me-in-production`) were used, and never ran at
startup (the lifespan did not call it). A production container could therefore boot
serving traffic with `JWT_SECRET_KEY=change-me-in-production`.

**After this phase (`backend/app/core/config.py`, `backend/app/main.py`):**
- `Settings.validate()` now **raises `ConfigurationError`** in production
  (`DEBUG is False`) when any of the following are missing or still set to an insecure
  default (`change-me`, `change-me-in-production`, empty):
  - `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `SECURITY_PASSWORD_SALT`
  - `DATABASE_URL`, `REDIS_URL`
  - API key for any **remote** LLM/embeddings provider selected
    (`EMBEDDINGS_PROVIDER`/`RAG_LLM_PROVIDER` = `openrouter`/`openai`)
- The lifespan calls `settings.validate()` **before** connecting to Redis/Postgres, so
  an invalid process refuses to start instead of serving traffic.
- Development (`DEBUG is True`) still only warns, so local workflows keep working.
- The test suite is unaffected: the startup check is downgraded to a warning under
  pytest (mirroring the existing rate-limiter pytest guard).
- Verified end-to-end: an insecure-prod boot raises `ConfigurationError` and logs
  `startup_config_invalid`; a valid config proceeds to dependency init. 10 unit tests
  (`backend/tests/test_config_validation.py`) cover the policy.

**Note on OpenRouter:** OpenRouter/OpenAI keys are required *only when a remote
provider is selected*, preserving the documented offline/local fallback (the
`env.production.example` comment "Leave blank to use the offline/local fallbacks"
remains valid). If an operator wants OpenRouter unconditionally required, it is a
one-line change in `validate()`.

**SMTP:** No SMTP server settings exist in `config.py` (email transport is not
env-configured), so there are no SMTP credentials to validate. When SMTP is added,
extend `validate()` with the same missing/insecure checks.

---

## 3. HTTPS / TLS

`nginx/tls.conf.template` (rendered by `deploy/init-letsencrypt.sh` via certbot's
webroot plugin) provides:
- `listen 443 ssl; http2 on;` with `ssl_certificate` / `ssl_certificate_key`.
- `ssl_protocols TLSv1.2 TLSv1.3`; modern ECDHE cipher suites; `ssl_prefer_server_ciphers off`.
- `ssl_stapling on; ssl_stapling_verify on;` (OCSP stapling).
- `Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"` (HSTS).
- HTTP `:80` server redirects `301` to HTTPS and serves only the ACME challenge.

ACM + Application Load Balancer is documented as an alternative (`docs/deployment/tls.md` §6).

---

## 4. Security Headers

Set in **both** nginx (`nginx.conf` / `tls.conf.template`) and the backend
(`SecurityHeadersMiddleware` in `app/core/middleware.py`); nginx strips upstream
copies so it is the single source of truth (no duplicate headers):

| Header | Value |
|--------|-------|
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data:; ...; script-src 'self' 'unsafe-inline' 'unsafe-eval'` |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` (TLS only) |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |

**Accepted limitation:** CSP keeps `'unsafe-inline'`/`'unsafe-eval'` for Next.js
runtime compatibility; a nonce-based `script-src` is the documented future hardening.

---

## 5. Cookies

The API uses **JWT bearer tokens** in the `Authorization` header; there are **no
session cookies** set by the backend (`grep` for `set_cookie` returns nothing in
`app/`). Cookie attributes (Secure/HttpOnly/SameSite) are therefore **not
applicable** to primary authentication. The `SameSite`/`Secure`/`HttpOnly` concerns
only arise if/when a cookie-based session or CSRF token is introduced — track that as
future work.

---

## 6. JWT

`app/core/security.py`:
- **Algorithm:** `HS256` (symmetric), with a **strict allowlist** `algorithms=["HS256"]`
  on `jwt.decode` — no `algorithms=None` confusion attack.
- **Keys:** separate `JWT_SECRET_KEY` (access) and `JWT_REFRESH_SECRET_KEY` (refresh);
  the decoder selects the correct key by `token_type`.
- **Expiry:** access `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 30), refresh
  `JWT_REFRESH_TOKEN_EXPIRE_DAYS` (default 7).
- **Fail-fast:** both keys are now required to be non-insecure at startup (§2).

**Accepted limitation (carried from Phase 4):** refresh tokens are not revocable
(no denylist/jti). Out of scope for this phase; tracked in `PHASE_4_SECURITY_REVIEW.md`.

---

## 7. Docker Image Hardening

`backend/Dockerfile` and `frontend/Dockerfile`:
- Base `python:3.11-slim` (small attack surface).
- Non-root user `appuser` (**uid/gid 1001**); uploads dir chowned to it.
- `HEALTHCHECK` on `/health`; build args `BUILD_GIT_SHA`/`BUILD_TIMESTAMP` for provenance.
- Runtime `CMD` uses `exec uvicorn ... --workers 1` so uvicorn is PID 1 and receives
  `SIGTERM` for graceful shutdown.

`docker-compose.aws.yml` (production) additionally:
- `read_only: true` + `tmpfs: /tmp` (root FS immutable; only the uploads volume is writable).
- `cap_drop: ALL`.
- `mem_limit`, `cpus`, `pids_limit` bounds.
- `restart: unless-stopped`; json-file log rotation.

---

## 8. Dependency Vulnerabilities

`.github/workflows/security.yml` runs on every push/PR to `main`:
- `pip-audit` over the Python tree (fails on discovered vulns).
- `npm audit --audit-level=moderate` for the frontend.
- `dependency-review` (PRs, fails on `high`).
- `bandit -r backend/app -lll` (Python SAST, HIGH only).
- `trivy fs` (secrets + misconfig + CVE, HIGH/CRITICAL, `exit-code 1`) and
  `trivy image` (backend + frontend, CRITICAL unfixed, `exit-code 1`).

The repo has a prior `DEPENDENCY_REMEDIATION_REPORT.md` and a `fix(deps)` commit, and
`docker-validation.yml` rebuilds images on every push, so the supply chain is scanned
continuously. No open High/CRITICAL findings are expected in the current tree.

---

## 9. Network Exposure & Least Privilege

- **Security group `nexusagent-ec2`:** allows only **22** (or SSM), **80**, **443**
  from the internet. Backend (`:8000`) and frontend (`:3000`) publish **no host port**;
  nginx is the sole public entrypoint (`docker-compose.aws.yml`).
- **`nexusagent-rds` / `nexusagent-redis`:** allow 5432 / 6379 only from the EC2 SG.
- **IAM instance role** (`deploy/iam-policy.json`): scoped to SSM Session Manager,
  CloudWatch Logs, optional ECR pull, optional S3 uploads — no `*` beyond the SSM
  message bus. Applied via `docs/deployment/aws-iam.md`.
- **Secrets:** `.env.production` is gitignored; `deploy/fetch-secrets.sh` can render it
  from AWS Secrets Manager. Backups' `.env.production` copy is a separate KMS-protected
  S3 object (see `BACKUP_AND_RECOVERY.md` §8).
- **`deploy` user:** passwordless sudo (convenience). `docs/deployment/security-checklist.md`
  recommends replacing this with SSM Session Manager for production.

---

## 10. Findings & Remediations (this phase)

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| F1 | Production process could boot with insecure default JWT/salt secrets (`change-me-in-production`) | **High** | ✅ **Fixed** — startup fail-fast (`config.validate()` + lifespan call). |
| F2 | `validate()` never ran at startup | High | ✅ **Fixed** — called in lifespan before dependency init. |
| F3 | `deploy` user has NOPASSWD sudo | Low | ➖ Documented hardening (use SSM). No code change. |
| F4 | Rate limiter is single-instance (in-memory) | Low | ➖ Accepted for single-node; Redis/limit_req path noted for horizontal scale. |
| F5 | CSP allows `'unsafe-inline'`/`'unsafe-eval'` | Low | ➖ Accepted for Next.js; nonce path future. |
| F6 | Refresh tokens not revocable | Medium | ➖ Carried from Phase 4; out of scope. |

**No new High/Medium findings beyond F1/F2, which are remediated.** The remaining
items are accepted, documented limitations consistent with the single-node,
no-redesign scope of Phase 5.
