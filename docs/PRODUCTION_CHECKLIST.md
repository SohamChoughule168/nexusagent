# NexusAgent AI — Production Checklist

Tick every box before declaring the deployment live on **public HTTPS**. This
checklist pairs with [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md). The target
recommended there is **Railway**; the Render and AWS EC2 equivalents are noted
where they differ.

> **Not done yet:** No deployment has been performed. Items marked **[YOU]**
> require your credentials/platform access and are the stopping point of the
> engineering deployment phase.

---

## 1. Pre-flight (one-time)

- [ ] Local tools installed: `railway`, `gh`, `node` ≥ 20, `python3` ≥ 3.11
      (see DEPLOYMENT_GUIDE §1).
- [ ] Repository is on the branch you intend to ship; working tree clean
      (`git status`).
- [ ] You have a Railway account and `railway login` succeeded **[YOU]**.
- [ ] Target domain decided (Railway `*.up.railway.app` default, or a custom
      domain you control) **[YOU]**.

## 2. Project & managed services

- [ ] Railway project created (`railway init`, empty project) **[YOU]**.
- [ ] PostgreSQL plugin added → `DATABASE_URL` injected **[YOU]**.
- [ ] Redis plugin added → `REDIS_URL` injected **[YOU]**.
- [ ] `railway variables get DATABASE_URL` and `… REDIS_URL` return values
      (masked is fine).

## 3. Backend service

- [ ] Service created from repo root, `dockerfilePath: backend/Dockerfile`,
      `rootDirectory: .` (DEPLOYMENT_GUIDE §3 / §8 `railway.toml`).
- [ ] Public networking enabled; note the assigned `https://<backend>…` URL.
- [ ] Healthcheck path = `/health`.
- [ ] `DEBUG=false`, `DOCS_ENABLED=false`, `TRUST_PROXY=true` set.
- [ ] **Required secrets present and unique** (generate, never reuse):
  - [ ] `JWT_SECRET_KEY`  (`openssl rand -hex 32`)
  - [ ] `JWT_REFRESH_SECRET_KEY`  (`openssl rand -hex 32`)
  - [ ] `SECURITY_PASSWORD_SALT`  (`openssl rand -hex 16`)
- [ ] `BACKEND_CORS_ORIGINS` includes the frontend's `https://` origin.
- [ ] LLM key set if cloud models wanted (`OPENROUTER_API_KEY`, etc.); else
      `EMBEDDINGS_PROVIDER=local` / `RAG_LLM_PROVIDER=local` keep offline mode.
- [ ] `railway variables` shows no leftover `change-me` placeholders.

## 4. Frontend service

- [ ] Service created from `frontend/`, `dockerfilePath: frontend/Dockerfile`
      (DEPLOYMENT_GUIDE §4 / §8).
- [ ] Public networking enabled; note the assigned `https://<frontend>…` URL.
- [ ] **Build** variable `NEXT_PUBLIC_API_BASE_URL` = the backend's
      `https://<backend>.up.railway.app/api/v1` (baked at build time).
- [ ] `NEXT_TELEMETRY_DISABLED=1` set.
- [ ] If the backend URL changes later, the frontend is **redeployed**
      (not just restarted).

## 5. Database migrations

- [ ] Migrations applied: `railway run alembic upgrade head`
      (DEPLOYMENT_GUIDE §6).
- [ ] `railway run alembic current` reports the latest revision (10 migrations
      in `backend/alembic/versions`).
- [ ] Note the current commit SHA for rollback: `git rev-parse HEAD`.

## 6. Deploy

- [ ] `railway up` builds both images successfully.
- [ ] Backend logs show `startup_complete` (no `config_insecure_default`
      errors — those mean a required secret is missing).
- [ ] Frontend logs show the Next.js production server listening.

## 7. Post-deploy verification (public HTTPS)

- [ ] `curl -fsS https://<backend>…/health` → `{"status":"healthy"}`.
- [ ] `curl -fsS https://<backend>…/ready` → `{"status":"ok",…}` (503 if a
      dependency is down).
- [ ] `curl -fsS https://<backend>…/version` → build metadata with
      `git_sha`/timestamp.
- [ ] `curl -fsS -o /dev/null -w "%{http_code}" https://<frontend>…/` → `200`.
- [ ] Frontend UI loads and the chat connects (WebSocket upgrade works).
- [ ] Security headers present on `https://<frontend>…/`:
      `X-Content-Type-Options`, `Content-Security-Policy`,
      `Referrer-Policy`, `Permissions-Policy` (set by nginx in EC2; Railway
      edge sets its own — verify in the browser devtools).
- [ ] Uploads work: upload a document and confirm it persists.

## 8. TLS / custom domain (optional but recommended for GA)

- [ ] Custom domain added in Railway dashboard → Domains **[YOU]**.
- [ ] DNS `CNAME`/`A` record points at Railway **[YOU — registrar]**.
- [ ] Certificate issued automatically (Railway-managed, auto-renewing).
- [ ] Update `BACKEND_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` to the
      `https://` custom origin, then redeploy the frontend.
- [ ] `curl -I https://<custom-domain>/` returns `200` over TLS.

## 9. CI/CD

- [ ] `.github/workflows/deploy.yml` present (auto-deploys on push to `main`).
- [ ] GitHub secret `RAILWAY_TOKEN` added **[YOU]**.
- [ ] A test push to `main` triggers the workflow and the deploy succeeds.
- [ ] Manual fallback documented: `railway up`.

## 10. Ongoing operations

- [ ] Database backups enabled (Railway Postgres automatic backups, or
      `pg_dump` on a schedule).
- [ ] Redis persistence acceptable (ephemeral cache; app degrades gracefully
      without it per `HEALTH_REQUIRE_REDIS=false`).
- [ ] Log access via `railway logs` confirmed.
- [ ] Secret rotation plan: `JWT_*` / `SECURITY_PASSWORD_SALT` rotation
      requires a redeploy (env change).
- [ ] Dependency/image patch cadence defined.

## 11. Before every code update

- [ ] Current commit SHA recorded (`git rev-parse HEAD`).
- [ ] Migration backward-compatibility reviewed (shared DB).
- [ ] Maintenance window noted if breaking migration or secret rotation.

---

### Emergency contacts / escalation
- Backend unhealthy: `railway logs --service backend`; check
  `railway run alembic current`; verify `DATABASE_URL`/`REDIS_URL`.
- Frontend 5xx: `railway logs --service frontend`; confirm
  `NEXT_PUBLIC_API_BASE_URL` was set at build time and frontend redeployed.
- TLS broken (custom domain): check DNS + Railway Domains status; fall back to
  the `*.up.railway.app` URL.
