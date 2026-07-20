# Milestone C — Implementation Plan (Enterprise & Scale)

> Companion to `MILESTONE_C_AUDIT.md`. This document is the **final revised
> roadmap**. No code was written to produce it; it is the plan only.

## Operating Principles

- **Preserve working systems.** Every step extends or hardens existing code; no
  rewrite of a functioning subsystem. Backwards-compatible schema changes only.
- **Per-priority branches + commits.** Execute one priority at a time on
  `phase/cN-<slug>`, commit separately, and report before starting the next.
- **No large infrastructure.** Kubernetes, multi-region, DB clustering, Redis
  replication, service mesh, and event buses are **out of scope** (see audit
  Section 5). Billing is **optional / deferred** (no foundation exists).
- **Verification gate.** Each step must pass Ruff (blocking), the existing test
  suite, and its stated tests before being marked complete.

Risk levels: **Low** (localized, fully backward-compatible) · **Medium**
(cross-cutting, new auth path, schema migration) · **High** (new external
dependency, security-critical, changes request path).

---

## Priority 1 — Provider Stabilization

### C1.1 Add automatic retry/backoff to providers
- **Objective:** Honor the existing `retryable` error flag with bounded
  exponential backoff + jitter inside `generate`/`stream`; wire
  `OpenRouterProviderWithFallback` (`openrouter.py:71-117`) into
  `create_llm_provider` (`factory.py:21-28`).
- **Files affected:** `ai/providers/base.py`, `openai_compatible.py`,
  `anthropic_provider.py`, `gemini_provider.py`, `openrouter.py`, `factory.py`,
  `ai/providers/__init__.py`.
- **Scope:** Medium. New shared retry helper in `base.py`; small edits per
  provider.
- **Risk:** Low.
- **Testing:** Unit tests for retry-on-`retryable`, no-retry-on-non-retryable,
  backoff count cap; extend `tests/test_provider_factory.py`. Mock HTTP layer.
- **Docs:** Update `factory.py` docstring (remove phantom
  `EMBEDDING_PROVIDER_REGISTRY` reference).
- **Success:** Transient `retryable` errors auto-retry (capped); fallback class
  is the default OpenRouter path; no behavior change for permanent errors.

### C1.2 Honor per-request timeouts
- **Objective:** Use `GenerationRequest.timeout` (`base.py:75`) in every
  provider's `httpx.Timeout` instead of hardcoded `120.0`.
- **Files affected:** `base.py`, `openai_compatible.py:37/55`,
  `anthropic_provider.py:70`, `gemini_provider.py:53`.
- **Scope:** Small.
- **Risk:** Low.
- **Testing:** Assert effective timeout equals request timeout in unit tests.
- **Docs:** None.
- **Success:** Per-call timeout configurable; default preserved where unset.

### C1.3 Fix Ollama default model fallback
- **Objective:** Apply `OllamaProvider.default_model` (`ollama.py:28`) when
  `request.model` is empty in `_build_payload` (`openai_compatible.py:118-164`).
- **Files affected:** `ollama.py`, `openai_compatible.py`.
- **Scope:** Small.
- **Risk:** Low.
- **Testing:** Unit test: empty `request.model` → falls back to configured
  `OLLAMA_LLM_MODEL`.
- **Docs:** None.
- **Success:** Ollama calls never send an empty model.

### C1.4 Compute Azure OpenAI cost
- **Objective:** Populate `MODEL_PRICING` (`azure_openai.py:23`) so
  `calculate_cost` returns real values consistent with other providers.
- **Files affected:** `azure_openai.py`.
- **Scope:** Small.
- **Risk:** Low.
- **Testing:** Unit test asserts non-zero cost for a known deployment.
- **Docs:** Note in provider config docs (none currently specify Azure pricing).
- **Success:** Azure usage costed in analytics/usage events.

### C1.5 Per-provider health / connectivity method
- **Objective:** Add `health()`/`connectivity()` to `BaseLLMProvider` and
  implement per provider; use it in `core/health.py:95-135` instead of a generic
  URL `HEAD` probe; keep `local`/`ollama` skips.
- **Files affected:** `base.py`, each provider, `core/health.py`.
- **Scope:** Medium.
- **Risk:** Low.
- **Testing:** Unit tests for each provider's `health()`; health endpoint still
  passes in CI (offline providers skipped).
