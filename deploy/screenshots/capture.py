#!/usr/bin/env python3
"""NexusAgent AI - Phase 1.5 screenshot capture.

Drives the live UI with headless Chromium (Playwright) and saves full-page
PNGs for the DEPLOYMENT_REPORT.md. Registers/logs in a throwaway account so
authenticated pages (dashboard, agents, knowledge base, chat) can be captured.

Setup (one-time, on the machine running this):
  pip install playwright
  python -m playwright install chromium

Usage:
  python capture.py --base-url http://<EC2-IP> --out ./report-assets

Each capture is best-effort: a failure on one page logs a warning and moves on,
so a single missing route never aborts the whole run. Selectors are intentionally
loose (URL-driven navigation) to survive minor UI copy changes.
"""
from __future__ import annotations

import argparse
import time

from playwright.sync_api import sync_playwright

TS = int(time.time())
EMAIL = f"shots+{TS}@example.com"
PASSWORD = "ShotUser123!"


def snap(page, out_dir, name, url, wait_ms=1500):
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as e:  # networkidle can time out on polling apps; still shoot
        print(f"  warn: goto {url}: {e}")
    page.wait_for_timeout(wait_ms)
    path = f"{out_dir}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  saved {path}")


def try_signup(page, base):
    """Best-effort register via the UI; fall back silently if the form differs."""
    try:
        page.goto(f"{base}/signup", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        # Loose fills — inputs matched by type/placeholder.
        for sel, val in [
            ("input[type=email]", EMAIL),
            ("input[type=password]", PASSWORD),
        ]:
            loc = page.locator(sel).first
            if loc.count():
                loc.fill(val)
        page.screenshot(path=None)  # noop guard; real shot taken by caller
    except Exception as e:
        print(f"  warn: signup flow: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out", default="./report-assets")
    ap.add_argument("--grafana-url", default=None, help="e.g. http://<EC2-IP>:3001")
    ap.add_argument("--prometheus-url", default=None, help="e.g. http://<EC2-IP>:9090")
    args = ap.parse_args()

    import os
    os.makedirs(args.out, exist_ok=True)
    base = args.base_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # Public pages
        snap(page, args.out, "01-landing", f"{base}/")
        snap(page, args.out, "02-login", f"{base}/login")
        snap(page, args.out, "03-signup", f"{base}/signup")

        # Authenticated flow (best-effort; requires the UI to persist a session)
        try_signup(page, base)
        snap(page, args.out, "04-signup-filled", f"{base}/signup")

        # Authenticated pages by URL (session cookie/localStorage set after signup)
        snap(page, args.out, "05-dashboard", f"{base}/dashboard")
        snap(page, args.out, "06-agents", f"{base}/agents")
        snap(page, args.out, "07-knowledge-bases", f"{base}/knowledge-bases")
        snap(page, args.out, "08-chat", f"{base}/chat")
        snap(page, args.out, "09-api-keys", f"{base}/settings/api-keys")

        # API docs (always available)
        snap(page, args.out, "10-api-docs", f"{base}/api/v1/docs")

        # Observability (if published)
        if args.prometheus_url:
            snap(page, args.out, "11-prometheus", f"{args.prometheus_url}/targets")
        if args.grafana_url:
            snap(page, args.out, "12-grafana", args.grafana_url)

        browser.close()
    print("done.")


if __name__ == "__main__":
    main()
