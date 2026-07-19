# NexusAgent — Beta Readiness

This document consolidates the checklists, known issues, limitations, and risk
assessment for the **public beta** rollout of NexusAgent `1.0.0`. It is the
operator/PM companion to [`docs/RELEASE.md`](RELEASE.md) and the deployment
runbooks under `docs/deployment/`.

> **Beta framing:** the public beta is the external rollout of the already-tagged
> `1.0.0` release (see `docs/RELEASE.md` §7). No version-number change is made
> for the beta.

---

## 1. Beta checklist (gate before opening the beta)

Run before inviting external users. Each item must be ticked or explicitly N/A.

### Product & docs
- [ ] README, Quickstart, and User Guide let a new developer clone → run → talk
      to the demo agent using only the docs.
- [ ] `docs/RELEASE.md` release process + version policy is current.
- [ ] This document (known issues, limitations, risks) is published alongside
      the beta.
- [ ] API docs (`/docs`) reviewed for accuracy against the running endpoints.

### Security & isolation
- [ ] `docs/deployment/security-checklist.md` passed (headers, CORS, rate
      limiting, secrets).
- [ ] Multi-tenant isolation verified (RLS on core tables; app-layer isolation
      on `memories`).
- [ ] JWT + refresh secrets are unique, non-default, and stored via Secrets
      Manager (not in the image or `.env.production` on disk longer than needed).
- [ ] `/auth/change-password` reviewed for the no-session (email + current
      password) design and its abuse surface (see §3 Known issues).

### Operations
- [ ] Backups (`deploy/backup.sh`) run nightly and a test restore is verified.
- [ ] Health probes (`/health`, `/health/ready`, `/health/startup`) return green
      under load.
- [ ] `/metrics` scraped by Prometheus; Grafana dashboards load.
- [ ] Rollback runbook (`docs/deployment/ROLLBACK.md`) rehearsed once.

### Support readiness
- [ ] Support checklist (§5) staffed and a triage queue exists.
- [ ] Known limitations are written in customer-facing language.
- [ ] Demo workspace + sample credentials documented for support repro.

---

## 2. Limitations (what the beta does NOT do yet)

Carried from `RELEASE_NOTES_v1.0.0.md` and verified against the codebase:

- **Document formats:** ingestion accepts **PDF only** (`ALLOWED_MIME_TYPES =
  ["application/pdf"]`), even though `ALLOWED_EXTENSIONS` lists additional types.
  Other formats (docx, txt, csv, html, md, json) are accepted by the allow-list
  config but not parsed by the ingestion pipeline yet.
- **LLM/RAG offline fallback:** without `OPENROUTER_API_KEY` (+ provider set),
  RAG answers use the local composer over retrieved chunks — useful for demos,
  not production answer quality.
- **`memories` table has no DB-level RLS:** long-term memory isolation is
  enforced at the application/service layer only. Keep all memory access through
  the tenant-scoped services.
- **Single Uvicorn worker per container:** scale horizontally (more containers),
  not by raising workers in one process.
- **mypy is non-blocking** and `ruff` runs with a temporary ignore baseline
  (`F401/F541/F841/F821/E402`) for pre-1.0 code; both are green as gates today.
- **Frontend image size:** ships full `node_modules`; Next.js standalone output
  is a deferred size optimization.
- **Rate limiting** is app-layer and coarse (per-IP minute budget); it is not a
  full WAF/DDoS defense — the nginx edge + provider limits are the real boundary.
- **No automated email verification / password reset flow:** `email_verified`
  is set `True` at registration for the self-service beta; a real verification
  email is a post-beta item.

---

## 3. Known issues (tracked)

