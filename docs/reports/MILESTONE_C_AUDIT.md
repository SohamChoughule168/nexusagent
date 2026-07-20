# Milestone C — Enterprise & Scale: Revised Audit

| Field | Value |
| --- | --- |
| Milestone | C — "Enterprise & Scale" |
| Date | 2026-07-20 |
| Branch | `phase/3b-repository-health` |
| Scope | Backend (FastAPI) capability audit for enterprise readiness |
| Method | Direct repository verification (read-only); every finding cites file:line |
| Status legend | Already implemented · Partially implemented · Missing · Not applicable |

> **Note on provenance.** The previous draft of this audit was produced in an
> earlier session and cleared from the conversation. This document is a
> **re-derivation from the current repository** — every capability below was
> re-verified against the code, not carried over from memory. Speculative or
> unverified claims from any prior draft have been removed.

---

## 1. Executive Summary

The platform already has a strong enterprise *foundation*: multi-tenant
isolation, local auth with Argon2 hashing, JWT issuance, role-based access
control, a persisted audit log, tenant-scoped usage analytics, Prometheus
metrics, and a background-task status table. None of these are missing at the
architectural level — they exist and are wired.

What is **missing or thin** is the *hardening* layer that makes those
foundations enterprise-grade:

- **Provider resilience** exists (rich error hierarchy) but **retry/backoff is
  not actually executed**, and per-request timeouts are dead.
- **OIDC/OAuth2/SSO is entirely absent** — the single biggest gap. Local auth,
  RBAC, and tenant isolation are solid and can host it.
- **Audit logging** is wired but **authentication events are never recorded**
  and the rich fields the schema supports (source IP, request ID) are never
  populated.
- **Tenant quotas** have no schema, no enforcement, and the rate limiter is
  IP-keyed (not tenant-aware). Usage *analytics* exist; usage *metering against
  limits* does not.
- **Background tasks** are a status table only — work still runs **synchronously
  inside the HTTP request**, and there is no broker, worker, retry, or
  dead-letter path.
- **Billing has zero functional foundation** (four unused `stripe_*` columns and
  an unused permission property). It is intentionally **not** prioritized.
- The six "large infrastructure" capabilities (Kubernetes, multi-region, DB
  clustering, Redis replication, service mesh, event bus) have **no
  foundation** and are explicitly out-of-scope per the deployment artifacts.
  They are moved to the Future Roadmap.

---

## 2. Capability Status Matrix

Status per capability (verified against current code):

