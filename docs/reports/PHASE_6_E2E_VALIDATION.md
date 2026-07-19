# Phase 6 — End-to-End User Journey Validation

**Scope:** Validate the ten core user journeys against the implemented API and
the Brightpath demo seed. **Method:** code + seed-script inspection (paths,
auth, error shapes) and a live version/health probe. Where a journey requires a
live LLM/embeddings key or a running Postgres+Redis stack to *fully* exercise,
it is marked **[live-creds]**; journeys that are demonstrable from the seed
script or static analysis are marked **[verified-by-inspection]**.

Endpoints referenced are mounted under `/api/v1` (see
`backend/app/api/v1/router.py`).

---

## Journey 1 — Registration & organization creation  ✅ [verified-by-inspection]

`POST /api/v1/auth/register` (`auth.py:45`)

- Creates `Organization` (plan `starter`), an owner `User`, an
  `OrganizationMember` (role `owner`), and a **default Knowledge Base**
  ("Default Knowledge Base") in one transaction.
- Returns `TokenResponse` (access + refresh + user object with
  `organization_id`, `organization_name`, `role`).
- **Auth:** open. **Validated:** 400 on duplicate email (`auth.py:51`).
- **Edge case:** non-unique `organization_slug` is not caught before the DB
  `INSERT` → surfaces as a 500 (IntegrityError). Friendly 409 mapping is a
  pre-GA fix candidate (see `docs/BETA_READINESS.md` K6).

## Journey 2 — Login & token refresh  ✅ [verified-by-inspection]

- `POST /api/v1/auth/login` (`auth.py:125`) — OAuth2 password form; 401 on bad
  credentials; 403 if `is_active` is false; updates `last_login_at`.
- `POST /api/v1/auth/refresh` (`auth.py:192`) — rotates access + refresh from a
  valid refresh token.
