# Phase 6 — API Readiness Review

**Scope:** the public HTTP API mounted under `/api/v1` (and root health/metrics/
version). **Method:** static review of `backend/app/api/v1/endpoints/*`,
`auth_dependencies.py`, `exceptions.py`, `config.py`, and `main.py`. Endpoints
verified against source.

---

## 1. Endpoint surface (auth = dependency)

| Router | Method & Path | Auth | Response model | Notes |
|--------|--------------|------|----------------|-------|
| auth | `POST /auth/register` | open | `TokenResponse` (201) | Provisions org + owner + default KB + tokens |
| auth | `POST /auth/login` | open | `TokenResponse` | OAuth2 password form |
| auth | `POST /auth/refresh` | open | `TokenResponse` | Rotates access+refresh |
| auth | `POST /auth/change-password` | **open (no session)** | raw `dict` | ⚠ K1 — email+current pw only |
| auth | `POST /auth/api-keys` | tenant | `APIKeyResponse` (201) | Plaintext key returned once |
| auth | `GET /auth/api-keys` | tenant | `dict` (untyped) | ⚠ K4 — untyped |
| agents | `GET/POST /agents/` | tenant / RBAC | `List[AgentResponse]` / `AgentResponse` (201) | CRUD |
| agents | `GET/PUT/DELETE /agents/{public_id}` | tenant / RBAC | typed / 204 | RBAC on write/delete |
| conversations | `GET/POST /conversations/` | tenant | typed / 201 | List + create |
| conversations | `GET/PUT/DELETE /conversations/{id}` | tenant | typed / 204 | |
| conversations | `GET /conversations/{id}/messages` | tenant | typed | History |
| conversations | `POST /conversations/{id}/chat` | tenant | `StreamingResponse` | RAG chat (SSE/text) |
| conversations | `POST /conversations/{id}/orchestrate` | tenant | `StreamingResponse` (NDJSON) | Multi-agent |
| conversations | `POST /conversations/{id}/route` | tenant | `StreamingResponse` (NDJSON) | Router |
| knowledge-bases | `POST /knowledge-bases/` | tenant | `KnowledgeBaseResponse` (201) | Create |
| knowledge-bases | `GET /knowledge-bases/`, `/{kb_id}` | tenant | typed | List + read |
| knowledge-bases | `PUT/DELETE /knowledge-bases/{kb_id}` | tenant | typed / 204 | |
| knowledge-bases | `POST /knowledge-bases/{kb_id}/documents` | tenant | typed (201) | Upload (PDF) |
| knowledge-bases | `GET /knowledge-bases/{kb_id}/documents` | tenant | typed | List docs |
| knowledge-bases | `GET /knowledge-bases/{kb_id}/search` | tenant | typed | Vector search |
| knowledge-bases | `POST /knowledge-bases/{kb_id}/query` | tenant | typed | RAG answer + sources |
| documents | `POST /documents/{id}/ingest` | tenant / RBAC | typed | Extract+chunk |
| documents | `GET /documents/{id}` | tenant | typed | Meta |
| documents | `DELETE /documents/{id}` | tenant / RBAC | 204 | |
| documents | `POST /documents/{id}/embed` | tenant / RBAC | typed | Embed chunks |
| tools | `GET /tools/`, `GET /tools/types` | tenant | `List[ToolResponse]` / `List[str]` | List + types |
| tools | `GET/POST /tools/{id}` | tenant / RBAC | typed / 201 | Read + create |
| tools | `PUT/DELETE /tools/{id}` | tenant / RBAC | typed / 204 | Update + delete |
| tools | `POST /tools/{id}/execute` | tenant | typed | Run tool |
| routing | `POST /routing/{conversation_id}/route` | tenant | `StreamingResponse` | (alias of router) |

**Root:** `GET /` (`{name,version}`), `GET /health` (`{status:"healthy"}`),
`/health/live|ready|startup|db|redis`, `/liveness`, `/ready`, `GET /metrics`
(Prometheus), `GET /version` (build info), `GET /docs`, `/redoc`,
`/openapi.json`.

---

## 2. OpenAPI / Swagger

- FastAPI serves the default UI at **`/docs`** (`Swagger UI`) and **`/redoc`**,
  plus **`/openapi.json`** — all unauthenticated.
