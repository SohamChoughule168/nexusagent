#!/usr/bin/env python3
"""NexusAgent AI - Phase 1.5 load test.

Drives the live deployment with a fixed concurrency of virtual users at a
capped aggregate request rate for a fixed duration, then reports latency
percentiles and error counts. Pair with `docker stats` sampling on the host
to capture CPU / RAM (see loadtest.md).

Target profile (Phase 1.5):
  * 25 concurrent users
  * 100 requests / minute (aggregate)
  * 15 minutes

Usage:
  python loadtest.py --base-url http://<EC2-IP> \
      --email loadtest@example.com --password 'S3cret!' \
      --users 25 --rpm 100 --duration 900

Only depends on aiohttp (pip install aiohttp). No external load tool needed.
The request mix is read-heavy and safe to run against a live box: health,
auth'd GETs (agents/conversations list), and optionally a chat turn.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass, field

import aiohttp


@dataclass
class Stats:
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    by_status: dict[int, int] = field(default_factory=dict)
    total: int = 0


async def ensure_user(session: aiohttp.ClientSession, base: str, email: str, pw: str) -> str | None:
    """Register (idempotently) then log in; return a bearer token or None."""
    reg = {
        "email": email,
        "password": pw,
        "full_name": "Load Test",
        "organization_name": "LoadTest Org",
        "organization_slug": "loadtest-org",
    }
    try:
        async with session.post(f"{base}/api/v1/auth/register", json=reg) as r:
            if r.status in (200, 201):
                data = await r.json()
                return data.get("access_token")
    except Exception:
        pass
    # Already registered -> log in.
    try:
        async with session.post(
            f"{base}/api/v1/auth/login", json={"email": email, "password": pw}
        ) as r:
            if r.status == 200:
                data = await r.json()
                return data.get("access_token")
    except Exception:
        pass
    return None


async def one_request(session, base, token, stats, sem):
    """Perform a single read-mostly request from the mix."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # Rotate through a realistic read-heavy mix.
    stats.total += 1
    idx = stats.total % 4
    if idx == 0:
        url, kw = f"{base}/health", {}
    elif idx == 1:
        url, kw = f"{base}/api/v1/agents", {"headers": headers}
    elif idx == 2:
        url, kw = f"{base}/api/v1/conversations", {"headers": headers}
    else:
        url, kw = f"{base}/api/v1/tools", {"headers": headers}

    async with sem:
        t0 = time.perf_counter()
        try:
            async with session.get(url, **kw) as r:
                await r.read()
                dt = (time.perf_counter() - t0) * 1000.0
                stats.latencies_ms.append(dt)
                stats.by_status[r.status] = stats.by_status.get(r.status, 0) + 1
                if r.status >= 500:
                    stats.errors += 1
        except Exception:
            stats.errors += 1


async def run(args):
    stats = Stats()
    sem = asyncio.Semaphore(args.users)
    interval = 60.0 / args.rpm  # seconds between request launches (aggregate)
    deadline = time.time() + args.duration

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        token = await ensure_user(session, args.base_url, args.email, args.password)
        if not token:
            print("WARN: could not obtain token; running unauthenticated health mix only")

        tasks: list[asyncio.Task] = []
        launched = 0
        start = time.time()
        while time.time() < deadline:
            tasks.append(asyncio.create_task(one_request(session, args.base_url, token, stats, sem)))
            launched += 1
            if launched % 50 == 0:
                elapsed = time.time() - start
                print(f"  t+{elapsed:6.1f}s launched={launched} errors={stats.errors}")
            await asyncio.sleep(interval)
        await asyncio.gather(*tasks, return_exceptions=True)

    lat = sorted(stats.latencies_ms)
    n = len(lat)

    def pct(p):
        if not lat:
            return 0.0
        return lat[min(n - 1, int(p / 100.0 * n))]

    print("\n===== Load Test Results =====")
    print(f"base_url      : {args.base_url}")
    print(f"users         : {args.users}")
    print(f"target rpm    : {args.rpm}")
    print(f"duration      : {args.duration}s")
    print(f"requests      : {stats.total}")
    print(f"completed     : {n}")
    print(f"errors (5xx/exc): {stats.errors}")
    print(f"error rate    : {100.0 * stats.errors / max(1, stats.total):.2f}%")
    print(f"status counts : {dict(sorted(stats.by_status.items()))}")
    if lat:
        print(f"latency ms    : min={lat[0]:.1f} p50={pct(50):.1f} "
              f"p95={pct(95):.1f} p99={pct(99):.1f} max={lat[-1]:.1f} "
              f"mean={statistics.mean(lat):.1f}")
    print("=============================")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True, help="e.g. http://<EC2-IP>")
    ap.add_argument("--email", default="loadtest@example.com")
    ap.add_argument("--password", default="LoadTest123!")
    ap.add_argument("--users", type=int, default=25)
    ap.add_argument("--rpm", type=int, default=100)
    ap.add_argument("--duration", type=int, default=900)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
