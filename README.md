# NexusAgent

**The AI agent platform that knows your business.**

NexusAgent is a multi-tenant AI agent SaaS platform. Organizations build agents,
ground them in their own knowledge bases with retrieval-augmented generation
(RAG), extend them with tools and function calling, and hold conversations with
short- and long-term memory. All data is isolated per tenant.

> Version **1.0.0** — first production release. See [RELEASE_NOTES_v1.0.0.md](RELEASE_NOTES_v1.0.0.md).

## Why NexusAgent

Most chatbots guess. NexusAgent answers from *your* knowledge and shows its
work:

- **Grounded answers** — agents retrieve from your PDFs and docs (RAG) and cite
  the source, so replies are facts, not hallucinations.
- **Multi-agent orchestration** — route each request to the best agent; agents
  plan, delegate, and recover from failures.
- **Memory** — short-term context plus long-term, semantic memory that
  consolidates and ranks what matters across sessions.
- **Tools & function calling** — give agents real capabilities through a
  tenant-scoped tool registry.
- **Secure by default** — multi-tenant isolation, JWT auth, Argon2 hashing, and
  RBAC (owner / admin / member / viewer).

## Explore it live

You don't need an account to see it work:

- **Landing page** — <http://localhost:3000/> (or your deployed URL)
- **Live demo** — <http://localhost:3000/demo> — talk to *Aria*, a support
  agent grounded in a sample help center. One click, no sign-up.
- **Pricing** — <http://localhost:3000/pricing>

## Features

- **Multi-tenancy** — organization-scoped data with PostgreSQL Row-Level
  Security plus an app-layer tenant repository for defense in depth.
- **Authentication** — JWT access/refresh, Argon2 password hashing, RBAC
  (owner/admin/member/viewer), and tenant-scoped API keys.
- **Agents** — full CRUD with per-agent model, prompt, tools, and knowledge bases.
- **Knowledge Bases & RAG** — PDF ingestion, chunking, embeddings, cosine-similarity
  retrieval, and retrieve-and-compose answering (pluggable providers).
- **Conversations & Memory** — chat with history, short-term memory, summaries,
  and long-term memory (semantic retrieval, consolidation, ranking).
- **Tools & Orchestration** — tenant-scoped tool registry, sandboxed execution,
  LLM function calling, an agent orchestrator, and a multi-agent router.
- **Frontend** — Next.js 15 / React 19 app (chat, knowledge bases, agent builder,
  dashboard hub).
- **Operations** — Prometheus metrics, Grafana dashboards, Docker images,
  compose + AWS deployment tooling, and structured logging.

## Quick start (local)

```bash
# One command launches the whole stack (Postgres, Redis, backend, frontend)
# and seeds the demo workspace (Brightpath org + Aria agent + sample PDFs):
./run.sh          # macOS / Linux   (or: make dev)
run.bat           # Windows

# Then open the app
#    Landing:  http://localhost:3000/
#    Demo:     http://localhost:3000/demo
#    Sign in:  http://localhost:3000/login   (demo@nexusagent.dev / nexusagent-demo)
```

Requires **Docker + Docker Compose** and **Python 3.11+** (verified on 3.13).
Full guidance, the non-Docker path, and troubleshooting:
[docs/user-guide/quickstart.md](docs/user-guide/quickstart.md).

## Repository layout

```
backend/        FastAPI application (installed as the `app` package)
frontend/       Next.js 15 frontend
docs/           deployment, security, observability, performance, and user guides
demo/           demo PDFs + seed script (the Brightpath sample workspace)
brand/          logo, favicon, and brand guidelines
deploy/         AWS single-instance deployment scripts
monitoring/     Prometheus + Grafana stack
nginx/          reverse proxy config
docker-compose.yml / docker-compose.aws.yml
```

## Documentation

- [User Guide](docs/user-guide/README.md) — quickstart, knowledge bases, agents,
  chat & memory, and running the live demo.
- [ARCHITECTURE.md](ARCHITECTURE.md) — system, backend, frontend, RAG, memory, tools.
- [OPERATIONS.md](OPERATIONS.md) — deploy, monitor, backup, restore, incident response.
- [docs/deployment/](docs/deployment/) — local, AWS, security, observability, backups.
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup and development workflow.
- [CHANGELOG.md](CHANGELOG.md) — milestone-by-milestone history.
- [docs/PERFORMANCE.md](docs/PERFORMANCE.md) — performance baselines.

## Branding

Logo, favicon, color palette, and voice are defined in
[`brand/BRAND_GUIDE.md`](brand/BRAND_GUIDE.md). The product uses a violet→cyan
brand gradient layered on a neutral shadcn base.

## License

Proprietary — see repository policy.
