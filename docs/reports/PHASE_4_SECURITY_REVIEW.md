# Phase 4 — Security Review

**Scope:** Production-deployment & DevOps security posture of NexusAgent.
No AI features, architecture, or business logic were changed. This review
audits the existing controls and the deployment hardening added in this phase.

**Method:** Static review of the backend (`backend/app`), the Docker images,
compose files, nginx config, and CI security gates. Findings are rated
**High / Medium / Low / Info** and tagged **Hardened** (control present and
adequate), **Acceptable** (residual risk is acceptable for this deployment
model), or **Recommendation** (should be tightened).

---

## Summary

| Area | Rating | Status |
|------|--------|--------|
| Authentication (passwords) | Low | Hardened |
| Authentication (JWT) | Low | Hardened |
| Authorization / tenant isolation | Low | Hardened |
| API keys | Low | Hardened |
| Secrets management | Low | Hardened |
| CORS | Low | Hardened |
| CSRF | Info | Acceptable (bearer-token design) |
| Rate limiting | Medium | Acceptable (single-instance) |
| Security headers | Low | Hardened |
| SQL injection | Low | Hardened |
| Prompt injection | Medium | Acceptable (inherent, mitigated) |
| Dependency vulnerabilities | Low | Hardened (CI gates) |
| Container / supply chain | Low | Hardened |
| Trusted proxy (X-Forwarded-*) | Low | Hardened (this phase) |
| Insecure-default secret fallback | Medium | Recommendation |

**No High-severity findings.** Two Medium items are accepted for the current
single-instance deployment model with documented hardening paths.

---

## 1. Authentication

**Passwords** — Argon2 hashing (`backend/app/core/security.py`,
`CryptContext(schemes=["argon2"])`). No plaintext or fast hashes (MD5/SHA/bcrypt)
in use. **Hardened.**

**Token model** — JWT access (HS256, 30 min) + refresh (HS256, 7 days) issued
with *separate* secrets (`JWT_SECRET_KEY` / `JWT_REFRESH_SECRET_KEY`). Tokens are
returned in the JSON body as `Authorization: Bearer` and stored by the frontend
in `localStorage` (`frontend/lib/token-storage.ts`). `decode_token` validates the
`type` claim and expiry. **Hardened.**

**Recommendations (non-blocking):**
- Refresh tokens have no `jti`/revocation list — a stolen refresh token is valid
  until expiry. Add rotation/denylist if long-lived sessions are a concern.
- `POST /auth/change-password` authenticates with `email + current_password` but
  does **not** require an authenticated session (`get_tenant_context`). It is
  protected by knowing the current password, but should require a valid access
  token for consistency.
- `POST /auth/register` sets `email_verified=True` unconditionally. Acceptable
  for a demo platform; gate behind verification before any real outbound email.

## 2. Authorization & Tenant Isolation

Role-based access control (owner / admin / member / viewer) is enforced via
`OrganizationMember` lookups and a `TenantContext` dependency
(`backend/app/core/auth_dependencies.py`). Tenant isolation is defense-in-depth:
PostgreSQL Row-Level Security **plus** an app-layer tenant repository. **Hardened.**

## 3. API Keys

Tenant-scoped API keys (`nx_<token>`) are generated with `secrets.token_urlsafe`,
stored **hashed** (Argon2), and only a non-secret `key_prefix` is returned on
read (`backend/app/api/v1/endpoints/auth.py`). Key creation/listing requires an
authenticated tenant context. **Hardened.**

## 4. Secrets Management

- All secrets are environment-provided; only `.env.example` / `env.production.example`
  ship (placeholders only). Real `.env*` are git-ignored
  (`!.env.example` allow-lists the template). **Hardened.**
- AWS deployment documents AWS Secrets Manager as an optional upgrade
  (`docs/deployment/aws-secrets.md`). **Hardened.**
- **Recommendation (Medium):** `Settings.validate()` only *warns* (does not
  fail) when a secret equals `change-me-in-production`. A production deploy with
  the default secret proceeds. Consider failing fast when `DEBUG=false` and a
  secret is still the insecure default.

## 5. CORS

`BACKEND_CORS_ORIGINS` is an explicit, operator-configured list (no `*`).
`allow_credentials=True` is only safe because auth is bearer-token (not cookies);
a wildcard origin with credentials is never produced. `backend-cors` parsing now
accepts comma-separated values both via `.env` and real environment variables
(this phase — previously a latent container-startup crash). **Hardened.**

## 6. CSRF

**Not applicable** by design: the API is stateless and authenticated with a
bearer token in the `Authorization` header; no session cookies are set, so there
is no CSRF surface. **Acceptable.**

