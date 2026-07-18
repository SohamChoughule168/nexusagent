# NexusAgent

**Multi-tenant AI Agent SaaS platform** — organizations create AI agents,
ground them in their own knowledge bases with retrieval-augmented generation
(RAG), extend them with tools and function calling, and hold conversations with
short- and long-term memory. All data is isolated per tenant.

> Version **1.0.0** — first production release. See [RELEASE_NOTES_v1.0.0.md](RELEASE_NOTES_v1.0.0.md).

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

## Repository layout

```
backend/        FastAPI application (installed as the `app` package)
frontend/       Next.js 15 frontend
docs/           deployment, security, observability, performance guides
deploy/         AWS single-instance deployment scripts
monitoring/     Prometheus + Grafana stack
nginx/          reverse proxy config
docker-compose.yml / docker-compose.aws.yml
```

## Quick start

```bash
# Backend
pip install -e .
cp .env.example .env          # fill in secrets
# start Postgres + Redis, then:
python -c "import app.models.all_models; from app.core.database import init_db; init_db()"

# Frontend
cd frontend && npm ci && npm run dev
```

Full deployment and operations guidance:

- [ARCHITECTURE.md](ARCHITECTURE.md) — system, backend, frontend, RAG, memory, tools.
- [OPERATIONS.md](OPERATIONS.md) — deploy, monitor, backup, restore, incident response.
- [docs/deployment/](docs/deployment/) — local, AWS, security, observability, backups.
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup and development workflow.
- [CHANGELOG.md](CHANGELOG.md) — milestone-by-milestone history.
- [docs/PERFORMANCE.md](docs/PERFORMANCE.md) — performance baselines.

## License

Proprietary — see repository policy.
