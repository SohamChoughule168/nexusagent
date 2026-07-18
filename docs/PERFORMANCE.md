# NexusAgent — Performance Sanity Check (v1.0.0)

This is a **lightweight** production-readiness measurement, not a formal load
test. Numbers were captured on a developer workstation (Windows, Python 3.13,
Node 20, local PostgreSQL 16) against the release candidate. Treat them as
order-of-magnitude baselines to detect regressions, not SLA guarantees.

## Backend

| Metric | Value | Method |
| --- | --- | --- |
| Cold import (`import app.main`, fresh process) | ~0.88 s (stable across 3 runs: 885 / 881 / 882 ms) | `python -c "import time; t=…; import app.main"` |
| Warm import (same process) | ~0.92 s first, ~0 ms cached | in-process timer |
| Process RSS after full app load | ~93 MB | Win32 `GetProcessMemoryInfo` working set |
| `/health` latency | p50 3.4 ms · p95 5.4 ms · max 6.3 ms | 100 requests via `TestClient`, 5-request warmup |
| `/` (root) latency | p50 3.4 ms · p95 5.5 ms | 100 requests via `TestClient` |
| Backend source (`backend/app`) | ~1.3 MB | `du -sh` |

Notes:
- Latency was measured in-process with `TestClient` (no network hop), so it
  reflects application + framework overhead, **excluding** LLM/embedding
  provider calls and network. Real chat/RAG latency is dominated by the
  upstream LLM provider, not the app.
- RSS is for a single Uvicorn worker with the full app + SQLAlchemy models +
  Redis client loaded. Production compose runs `--workers 1` per container;
  size the instance for `~100 MB × workers` plus headroom.

## Frontend

| Metric | Value | Method |
| --- | --- | --- |
| Production build time | ~5.1 s compile | `next build` |
| Largest route First Load JS | `/chat` = 260 kB | `next build` route table |
| Dashboard First Load JS | 140 kB | `next build` |
| Login First Load JS | 163 kB | `next build` |
| Shared JS (all routes) | 102 kB (46.2 kB + 54.2 kB + 2 kB) | `next build` |
| Shipped static chunks (`.next/static`) | ~1.7 MB | `du -sh` |
| `.next` total (incl. server + cache) | ~258 MB | `du -sh` (build cache, not shipped) |

Notes:
- First Load JS values are within Next.js's healthy range (the framework flags
  bundles that push well past ~300 kB). `/chat` is the heaviest route because
  it bundles the markdown renderer + syntax highlighting.
- `.next/static` (~1.7 MB) is the client-shipped payload; the 258 MB `.next`
  total is mostly the server build and cache and is not sent to browsers.

## Docker images (estimated from Dockerfiles)

Docker was not available in the validation environment, so image sizes are
**estimates** based on the base images and layers. Verify with
`docker images` after the first `docker compose build` (the
`docker-validation.yml` CI workflow builds both images on every push).

| Image | Base | Estimated size | Notes |
| --- | --- | --- | --- |
| Backend | `python:3.11-slim` | ~250–350 MB | Multi-stage; only site-packages + alembic copied to runtime. `curl` added for healthcheck. |
| Frontend | `node:20-alpine` | ~300–450 MB | Ships `node_modules` + `.next` + `next start`. Alpine base keeps it lean. |

## Optimization opportunities (documented, not performed)

These are **deliberately deferred** — none is release-blocking. Recorded here so
they are not lost:

1. **Frontend image size** — the runtime stage copies the full
   `node_modules`. Switching to Next.js **standalone output**
   (`output: 'standalone'` in `next.config.mjs`) would ship only the traced
   runtime dependencies and typically cut the image by 50–70%. Deferred to
   avoid changing the build contract right before release.
2. **`/chat` bundle (260 kB)** — `highlight.js` / `rehype-highlight` dominate.
   Lazy-loading syntax highlighting (dynamic import on first code block) would
   drop the initial payload. Low priority; the route is already acceptable.
3. **Backend cold start (~0.88 s)** — acceptable for a long-running service.
   If faster boot is ever needed, lazy-importing heavy submodules (already done
   for health/metrics) could be extended, but the current time is fine for
   container orchestration with a 30 s start-period healthcheck.
4. **Multiple Uvicorn workers** — production compose runs 1 worker per
   container and scales horizontally. For vertical scaling on a larger
   instance, raise `--workers` (budget ~100 MB RSS each).

## Reproducing

```bash
# Backend (from repo root, app installed via `pip install -e .`)
export DATABASE_URL=postgresql+psycopg2://USER:PASS@localhost:5432/nexusagent
export JWT_SECRET_KEY=… JWT_REFRESH_SECRET_KEY=…
python -c "import time; t=time.perf_counter(); import app.main; print((time.perf_counter()-t)*1000,'ms')"

# Frontend
cd frontend && npm run build   # prints the route/bundle table
```
