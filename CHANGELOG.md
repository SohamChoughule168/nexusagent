# Changelog

All notable changes to NexusAgent are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-07-18

First production release. Consolidates Milestones 1–7 into a verified,
documented, deployable platform.

### Added
- **Release engineering & docs**: `CHANGELOG.md`, `RELEASE_NOTES_v1.0.0.md`,
  `ARCHITECTURE.md`, `OPERATIONS.md`, `CONTRIBUTING.md`, `VERSION`,
  `docs/PERFORMANCE.md`.
- **API keys**: completed the `POST /auth/api-keys` and `GET /auth/api-keys`
  endpoints — now authenticated, tenant-scoped, and persistent. The plaintext
  key is returned exactly once on creation; only its hash is stored and listing
  exposes non-secret metadata only. Added `test_api_keys.py` (5 tests).

### Fixed
- **`APIKey.id` primary key** had no default generator (it shadowed the
  `TimestampedModel` UUID default), which prevented API-key rows from being
  inserted. Restored the `default=uuid.uuid4` generator to match the other
  tenant models.
- **Stale security-header test**: `test_security_headers_present` still asserted
  `X-Frame-Options: DENY`; aligned it with the Phase 6 hardening value
  `SAMEORIGIN` (documented in `docs/deployment/security-headers.md`).

### Changed
- Bumped version to `1.0.0` across `pyproject.toml`, `frontend/package.json`,
  backend `APP_VERSION`, and env templates.
- Dashboard landing page comment updated: it is a navigation hub for 1.0;
  in-app product analytics is a post-1.0 enhancement (operational metrics are
  served by Prometheus/Grafana).

### Removed
- Obsolete Express prototype (`backend/app.js`, `backend/middleware/`,
  `backend/models/` [JS], `backend/routes/`, `backend/services/` [JS]) — dead
  code never referenced by the FastAPI application. Moved outside the repository.
- `frontend/app/dashboard/README.md` placeholder note.

---

## [0.5.0] — 2026-07-16 — Milestone 5: Memory System

### Added
- **Conversation Memory** (Phase 1): short-term memory integrated into the chat,
  router, and orchestrator pipelines with token budgeting.
- **Conversation Summary Engine** (Phase 2.1): rolling summarization of long
  conversations.
- **Long-Term Memory Store** (Phase 2.2): tenant-scoped persistent memory
  (`memories` table; app-layer tenant isolation).
- **Semantic Memory Retrieval** (Phase 2.3): embedding-based recall of relevant
  past memories.
- **Memory Consolidation** (Phase 2.4): deduplication/merging of related
  memories.
- **Memory Ranking** (Phase 2.5): recency/relevance scoring for retrieval.

---

## [0.4.4] — 2026-07-15 — Milestone 4: Tools, Function Calling & Orchestration

### Added
- **Tool Registry** (Phase 1): tenant-scoped registry of executable tools.
- **Tool Execution Engine** (Phase 2): sandboxed execution with timeout and
  output-size bounds.
- **Function Calling** (Phase 3): LLM function-calling wired into the chat
  pipeline with tenant isolation.
- **Agent Orchestrator** (Phase 4): task planning, agent-to-agent
  communication, sequential/parallel execution, and failure recovery.
- **Multi-Agent Router** (Phase 5): routes an incoming request to the best-fit
  agent.

### Fixed
- Inactive-user authentication regression.

---

## [0.3.x] — 2026-07-14 — Milestone 3: Conversation & RAG Layer

### Added
- **Knowledge Base API**: CRUD for tenant-scoped knowledge bases.
- **Document Upload API**: PDF upload into a knowledge base.
- **Document Ingestion API**: text extraction and chunking into
  `document_chunks`.
- **Vector Storage & RAG Retrieval**: per-chunk embeddings + cosine-similarity
  search.
- **RAG Query endpoint**: retrieve-and-compose answering.
- **Streaming Chat + RAG**: conversation chat endpoint with retrieval grounding.
- **Tenant-scoped Agent API**: CRUD for agents with RBAC.
- Reconciled Milestone 3 architecture/schema drift.

---

## Milestones 1–2 — Foundation (pre-0.3.0)

### Added
- **Milestone 1**: FastAPI application skeleton, health endpoints, request-ID
  and security-header middleware, structured logging, configuration system,
  initial database schema and migrations.
- **Milestone 2**: authentication (JWT access/refresh, Argon2 password hashing),
  organizations and membership, multi-tenant data model with Row-Level Security
  policies, tenant-scoped repository layer.

---

## Milestone 6 — Frontend (0.x, 2026-07-16 → 2026-07-18)

### Added
- **Phase 1**: Next.js 15 + React 19 frontend foundation (App Router, Tailwind,
  React Query, Zustand, auth shell).
- **Phase 2**: Chat UI (streaming messages, markdown, citations, token usage).
- **Phase 3**: Knowledge Base management UI (documents, ingestion status).
- **Phase 4**: Agent Builder UI.

---

## Milestone 7 — Production Readiness (2026-07-18)

### Added
- **Phase 1**: Docker containerization (multi-stage backend + frontend images).
- **Phase 2**: GitHub Actions CI/CD (backend tests, frontend tests, docker
  validation, security scanning).
- **Phase 3**: production deployment foundation (compose, nginx, env templates).
- **Phase 4**: AWS single-instance deployment (user-data, IAM policy, secrets,
  backup/restore scripts, deployment docs).
- **Phase 5**: production observability (Prometheus metrics, Grafana dashboards,
  access logs, request context).
- **Phase 6**: security hardening (security headers, rate limiting, secrets
  handling, security scanning, checklist).

[1.0.0]: https://github.com/SohamChoughule168/nexusagent/releases/tag/v1.0.0