| # | Area | Issue | Severity | Status |
|---|------|-------|----------|--------|
| K1 | Auth | `POST /auth/change-password` requires only `email` + `current_password` (no session/Bearer). Convenient for no-session resets but widens the account-takeover surface if an attacker already knows the current password. Consider requiring a logged-in session or a reset token. | Medium | Documented; review before GA |
| K2 | Config | `ALLOWED_EXTENSIONS` advertises 8 types but `ALLOWED_MIME_TYPES` restricts to PDF. Misleading; reconcile or document. | Low | Fix candidate (Phase 8) |
| K3 | API | Several list endpoints return unbounded results (no pagination/limit/offset). Acceptable at beta scale; add cursor pagination before GA. | Low/Medium | Tracked |
| K4 | API | `GET /auth/api-keys` uses `response_model=dict` (untyped) and `POST /auth/change-password` returns a raw dict. Low-risk typing cleanup. | Low | Fix candidate (Phase 8) |
| K5 | Memory | No DB-level RLS on `memories` (see §2). Relies on app-layer isolation. | Medium | By design; monitor |
| K6 | UX | Registration does not surface a non-unique `organization_slug` as a friendly 409 — a DB IntegrityError surfaces as 500. Better error mapping pre-GA. | Low | Fix candidate |

See `docs/reports/PHASE_6_RELEASE_AUDIT.md` for the full audit, including code
and config findings.

---

## 4. Production checklist (reference)

The authoritative, step-by-step production checklist is
[`docs/deployment/PRODUCTION_CHECKLIST.md`](deployment/PRODUCTION_CHECKLIST.md)
(AWS single-instance). The beta may run on the same stack; treat the production
checklist as the bar for promoting the beta to GA.

---

## 5. Support checklist

- [ ] **Triage queue** (issue tracker or shared inbox) monitored during beta
      hours.
- [ ] **Repro path:** sign into the Brightpath demo workspace
      (`demo@nexusagent.dev` / `nexusagent-demo`) to reproduce chat/KB issues.
- [ ] **Log correlation:** every request carries `X-Request-ID`; ask reporters
      for it and grep backend logs / Grafana by it.
- [ ] **Version first:** confirm the reporter's `GET /version`
      (`build_git_sha`) before debugging — mismatches mean a stale image.
- [ ] **Escalation:** request ID(s), last deploy tag (`git describe`), backend
      logs around the timestamp, and Prometheus signals (error rate, p95).
- [ ] **Known-issues pointer:** link §3 above before filing new bugs.
- [ ] **Rollback authority:** only on-call may run `deploy/restore.sh`
      (destructive) — see §6.

---

## 6. Rollback checklist (reference)

The full procedure is [`docs/deployment/ROLLBACK.md`](deployment/ROLLBACK.md).
Short version for the beta on-call:

- [ ] **Triage:** did a migration run? If no → redeploy last-good tag (§1 of
      ROLLBACK). If yes and not backward-compatible → restore pre-deploy DB
      backup **then** redeploy last-good code.
- [ ] **Backup first:** `./deploy/backup.sh` before any restore.
- [ ] **Code rollback:** `git checkout <last-good-sha>` →
      `./deploy/update-containers.sh` (health-gated).
- [ ] **Data rollback:** `./deploy/restore.sh <ts>` (requires typed `RESTORE`),
      then `./deploy/rolling-restart.sh backend`.
- [ ] **Verify:** `/health` healthy, all services `healthy`, chat/agent flows
      work, `alembic current` matches restored code.

---

## 7. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Cross-tenant data exposure | Low | Critical | RLS on core tables + app-layer tenant repository; keep all data access through `get_tenant_context`. Monitored in beta. |
| No-session password change abused (K1) | Low | High | Documented; restrict endpoint or add session/reset-token requirement before GA. |
| Migration not backward-compatible → bad rollback | Low | High | Additive migrations in hotfixes; backup before every update; rehearsed rollback. |
| LLM/embedding key missing → poor answers | Medium | Medium | Clear offline-fallback messaging in UI; require keys for GA answer quality. |
| Rate-limit exhaustion / abuse | Medium | Medium | App-layer limiter + nginx edge; tighten budget with beta telemetry. |
| Backup not restorable | Low | High | Monthly restore verification; S3 off-host copies. |
| Stale image served (version mismatch) | Low | Medium | `/version` verification in support + deploy gates. |
| Single-worker throughput ceiling | Medium | Low | Horizontal scaling guidance; autoscale containers. |

**Overall beta risk:** Moderate and well-contained. No release-blocking issues
remain for a controlled public beta; K1 and K5 are the items to resolve before a
general-availability (GA) promotion.
