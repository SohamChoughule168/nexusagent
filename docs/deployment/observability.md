# Observability

Production observability for NexusAgent — monitoring, logging, metrics, health
checks, alerting and the operational runbook. **Milestone 7, Phase 5.**

> Companion docs: [backups.md](./backups.md), [production.md](./production.md),
> [aws.md](./aws.md), [docker.md](./docker.md).

## 1. Architecture

```
                         ┌──────────────────────────────────────────────┐
   Browser / API client  │              NexusAgent host                  │
        │                 │                                              │
        │  :80 / :443     │   ┌──────────┐    ┌─────────────────────┐    │
        └────────────────►│   │  nginx   │───►│  backend (FastAPI)   │    │
                          │   └──────────┘    │  :8000 /metrics      │    │
                          │                   │  /health/*           │    │
                          │                   └──────────┬──────────┘    │
                          │                              │                │
                          │                   ┌──────────┼──────────┐     │
                          │                   │     Postgres │ Redis    │     │
                          │                   └──────────┬──────────┘     │
                          │                              │                │
   ┌──────────────────────┴──────────────────────────────┴───────────┐   │
   │ Observability stack (monitoring/docker-compose.monitoring.yml)   │   │
   │  Prometheus :9090 ──scrape──► /metrics, node, postgres, redis     │   │
   │      │ rules/alerts                                           │   │
   │      ├──────────────► Alertmanager :9093 ──► Slack/email/Pager  │   │
   │      └──────────────► Grafana :3001 (7 dashboards)              │   │
   └────────────────────────────────────────────────────────────────┘   │
```

The backend emits everything Prometheus needs from a single `/metrics`
endpoint (plus the standard `node`/`postgres`/`redis` exporters for the
infrastructure layer). Structured JSON logs go to stdout (container-friendly)
with optional rotating on-disk files.

### Components

| Layer | Component | Port | Source |
|-------|-----------|------|--------|
| App metrics | FastAPI `/metrics` | 8000 | `app/core/metrics.py` |
| Structured logs | structlog → stdout (JSON) | — | `app/core/logging.py` |
| Health | `/health/live`, `/health/ready`, `/health/startup` | 8000 | `app/core/health.py` |
| Scrape/store | Prometheus | 9090 | `monitoring/prometheus/` |
| Visualise | Grafana (7 dashboards) | 3001 | `monitoring/grafana/` |
| Alerting | Alertmanager + rules | 9093 | `monitoring/prometheus/alerts.yml` |
| Node metrics | node_exporter | 9100 | monitoring stack |
| PG metrics | postgres_exporter | 9187 | monitoring stack |
| Redis metrics | redis_exporter | 9121 | monitoring stack |

## 2. Logging

Structured **JSON** logging via `structlog` (`app/core/logging.py`).