- The app is constructed with `version=settings.APP_VERSION`, so the OpenAPI
  `info.version` reflects the release.
- **Gap (rec):** for a *public* deployment, `/docs` + `/openapi.json` should be
  environment-gated or auth-gated (they currently expose the full surface to
  anyone). Low effort — wrap in a conditional on a settings flag.

## 3. Authentication

- Protected endpoints uniformly depend on `get_tenant_context` /
  `require_roles(...)`, deriving `organization_id` from the JWT — never from
  request data. Consistent and correct.
- JWT access (30 min) + refresh (7 days), Argon2 password hashing, RBAC
  (owner/admin/member/viewer). 401 on missing/invalid/expired token or
  inactive user; 403 on missing membership / insufficient role.
- `POST /auth/change-password` is the **one** endpoint that eschews the auth
  dependency (accepts `email` + `current_password` in the body). Convenient for
  a no-session reset, but it widens the account-takeover surface if an attacker
  already knows the current password. **Recommend reviewing before GA (K1).**

## 4. Error responses

- Custom handler: `NexusAgentError` → `{"error": <msg>, "type": <class>}`;
  top-level `Exception` → `{"error": "Internal server error"}` (500) with
  `request_id` logged.
- **Two coexisting shapes:** most endpoints `raise HTTPException` → FastAPI
  renders `{"detail": …}`, while the custom handler renders `{"error","type"}`.
  Validation errors render `{"detail": […]}`. This is acceptable but inconsistent
  for API consumers. **Rec:** add an `HTTPException` handler that normalizes to
  `{"error","type"}` so the whole API speaks one error dialect.
- Streaming endpoints (chat/orchestrate/route) emit errors mid-stream as
  text/NDJSON and are not covered by the JSON error schema — document this in
  the API guide.

## 5. Pagination

- **Absent.** Every list endpoint returns an unbounded collection
  (`get_all()` / `get_by_*`). Fine for beta-scale tenants; a scaling/UX risk at
  GA. **Rec:** add limit/offset (or cursor) to `GET /agents`, `/conversations`,
  `/conversations/{id}/messages`, `/knowledge-bases`, `/tools`,
  `/knowledge-bases/{id}/documents`, and `GET /auth/api-keys`. Tracked as K3.

## 6. Request validation

- Bodies are Pydantic models. Constraints are uneven: `tool.py` has good
  `Field(min/max_length)` + validators; `agent.py` has **no numeric bounds**
  (unbounded `temperature`, `top_p`, `max_tokens`).
- Loose `Dict[str,Any]` accepted for `config`, `input_schema`, `user_metadata`,
  `citations`, `tool_calls`. Acceptable for flexibility; tighten where a schema
  is known.
- **Rec:** add bounds to agent LLM params; tighten document search to a model
  (`q`/`top_k` are raw query params today).

## 7. Response models

- Mostly typed (`*Response`). **Two untyped gaps:**
  - `GET /auth/api-keys` → `response_model=dict` (K4).
  - `POST /auth/change-password` → returns raw `{"message": …}` (K4).
- All root health/meta endpoints return bare `dict` (intentional, machine-facing).
- **Rec:** give `list_api_keys` and `change_password` typed `response_model`s.

## 8. Examples

- **None** in OpenAPI (no `json_schema_extra` / `Field(example=)`). Low effort,
  high value for a public beta — add `example` values to the primary request
  schemas (`UserRegister`, `AgentCreate`, `KnowledgeBaseCreate`,
  `DocumentUpload`, tool execute).

---

## 9. Readiness verdict

| Dimension | Status | Action before GA |
|-----------|--------|------------------|
| OpenAPI exposed | ✅ (ungated) | Gate `/docs` in production |
| Auth consistency | ✅ | Review `change-password` (K1) |
| Error schema | ⚠ | Unify to one shape |
| Pagination | ⚠ | Add before scale (K3) |
| Request validation | ✅ / ⚠ | Bound agent LLM params |
| Response models | ✅ / ⚠ | Type the 2 untyped (K4) |
| Examples | ⚠ | Add `example` values |

**No API issue blocks the public beta.** The ⚠ items are pre-GA polish,
tracked in `docs/BETA_READINESS.md`. See also the curl examples added at
`docs/user-guide/api-examples.md`.
