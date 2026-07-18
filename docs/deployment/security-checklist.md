# Production Security Checklist

Pre-/post-deployment, incident-response, and key-rotation checklists for
NexusAgent AI (Milestone 7, Phase 6). Pair with
[`secrets.md`](secrets.md) and [`security-scanning.md`](security-scanning.md).

---

## A. Pre-deployment checklist

- [ ] **Secrets** — every `replace-with-*` in `env.production.example` replaced
      with a freshly generated value (see `secrets.md` §2). No `change-me-*`
      defaults remain.
- [ ] **JWT keys** — `JWT_SECRET_KEY` and `JWT_REFRESH_SECRET_KEY` are distinct,
      32-byte hex values.
- [ ] **DB password** — strong, unique, from `openssl rand -base64 24`.
- [ ] **CORS** — `BACKEND_CORS_ORIGINS` set to the real production origin(s)
      only (no `*`); `NEXT_PUBLIC_API_BASE_URL` uses `https://`.
- [ ] **TLS** — certificates obtained and mounted; `nginx/tls.conf.example`
      activated (HTTP→HTTPS redirect + HSTS). See `production.md` §5.
- [ ] **Debug off** — `DEBUG=false`; `LOG_FORMAT=json`.
- [ ] **Container hardening applied** — `docker-compose.aws.yml` hardening keys
      present: `cap_drop: [ALL]`, `read_only: true` + `tmpfs: /tmp` on backend,
      `read_only` + `tmpfs` + `NEXT_TELEMETRY_DISABLED=1` on frontend, resource
      limits on all services.
- [ ] **Rate limiting** — `RATE_LIMIT_PER_MINUTE` set (default 100); behind
      nginx, client IP is taken from `X-Forwarded-For`/`X-Real-IP`.
- [ ] **Security headers** — nginx sets `Content-Security-Policy`,
      `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
      `Permissions-Policy`; HSTS present under TLS. See `security-headers.md`.
- [ ] **Security scans green** — `pip-audit`, `npm audit`, `bandit`, and
      `trivy` jobs in `.github/workflows/security.yml` pass (or known issues are
      documented exceptions).
- [ ] **Firewall / Security Group** — only `22` (or SSM), `80`, `443` open to
      the world; backend/frontend ports reachable only on the internal bridge.
- [ ] **Backups** — DB and upload-volume backup verified; secret recovery
      procedure documented (`secrets.md` §6).
- [ ] **Dependency pins** — `pyproject.toml` and `package-lock.json` committed
      with pinned versions (no floating `^` in the lockfile at deploy time).

---

## B. Post-deployment checklist

- [ ] **Health** — `curl -fsS https://<domain>/health` returns `healthy`; all
      compose services report `healthy`.
- [ ] **TLS** — `https://<domain>` works; `http://<domain>` 301-redirects to
      HTTPS; HSTS header present (`Strict-Transport-Security`).
- [ ] **Headers** — `curl -I https://<domain>` shows CSP, X-Content-Type-Options
      `nosniff`, X-Frame-Options `SAMEORIGIN`, Referrer-Policy, Permissions-Policy
      (no duplicate copies).
- [ ] **CORS** — browser console shows no CORS errors; only the app origin is
      allowed.
- [ ] **Rate limit** — a burst past `RATE_LIMIT_PER_MINUTE` returns `429` with a
      `Retry-After` header.
- [ ] **Auth** — login/refresh/protected endpoints behave; an invalid token
      yields `401`; missing/invalid tenant membership yields `403`.
- [ ] **Secrets not leaked** — `git log` / repo contains no real secrets;
      `.env.production` is `chmod 600` and gitignored.
- [ ] **Monitoring** — Prometheus `/metrics` reachable only internally (not
      proxied by nginx); logs shipping to the aggregation target.
- [ ] **Backups scheduled** — automated DB + upload backup confirmed running.

---

## C. Incident response checklist

1. **Triage** — confirm the incident (which secret/endpoint/service), capture
   timestamps and affected scope.
2. **Contain** —
   - Suspected **JWT key** compromise → rotate both JWT keys immediately
     (`secrets.md` §4) and rolling-restart the backend; all sessions invalidated.
   - Suspected **DB credential** compromise → rotate the RDS password, update the
     secret, restart backend; review RDS connection logs.
   - Suspected **LLM key** compromise → disable/rotate the provider key; check
     provider billing for anomalous spend.
   - Active **abuse / DoS** → lower `RATE_LIMIT_PER_MINUTE`; if needed, block the
     offender at the Security Group / WAF.
3. **Preserve evidence** — snapshot logs, the running container/image digest, and
   recent deployments before cleanup.
4. **Eradicate** — patch the exploited path; re-run the security scans
   (`security-scanning.md`); verify the fix.
5. **Recover** — redeploy the patched image; restore from a known-good backup
   only if data was corrupted (not for secrets — regenerate instead).
6. **Post-mortem** — document root cause, add a regression test/scan check, and
   update this checklist.

---

## D. Key rotation checklist

| Key | Frequency | Steps | Impact |
|-----|-----------|-------|--------|
| `JWT_SECRET_KEY` / `JWT_REFRESH_SECRET_KEY` | 90 days or on suspicion | 1. Regenerate (§2). 2. Update secret store. 3. `deploy/rolling-restart.sh backend`. | All sessions log out; users re-auth. |
| `SECURITY_PASSWORD_SALT` | On suspicion only | 1. Regenerate. 2. Restart backend. | Existing password hashes no longer verify — **forces a password reset for all users**. Plan accordingly. |
| `POSTGRES_PASSWORD` | 180 days or on suspicion | 1. Rotate in RDS. 2. Update `POSTGRES_PASSWORD`. 3. Restart backend. | Brief reconnect; no user impact. |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | On provider compromise | 1. Rotate at provider. 2. Update secret. 3. Restart backend. | No token impact; resume spend under new key. |

> Rotating `SECURITY_PASSWORD_SALT` is destructive (it invalidates every stored
> password hash). Only do it on confirmed compromise, and coordinate a forced
> reset. Prefer rotating the DB password / JWT keys for routine hygiene.
