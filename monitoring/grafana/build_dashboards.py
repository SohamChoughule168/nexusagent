#!/usr/bin/env python3
"""Generate the 7 Grafana dashboards for NexusAgent observability.

Run from the repo root:

    python monitoring/grafana/build_dashboards.py

Emits one JSON file per dashboard into monitoring/grafana/dashboards.
Every dashboard binds to the provisioned Prometheus datasource (uid
``prometheus``) so it imports cleanly with no manual wiring.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

DS = {"type": "prometheus", "uid": "prometheus"}

# --------------------------------------------------------------------------- #
# Panel builders
# --------------------------------------------------------------------------- #
_panel_id = 0


def _next_id() -> int:
    global _panel_id
    _panel_id += 1
    return _panel_id


def timeseries(
    title: str,
    expr: str,
    *,
    legend: str = "{{endpoint}}",
    unit: str = "short",
    grid: Tuple[int, int] = (12, 8),
    stack: bool = False,
    fill: int = 10,
) -> Dict[str, Any]:
    return {
        "id": _next_id(),
        "type": "timeseries",
        "title": title,
        "datasource": DS,
        "gridPos": {"h": grid[1], "w": grid[0], "x": 0, "y": 0},
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "calcs": ["mean", "max"]},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "lines",
                    "lineWidth": 1,
                    "fillOpacity": fill,
                    "stacking": {"mode": "normal" if stack else "none"},
                    "axisCenteredZero": False,
                },
            },
            "overrides": [],
        },
        "targets": [{"expr": expr, "legendFormat": legend, "refId": "A"}],
    }


def stat(
    title: str,
    expr: str,
    *,
    unit: str = "short",
    grid: Tuple[int, int] = (6, 4),
    thresholds: Optional[List[Tuple[float, str]]] = None,
    color: str = "blue",
) -> Dict[str, Any]:
    overrides = []
    if thresholds:
        steps = [{"color": "green", "value": None}]
        for val, col in thresholds:
            steps.append({"color": col, "value": val})
        overrides = [{"matcher": {"id": "byName", "name": "Value"}, "properties": [
            {"id": "thresholdsStyle", "value": {"mode": "background"}},
        ]}]
    else:
        steps = [{"color": color, "value": None}]
    return {
        "id": _next_id(),
        "type": "stat",
        "title": title,
        "datasource": DS,
        "gridPos": {"h": grid[1], "w": grid[0], "x": 0, "y": 0},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": ""},
            "colorMode": "background" if thresholds else "value",
            "graphMode": "area",
            "justifyMode": "auto",
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "thresholds": {"mode": "absolute", "steps": steps},
                "custom": {"width": 0},
            },
            "overrides": overrides,
        },
        "targets": [{"expr": expr, "legendFormat": "value", "refId": "A"}],
    }


def gauge(
    title: str,
    expr: str,
    *,
    unit: str = "percent",
    max: float = 100,
    grid: Tuple[int, int] = (6, 6),
    thresholds: List[Tuple[float, str]] = None,
) -> Dict[str, Any]:
    if thresholds is None:
        thresholds = [(70, "green"), (85, "yellow"), (95, "red")]
    steps = [{"color": "green", "value": None}]
    for val, col in thresholds:
        steps.append({"color": col, "value": val})
    return {
        "id": _next_id(),
        "type": "gauge",
        "title": title,
        "datasource": DS,
        "gridPos": {"h": grid[1], "w": grid[0], "x": 0, "y": 0},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": ""},
            "orientation": "auto",
            "showThresholdLabels": False,
            "showThresholdMarkers": True,
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": 0,
                "max": max,
                "thresholds": {"mode": "absolute", "steps": steps},
                "custom": {"width": 0},
            },
            "overrides": [],
        },
        "targets": [{"expr": expr, "legendFormat": "value", "refId": "A"}],
    }


# --------------------------------------------------------------------------- #
# Layout: simple 2-column greedy shelf packer (guarantees no overlaps)
# --------------------------------------------------------------------------- #
def _layout(panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    col_y = [0, 0]
    for p in panels:
        w = p["gridPos"]["w"]
        h = p["gridPos"]["h"]
        col = 0 if col_y[0] <= col_y[1] else 1
        if w > 12:  # full-width row: place on its own line
            col_y[1] = max(col_y[0], col_y[1])
            col = 0
        x = col * 12
        p["gridPos"] = {"h": h, "w": min(w, 24), "x": x, "y": col_y[col]}
        col_y[col] += h
    return panels


def make_dashboard(uid: str, title: str, description: str, panels: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": None,
        "uid": uid,
        "title": title,
        "description": description,
        "tags": ["nexusagent", "observability", uid.replace("nx-", "")],
        "editable": True,
        "grafana_net": False,
        "schemaVersion": 39,
        "version": 1,
        "timezone": "",
        "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"},
        "templating": {"list": []},
        "annotations": {"list": [{"builtIn": 1, "datasource": "--grafana--", "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"}]},
        "panels": _layout(panels),
        "requirements": [{"type": "grafana", "id": ">=9.0.0"}, {"type": "datasource", "id": "prometheus", "name": "Prometheus"}],
    }


# --------------------------------------------------------------------------- #
# Dashboards
# --------------------------------------------------------------------------- #
def dash_api() -> Dict[str, Any]:
    panels = [
        stat("Request rate", "sum(rate(nexusagent_http_requests_total[5m]))", unit="reqps", grid=(6, 4)),
        stat(
            "Error rate",
            "(sum(rate(nexusagent_http_errors_total[5m])) / clamp_min(sum(rate(nexusagent_http_requests_total[5m])), 1)) * 100",
            unit="percent", grid=(6, 4),
            thresholds=[(1, "green"), (5, "yellow"), (5.0001, "red")],
        ),
        stat("p95 latency (s)",
             "histogram_quantile(0.95, sum(rate(nexusagent_http_request_duration_seconds_bucket[5m])) by (le))",
             unit="s", grid=(6, 4)),
        stat("In-progress requests", "nexusagent_http_requests_in_progress", unit="short", grid=(6, 4)),
        timeseries("Requests by endpoint",
                   "sum(rate(nexusagent_http_requests_total[5m])) by (endpoint)", legend="{{endpoint}}", unit="reqps"),
        timeseries("Requests by status",
                   "sum(rate(nexusagent_http_requests_total[5m])) by (status)", legend="{{status}}", unit="reqps"),
        timeseries("Latency percentiles (s)",
                   "histogram_quantile(0.50, sum(rate(nexusagent_http_request_duration_seconds_bucket[5m])) by (le))",
                   legend="p50", unit="s", fill=4),
        timeseries("",
                   "histogram_quantile(0.95, sum(rate(nexusagent_http_request_duration_seconds_bucket[5m])) by (le))",
                   legend="p95", unit="s", fill=0),
        timeseries("",
                   "histogram_quantile(0.99, sum(rate(nexusagent_http_request_duration_seconds_bucket[5m])) by (le))",
                   legend="p99", unit="s", fill=0),
        timeseries("Errors by status",
                   "sum(rate(nexusagent_http_errors_total[5m])) by (status)", legend="{{status}}", unit="reqps"),
    ]
    return make_dashboard("nx-api", "NexusAgent · API", "HTTP traffic, errors and latency for the FastAPI backend.", panels)


def dash_db() -> Dict[str, Any]:
    panels = [
        stat("Database up", "nexusagent_db_up", unit="short", grid=(6, 4),
             thresholds=[(0.999, "green"), (1.0001, "red")]),
        stat("Pool utilization",
             "(nexusagent_db_connections_in_use / clamp_min(nexusagent_db_connection_pool_size, 1)) * 100",
             unit="percent", grid=(6, 4), thresholds=[(70, "green"), (85, "yellow"), (95, "red")]),
        timeseries("Connection pool",
                   "nexusagent_db_connections_in_use", legend="in_use", unit="short", fill=4),
        timeseries("",
                   "nexusagent_db_connections_idle", legend="idle", unit="short", fill=4),
        timeseries("",
                   "nexusagent_db_connection_pool_size", legend="size", unit="short", fill=0),
        timeseries("Pool overflow", "nexusagent_db_connections_overflow", legend="overflow", unit="short"),
        stat("Active PostgreSQL backends", "sum(pg_stat_database_numbackends)", unit="short", grid=(6, 4)),
        timeseries("Postgres stat activity", "sum(pg_stat_activity_count)", legend="count", unit="short"),
        timeseries("Active conversations", "nexusagent_active_conversations", legend="conversations", unit="short"),
        timeseries("Active agents", "nexusagent_active_agents", legend="agents", unit="short"),
        gauge("Total tokens consumed", "nexusagent_total_tokens", unit="short", grid=(6, 6)),
        stat("Scrape errors", "nexusagent_scrape_errors_total", unit="short", grid=(6, 4),
             thresholds=[(0.999, "green"), (1.0001, "red")]),
    ]
    return make_dashboard("nx-db", "NexusAgent · Database", "PostgreSQL health, connection pool and application state.", panels)


def dash_redis() -> Dict[str, Any]:
    panels = [
        stat("Redis up", "nexusagent_redis_up", unit="short", grid=(6, 4),
             thresholds=[(0.999, "green"), (1.0001, "red")]),
        stat("Connected clients", "nexusagent_redis_connected_clients", unit="short", grid=(6, 4)),
        stat("Cache hit rate",
             "(nexusagent_redis_keyspace_hits / clamp_min(nexusagent_redis_keyspace_hits + nexusagent_redis_keyspace_misses, 1)) * 100",
             unit="percent", grid=(6, 4), thresholds=[(80, "green"), (60, "yellow"), (40, "red")]),
        stat("Uptime (s)", "nexusagent_redis_uptime_seconds", unit="s", grid=(6, 4)),
        timeseries("Memory used", "nexusagent_redis_memory_used_bytes", legend="bytes", unit="bytes"),
        timeseries("Keyspace", "nexusagent_redis_keyspace_hits", legend="hits", unit="short", fill=4),
        timeseries("", "nexusagent_redis_keyspace_misses", legend="misses", unit="short", fill=4),
        timeseries("Expired / evicted keys",
                   "nexusagent_redis_expired_keys", legend="expired", unit="short", fill=0),
        timeseries("", "nexusagent_redis_evicted_keys", legend="evicted", unit="short", fill=0),
        timeseries("Connected clients over time", "nexusagent_redis_connected_clients", legend="clients", unit="short"),
    ]
    return make_dashboard("nx-redis", "NexusAgent · Redis", "Redis connectivity, memory, cache hit rate and key lifecycle.", panels)


def dash_agents() -> Dict[str, Any]:
    panels = [
        stat("Active agents", "nexusagent_active_agents", unit="short", grid=(6, 4)),
        stat("Active conversations", "nexusagent_active_conversations", unit="short", grid=(6, 4)),
        timeseries("Active agents over time", "nexusagent_active_agents", legend="agents", unit="short"),
        timeseries("Active conversations over time", "nexusagent_active_conversations", legend="conversations", unit="short"),
        timeseries("Request volume by endpoint",
                   "sum(rate(nexusagent_http_requests_total[5m])) by (endpoint)", legend="{{endpoint}}", unit="reqps"),
        timeseries("Token consumption rate",
                   "sum(increase(nexusagent_total_tokens[1h]))", legend="tokens/h", unit="short"),
    ]
    return make_dashboard("nx-agents", "NexusAgent · Agent Activity", "Agents and conversations in flight and their request volume.", panels)


def dash_tokens() -> Dict[str, Any]:
    panels = [
        gauge("Total tokens", "nexusagent_total_tokens", unit="short", grid=(8, 8)),
        gauge("Total cost (USD)", "nexusagent_total_cost_usd", unit="$", max=100000, grid=(8, 8),
              thresholds=[(0, "green"), (1000, "yellow"), (10000, "red")]),
        timeseries("Token rate (tokens/hour)",
                   "sum(increase(nexusagent_total_tokens[1h]))", legend="tokens/h", unit="short"),
        timeseries("Cost rate (USD/hour)",
                   "sum(increase(nexusagent_total_cost_usd[1h]))", legend="usd/h", unit="$"),
        timeseries("Cumulative tokens", "nexusagent_total_tokens", legend="total", unit="short"),
    ]
    return make_dashboard("nx-tokens", "NexusAgent · Token Usage", "LLM token and cost consumption (cumulative and rate).", panels)


def dash_errors() -> Dict[str, Any]:
    panels = [
        stat("Error rate",
             "(sum(rate(nexusagent_http_errors_total[5m])) / clamp_min(sum(rate(nexusagent_http_requests_total[5m])), 1)) * 100",
             unit="percent", grid=(6, 4), thresholds=[(1, "green"), (5, "yellow"), (5.0001, "red")]),
        stat("Errors / 5m", "sum(increase(nexusagent_http_errors_total[5m]))", unit="short", grid=(6, 4),
             thresholds=[(0.999, "green"), (1.0001, "red")]),
        timeseries("Error rate over time",
                   "(sum(rate(nexusagent_http_errors_total[5m])) / clamp_min(sum(rate(nexusagent_http_requests_total[5m])), 1)) * 100",
                   legend="error %", unit="percent"),
        timeseries("Errors by status",
                   "sum(rate(nexusagent_http_errors_total[5m])) by (status)", legend="{{status}}", unit="reqps"),
        timeseries("Errors by endpoint",
                   "sum(rate(nexusagent_http_errors_total[5m])) by (endpoint)", legend="{{endpoint}}", unit="reqps"),
        timeseries("Errors by method",
                   "sum(rate(nexusagent_http_errors_total[5m])) by (method)", legend="{{method}}", unit="reqps"),
    ]
    return make_dashboard("nx-errors", "NexusAgent · Errors", "HTTP error rate, breakdown by status, endpoint and method.", panels)


def dash_infra() -> Dict[str, Any]:
    panels = [
        stat("Host up", "up{job=\"node\"}", unit="short", grid=(6, 4),
             thresholds=[(0.999, "green"), (1.0001, "red")]),
        gauge("CPU usage",
              "(1 - avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m]))) * 100",
              unit="percent", grid=(6, 6)),
        gauge("Memory usage",
              "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
              unit="percent", grid=(6, 6)),
        gauge("Disk free",
              "min(node_filesystem_avail_bytes{fstype!~\"tmpfs|overlay\"} / node_filesystem_size_bytes{fstype!~\"tmpfs|overlay\"}) * 100",
              unit="percent", grid=(6, 6)),
        timeseries("CPU by mode",
                   "rate(node_cpu_seconds_total[5m])", legend="{{mode}}", unit="short", fill=4),
        timeseries("Memory (available vs total)",
                   "node_memory_MemAvailable_bytes", legend="available", unit="bytes", fill=4),
        timeseries("", "node_memory_MemTotal_bytes", legend="total", unit="bytes", fill=0),
        timeseries("Disk free by mountpoint",
                   "node_filesystem_avail_bytes{fstype!~\"tmpfs|overlay\"} / node_filesystem_size_bytes{fstype!~\"tmpfs|overlay\"} * 100",
                   legend="{{mountpoint}}", unit="percent"),
        timeseries("Network (bytes/s)",
                   "rate(node_network_receive_bytes_total{device!~\"lo\"}[5m])", legend="rx {{device}}", unit="Bps", fill=4),
        timeseries("", "rate(node_network_transmit_bytes_total{device!~\"lo\"}[5m])",
                   legend="tx {{device}}", unit="Bps", fill=4),
        timeseries("Dependency health",
                   "nexusagent_db_up", legend="postgres", unit="short", fill=0),
        timeseries("", "nexusagent_redis_up", legend="redis", unit="short", fill=0),
        timeseries("", "nexusagent_llm_up", legend="llm", unit="short", fill=0),
        timeseries("", "nexusagent_storage_up", legend="storage", unit="short", fill=0),
    ]
    return make_dashboard("nx-infra", "NexusAgent · Infrastructure", "Host CPU/memory/disk/network plus NexusAgent dependency health.", panels)


DASHBOARDS = [dash_api, dash_db, dash_redis, dash_agents, dash_tokens, dash_errors, dash_infra]


def main() -> None:
    global _panel_id
    out_dir = os.path.join(os.path.dirname(__file__), "dashboards")
    os.makedirs(out_dir, exist_ok=True)
    for builder in DASHBOARDS:
        _panel_id = 0
        dash = builder()
        path = os.path.join(out_dir, f"{dash['uid']}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dash, fh, indent=2, ensure_ascii=False)
        print(f"wrote {path}  ({len(dash['panels'])} panels)")


if __name__ == "__main__":
    main()