| Capability | Status | Primary evidence |
| --- | --- | --- |
| LLM provider interface (`BaseLLMProvider`) | Already implemented | `backend/app/ai/providers/base.py` |
| Provider error hierarchy (retryable, rate-limit, auth, context-length) | Already implemented | `base.py` (`ProviderError`, `RateLimitError`, etc.) |
| Provider factory / registry dispatch | Already implemented | `factory.py:100-138` |
| OpenRouter provider | Already implemented | `openrouter.py` |
| Anthropic provider | Already implemented | `anthropic_provider.py` |
| Google Gemini provider | Already implemented | `gemini_provider.py` |
| Azure OpenAI provider | Partially implemented | `azure_openai.py:23` cost pricing empty |
| Ollama provider | Partially implemented | `ollama.py:28` `default_model` unused |
| OpenAI-compatible provider | Already implemented | `openai_compatible.py` |
| Provider automatic retry / backoff | **Missing** | no retry loop in any provider; `openrouter.py:71-117` unwired |
| Per-request timeout honored | **Missing** | `base.py:75` `timeout` field never read |
| Per-provider health / connectivity method | **Missing** | `core/health.py:95-135` URL `HEAD` probe only |
| Embedding layer consistency with providers | **Missing** (disjoint) | `services/embeddings.py` sync, no error/retry mapping |
| Secrets handling in providers | Already implemented | keys from `Settings`, passed via headers/query |
| Local email/password auth (Argon2) | Already implemented | `auth.py:53-215`, `core/security.py:14` |
| JWT issuance / validation | Already implemented | `core/security.py:31-87` |
| Role-based access control | Already implemented | `auth_dependencies.py:133-162`, `tenant_context.py:165-320` |
| Multi-tenant isolation in auth | Already implemented | `auth_dependencies.py:113-130`, `tenant_repository.py:54-58` |
| API-key persistence | Already implemented | `auth.py:298-363`, `all_models.py:400-427` |
| API-key request authentication | **Missing** | `verify_api_key` (`security.py:134`) never called |
| API-key revoke / delete / scope enforcement | **Missing** | no `DELETE /api-keys/{id}`; scopes unenforced |
| Logout / token blacklist / revocation | **Missing** | refresh stateless (`security.py:54-66`); no logout |
| Email verification / password reset | **Missing** | `email_verified=True` auto-set (`auth.py:89`) |
| OIDC / OAuth2 / SSO | **Missing** | zero SSO code/config/routes in `backend/app` |
| Audit log model + persistence | Already implemented | `models/base.py:49-64`, `services/audit.py:52-54` |
| Audit write service | Already implemented | `services/audit.py:25-62` |
| Audit read endpoint (`GET /audit/logs`) | Already implemented | `endpoints/audit.py:36-100`, `router.py:11,25` |
| Rich audit fields (IP, UA, request ID, status, duration) | Partially implemented | columns/params exist but never populated |
| Audit retention / export / tamper-evidence | **Missing** | no retention/export/hash-chain in `backend/app` |
| Authentication events captured in audit trail | **Missing** | auth uses `record_event` (analytics), not `record_audit` |
| Organization plan tier + quota fields | Partially implemented | `models/organization.py:11-40` (`plan` string only) |
| Usage metering (events captured) | Partially implemented | `services/usage.py:18-63`, `all_models.py:358-394` |
| Quota enforcement | **Missing** | no gating logic anywhere |
| Tenant-aware rate limiting | **Missing** | `core/rate_limit.py:36-52` keyed by client IP |
| Usage analytics endpoints | Already implemented | `endpoints/analytics.py:64-239` (tenant-scoped) |
| Billing / Stripe / Razorpay | **Missing** | only unused `stripe_*` columns; no SDK/endpoints |
| Background task framework (broker + worker) | **Missing** | `background_tasks.py` is CRUD only; no Celery worker |
| Background task durability (retry/recovery/DLQ) | Partially implemented | status persistence yes; retry/DLQ no |
| Redis as cache/session/broker | **Missing** (at runtime) | only health/metrics probes; in-memory limiter |
| Analytics Prometheus metrics | Already implemented | `core/metrics.py`, `main.py:120-134`, Grafana dashboards |
| Event tracking (product analytics) | Partially implemented | only `tools.py`, `documents.py` call `record_event` |
| Cross-tenant / platform admin analytics | **Missing** | endpoints org-scoped only |
| Enterprise Deployment Guide | Partially implemented | `docs/deployment/{production,aws,docker,github-actions}.md` |
| Disaster Recovery Guide | Partially implemented | `docs/deployment/backups.md`, `docs/reports/BACKUP_AND_RECOVERY.md` |
| Backup Strategy | Already implemented | `docs/deployment/backups.md`, `docs/reports/BACKUP_AND_RECOVERY.md` |
| Security Architecture doc | Partially implemented | spread across `ARCHITECTURE.md` + `docs/deployment/security-*.md` |
| SSO/OIDC Setup Guide | **Missing** | no feature, no doc |
| Compliance Checklist (regulatory) | **Missing** | `security-checklist.md` is operational, not attestation |
| Operational Runbooks | Already implemented | `OPERATIONS.md`, `docs/deployment/ROLLBACK.md`, `PRODUCTION_CHECKLIST.md` |

---

## 3. Area-by-Area Findings

### 3.1 Provider Stabilization

The LLM provider layer is mature and uniform. All six concrete providers
(OpenRouter, Anthropic, Google Gemini, Azure OpenAI, Ollama, OpenAI-compatible)
implement the `BaseLLMProvider` contract, and a clear error hierarchy
(`ProviderError` carrying `retryable`, plus `RateLimitError`,
`AuthenticationError`, `ContextLengthError`, `ModelNotFoundError`) is present.
No hardcoded secrets — every key is read from `Settings` and passed via
headers/query as each vendor requires.

Gaps are **stabilization**, not construction:

- **No automatic retry/backoff.** Errors carry a `retryable` flag, but no
  `generate`/`stream` method retries. `OpenRouterProviderWithFallback`
  (`openrouter.py:71-117`) honors it but is **never wired into the factory**
  (`factory.py:21-28` returns the plain `OpenRouterProvider`). Resilience is
  effectively absent.
- **`GenerationRequest.timeout` is dead.** Declared at `base.py:75` (default
  `60.0`) but every provider uses its own hardcoded `httpx.Timeout(120.0)`
  (`openai_compatible.py:37/55`, `anthropic_provider.py:70`,
  `gemini_provider.py:53`). Per-call timeouts are not honored.
- **Ollama `default_model` is unused.** `ollama.py:28` stores it, but
  `_build_payload` (`openai_compatible.py:118-164`) sends `request.model`
  verbatim, so an empty model reaches the Ollama API.
- **Azure cost is always `0.0`.** `azure_openai.py:23` sets `MODEL_PRICING = {}`,
  so `calculate_cost` returns `0.0` for all Azure usage — unlike every other
  remote provider.
- **No per-provider health method.** `core/health.py:95-135` does a generic
  `httpx.head(base_url)` probe and skips `local`/`ollama`; `BaseLLMProvider`
  exposes no `health()`/`connectivity()` hook.
- **Embeddings are disjoint and weaker.** `services/embeddings.py` is sync, has
  no `ProviderError` mapping, no retry, and no relationship to the LLM provider
  abstraction. The `factory.py` docstring also references a non-existent
  `EMBEDDING_PROVIDER_REGISTRY`.
- **Minor drift:** duplicate provider-key/metadata maps (`factory._provider_key`,
  `endpoints/providers.py:_EMBEDDING_PROVIDERS`); `create_llm_provider` forwards
  a `model` parameter no builder uses.

### 3.2 Enterprise Authentication (OIDC / OAuth2)

Foundation is **solid and already implemented**: local email/password auth with
Argon2 (`security.py:14`), JWT issuance/validation (`security.py:31-87`), RBAC
via `require_roles` (`auth_dependencies.py:133-162`) and `RoleManager`
(`tenant_context.py:165-320`), and tenant isolation through
`get_tenant_context` + `TenantAwareRepository._apply_tenant_filter`
(`tenant_repository.py:54-58`).

Gaps:

- **OIDC / OAuth2 / SSO is entirely missing.** No `authlib`/OAuth client, no
  `/auth/{provider}` routes, no JWKS verification, and **no config keys**
  (`config.py:126-130` has only JWT secrets). This is the headline Milestone C
  build.
- **API-key authentication is not wired.** `verify_api_key` (`security.py:134`)
  is defined but never called; every protected route uses JWT bearer only. No
  `DELETE /api-keys/{id}` revoke endpoint; stored `scopes` are never enforced.
- **No logout / blacklist / revocation.** Refresh tokens are stateless
  (`security.py:54-66`); a logout cannot invalidate a still-valid token.
- **No email verification or password reset** flow (`email_verified=True`
  auto-set at `auth.py:89`).
- **Insecure JWT defaults.** Symmetric HS256 with default secret
  `"change-me-in-production"` (`config.py:127-128`). No asymmetric/JWKS support.

### 3.3 Audit Enrichment

The audit subsystem is structurally complete and wired end-to-end: a persisted
`audit_logs` table (`models/base.py:49-64`), a defensive `record_audit` service
(`services/audit.py:25-62`), and a tenant-scoped `GET /audit/logs` endpoint
gated to `owner`/`admin` (`endpoints/audit.py:36-100`). Coverage includes
document, knowledge-base, tool, user-membership, and webhook mutations.

Gaps are **enrichment**:

- **Authentication events are not audited at all.** `auth.py:125/158/188/219+`
  use the analytics `record_event`, not `record_audit`. Login, failed login,
  registration, refresh, and password change never reach `audit_logs`.
- **Rich fields are never populated.** `ip_address`/`user_agent` have params
  (`audit.py:33-34,48-49`) but no caller passes them; `request_id` exists in the
  DB migration (`001_initial_migration.py:342`) but is absent from the ORM model
  and never threaded from the middleware; no `duration` column.
