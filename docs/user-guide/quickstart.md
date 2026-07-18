# Quickstart

Get NexusAgent running locally and seed the demo workspace in a few minutes.

## 1. Prerequisites

- Docker + Docker Compose (for the local stack: Postgres, Redis, backend, frontend)
- Python 3.11+ (to run the seed script)
- Node.js 20+ (only if you want to run the frontend separately)

## 2. Start the stack

From the repository root:

```bash
docker compose up -d
```

This starts Postgres, Redis, the backend (port 8000), and the frontend
(port 3000), runs database migrations, and applies the demo/seed automatically
if configured. Wait until the backend health check is green:

```bash
curl -f http://localhost:8000/health || echo "backend not ready yet"
```

## 3. Seed the demo workspace

If the stack did not seed automatically, run the seed script (it creates the
**Brightpath** demo organization, a help-center knowledge base, the demo PDFs,
and the **Aria** support agent):

```bash
pip install -e .
python backend/scripts/seed_demo.py --init-db   # --init-db creates tables for a fresh DB
```

The script prints the demo credentials and a demo API key when it finishes.

## 4. Open the app

- Landing page: <http://localhost:3000/>
- Live demo: <http://localhost:3000/demo>
- Pricing: <http://localhost:3000/pricing>
- Dashboard (sign in with the demo credentials): <http://localhost:3000/login>

## 5. Talk to the demo agent

Open the [live demo](http://localhost:3000/demo) and click **Launch live demo**.
You are signed into the Brightpath demo workspace as the demo user. Ask Aria
about inviting a team, pricing, or SSO and watch it cite the help center.

## Default demo credentials

| Field    | Value                |
|----------|----------------------|
| Email    | `demo@nexusagent.dev` |
| Password | `nexusagent-demo`     |

Override any of these with environment variables before seeding:
`DEMO_ORG_NAME`, `DEMO_ORG_SLUG`, `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`.

## Troubleshooting

- **Backend unreachable from the demo page:** the frontend calls the backend at
  `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000/api/v1`). Make sure
  the backend container is healthy.
- **Empty answers from the agent:** the knowledge base may not be embedded.
  Re-run the seed script, or check the document status in the knowledge-base UI.
- **No LLM responses (offline):** without an embeddings/LLM key the pipeline
  still retrieves chunks but answers with the offline composer. Set
  `OPENROUTER_API_KEY` (and `RAG_LLM_PROVIDER`/`EMBEDDINGS_PROVIDER`) for full
  generated answers.
