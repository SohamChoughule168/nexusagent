# NexusAgent v1.0.0 — Release Notes

**Release date:** 2026-07-18
**Tag:** `v1.0.0`

NexusAgent is a multi-tenant AI Agent SaaS platform: organizations create
AI agents, ground them in their own knowledge bases with retrieval-augmented
generation (RAG), give them tools and function calling, and hold conversations
with short- and long-term memory — all isolated per tenant.

This is the first production release, consolidating seven milestones of work
into a verified, documented, and deployable system.

---

## Features

### Multi-tenancy & authentication
- Organization-scoped data model with **PostgreSQL Row-Level Security** plus an
  app-layer tenant repository for defense in depth.
- JWT authentication (access + refresh tokens), **Argon2** password hashing,
  role-based access control (owner / admin / member / viewer).
- Self-service registration that provisions an organization, an owner
  membership, and a default knowledge base in one transaction.
- **API keys** for programmatic access — tenant-scoped, hashed at rest, and
  shown in plaintext only once at creation.

### AI agents
- Full agent CRUD with per-agent model, system prompt, temperature, token
  limits, enabled tools, and attached knowledge bases.
- **Agent Builder** UI for composing and configuring agents.

### Knowledge bases & RAG
- Knowledge base CRUD, PDF document upload, text extraction + chunking, and
  per-chunk embedding generation.
- Cosine-similarity retrieval and retrieve-and-compose answering.
- Pluggable embedding and RAG-LLM providers (local fallback or OpenRouter).

### Conversations & memory
- Conversation and message management with history.
- **Short-term** conversation memory with token budgeting.
- **Long-term** memory: summary engine, semantic retrieval, consolidation, and
  recency/relevance ranking.

### Tools, function calling & orchestration
- Tenant-scoped **Tool Registry** and a sandboxed **Tool Execution Engine**
  (timeout + output-size bounds).
- LLM **function calling** wired into the chat pipeline.
- **Agent Orchestrator** (task planning, agent-to-agent comms, sequential /
  parallel execution, failure recovery) and a **Multi-Agent Router**.

### Frontend
- Next.js 15 / React 19 app: login, dashboard hub, chat workspace (streaming,
  markdown, citations, token usage), knowledge base management, and agent builder.

### Operations & observability
- Prometheus `/metrics`, Grafana dashboards, structured JSON logging, access
  logs, request-ID propagation, and Kubernetes-style health probes
  (`/health/live`, `/health/ready`, `/health/startup`).
- Docker images for backend and frontend, `docker-compose` for local and AWS,
  nginx reverse proxy, and AWS single-instance deployment tooling.

---

## Improvements
- Completed and hardened the API-key endpoints (previously stubs).
- Version unified to `1.0.0` across backend, frontend, and env templates.
- Repository cleaned of the obsolete Express prototype and placeholder docs.
- New documentation set: architecture, operations, contributing, performance,
  changelog, and these release notes.

---

## Security
- Argon2 password hashing; JWT access/refresh with configurable expiry.
- Row-Level Security on tenant tables plus app-layer isolation.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN`,
  CSP, HSTS via nginx), configurable rate limiting, and CORS allow-listing.
- Secrets are never committed: fail-fast on missing production secrets, env
  templates with placeholders, and AWS Secrets Manager guidance.
- CI security scanning (dependency audit + Bandit static analysis).
- See `docs/deployment/security-checklist.md` before going live.

---

## Known limitations
- **In-app product analytics** — the dashboard is a navigation hub; operational
  metrics live in Grafana. A product-level analytics view is post-1.0.
- **Document formats** — ingestion accepts **PDF only** (`application/pdf`).
  Other formats are a future enhancement.
- **`memories` table has no DB-level RLS** — long-term memory isolation is
  enforced at the application layer only. Keep queries going through the
  tenant-scoped services.
- **Embeddings/RAG default to a local fallback** — for production-quality
  answers, configure a real provider (`OPENROUTER_API_KEY`,
  `EMBEDDINGS_PROVIDER`, `RAG_LLM_PROVIDER`).
- **Single Uvicorn worker per container** — scale horizontally (more containers)
  rather than relying on one process.
- **mypy is non-blocking** and ruff runs with a temporary ignore baseline
  (`F401/F541/F841/F821/E402`) for pre-1.0 code; both are green as gates today
  and slated to tighten post-1.0.
- **Frontend Docker image** ships full `node_modules`; Next.js standalone output
  is a documented, deferred size optimization (see `docs/PERFORMANCE.md`).

---

## Upgrade notes
This is the initial release — there is no prior production version to upgrade
from. For fresh deployment:

1. Copy `env.production.example` → `.env.production` and fill in **every**
   `replace-with-*` secret (JWT keys, DB password, password salt). Required
   secrets have no defaults and the app fails fast if omitted.
2. Provision PostgreSQL and Redis (RDS + ElastiCache on AWS, or containers).
3. Run database migrations: `alembic upgrade head` (see `deploy/db-migrate.sh`).
4. Deploy with `docker compose -f docker-compose.aws.yml --env-file .env.production up -d`.
5. Follow `docs/deployment/production.md` and `docs/deployment/security-checklist.md`.

Full deployment and operations detail: `OPERATIONS.md` and `docs/deployment/`.