- **No standardized status/outcome column** — outcome survives only inside
  `meta` for a few actions.
- **No retention / export / tamper-evidence.** `record_audit` swallows all
  errors silently, so dropped rows are undetectable.
- **ORM/DB drift** on `audit_logs`: the ORM model omits `api_key_id` and
  `request_id` present in the migration-built table.

### 3.4 Tenant Quotas & Usage

Usage **analytics** and raw usage-event **capture** are real and shipped
(`endpoints/analytics.py:64-239` tenant-scoped; `services/usage.py:18-63`). The
`Organization` model carries a `plan` string label and `stripe_*` columns but
**no numeric quota fields**.

Gaps:

- **No quota schema.** No `storage_quota`, `request_quota`, `seat_limit`,
  `kb_limit`, or `max_*` fields anywhere (`models/organization.py:11-40`).
- **No quota enforcement.** No middleware/dependency gates KB creation, document
  upload, seat addition, or API calls against any limit.
- **Rate limiter is not tenant-aware.** `core/rate_limit.py:36-52` keys on
  client IP with a process-local dict; all tenants behind one IP share a bucket.
- **Usage metering is capture-only.** `usage.py` records tokens/`cost_usd` but no
  service aggregates per-tenant usage (documents, storage bytes, seats, KB
  count, request count) against limits.
- **Billing is absent.** No Stripe/Razorpay SDK, no billing endpoints, the
  `stripe_*` columns are never read/written, and `can_manage_billing`
  (`tenant_context.py:68`) is unused. **No functional billing foundation
  exists.**

### 3.5 Background Task Durability & Infrastructure

`services/background_tasks.py` is a **thin CRUD layer** over a Postgres table —
it records status/progress for polling but performs **no execution**. Document
embedding still runs **synchronously inside the HTTP request**
(`documents.py:431-462`, which blocks on `provider.embed` then writes chunks).

- **No broker, no worker.** Celery is *configured* (`CELERY_BROKER_URL` /
  `CELERY_RESULT_BACKEND` in `config.py:299-301`, passed to compose containers)
  but is **not a dependency**, **never imported**, and has **no worker/beat
  service** in any `docker-compose*.yml`.
- **Durability is partial.** Persistence + status yes; retries, idempotency,
  failure-recovery, and dead-letter handling are **missing** (webhook delivery
  hardcodes `attempt_count = 1` at `notifications.py:131-141`).
- **Redis is runtime-idle.** Configured and connected (`core/redis.py`), used
  only for health/metrics probes; not used as cache/session/broker. The rate
  limiter is explicitly in-memory and single-instance.

**Large-infrastructure capabilities — all explicitly out-of-scope:** Kubernetes,
multi-region, database clustering, Redis replication, service mesh, and event
buses have **no foundation** in code or deployment artifacts. Every occurrence in
`docker-compose.yml`, `docker-compose.aws.yml`, `docs/deployment/*.md`, and
`PHASE_5_DEPLOYMENT_PLAN.md` states they are deferred to a later milestone.
**These are moved to the Future Roadmap (Section 5) and are not part of this
implementation plan.**

### 3.6 Analytics Improvements

`GET /metrics` (`main.py:120-134`) exposes a rich Prometheus surface
(`core/metrics.py`: HTTP, dependency health, app state, queue length, DB pool,
Redis) with Grafana dashboards (`monitoring/grafana/`). Tenant-scoped analytics
endpoints exist (`endpoints/analytics.py:64-239`).

Gaps:

- **Event capture is narrow.** `UsageEvent` model + `record_event` exist, but
  only `tools.py:241` and `documents.py:596` call it. Chat-message, RAG-query,
  agent/KB/user-creation events are **not** recorded (contradicting the
  `usage.py`/`analytics.py` docstrings).
- **No cross-tenant / platform admin view.** Endpoints filter by the caller's
  `organization_id` only.
- **No per-user breakdown or pagination** on large result sets.
- **No in-app product-analytics dashboard** — the frontend has no analytics
  route; only raw JSON endpoints. No cost-attribution per user, budgets, or
  quota alerts.

### 3.7 Enterprise Documentation

