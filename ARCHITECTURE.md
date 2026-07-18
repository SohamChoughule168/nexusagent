# NexusAgent — Architecture

This document describes the system as shipped in v1.0.0.

## 1. System overview

NexusAgent is a multi-tenant AI Agent SaaS platform. Each **organization**
(tenant) owns its agents, knowledge bases, documents, conversations, tools, and
memories. Users authenticate, act within their organization, and interact with
AI agents that are grounded in the organization's knowledge base via RAG,
extended with tools and function calling, and aware of conversation history and
long-term memory.

```
                         ┌──────────────────────────┐
        Browser  ─────►  │  nginx (TLS, rate limit) │
                         └────────────┬─────────────┘
                          /            \
                   /api/*  \            \  /
                           ▼             ▼
              ┌───────────────────┐   ┌──────────────────┐
              │  Backend (FastAPI)│   │ Frontend (Next.js)│
              │  Uvicorn worker   │   │  next start       │
              └─────────┬─────────┘   └──────────────────┘
                        │
          ┌─────────────┼───────────────┐
          ▼             ▼               ▼
   ┌────────────┐ ┌──────────┐  ┌────────────────┐
   │ PostgreSQL │ │  Redis   │  │ LLM/Embeddings │
   │  (RLS)     │ │ (cache/  │  │  provider      │
   │            │ │  ratelim)│  │ (OpenRouter…)  │
   └────────────┘ └──────────┘  └────────────────┘

   Observability: Prometheus scrapes /metrics · Grafana dashboards
```

## 2. Backend architecture

FastAPI application (`backend/app`), installed as a top-level `app` package via
`pyproject.toml` (`package-dir = {"" = "backend"}`).

### Layering
- **`app/main.py`** — application factory: middleware stack, exception handlers,
  router mounting, health/metrics endpoints, and the lifespan (Redis init/close,
  startup-probe flip).
- **`app/api/v1/`** — HTTP layer. `router.py` aggregates endpoint routers under
  `/api/v1`. Endpoints: `auth`, `agents`, `conversations`, `knowledge_bases`,
  `documents` (KB documents + document ops), `tools`, `routing`.
- **`app/schemas/`** — Pydantic request/response models (validation boundary).
- **`app/services/`** — business logic: `rag`, `ingestion`, `embeddings`,
  `conversation_memory`, `long_term_memory`, `semantic_memory`,
  `memory_consolidation`, `memory_ranking`, `tool_registry`, `tool_executor`,
  `function_calling`, `agent_orchestrator`, `multi_agent_router`,
  `tenant_context`.
- **`app/repositories/`** — tenant-scoped data access (`tenant_repository`)
  enforcing organization isolation at the query layer.
- **`app/models/`** — SQLAlchemy models. `base.py` defines
  `TimestampedModel` (UUID PK + timestamps) and `MultiTenantModel`;
  `all_models.py` holds the concrete tables; `user.py` and `organization.py`
  hold those aggregates.
- **`app/ai/`** — provider abstraction (`ai/providers/base.py`,
  `openrouter.py`) for LLM/embeddings, with local fallbacks.
- **`app/core/`** — cross-cutting concerns: `config` (pydantic-settings),
  `database` (sync SQLAlchemy engine/session), `redis`, `security` (JWT, Argon2,
  API-key hashing), `auth_dependencies` (`get_current_user`,
  `get_tenant_context`, `require_roles`), `middleware` + `observability_middleware`,
  `rate_limit`, `metrics`, `health`, `logging`, `exceptions`.

### Middleware stack (outermost → innermost)
`CORS → GZip → SecurityHeaders → RateLimit (optional) → Metrics → AccessLog →
RequestContext → RequestID`. RequestID is registered last so it sets
`request.state.request_id` before observability middleware reads it.

## 3. Frontend architecture

Next.js 15 (App Router) + React 19, TypeScript, Tailwind.

- **`app/`** — routes: `login`, `dashboard`, `chat`, `knowledge-bases`
  (+ `[kbId]`), `agents`.
- **`features/`** — feature modules: `auth`, `chat`, `knowledge-base`,
  `agent-builder`.
- **`components/`** — shared UI: `ui/` (design system), `chat/`, `layout/`.
- **`services/`** — API clients (axios) to the backend.
- **`store/`** — Zustand stores (chat, notifications).
- **`providers/`** — React Query + theme providers.
- **`hooks/`, `lib/`, `types/`** — shared hooks, utilities, and types.

Data fetching uses React Query; `NEXT_PUBLIC_API_BASE_URL` is inlined at build
time and the browser calls the backend on the same origin through nginx (`/api`).

## 4. Database

PostgreSQL 16, SQLAlchemy 2.0, Alembic migrations (`backend/alembic/versions/`).

Core tables (`organizations`, `organization_members`, `organization_settings`,
`system_settings`, `users`, `agents`, `knowledge_bases`, `documents`,
`document_chunks`, `conversations`, `messages`, `leads`, `tools`,
`tool_configs`, `usage_events`, `api_keys`, `memories`).

- Every tenant table carries `organization_id`. **Row-Level Security** policies
  (migration `002_rls_policies`) enforce isolation at the database layer for the
  core tables.
