# Rate Limiting

How NexusAgent AI throttles client traffic (Milestone 7, Phase 6).

---

## What it is

A lightweight, in-memory **fixed-window** rate limiter implemented with the
existing FastAPI / Starlette stack (`backend/app/core/rate_limit.py`). It adds
no new framework or dependency.

- **Budget:** `RATE_LIMIT_PER_MINUTE` (default `100`) requests per client IP,
  per rolling 60-second window.
- **Key:** client IP, taken from `X-Forwarded-For` (leftmost = original client)
  or `X-Real-IP` set by nginx. Falls back to `request.client.host` only if those
  headers are absent.
- **Exempt paths:** `/health`, `/metrics`, `/health/live`, `/health/ready`,
  `/health/startup` are never throttled, so probes and Prometheus scrapes are
  unaffected.
- **Behavior on exceed:** `429 Too Many Requests` with a `Retry-After` header
  (seconds until the oldest request in the window ages out).

The limiter runs as FastAPI middleware, just inside the CORS layer, so
unauthenticated clients are throttled before reaching any business logic. It
**never reads the request body**, so it is safe in front of the file-upload
endpoint.

---

## Configuration

Set `RATE_LIMIT_PER_MINUTE` in `.env` / `.env.production`
(see `.env.example`). It is already wired through `docker-compose*.yml` into the
backend container.

```bash
RATE_LIMIT_PER_MINUTE=100
```

---

## Verify

```bash
# Fire requests faster than the limit from one IP (behind nginx):
for i in $(seq 1 120); do curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/api/v1/... ; done
# Expect a 429 with a Retry-After header once the budget is exhausted.
```

---

## Known limitations (single-instance by design)

- **Per-process state.** The counter lives in the backend process. With the
  project's single-instance deployment this is correct. If you later run
  multiple backend replicas, each replica enforces its own budget — deploy
  `nginx limit_req` (or a Redis-backed limiter) for a shared budget.
- **Unbounded key set.** One bucket per distinct client IP; buckets are pruned
  as the window rolls. For a long-lived, high-cardinality client population,
  periodically restart or front with nginx. Acceptable for the MVP scale.
- **Best-effort accuracy.** A small over-count under heavy concurrency is
  possible; it never under-counts, so the throttle is safe.