The repository documents deployment, backup/recovery, security operations, and
runbooks well. What is **absent by name**: a dedicated *Enterprise Deployment
Guide*, a standalone *Disaster Recovery Guide* (RTO/RPO), a consolidated
*Security Architecture* doc, an *SSO/OIDC Setup Guide* (no feature to document),
and a regulatory *Compliance Checklist* (the existing `security-checklist.md`
is operational, not a GDPR/SOC 2/HIPAA control mapping). See Section 6.

---

## 4. Reprioritized Milestone C Roadmap (Order)

The repository's actual state dictates the order. Work that improves enterprise
readiness first; defer anything with no foundation.

| # | Priority | Why this order (verified state) |
| --- | --- | --- |
| 1 | **Provider stabilization** | Providers exist and are correct; only resilience gaps remain (retry, timeout, health, cost, Ollama default). Lowest-risk, highest-confidence win. |
| 2 | **Enterprise Authentication (OIDC/OAuth2)** | Largest genuine gap (entirely missing) but builds on a solid local-auth/RBAC/tenant-isolation base. Required before SSO-dependent docs and enterprise onboarding. |
| 3 | **Audit enrichment** | Subsystem already wired; fill IP/request-ID/status, audit auth events, add retention/export. High compliance value, low architectural risk. |
| 4 | **Tenant quotas** | Add quota schema + enforcement + tenant-aware rate limiting on top of existing `Organization`/`usage` data. |
| 5 | **Background task durability** | Make the existing `background_tasks` table actually drive async work (worker + retry + DLQ) instead of in-request execution. |
| 6 | **Analytics improvements** | Broaden event capture, add cross-tenant admin view, per-user cost, dashboards. |
| 7 | **Enterprise documentation** | Author the seven named enterprise docs (Deployment, DR, Backup, Security Architecture, SSO/OIDC, Compliance, Runbooks). |
| 8 | **Billing (optional)** | **Deferred** — no functional foundation. Do not implement unless/until a real billing base is added. |

---

## 5. Future Roadmap (Deferred — Not in This Milestone)

These capabilities are **not proposed for implementation** in Milestone C because
the repository contains no foundation for them (confirmed in Section 3.5). They
are recorded here as directional, to be revisited only when a concrete need and
a foundation exist.

- **Kubernetes / container orchestration** — current model is single-host Docker
  Compose (or single-EC2 compose on AWS). No manifests, no operator.
- **Multi-region deployment** — `docs/deployment/backups.md:7-10` explicitly
  scopes to single-instance, no cross-region replication.
- **Database clustering / read replicas** — single Postgres container / single
  managed RDS; no replica topology.
- **Redis replication (ElastiCache replication group)** — single-node Redis;
  `env.production.example:24` lists it only as a placeholder field.
- **Service mesh (Istio/Linkerd/Envoy)** — nginx is the sole reverse proxy.
- **Event buses (Kafka/RabbitMQ)** — webhooks are synchronous HTTP POSTs with no
  queue; no broker exists.
- **Billing / subscription (Stripe/Razorpay)** — gated on first establishing a
  real billing foundation (currently only unused `stripe_*` columns).

---

## 6. Enterprise Documentation Gap Analysis

| Document | Status | Current location |
| --- | --- | --- |
| Enterprise Deployment Guide | Partial | `docs/deployment/{production,aws,docker,github-actions}.md` |
| Disaster Recovery Guide | Partial | `docs/deployment/backups.md`, `docs/reports/BACKUP_AND_RECOVERY.md` |
| Backup Strategy | Exists | `docs/deployment/backups.md`, `docs/reports/BACKUP_AND_RECOVERY.md` |
| Security Architecture | Partial | `ARCHITECTURE.md` §2/§5 + `docs/deployment/security-{checklist,headers,scanning,secrets,aws-iam,aws-secrets}.md` |
| SSO/OIDC Setup Guide | Missing | — (depends on Priority 2) |
| Compliance Checklist | Missing | `docs/deployment/security-checklist.md` is operational only |
| Operational Runbooks | Exists | `OPERATIONS.md`, `docs/deployment/ROLLBACK.md`, `PRODUCTION_CHECKLIST.md` |

See the implementation plan (Priority 7) for the authoring tasks that fill the
Partial/Missing rows above.