- **Docs:** Note provider health semantics in ops docs.
- **Success:** `/health` reflects real provider liveness; no external calls for
  `local`/`ollama`.

### C1.6 Reconcile embeddings layer with provider abstraction
- **Objective:** Make `services/embeddings.py` consistent with the LLM provider
  model — error mapping to `ProviderError`, retry/backoff, and either create the
  `EMBEDDING_PROVIDER_REGISTRY` the factory docstring references or correct the
  docstring. Decide async-vs-sync boundary explicitly.
- **Files affected:** `services/embeddings.py`, `ai/providers/factory.py`,
  `endpoints/providers.py`.
- **Scope:** Medium.
- **Risk:** Medium (touches ingestion/RAG paths).
- **Testing:** Embedding error/retry unit tests; `tests/test_document_embeddings.py`
  stays green; ingestion smoke test in CI.
- **Docs:** Document embedding provider contract.
- **Success:** Embeddings share the provider error/retry model; no duplicate
  metadata maps; docstring accurate.

---

## Priority 2 — Enterprise Authentication (OIDC / OAuth2)

### C2.1 OIDC configuration keys
- **Objective:** Add `OIDC_*` / `SSO_*` settings (issuer/discovery URL, client
  id/secret, redirect URI, scopes, allowed providers) to `core/config.py` and
  `.env.example` / `env.production.example`.
- **Files affected:** `core/config.py`, `.env.example`,
  `env.production.example`.
- **Scope:** Small.
- **Risk:** Low.
- **Testing:** `tests/test_config_validation.py` covers new required/optional
  keys; config loads without OIDC configured (feature-off by default).
- **Docs:** SSO/OIDC Setup Guide stub (filled in C2.7).
- **Success:** App boots with OIDC disabled; enabling requires explicit config.

### C2.2 OIDC client + discovery
- **Objective:** Add `authlib` dependency; implement OIDC discovery (JWKS), token
  exchange, and provider adapters (Google, GitHub, Microsoft, generic).
- **Files affected:** `pyproject.toml`, new `core/oidc.py` (or
  `services/oidc.py`), `core/security.py`.
- **Scope:** Large.
- **Risk:** High (external dependency, security-critical).
- **Testing:** Unit tests with mocked IdP discovery + token exchange; JWT/JWKS
  verification tests; no network in CI.
- **Docs:** Internal design note in Security Architecture doc (C7.4).
- **Success:** Discovery + token exchange verified against a mock IdP; no
  production secrets in tests.

### C2.3 OIDC login/callback endpoints + account linking
- **Objective:** Add `/auth/{provider}/login` + `/auth/{provider}/callback`;
  link/dedupe to existing org/user by verified email; create org on first
  enterprise signup per policy.
- **Files affected:** `endpoints/auth.py`, `router.py`, `core/security.py`,
  `repositories/tenant_repository.py`, `services/` (account linking).
- **Scope:** Large.
- **Risk:** High.
- **Testing:** Endpoint tests (mocked IdP) for new-account, existing-account
  link, and rejection of unverified email; `tests/test_registration.py` stays
  green.
- **Docs:** SSO/OIDC Setup Guide (C2.7).
- **Success:** Enterprise SSO logs in / links correctly; local auth unaffected.

### C2.4 Wire OIDC into auth dependencies
- **Objective:** Extend `get_tenant_context` / `auth_dependencies.py:113-130`
  to accept the OIDC session credential and resolve the same `TenantContext`
  (tenant isolation unchanged).
- **Files affected:** `core/auth_dependencies.py`, `core/security.py`,
  middleware.
- **Scope:** Medium.
- **Risk:** Medium (changes credential resolution path).
- **Testing:** Auth-dependency tests cover JWT + OIDC session; tenant scoping
  enforced; `tests/test_auth_dependencies.py` extended.
- **Docs:** Note in Security Architecture doc.
- **Success:** Both credential types yield identical, isolated tenant context.

### C2.5 API-key request authentication
- **Objective:** Wire `verify_api_key` (`security.py:134`) into a FastAPI
  dependency; add `DELETE /api-keys/{id}` revoke endpoint; enforce stored
  `scopes`.
