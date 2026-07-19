# NexusAgent — FAQ

Answers to common questions about NexusAgent `1.0.0` (General Availability).
For operators, see [`OPERATIONS.md`](../OPERATIONS.md) and the
[deployment guides](deployment/). For a hands-on walkthrough, see the
[User Guide](user-guide/README.md).

---

### What is NexusAgent?

NexusAgent is a multi-tenant AI agent platform. Organizations build agents,
ground them in their own knowledge bases with retrieval-augmented generation
(RAG), extend them with tools and function calling, and hold conversations with
short- and long-term memory. All data is isolated per tenant.

### How do I try it without setting anything up?

Run the local stack ([quickstart](user-guide/quickstart.md)), then open the
[live demo](http://localhost:3000/demo) — it drops you into a chat with *Aria*,
a sample support agent grounded in a seeded help center. No account required.

### Is there a hosted cloud version?

No. NexusAgent `1.0.0` is self-hosted via Docker Compose (single-host or
AWS single-instance). See [`docs/deployment`](deployment/).

### Which file formats can I upload to a knowledge base?

**PDF only** in this release. The upload allow-list is configured for more
types, but only PDF is parsed by the ingestion pipeline today. Other formats
(text, docx, csv, html, md, json) are a fast-follow. See
[`docs/BETA_READINESS.md`](../BETA_READINESS.md) limitation L1.

### Does it work without an LLM / embedding API key?

Yes. With no provider key configured, RAG answers use a local composer over the
retrieved chunks and embeddings use a deterministic local embedder, so the
demo seeds and answers **offline**. For production answer quality, configure an
OpenRouter (or OpenAI) key.

### How is my data isolated from other tenants?

Every tenant's data lives in one PostgreSQL database, isolated by Row-Level
Security on the core tables plus an app-layer tenant repository that all data
access flows through. Long-term memory (`memories`) is isolated at the
application/service layer (no DB-level RLS yet) — keep memory access through the
tenant-scoped services. See [`ARCHITECTURE.md`](../ARCHITECTURE.md).

### How are passwords and tokens handled?

- Passwords are hashed with Argon2; never stored in plaintext.
- Access is via JWT bearer tokens (short-lived access + refresh).
- Role-based access control: owner / admin / member / viewer.

Changing a password requires an authenticated session — the target account is
derived from your active login, never from a value you send in the request.

### Is email verification / password reset available?

For the self-service beta/GA, `email_verified` is set `true` at registration so
users can get started immediately. A real email-verification and
password-reset-with-token flow is a post-GA item.

### Is there a public API?

Yes — a versioned REST API under `/api/v1` (auth, agents, conversations,
knowledge bases, documents, tools, routing). In development the interactive
Swagger docs are at `/docs` and the OpenAPI schema at `/openapi.json`. **In
production both are disabled** (`DOCS_ENABLED=false`) so the API surface is not
publicly advertised; see [`docs/user-guide/api-examples.md`](user-guide/api-examples.md)
for worked examples.

### Are there rate limits?

Yes — an app-layer, per-IP budget (`RATE_LIMIT_PER_MINUTE`, default 100) throttles
unauthenticated clients before they reach business logic. The nginx edge plus
provider limits are the primary abuse boundary; tighten the budget with
production telemetry.

### How do I report a problem?

Open an issue with the app version (`GET /version` → `build_git_sha`), the
request `X-Request-ID` (echoed in every response), and a timestamp. See the
support checklist in [`docs/BETA_READINESS.md`](../BETA_READINESS.md) §5.

### Where can I see known limitations and issues?

[`docs/BETA_READINESS.md`](../BETA_READINESS.md) tracks limitations (L1–L7) and
known issues (K1–K6) with severity and disposition.
