# Load Testing Report

**Phase 5 — Step 8 deliverable**
**Tooling:** `deploy/loadtest/loadtest.py` (aiohttp-based, no external load runner)
**Companion:** `PHASE_5_REPORT.md` (Performance section), `docs/deployment/observability.md`

> **Execution note:** Running the load test requires a *live* deployment (backend
> reachable on `:8000`, with RDS + ElastiCache up). This document specifies the
> tooling, the target profile, how to run it, the expected baselines, and how to
> read the results. The numeric results below are **expected baselines for the
> recommended t3.medium sizing**; re-run against your deployment to capture real
> numbers and attach them here.

---

## 1. Objective

Validate that the single-instance production deployment sustains the target
concurrency with acceptable latency and error rate, and identify bottlenecks before
they hit real users.

---

## 2. Tooling

`deploy/loadtest/loadtest.py` is a self-contained Python 3 script (only dependency:
`aiohttp`). It is **read-heavy and safe to run against a live box**:

- Registers (idempotently) or logs in a test user, obtaining a JWT bearer token.
- Drives a rotating request mix: `/health` (unauth), then authenticated
  `GET /api/v1/agents`, `GET /api/v1/conversations`, `GET /api/v1/tools`.
- Caps aggregate throughput with a fixed inter-launch interval and bounds concurrency
  with an `asyncio.Semaphore(users)`.

It does **not** exercise the chat/LLM path (no token spend, no provider load) — that
is deliberate for a routine load check. To stress LLM latency specifically, add a
`POST /api/v1/chat` turn to the mix (beware provider rate limits / cost).

---

## 3. Target Profile

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `--users` | `25` | Concurrent virtual users (semaphore size). |
| `--rpm` | `100` | Aggregate request rate (launch one request every `60/rpm` s). |
| `--duration` | `900` | Test length in seconds (15 min). |
| `--base-url` | _(required)_ | e.g. `http://<EC2-IP>` or `https://<domain>`. |
| `--email` / `--password` | loadtest creds | Test-org credentials. |

Total requests over the run ≈ `rpm × duration/60` = **100 × 15 = ~1,500 requests**
spread across 25 users. This models a small-but-busy production tenant, not a
black-Friday spike.

---

## 4. How to Run

On any machine with Python 3.11+ and network access to the deployment:

```bash
pip install aiohttp
python deploy/loadtest/loadtest.py \
  --base-url https://nexusagent.example.com \
  --email loadtest@example.com --password 'LoadTest123!' \
  --users 25 --rpm 100 --duration 900
```

**Capture resource usage in parallel** (on the EC2 host, in a second terminal):

```bash
# 1-sample-per-2s for the 15-min run:
docker stats --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" --no-stream \
  | ts >> /tmp/docker-stats.log
# or sample continuously:
docker stats --no-stream >> /tmp/docker-stats.log &
SAR_PID=$!; sleep 900; kill $SAR_PID
```

The load script reports latency percentiles and error counts; `docker stats` gives
CPU%/RAM for backend/frontend/nginx to find the bottleneck.

---

## 5. Expected Baselines (t3.medium, 2 vCPU / 4 GiB)

Given container limits in `docker-compose.aws.yml` (backend/frontend `mem_limit
512m`, `cpus 1.0`; nginx `128m`), and a read-heavy mix that is mostly served from the
DB connection pool + Redis cache:

| Metric | Expected (healthy) | Concern threshold |
|--------|--------------------|-------------------|
| Aggregate throughput | ~100 rpm sustained | < 80 rpm sustained |
| p50 latency | < 50 ms | > 200 ms |
| p95 latency | < 250 ms | > 1 s (trips `HighLatency` alert) |
| p99 latency | < 500 ms | > 2 s |
| Error rate (5xx + exceptions) | ~0% | > 1% |
| Backend CPU | < 60% | sustained > 85% (`CpuUsageHigh`) |
| Backend RAM | < 400 MiB of 512 MiB | > 90% (`MemoryUsageHigh`) |
| DB pool in-use (`nexusagent_db_connections_in_use`) | < pool size (5) | near/over pool + overflow |

These are **planning baselines**, not measured results. Record your actual run in the
table above after executing §4.

---

## 6. Bottleneck Analysis (where to look)

| Symptom | Likely bottleneck | Action |
|---------|-------------------|--------|
| High `nexusagent_db_connections_in_use`, latency climbs | DB pool exhaustion (`DB_POOL_SIZE=5`) | Raise `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`; check leaked connections (`nx-db`). |
| p95 spikes only on `/api/v1/agents` | Large tenant result sets / N+1 queries | Add pagination/caching; inspect query plan. |
| Backend CPU pinned, latency up | Single uvicorn worker at `cpus: 1.0` | Raise `cpus` / `mem_limit`; or go multi-worker (see scaling note). |
| Backend RAM near 512 MiB | In-memory state / request buffering | Raise `mem_limit`; verify streaming for large uploads. |
| Errors appear only after X minutes | Connection/pool timeouts under sustained load | Tune `DB_POOL_TIMEOUT`; verify RDS max_connections. |
| Latency fine but error rate > 0 | Transient 5xx on deploys / provider calls | Correlate with deploy timeline; check `nx-errors`. |

---

## 7. Recommendations

1. **Run the baseline on every major release** (pair with `update-containers.sh`) and
   keep the numbers in this doc so regressions are visible.
2. **Watch the pool, not just latency.** `nexusagent_db_connections_in_use` is the
   earliest saturation signal on a single host.
3. **Right-size from data.** t3.medium is sized for the 25-user/100-rpm profile. If
   real traffic exceeds ~300 rpm sustained, move to t3.large or split the app tier
   behind an ALB (see scaling path in `PHASE_5_DEPLOYMENT_PLAN.md` §6).
4. **Add an LLM-path probe** to a *separate*, lower-rate test if chat latency SLOs
   matter — provider latency dominates p95 there and shouldn't be mixed into the
   infra baseline.
5. **Alerts already cover this:** `HighLatency`, `HighErrorRate`, `CpuUsageHigh`,
   `MemoryUsageHigh`, and `DatabaseUnavailable` in `monitoring/prometheus/alerts.yml`
   will fire on the conditions above during a real run.

---

## 8. Scaling Note

The load profile here targets a **single node**. Because the app tier is stateless
(JWT sessions, external RDS/Redis, uploads on shared EBS/S3), the same images scale
horizontally by running N hosts behind an Application Load Balancer. At that point,
move the in-memory rate limiter to Redis (`RATE_LIMIT_PER_MINUTE` is currently
single-instance — see `PHASE_5_SECURITY_REPORT.md` / `docs/deployment/rate-limiting.md`)
and verify the Prometheus `node`/`postgres`/`redis` exporters still resolve.
