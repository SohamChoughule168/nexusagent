# API Examples (curl)

A copy-paste walkthrough of the NexusAgent public API. The API is mounted under
`/api/v1`. For the full, authoritative schema of every request/response, open
the live Swagger UI at `http://localhost:8000/docs` (or `https://<DOMAIN>/docs`
in production).

> **Base URL.** Local (direct backend): `http://localhost:8000/api/v1`.
> Through nginx (recommended): `http://localhost/api/v1`.
> The demo workspace (`demo@nexusagent.dev` / `nexusagent-demo`) is seeded by
> `backend/scripts/seed_demo.py` — you can sign in with those credentials, or
> register your own org below.

Set a base for the examples:

```bash
BASE=http://localhost:8000/api/v1
```

---

## 1. Health & version

```bash
curl -fsS http://localhost:8000/health          # {"status":"healthy"}
curl -fsS http://localhost:8000/version | python -m json.tool
```

---

## 2. Register an organization + owner

```bash
curl -fsS -X POST "$BASE/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "you@example.com",
    "password": "a-strong-password",
    "full_name": "You",
    "organization_name": "Acme",
    "organization_slug": "acme"
  }'
```

Response includes `access_token`, `refresh_token`, and a `user` object with
`organization_id`. Capture the token:

```bash
TOKEN=$(curl -s -X POST "$BASE/auth/register" -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"a-strong-password","full_name":"You","organization_name":"Acme","organization_slug":"acme"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

---

## 3. Login (OAuth2 password form)

```bash
curl -fsS -X POST "$BASE/auth/login" \
  -d "username=you@example.com&password=a-strong-password"
```

---

## 4. Create a knowledge base

```bash
curl -fsS -X POST "$BASE/knowledge-bases/" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Acme Help Center",
    "description": "Support articles for Acme",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "chunk_strategy": "recursive"
  }'
# Capture the KB id:
KB=$(curl -s "$BASE/knowledge-bases/" -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
```

---

## 5. Upload a document (PDF)

```bash
curl -fsS -X POST "$BASE/knowledge-bases/$KB/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./path/to/article.pdf"
# Capture the document id:
DOC=$(curl -s "$BASE/knowledge-bases/$KB/documents" -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
```

> Ingestion accepts **PDF only** today (`ALLOWED_MIME_TYPES=["application/pdf"]`).

---

## 6. Ingest + embed

```bash
curl -fsS -X POST "$BASE/documents/$DOC/ingest"   -H "Authorization: Bearer $TOKEN"
curl -fsS -X POST "$BASE/documents/$DOC/embed"    -H "Authorization: Bearer $TOKEN"
```

---

## 7. Create an agent

Field names follow the agent schema in `/docs`; the snippet below is
representative — confirm exact fields there.

```bash
curl -fsS -X POST "$BASE/agents/" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Support Agent",
    "description": "Answers from the Acme Help Center",
    "system_prompt": "You are Acme support. Cite the help center.",
    "model_provider": "openrouter",
    "model_name": "anthropic/claude-3.5-sonnet",
    "temperature": 0.4,
    "status": "active",
    "knowledge_base_ids": ["'$KB'"]
  }'
AGENT=$(curl -s "$BASE/agents/" -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; print(json.load(sys.stdin)[0]['public_id'])")
```

---

## 8. Chat with the agent (streaming)

```bash
curl -N -X POST "$BASE/conversations/" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "'$AGENT'", "title": "First chat"}'
# Capture conversation id, then chat:
CONV=$(curl -s "$BASE/conversations/" -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

curl -N -X POST "$BASE/conversations/$CONV/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message": "How do I reset my password?"}'
```

The chat endpoint streams the answer (SSE/text). Responses include citations
when the agent is grounded in a knowledge base.

---

## 9. Execute a tool

```bash
curl -fsS -X POST "$BASE/tools/$TOOL_ID/execute" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"input": {"url": "https://example.com/webhook", "payload": {"hello": "world"}}}'
```

---

## 10. Mint an API key

```bash
curl -fsS -X POST "$BASE/auth/api-keys" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "CI key", "scopes": ["chat", "read"]}'
# The plaintext `key` is returned exactly once — store it securely.
```

---

## Errors

- `401` missing/invalid/expired token → include `Authorization: Bearer <token>`.
- `403` not a member / role not permitted.
- `404` resource not found.
- `500` unexpected — the `X-Request-ID` response header correlates with logs.

See `docs/reports/PHASE_6_API_READINESS.md` for the full endpoint table and
readiness notes.