- The `memories` table has **no DB-level RLS**; its isolation is enforced in the
  application/service layer only.
- Primary keys are UUIDs with both Python-side (`uuid.uuid4`) and server-side
  (`gen_random_uuid()`) defaults.

Migrations: `001_initial`, `002_rls_policies`, `003_reconcile_orm_schema`,
`004_document_chunk_embedding`, `005_reconcile_models_to_migrations`,
`006_long_term_memory`.

## 5. Authentication

- **Passwords**: Argon2 (`argon2-cffi`) hashing.
- **Tokens**: JWT access (default 30 min) + refresh (default 7 days), signed
  with separate secrets (`JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`).
- **Dependencies**: `get_current_user` resolves the principal from the bearer
  token; `get_tenant_context` validates active membership and yields a
  `TenantContext` (organization_id, user_id, role); `require_roles(...)`
  enforces RBAC.
- **Roles**: owner, admin, member, viewer (capabilities exposed as
  `TenantContext` properties, e.g. `can_manage_agents`).
- **API keys**: generated, prefixed, and hashed; plaintext returned once. Stored
  in `api_keys`, tenant-scoped.

## 6. RAG pipeline

1. **Upload** (`POST /knowledge-bases/{id}/documents`) — PDF stored on disk
   (EBS volume in production), row in `documents`.
2. **Ingest** (`POST /documents/{id}/ingest`) — extract text, split into
   `document_chunks`.
3. **Embed** (`POST /documents/{id}/embed`) — generate a vector per chunk
   (stored on `document_chunks.embedding`) via the configured embeddings
   provider.
4. **Retrieve** (`GET /knowledge-bases/{id}/search`) — rank chunks by cosine
   similarity to the query embedding.
5. **Compose** (`POST /knowledge-bases/{id}/query` and the chat pipeline) —
   assemble retrieved context and generate an answer with the RAG LLM provider.

Providers are pluggable (`EMBEDDINGS_PROVIDER`, `RAG_LLM_PROVIDER`) with a local
fallback for offline/dev use.

## 7. Memory system

- **Short-term** (`conversation_memory`) — recent turns injected into the
  prompt under a token budget.
- **Summary engine** — rolling summaries of long conversations.
- **Long-term store** (`long_term_memory`, `memories` table) — persistent,
  tenant-scoped memories.
- **Semantic retrieval** (`semantic_memory`) — embedding-based recall.
- **Consolidation** (`memory_consolidation`) — dedup/merge related memories.
- **Ranking** (`memory_ranking`) — recency/relevance scoring.

Memory is consumed by the chat pipeline, the multi-agent router, and the
orchestrator.

## 8. Tool execution & orchestration

- **Registry** (`tool_registry`, `tools` table) — tenant-scoped tool
  definitions with JSON-Schema input validation and a `tool_type` dispatch.
- **Executor** (`tool_executor`) — runs tools with a timeout
  (`TOOL_EXECUTION_TIMEOUT_SECONDS`) and output cap
  (`TOOL_EXECUTION_MAX_OUTPUT_CHARS`). Built-in tool types gated by feature
  flags (webhook, lead capture, human escalation).
- **Function calling** (`function_calling`) — exposes tools to the LLM and
  executes requested calls within the chat pipeline.
- **Orchestrator** (`agent_orchestrator`) — plans tasks, coordinates
  agent-to-agent communication, runs steps sequentially/in parallel, and
  recovers from failures.
- **Router** (`multi_agent_router`) — selects the best agent for a request.

## 9. Deployment architecture

- **Containers**: multi-stage Docker images for backend (`python:3.11-slim`,
  runs `uvicorn app.main:app` as non-root) and frontend (`node:20-alpine`,
  `next start` as non-root). Both define healthchecks.
- **Compose**: `docker-compose.yml` (local: db + redis + backend + frontend)
  and `docker-compose.aws.yml` (production: RDS/ElastiCache endpoints,
  read-only root FS, dropped capabilities, env-file secrets).
- **Reverse proxy**: nginx (`nginx/nginx.conf`, `tls.conf.example`) terminates
  TLS, applies HSTS, and routes `/api` → backend, everything else → frontend.
- **AWS**: single-instance deployment via `deploy/` scripts (`user-data.sh`,
  `init-deploy.sh`, `update-containers.sh`, `rolling-restart.sh`,
  `backup.sh`, `restore.sh`, `db-migrate.sh`, `healthcheck.sh`) and
  `deploy/iam-policy.json`. See `docs/deployment/aws.md`.
- **Observability**: Prometheus scrapes `/metrics`; Grafana dashboards in
  `monitoring/`. See `docs/deployment/observability.md`.
- **CI/CD**: GitHub Actions — `backend-ci.yml` (pytest + coverage against
  ephemeral Postgres/Redis), `frontend-ci.yml`, `docker-validation.yml`,
  `security.yml`.

## Related documents
- `OPERATIONS.md` — deploy, monitor, backup, restore, incident response.
- `docs/deployment/` — detailed deployment, security, and observability guides.
- `docs/PERFORMANCE.md` — performance baselines.
- `CONTRIBUTING.md` — local setup and development workflow.