- **Files affected:** `core/security.py`, `core/auth_dependencies.py`,
  `endpoints/auth.py`, `router.py`, `schemas/auth.py`.
- **Scope:** Medium.
- **Risk:** Medium.
- **Testing:** Unit tests: valid key authenticates, revoked key rejected,
  scope mismatch rejected; `tests/test_api_keys.py` extended.
- **Docs:** API-key usage section in Security Architecture / user guide.
- **Success:** API keys are a working, revocable, scope-checked credential.

### C2.6 Logout + token revocation/blacklist
- **Objective:** Add `/auth/logout` and a Redis-backed token blacklist /
  refresh-token revocation store; reject blacklisted JWTs in
  `decode_token` (`security.py:69-87`).
- **Files affected:** `core/security.py`, `core/redis.py`, `endpoints/auth.py`,
  `dependencies.py`.
- **Scope:** Medium.
- **Risk:** Medium (Redis-backed; degrade gracefully if Redis down).
- **Testing:** Tests: logout invalidates token; blacklisted token rejected;
  graceful behavior when Redis unavailable.
- **Docs:** Note in Security Architecture doc + runbooks.
- **Success:** Logout actually invalidates sessions; safe under Redis outage.

### C2.7 SSO/OIDC Setup Guide + JWT hardening
- **Objective:** Author the SSO/OIDC Setup Guide; enforce strong JWT secrets
  (fail fast if default/weak) and document asymmetric/JWKS option.
- **Files affected:** `docs/` (new guide), `core/config.py` (validation),
  `core/security.py`.
- **Scope:** Medium.
- **Risk:** Low–Medium.
- **Testing:** Config validation test rejects default secret in production mode.
- **Docs:** New `docs/deployment/sso-oidc-setup.md`.
- **Success:** Guide reproducible from config; weak-secret misconfiguration
  blocked at startup.

---

## Priority 3 — Audit Enrichment

### C3.1 Populate source IP + user-agent
- **Objective:** Pass `request.client.host` and `user-agent` into every
  `record_audit` call site.
- **Files affected:** `services/audit.py`, `endpoints/{documents,knowledge_bases,organizations,tools,webhooks}.py`.
- **Scope:** Medium.
- **Risk:** Low.
- **Testing:** Tests assert IP/UA captured for representative mutations.
- **Docs:** None.
- **Success:** Audit rows carry real source IP + user agent.

### C3.2 Thread request ID + fix ORM/DB drift
- **Objective:** Add `request_id` to the `AuditLogModel` ORM
  (`models/base.py:49-64`) to match the migration (`001_initial_migration.py:342`);
  thread middleware `request_id` (`core/observability_middleware.py:132-136`)
  into `record_audit`.
- **Files affected:** `models/base.py`, `services/audit.py`, middleware, call
  sites.
- **Scope:** Medium (ORM/DB reconciliation).
- **Risk:** Medium (schema alignment).
- **Testing:** Migration idempotency check (`alembic upgrade head` in CI);
  request_id populated in tests.
- **Docs:** Note ORM/DB parity in Security Architecture doc.
- **Success:** ORM matches live `audit_logs`; request_id populated end-to-end.

### C3.3 Standardized status + duration columns
- **Objective:** Add `status`/`outcome` and `duration_ms` columns to the audit
  model + migration; standardize writes (move ad-hoc `meta` outcomes into the
  column).
- **Files affected:** `models/base.py`, `schemas/audit.py`, migration,
  `services/audit.py`, call sites (`tools.py:253`).
- **Scope:** Medium.
- **Risk:** Medium (migration).
- **Testing:** Migration applies in CI; status/duration asserted in tests.
- **Docs:** Audit schema note.
- **Success:** Outcome/duration are first-class, queryable fields.

### C3.4 Audit authentication events
- **Objective:** Emit `record_audit` for login, failed login, registration,
  token refresh, password change, and API-key creation (`auth.py:125/158/188/219+/310`).
- **Files affected:** `endpoints/auth.py`, `services/audit.py`, `schemas/audit.py`.
- **Scope:** Medium.
- **Risk:** Low.
- **Testing:** Auth tests assert corresponding audit rows exist.
- **Docs:** Note auth events in Compliance Checklist.
- **Success:** All auth events appear in `audit_logs`, tenant-scoped.