**Caveat (Info):** because the bearer token lives in `localStorage`, any XSS can
exfiltrate it. Mitigations already present: a restrictive CSP
(`docs/deployment/security-headers.md`, nginx + `SecurityHeadersMiddleware`). A
future hardening path is HttpOnly + Secure + SameSite cookies, but that redesigns
the auth transport and is out of scope for this phase.

## 7. Rate Limiting

Fixed-window per-client-IP limiter (`backend/app/core/rate_limit.py`), keyed off
`X-Forwarded-For` / `X-Real-IP` set by nginx (trusts the proxy, not
`request.client.host`). `/health*` and `/metrics` are exempt. Disabled when
`RATE_LIMIT_PER_MINUTE <= 0` or under pytest. **Acceptable for single-instance.**

**Recommendation (Medium):** the limiter state is process-local. Horizontal
scaling (multiple backend replicas) requires moving the budget to Redis or
enforcing it at nginx (`limit_req`). Also, when the backend port is published
directly (local `docker-compose.yml` exposes `:8000`), a client can spoof
`X-Forwarded-For` and bypass the limit — the AWS compose does not publish the
backend, so this only affects local dev.

## 8. Security Headers

`SecurityHeadersMiddleware` + nginx set: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection`, `Referrer-Policy`,
`Permissions-Policy` (geolocation/mic/cam disabled), and a same-origin CSP.
HSTS is applied in the TLS nginx config. **Hardened.** CSP keeps
`'unsafe-inline'`/`'unsafe-eval'` for Next.js runtime compatibility; tightening to
nonce-based `script-src` is a future hardening path (documented in
`docs/deployment/security-headers.md`).

## 9. SQL Injection

All data access goes through SQLAlchemy ORM / parameterized statements
(`backend/app/core/database.py`). Alembic migrations are parameterized DDL. No
string-interpolated SQL was found in application paths. **Hardened.**

## 10. Prompt Injection

Inherent to any LLM/RAG product: knowledge-base documents and chat input can
contain adversarial instructions. Mitigations present:
- Tool execution is bounded (`TOOL_EXECUTION_TIMEOUT_SECONDS=15`,
  `TOOL_EXECUTION_MAX_OUTPUT_CHARS=10000`).
- The local RAG composer returns retrieved context without executing model
  output as code; no `eval` of LLM responses.
- Strict tenant isolation prevents cross-tenant data leakage via injected prompts.

**Acceptable** for the current offline/local-default deployment. Future work:
input sanitization/sandboxing of ingested documents, and explicit "untrusted
content" labelling in prompts.

## 11. Dependency Vulnerabilities

CI enforces a multi-layer gate (`security.yml`): `pip-audit`, `npm audit`
(moderate+), GitHub Dependency Review (high, PRs), Bandit (HIGH only), and Trivy
filesystem + image scans (HIGH/CRITICAL). Core dependencies are deliberately
pinned to advisory-clean versions (e.g. `fastapi==0.135.0`,
`starlette==1.3.1`). **Hardened.** Re-run scans periodically — advisories evolve
even for pinned versions.

## 12. Container & Supply Chain

- Backend image: multi-stage, non-root `appuser` (uid 1001), slim base,
  `curl` healthcheck, `exec uvicorn` as PID 1 for clean shutdown.
- Frontend image: multi-stage, non-root `nextjs` (uid 1001), `next start`.
- `docker-compose.aws.yml`: `read_only: true` + `tmpfs /tmp`, `cap_drop: ALL`,
  `mem_limit`/`cpus`/`pids_limit` bounds, `json-file` log rotation, named volumes.
- Build metadata (`BUILD_GIT_SHA` / `BUILD_TIMESTAMP`) injected for provenance
  (this phase), surfaced by `GET /version`. **Hardened.**

## 13. Trusted Reverse Proxy (this phase)

`TRUST_PROXY` setting + uvicorn `ProxyHeadersMiddleware` honours `X-Forwarded-*`
**only** when enabled. Enabled solely in `docker-compose.aws.yml`, where nginx is
the only public entrypoint and the backend publishes no host port. The local
compose keeps it `false` because it publishes `:8000`. This removes the previous
inconsistency where `request.client` / `url_for` would be wrong behind the proxy.
**Hardened.**

---

## Conclusion

The application enters Phase 4 with a strong, multi-layered security posture and
no High-severity findings. The deployment path (containers, compose, nginx, CI
scans, secrets handling) is production-grade for a single-instance model. The two
Medium items are explicitly accepted with documented hardening paths, and one
critical latent bug (comma-separated `BACKEND_CORS_ORIGINS` crashing container
startup) was fixed as part of this phase.
