# NexusAgent AI — Observability stack

Prometheus, Grafana, Alertmanager and the standard exporters for monitoring a
production NexusAgent deployment. Part of **Milestone 7, Phase 5 (Observability)**.

## Layout

```
monitoring/
├── docker-compose.monitoring.yml   # prometheus + alertmanager + grafana + exporters
├── prometheus/
│   ├── prometheus.yml              # scrape configs (backend, node, postgres, redis)
│   ├── alerts.yml                  # 8 recommended alerting rules
│   └── alertmanager.yml            # routing / receivers (placeholder)
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/datasource.yml     # Prometheus datasource (uid: prometheus)
│   │   └── dashboards/dashboards.yml      # auto-load the dashboards below
│   ├── dashboards/                 # 7 generated dashboards (nx-*.json)
│   │   ├── nx-api.json             # API traffic / errors / latency
│   │   ├── nx-db.json              # PostgreSQL + connection pool
│   │   ├── nx-redis.json           # Redis + cache hit rate
│   │   ├── nx-agents.json          # Agent / conversation activity
│   │   ├── nx-tokens.json          # LLM token + cost usage
│   │   ├── nx-errors.json          # Error breakdown
│   │   └── nx-infra.json           # Host CPU/mem/disk/network + dependency health
│   └── build_dashboards.py         # regenerates dashboards/*.json
└── README.md
```

## Quick start

The application (`docker-compose.yml`) must already be running and reachable on
the host (ports `8000`, `5432`, `6379`).

```bash
# Bring up the observability stack
docker compose -f monitoring/docker-compose.monitoring.yml up -d

# URLs (default Grafana admin/admin — set GRAFANA_ADMIN_PASSWORD in .env!)
open http://localhost:9090   # Prometheus
open http://localhost:9093   # Alertmanager
open http://localhost:3001   # Grafana → "NexusAgent" folder
```

In a few seconds Prometheus begins scraping `/metrics` and the dashboards
populate. Confirm targets are `UP` under **Status → Targets** in Prometheus.

## Regenerating dashboards

```bash
python monitoring/grafana/build_dashboards.py
```

## Wiring real alerts

`alertmanager.yml` ships with placeholder webhook/email receivers. Before
relying on paging, set `ALERT_WEBHOOK_URL` / `ALERT_WEBHOOK_URL_CRITICAL` (e.g.
Slack/Generic Webhook) or the `ALERT_EMAIL_*` / `ALERT_SMTP_SMARTHOST` settings
to your real incident channel.

## Validation

```bash
python -c "import yaml,sys; yaml.safe_load(open('monitoring/prometheus/prometheus.yml')); yaml.safe_load(open('monitoring/prometheus/alerts.yml')); print('prometheus + alerts YAML OK')"
python -c "import json,glob; [json.load(open(f)) for f in glob.glob('monitoring/grafana/dashboards/*.json')]; print('dashboard JSON OK')"
```