- **Edge case:** a user with **no** membership (shouldn't happen post-register)
  gets a 400 "not a member of any organization" (`auth.py:154`).

## Journey 3 — Agent creation  ✅ [verified-by-inspection]

`POST /api/v1/agents/` (`agents.py`) — tenant-scoped (auth), `response_model=
AgentResponse`, 201. All agent CRUD (`GET /`, `GET /{public_id}`, `PUT`,
`DELETE`) present. **RBAC:** create/update/delete gated by `require_roles`
where applicable.

## Journey 4 — Knowledge base creation  ✅ [verified-by-inspection]

`POST /api/v1/knowledge-bases/` (`knowledge_bases.py`) — tenant-scoped; full
CRUD with `response_model=KnowledgeBaseResponse`.

## Journey 5 — Document upload  ✅ [verified-by-inspection] / [live-creds]

`POST /api/v1/knowledge-bases/{kb_id}/documents` — uploads a PDF, persists raw
bytes to `UPLOAD_STORAGE_DIR`, and registers a `Document` row.

- **Constraint:** `ALLOWED_MIME_TYPES = ["application/pdf"]` — only PDFs are
  accepted by the pipeline (see Limitation L1 in `docs/BETA_READINESS.md`).
- **Edge case:** `ALLOWED_EXTENSIONS` lists 8 types but MIME allow-list is PDF
  only — a non-PDF upload is rejected at the MIME layer (K2).

## Journey 6 — Ingestion & embedding  ✅ [verified-by-seed]

Driven end-to-end by `backend/scripts/seed_demo.py` against the demo PDFs:

- `ingest_document(db, tenant, doc, kb)` extracts text and chunks it into
  `document_chunks` (`seed_demo.py:250`).
- `embed_document(...)` calls the KB's embedding provider and writes per-chunk
  vectors (`seed_demo.py:157`), sets `doc.status = "indexed"`.
- **Offline-capable:** with `EMBEDDINGS_PROVIDER=local` (default) the embedder
  is deterministic and needs **no API key** — the demo seeds fully offline
  (`seed_demo.py` uses the local provider).
- **Endpoints** (live-creds to run via API): `POST /documents/{id}/ingest`,
  `POST /documents/{id}/embed`.

## Journey 7 — Chat with agent  ✅ [verified-by-inspection] / [live-creds]

`POST /api/v1/conversations/{id}/chat` (`conversations.py`) — streaming RAG
chat. Retrieval is grounded in the agent's knowledge bases; citations are
returned with assistant messages.

- **Offline fallback:** without `RAG_LLM_PROVIDER`/`OPENROUTER_API_KEY`, the
  local composer returns the most relevant retrieved context (demo-grade, not
  production answer quality — Limitation L3).
- **History:** `GET /conversations/{id}/messages` returns the message list
  (Journey 9).

## Journey 8 — Tool execution  ✅ [verified-by-inspection]

`POST /api/v1/tools/{tool_id}/execute` (`tools.py`) — runs a tenant-scoped tool
through the execution engine (timeout `TOOL_EXECUTION_TIMEOUT_SECONDS`,
output cap `TOOL_EXECUTION_MAX_OUTPUT_CHARS`). Tool registry CRUD + `GET /types`
present. Built-in tool types (webhook, lead capture, human escalation) gated by
feature flags.

## Journey 9 — Conversation history  ✅ [verified-by-inspection]

- `GET /conversations/` (list), `GET /conversations/{id}` (detail),
  `GET /conversations/{id}/messages` (history, `response_model` typed).
- Sample conversations in the demo seed include assistant messages with
  `citations.sources` (`seed_demo.py:324`).

## Journey 10 — Error recovery  ✅ [verified-by-inspection]

- **401 Unauthorized:** missing/invalid/expired token, unknown/inactive user
  (`auth_dependencies.py:62-108`), bad login credentials (`auth.py:137`).
- **403 Forbidden:** missing/inactive membership, role not permitted
  (`auth_dependencies.py:127,153`).
- **404 Not Found:** `ResourceNotFoundError` handler → `{"error","type"}`.
- **500 / unexpected:** centralized handler returns `{"error":"Internal server
  error"}` and logs with `request_id` (`exceptions.py:59`).
- **Graceful degradation:** app boots without Redis (rate limiter falls back to
  in-process; readiness reports `degraded`, not `unhealthy`); without Postgres
  it fails fast.
- **Config fail-fast:** production `settings.validate()` refuses to boot on
  missing/insecure secrets (JWT keys, salt, DB/Redis URLs, provider keys).

---

## Summary

| Journey | Status | Evidence |
|---|---|---|
| 1. Register + org | ✅ | `auth.py:45-122` |
| 2. Login + refresh | ✅ | `auth.py:125-242` |
| 3. Agent creation | ✅ | `agents.py` |
| 4. KB creation | ✅ | `knowledge_bases.py` |
| 5. Document upload | ✅ | `knowledge_bases.py`, `config.py` MIME list |
| 6. Ingest + embed | ✅ (seed) | `seed_demo.py:157-254` |
| 7. Chat + RAG | ✅ | `conversations.py:chat`, fallback composer |
| 8. Tool execution | ✅ | `tools.py` |
| 9. Conversation history | ✅ | `conversations.py:messages` |
| 10. Error recovery | ✅ | `exceptions.py`, `auth_dependencies.py` |

**All ten journeys are implemented and internally consistent.** Full live
execution of 5/6/7 requires a running Postgres+Redis stack and (for generated
answers) an `OPENROUTER_API_KEY`; the demo seed exercises 6 end-to-end offline.

### Missing UX / edge cases to close before GA (not blockers for beta)
- K6: duplicate `organization_slug` → 500 instead of 409.
- K3: list endpoints are unbounded (no pagination).
- K1: `/auth/change-password` has no session requirement (email + current
  password only).
- L1: non-PDF uploads advertised by `ALLOWED_EXTENSIONS` but rejected by MIME
  list.

See `docs/BETA_READINESS.md` for the tracked list.