### C3.5 Retention, export, tamper-evidence
- **Objective:** Add an audit retention policy (config-driven purge job), a
  `GET /audit/export` endpoint (CSV/JSON, owner/admin), and a lightweight
  tamper-evidence option (append-only note or hash chain). Keep scope modest.
- **Files affected:** `endpoints/audit.py`, `services/audit.py`, `core/config.py`,
  new migration/job.
- **Scope:** Medium.
- **Risk:** Medium.
- **Testing:** Export endpoint returns expected rows; retention job purges
  beyond threshold in a test DB.
- **Docs:** Audit retention/export section in Security Architecture + runbooks.
- **Success:** Operators can export and bound audit retention compliantly.

---

## Priority 4 — Tenant Quotas

### C4.1 Quota schema + plan tiers
- **Objective:** Add numeric quota fields to `Organization`
  (`models/organization.py:11-40`) and a plan→limits mapping in `core/config.py`.
- **Files affected:** `models/organization.py`, `core/config.py`, migration.
- **Scope:** Medium.
- **Risk:** Medium (schema migration).
- **Testing:** Migration applies in CI; default tier limits load.
- **Docs:** Quota model in Security Architecture doc.
- **Success:** Each org has explicit quota values derived from its plan.

### C4.2 Per-tenant usage aggregation
- **Objective:** Add a usage-aggregation service computing per-tenant
  documents, storage bytes, seats, KB count, request count vs. limits (reuse
  `usage.py` / `UsageEventRepository`).
- **Files affected:** `services/usage.py`, `repositories/tenant_repository.py`,
  new `services/quotas.py`.
- **Scope:** Medium.
- **Risk:** Low.
- **Testing:** Unit tests for aggregation against seeded tenant data.
- **Docs:** None.
- **Success:** Current usage vs. limit is computable per tenant.

### C4.3 Quota enforcement
- **Objective:** Add a dependency/middleware that rejects or alerts when a limit
  is exceeded for KB create, document upload, seat add, and API calls.
- **Files affected:** `core/auth_dependencies.py` (or new
  `core/quotas.py`), `endpoints/{knowledge_bases,documents,organizations}.py`.
- **Scope:** Medium.
- **Risk:** Medium (request-path change).
- **Testing:** Tests: over-quota request rejected (403/402) with headroom
  allowed; `tests/test_tenant_isolation.py` extended.
- **Docs:** Quota enforcement behavior in user guide + runbooks.
- **Success:** Limits are enforced; legitimate usage unimpeded.

### C4.4 Tenant-aware rate limiting
- **Objective:** Key the rate limiter (`core/rate_limit.py:36-52`) by
  `organization_id` (fallback to IP); support an optional shared Redis store for
  multi-host. Keep in-memory default.
- **Files affected:** `core/rate_limit.py`, `dependencies.py`, `core/config.py`.
- **Scope:** Medium.
- **Risk:** Medium.
- **Testing:** `tests/test_rate_limit.py` extended for per-tenant buckets;
  graceful single-instance behavior.
- **Docs:** Rate-limiting notes in Security Architecture doc.
- **Success:** Tenants are rate-limited independently; no cross-tenant bleed.

---

## Priority 5 — Background Task Durability

### C5.1 Async worker for existing task table
- **Objective:** Move document embedding (`documents.py:431-462`) off the request
  thread into a worker that reads the existing `background_tasks` table.
  Recommend a lightweight worker (Redis-backed queue or APScheduler) reusing the
  current `create_task`/`start_task`/`finish_task`/`fail_task` API. Do **not**
  add Celery unless its dependency is deliberately introduced.
- **Files affected:** `services/background_tasks.py`, `documents.py`,
  `core/redis.py`, new `services/worker.py` (or scheduler), `docker-compose*.yml`
  (optional worker service), `pyproject.toml` (if new dep).
- **Scope:** Large.
- **Risk:** High (execution model change).
- **Testing:** Embedding completes asynchronously; `/background-tasks/{id}`
  reflects progress; CI keeps embedding offline/deterministic (local embedder).
- **Docs:** Worker runbook in OPERATIONS.md / runbooks.
- **Success:** HTTP request returns immediately; embedding finishes via worker;
  status visible to client.