- **Application logs** — `get_logger(name)` emits JSON lines to stdout with
  `app_name`, `level`, ISO timestamp, and any bound context. When `LOG_FILE` is
  set they also write to a size-capped, **rotating** `RotatingFileHandler`
  (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`).
- **Access logs** — one structured line per HTTP request on a dedicated
  `app.access` logger (`log_type=access`): `request_id, method, path, status,
  duration_ms, bytes, user_agent`. Controlled by `LOG_ACCESS_ENABLED`; separate
  file via `ACCESS_LOG_FILE`.
- **Correlation** — `RequestIDMiddleware` assigns a `request_id`
  (`X-Request-ID` echoed on the response; client-supplied value honoured) and
  `RequestContextMiddleware` binds it (and tenant, if known) into the structlog
  context so every log during the request carries it.
- **Error logging** — unhandled exceptions go through the registered exception
  handlers; the middleware records 4xx/5xx in `HTTP_ERROR_COUNT` and the access
  log captures status + latency.

### Configuration

| Setting | Default | Effect |
|---------|---------|--------|
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`. |
| `LOG_FORMAT` | `json` | `json` (containers) or `console` (local dev). |
| `LOG_FILE` | _(unset)_ | App log also written (rotated) to this path. |
| `ACCESS_LOG_FILE` | _(unset)_ | Access log also written (rotated) to this path. |
| `LOG_MAX_BYTES` | `10 MiB` | Max size per rotated log file. |
| `LOG_BACKUP_COUNT` | `5` | Retained rotated copies. |
| `LOG_ACCESS_ENABLED` | `true` | Toggle per-request access logs. |

Example line:

```json
{"app_name":"NexusAgent AI","log_type":"access","request_id":"a1b2c3d4",
 "method":"POST","path":"/api/v1/chat","status":200,"duration_ms":412.3,
 "event":"request","timestamp":"2026-07-18T13:25:32Z","level":"info"}
```

## 3. Metrics catalog

All metrics are namespaced with `PROMETHEUS_NAMESPACE` (default `nexusagent_`).
Refreshed per scrape; DB/Redis/`llm` gauges are isolated so one subsystem
failing never zeroes the others.

### HTTP (event-driven — `MetricsMiddleware`)
| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `nexusagent_http_requests_total` | Counter | `method, endpoint, status` | Total requests. |
| `nexusagent_http_request_duration_seconds` | Histogram | `method, endpoint` | Latency (buckets 5ms→60s). |
| `nexusagent_http_errors_total` | Counter | `method, endpoint, status` | 4xx/5xx count. |
| `nexusagent_http_requests_in_progress` | Gauge | — | Concurrent in-flight requests. |

### Dependency availability
| Metric | Type | Meaning |
|--------|------|---------|
| `nexusagent_db_up` | Gauge | PostgreSQL reachable (1/0). |
| `nexusagent_redis_up` | Gauge | Redis reachable (1/0). |
| `nexusagent_storage_up` | Gauge | Upload dir writable (1/0). |
| `nexusagent_llm_up` | Gauge | LLM provider reachable (1/0). |
| `nexusagent_scrape_errors_total` | Counter | Refresh failures per subsystem. |

### Application state (from DB)
| Metric | Type | Meaning |
|--------|------|---------|
| `nexusagent_active_conversations` | Gauge | Conversations in `active` state. |
| `nexusagent_active_agents` | Gauge | Agents in `active` state. |
| `nexusagent_total_tokens` | Gauge | Cumulative LLM tokens. |
| `nexusagent_total_cost_usd` | Gauge | Cumulative LLM cost (USD). |

### Queue / DB pool / Redis
| Metric | Type | Meaning |
|--------|------|---------|
| `nexusagent_queue_length` | Gauge | Default Celery queue length (if Redis broker). |
| `nexusagent_db_connection_pool_size` | Gauge | Configured pool size. |
| `nexusagent_db_connections_in_use` | Gauge | Checked-out connections. |
| `nexusagent_db_connections_idle` | Gauge | Idle pool connections. |
| `nexusagent_db_connections_overflow` | Gauge | Overflow connections. |
| `nexusagent_redis_memory_used_bytes` | Gauge | Redis resident memory. |
| `nexusagent_redis_connected_clients` | Gauge | Connected clients. |
| `nexusagent_redis_keyspace_hits` / `_misses` | Gauge | Keyspace hit/miss counters. |
| `nexusagent_redis_expired_keys` / `_evicted_keys` | Gauge | Expired/evicted keys. |
| `nexusagent_redis_uptime_seconds` | Gauge | Redis uptime. |

> `endpoint` labels use the **templated** route path (`/api/v1/conversations/{id}`),
> not raw paths, to keep cardinality bounded. `/metrics`, `/docs`, `/redoc`,
> `/openapi.json` are excluded from HTTP metrics and access logs.

## 4. Health endpoints

| Endpoint | Probe | Returns | Failure mode |
|----------|-------|---------|--------------|
| `GET /health/live` | Liveness | `200 {status:"alive"}` always | Never fails while process runs. |
| `GET /health/ready` | Readiness | `200/503` aggregate | `503` when a **required** dep is down. Degrades to `200 {status:"degraded"}` when an optional dep is down. |
| `GET /health/startup` | Startup | `200 {started:true/false}` | `started:false` until lifespan completes. |
| `GET /health` | Legacy | `200 {status:"healthy"}` | Back-compat aggregate. |

Dependency checks:

| Check | Required? | Detail |
|-------|-----------|--------|
| PostgreSQL | **Yes** | `SELECT 1`. Down ⇒ readiness `503`. |
| Storage | **Yes** | Upload dir exists + writable. Down ⇒ readiness `503`. |
| Redis | Optional (configurable) | `ping`. Set `HEALTH_REQUIRE_REDIS=true` to make it required. |
| LLM provider | Optional | Non-destructive `HEAD` to provider base URL — no token spend. `skipped` if no API key. |

Readiness is safe-by-default: the API keeps serving when Redis/LLM are down
because it degrades gracefully; flip `HEALTH_REQUIRE_REDIS` only if Redis is a
hard dependency for your deployment.

## 5. Dashboards

Auto-provisioned into the **NexusAgent** folder (Grafana) — all bind to the
`prometheus` datasource.

| UID | Dashboard | Key panels |
|-----|-----------|-----------|
| `nx-api` | API | Request rate, error rate, p95 latency, in-progress, by endpoint/status, latency percentiles, errors-by-status. |
| `nx-db` | Database | DB up, pool utilisation, pool in/out/idle/overflow, PG backends, active conversations/agents, total tokens, scrape errors. |
| `nx-redis` | Redis | Redis up, connected clients, cache hit rate, memory, keyspace hits/misses, expired/evicted, uptime. |
| `nx-agents` | Agent Activity | Active agents, active conversations, their time series, request volume by endpoint, token rate. |
| `nx-tokens` | Token Usage | Total tokens, total cost, token rate/h, cost rate/h, cumulative. |
| `nx-errors` | Errors | Error rate, errors/5m, error rate over time, by status/endpoint/method. |
| `nx-infra` | Infrastructure | Host CPU/memory/disk gauges, CPU by mode, memory, disk per mountpoint, network, dependency health. |

Regenerate: `python monitoring/grafana/build_dashboards.py`.

## 6. Alert catalog

Defined in `monitoring/prometheus/alerts.yml`. Eight recommended alerts:

| Alert | Severity | Condition | For | Action |
|-------|----------|-----------|-----|--------|
| `ServiceDown` | critical | `up{job="nexusagent-backend"} == 0` | 1m | Backend not scrapable — check container/nginx/host. |
| `HighErrorRate` | critical | error ratio > 5% | 5m | Check `/health/ready`, recent deploy, logs. |
| `HighLatency` | warning | p95 latency > 1s | 10m | DB pool saturation, Redis/LLM latency. |
| `DatabaseUnavailable` | critical | `nexusagent_db_up == 0` | 1m | Verify RDS endpoint, SG, credentials. |
| `RedisUnavailable` | warning | `nexusagent_redis_up == 0` | 2m | Verify ElastiCache/Redis + broker URL. |
| `LLMProviderUnreachable` | warning | `nexusagent_llm_up == 0` | 10m | Check egress/DNS/provider status. |
| `DiskUsageHigh` | warning | free < 10% | 5m | Rotate logs, prune backups, grow EBS. |
| `MemoryUsageHigh` | warning | avail < 10% | 5m | Look for leaks, right-size instance. |
| `CpuUsageHigh` | warning | CPU > 85% | 10m | Inspect hot endpoints, scale up. |

`critical` alerts page via the `critical` Alertmanager route; everything else
goes to the default (Slack/email) receiver. `inhibit_rules` suppress warning
alerts when a critical on the same service/tier is already firing.

## 7. Monitoring stack — run it

```bash
# app must be up and reachable on host ports 8000/5432/6379
docker compose -f monitoring/docker-compose.monitoring.yml up -d
# Grafana http://localhost:3001  (admin/admin — set GRAFANA_ADMIN_PASSWORD)
# Prometheus http://localhost:9090   Alertmanager http://localhost:9093
```

Exporter connection strings come from `.env` (`POSTGRES_*`, `REDIS_URL`).
Confirm **Status → Targets** are `UP` in Prometheus before relying on alerts.

## 8. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---------|--------------|-------------|
| `/metrics` returns 404 | `METRICS_ENABLED=false` | Set `METRICS_ENABLED=true`. |
| `/metrics` slow or 503 | DB/Redis scrape error | `nexusagent_scrape_errors_total` > 0; check `up` signals; logs show `metrics_*_refresh_failed`. |
| Dashboards empty | Prometheus not scraping | **Status → Targets**; verify `host.docker.internal` reachability from monitoring container. |
| `up{job="nexusagent-backend"} == 0` | Backend down / wrong port | `curl localhost:8000/health`; check nginx + container. |
| `nexusagent_db_up == 0` but app works | Stale gauge / transient | Re-scrape; if persistent, RDS is down — see `DatabaseUnavailable`. |
| High `nexusagent_db_connections_in_use` | Pool exhaustion | Raise pool size; check for connections not returned; watch `db_connections_overflow`. |
| `nexusagent_redis_up == 0` but `redis_up` (exporter) ok | App can't reach Redis | App uses `REDIS_URL`; exporter uses `REDIS_ADDR` — reconcile both. |
| Access logs missing | `LOG_ACCESS_ENABLED=false` | Set `LOG_ACCESS_ENABLED=true`. |
| Logs not JSON | `LOG_FORMAT=console` | Set `LOG_FORMAT=json` for prod. |
| Logs not on disk | `LOG_FILE`/`ACCESS_LOG_FILE` unset | Set the path; rotation auto-attaches. |
| `DatabaseBackupAge` grows | Backup cron failed | Check `backups/cron.log`; see [backups.md](./backups.md). |
| Alerts never fire | Alertmanager misconfigured | `amtool check-config`; verify receivers + `ALERT_WEBHOOK_URL`. |

## 9. Operational runbook

### Daily
- Glance at `nx-infra` + `nx-api` (error rate, latency, dependency health).
- Confirm last nightly backup succeeded (`backups/cron.log`).

### On `ServiceDown` / `DatabaseUnavailable` (critical)
1. `curl -fsS localhost:8000/health/live` and `/health/ready`.
2. `docker logs nexusagent-backend --since 30m | tail -50`.
3. If RDS: check RDS status / security-group ingress; failover if needed.
4. If host: `deploy/rolling-restart.sh backend`; escalate to DR if unrecoverable
   (see [backups.md](./backups.md)).

### On `HighErrorRate`
1. `nx-errors` → which `status`/`endpoint`.
2. Cross-check `nx-api` latency + `nexusagent_db_connections_in_use`.
3. Recent deploy? `deploy/rolling-restart.sh backend` or roll back image tag.

### On `HighLatency`
1. `nx-db` pool utilisation + overflow; `nx-redis` hit rate; `LLMProviderUnreachable`.
2. Slow LLM → check provider status; pool saturation → raise pool / fix leaks.

### On `DiskUsageHigh`
1. `df -h`; `docker system prune` if safe; prune old backups beyond retention.
2. If EBS near full, grow volume (AWS) — see `aws.md`.

### Monthly
- **Restore drill** (verify a backup actually restores) — [backups.md](./backups.md).
- Review alert history; tune thresholds if noisy.
