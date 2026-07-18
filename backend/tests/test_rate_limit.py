"""Tests for the in-memory rate limiter (Milestone 7, Phase 6).

Builds a standalone app with the middleware directly (not via ``app.main``) so
the pytest skip in ``main.py`` does not disable it here — this exercises the
real throttle logic.
"""
import os

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimitMiddleware


def _make_app(limit: int):
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=limit,
        exempt_paths=("/health", "/metrics", "/health/live", "/health/ready", "/health/startup"),
    )
    return app


def test_within_limit_allows_requests():
    client = TestClient(_make_app(limit=5))
    for _ in range(5):
        assert client.get("/ping").status_code == 200


def test_exceeding_limit_returns_429_with_retry_after():
    # Force a tiny budget so the test is fast and deterministic.
    client = TestClient(_make_app(limit=3))
    for _ in range(3):
        assert client.get("/ping").status_code == 200
    resp = client.get("/ping")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 1


def test_health_path_is_exempt():
    # /health is exempt even though the budget is 1.
    client = TestClient(_make_app(limit=1))
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_limit_zero_disables_limiter():
    # RATE_LIMIT_PER_MINUTE <= 0 disables throttling.
    client = TestClient(_make_app(limit=0))
    for _ in range(10):
        assert client.get("/ping").status_code == 200


def test_distinct_ips_are_counted_separately():
    app = _make_app(limit=2)
    client = TestClient(app)

    # Two requests from 10.0.0.1 are fine.
    h1 = {"X-Forwarded-For": "10.0.0.1"}
    assert client.get("/ping", headers=h1).status_code == 200
    assert client.get("/ping", headers=h1).status_code == 200
    assert client.get("/ping", headers=h1).status_code == 429

    # A different client IP has its own budget.
    h2 = {"X-Forwarded-For": "10.0.0.2"}
    assert client.get("/ping", headers=h2).status_code == 200