### C5.2 Retry / idempotency / recovery
- **Objective:** Add bounded retry + idempotency keys to task execution; allow
  `fail_task` recovery/re-dispatch.
- **Files affected:** `services/background_tasks.py`, `services/worker.py`.
- **Scope:** Medium.
- **Risk:** Medium.
- **Testing:** Simulated failure retries up to cap; idempotent re-delivery safe.
- **Docs:** Recovery notes in runbooks.
- **Success:** Transient failures auto-recover; no duplicate side effects.

### C5.3 Webhook dead-letter handling
- **Objective:** Add retry loop + `attempt_count` to webhook delivery
  (`notifications.py:131-141`) and a dead-letter/replay path.
- **Files affected:** `services/notifications.py`, `models/all_models.py`
  (`WebhookDelivery`), `services/background_tasks.py`.
- **Scope:** Medium.
- **Risk:** Medium.
- **Testing:** Failed delivery retries then lands in DLQ; replay endpoint tested.
- **Docs:** Webhook reliability in runbooks.
- **Success:** Webhooks reliably deliver or quarantine for replay.

---

## Priority 6 — Analytics Improvements

### C6.1 Broaden event capture
- **Objective:** Emit `record_event` for chat messages, RAG queries, agent/KB/user
  creation; fix overstated `usage.py`/`analytics.py` docstrings.
- **Files affected:** `services/usage.py`, `endpoints/{conversations,rag?,knowledge_bases,organizations,agents}.py`,
  `analytics.py` docstrings.
- **Scope:** Medium.
- **Risk:** Low.
- **Testing:** Assert events recorded for each new path; no CI network calls.
- **Docs:** Correct docstrings.
- **Success:** Event coverage matches documented scope.

### C6.2 Per-user breakdown + pagination
- **Objective:** Add per-user dimensions and pagination to
  `endpoints/analytics.py:64-239`.
- **Files affected:** `endpoints/analytics.py`, `schemas`.
- **Scope:** Medium.
- **Risk:** Low.
- **Testing:** Endpoint tests for user filter + pagination bounds.
- **Docs:** Analytics API notes.
- **Success:** Large tenants paginate; per-user metrics available.

### C6.3 Cross-tenant / platform admin view
- **Objective:** Add a superuser-gated, cross-tenant analytics view
  (`is_superuser` on `User` model — currently unused).
- **Files affected:** `endpoints/analytics.py`, `core/auth_dependencies.py`,
  `models/user.py`.
- **Scope:** Medium.
- **Risk:** Medium (privileged surface).
- **Testing:** Superuser sees aggregate; non-superuser forbidden.
- **Docs:** Admin analytics in Security Architecture doc.
- **Success:** Provider/enterprise operators get platform-wide visibility.

### C6.4 Cost attribution + quota alerts
- **Objective:** Expose per-user cost breakdown and surface quota/budget alerts
  (ties to C4).
- **Files affected:** `endpoints/analytics.py`, `services/quotas.py` (C4.2).
- **Scope:** Medium.
- **Risk:** Low.
- **Testing:** Per-user cost endpoint tested; alert thresholds configurable.
- **Docs:** Cost/quota reporting notes.
- **Success:** Cost attributable to user; alerts fire near limits.

---

## Priority 7 — Enterprise Documentation

All seven docs below are Milestone C deliverables; little or no code is required.

### C7.1 Enterprise Deployment Guide
- **Objective:** Consolidate `docs/deployment/{production,aws,docker,github-actions}.md`
  into a single Enterprise Deployment Guide (single-host compose + AWS single-EC2),
  explicitly noting the no-Kubernetes / single-instance posture.
- **Files affected:** New `docs/deployment/ENTERPRISE_DEPLOYMENT.md`; optionally
  cross-link existing docs.
- **Scope:** Medium (docs).
- **Risk:** Low.
- **Testing:** Docs build / link-check (if present).
- **Docs:** The deliverable itself.
- **Success:** One authoritative enterprise deployment reference.

### C7.2 Disaster Recovery Guide
- **Objective:** Standalone DR guide with explicit RTO/RPO targets, restore
  runbook, and single-region scope statement (reuse
  `docs/reports/BACKUP_AND_RECOVERY.md`).
- **Files affected:** New `docs/deployment/DISASTER_RECOVERY.md`.
- **Scope:** Medium (docs).
- **Risk:** Low.
- **Testing:** DR steps reproducible in a test environment.
- **Docs:** The deliverable itself.
- **Success:** RTO/RPO stated; restore verified.

### C7.3 Backup Strategy
- **Objective:** Consolidate/extend `docs/deployment/backups.md` +
  `BACKUP_AND_RECOVERY.md` into a clear backup strategy (cadence, retention,
  restore, single-instance scope).
- **Files affected:** `docs/deployment/backups.md` (extend).
- **Scope:** Small (docs).
- **Risk:** Low.
- **Testing:** n/a.
- **Docs:** The deliverable itself.
- **Success:** Backup strategy unambiguous and current.

### C7.4 Security Architecture
- **Objective:** Author a consolidated Security Architecture doc (auth/RBAC/tenant
  isolation, secrets, OIDC design [C2], API keys [C2.5], audit [C3], quotas
  [C4], rate limiting [C4.4], metrics). Draw from `ARCHITECTURE.md` and the
  `security-*` docs.
- **Files affected:** New `docs/SECURITY_ARCHITECTURE.md`.
- **Scope:** Large (docs).
- **Risk:** Low.
- **Testing:** n/a.
- **Docs:** The deliverable itself.
- **Success:** Single source of truth for security posture.

### C7.5 SSO/OIDC Setup Guide
- **Objective:** Author the setup guide produced alongside C2.7.
- **Files affected:** `docs/deployment/sso-oidc-setup.md`.
- **Scope:** Medium (docs; depends on C2).
- **Risk:** Low.
- **Testing:** Steps reproducible against a test IdP.
- **Docs:** The deliverable itself.
- **Success:** An operator can enable SSO from the guide.

### C7.6 Compliance Checklist
- **Objective:** Author a regulatory-oriented Compliance Checklist
  (GDPR / SOC 2 / HIPAA control mapping) distinct from the operational
  `security-checklist.md`.
- **Files affected:** New `docs/COMPLIANCE_CHECKLIST.md`.
- **Scope:** Medium (docs).
- **Risk:** Low.
- **Testing:** n/a.
- **Docs:** The deliverable itself.
- **Success:** Controls mapped to framework requirements.

### C7.7 Operational Runbooks
- **Objective:** Consolidate/extend `OPERATIONS.md`, `ROLLBACK.md`,
  `PRODUCTION_CHECKLIST.md` with the new worker (C5.1), logout/revocation
  (C2.6), quota enforcement (C4.3), and audit export (C3.5) procedures.
- **Files affected:** `OPERATIONS.md` (extend).
- **Scope:** Medium (docs).
- **Risk:** Low.
- **Testing:** n/a.
- **Docs:** The deliverable itself.
- **Success:** Runbooks cover all new operational surfaces.

---

## Priority 8 — Billing (Optional / Deferred)

- **Objective:** **Not implemented in this milestone.** The repository has no
  billing foundation — only four unused `stripe_*` columns on `Organization`
  (`models/organization.py:19-21`) and an unused `can_manage_billing` property
  (`tenant_context.py:68`). No SDK, no endpoints, no webhook handler.
- **When to revisit:** Only after a deliberate billing foundation is introduced
  (payment SDK dependency, checkout/portal endpoints, webhook verification, and
  a plan→price config). Until then, leave Priority 8 as a Future Roadmap item.
- **Risk if attempted now:** High (building on zero foundation; would violate
  the "no large assumptions / preserve working systems" rules).
- **Success criteria (future):** A real billing base exists and is tested before
  any subscription logic is built on it.

---

## Appendix — Verification Gate (applies to every step)

1. `ruff check backend/app backend/tests` passes (blocking in CI).
2. `pytest` passes on Postgres 16 + Redis 7 service containers with
   `alembic upgrade head` (per `backend-ci.yml`).
3. New behavior covered by new/extended tests; no regression to
   `tests/test_tenant_isolation.py`, `test_auth_dependencies.py`,
   `test_provider_factory.py`, `test_rate_limit.py`, `test_api_keys.py`.
4. Migrations are idempotent and apply cleanly in CI.
5. Documentation updates (above) committed with the code.
