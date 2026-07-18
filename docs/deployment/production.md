# Production Deployment

NexusAgent AI — production deployment foundation (Milestone 7, Phase 3).

This document covers **deployment packaging, the reverse proxy, and TLS
preparation**. It does **not** cover AWS, Kubernetes, Terraform, Helm, or
monitoring — those are later phases.

---

## 1. Deployment Architecture

A single-host, container-based deployment composed of five services on one
private bridge network (`nexusagent-net`):

```
                        ┌─────────────────────────────────────────┐
        Browser ───────▶│  nginx  :80  (reverse proxy, public)     │
                        │   • /api/*      → backend:8000           │
                        │   • /health     → backend:8000/health     │
                        │   • /_next/static/* → frontend:3000 (cache)│
                        │   • /*          → frontend:3000           │
                        └───────────────┬───────────────┬──────────┘
                                        │               │
                              ┌─────────▼──────┐  ┌──────▼─────────┐
                              │  backend :8000 │  │ frontend :3000 │
                              │  (FastAPI)     │  │ (Next.js)      │
                              └───┬────────┬───┘  └────────────────┘
                                  │        │
                        ┌─────────▼──┐  ┌──▼─────────┐
                        │  postgres  │  │   redis    │
                        │   :5432    │  │   :6379    │
                        └────────────┘  └────────────┘
```

| Service   | Image                     | Internal port | Public port | Depends on            |
|-----------|---------------------------|---------------|-------------|----------------------|
| `db`      | `postgres:16-alpine`      | 5432          | 5432*       | —                    |
| `redis`   | `redis:7-alpine`          | 6379          | 6379*       | —                    |
| `backend` | `nexusagent-backend`      | 8000          | 8000*       | db, redis (healthy)  |
| `frontend`| `nexusagent-frontend`     | 3000          | —           | backend (healthy)    |
| `nginx`   | `nginx:1.27-alpine`       | 80 / 443      | 80          | backend, frontend    |

`*` Only published for local/debug access. In a hardened deployment, the
backend and frontend ports are **not** published — nginx is the sole public
entrypoint and talks to them over the internal network.

---

## 2. Build Process

### Repository layout (what gets packaged)

```
nexusagent/                  (repo root — also the backend build context)
├── pyproject.toml          # project + packaging config
├── README.md               # referenced by pyproject `readme`
├── backend/
│   ├── Dockerfile          # backend image (root build context)
│   ├── app/                # the `app` Python package (FastAPI)
│   ├── alembic/            # migration scripts
│   └── alembic.ini         # alembic config (script_location = alembic)
├── frontend/
│   ├── Dockerfile          # frontend image (./frontend build context)
│   └── ...                 # Next.js source
├── nginx/
│   ├── nginx.conf          # active HTTP reverse-proxy config
│   └── tls.conf.example    # HTTPS/TLS placeholder config
└── docker-compose.yml
```

### Backend packaging fix (this phase)

The Python package (`app` and its subpackages) lives under `backend/app/`.
`pyproject.toml` now declares:

```toml
[tool.setuptools]
package-dir = {"" = "backend"}
packages = ["app", "app.ai", "app.ai.providers", "app.api",
            "app.api.v1", "app.api.v1.endpoints", "app.core",
            "app.models", "app.repositories", "app.schemas", "app.services"]
```

`package-dir = {"" = "backend"}` maps the root import namespace to `backend/`,
so `pip install .` from the **repo root** builds and installs a normal,
top-level `app` package. No `PYTHONPATH` is required at build or runtime.

The backend image is built from the **repository root** (not `./backend`),
because its Dockerfile copies the root-level `pyproject.toml` and `backend/`.
This is enforced in `docker-compose.yml`:

```yaml
backend:
  build:
    context: .            # repo root
    dockerfile: backend/Dockerfile
```

The multi-stage `backend/Dockerfile`:

1. **deps** — `pip install .` installs the runtime dependencies **and** the
   `app` package into site-packages; `alembic` is added for migrations.
2. **runtime** — copies site-packages + binaries from `deps`, then copies
   `backend/alembic` and `backend/alembic.ini` (migration scripts/config).
   Runs `uvicorn app.main:app` as a non-root `appuser`. Because `app` is an
   installed top-level package, it resolves with **no `PYTHONPATH`**.

### Commands

```bash
# Validate the compose file (variable interpolation, service shape)
docker compose config

# Build every image (no workarounds needed)
docker compose build

# Build a single image directly (mirrors CI)
docker build -f backend/Dockerfile -t nexusagent-backend:ci .

# Install the backend package locally (packaging sanity check)
python -m venv .venv && . .venv/Scripts/activate   # or: source .venv/bin/activate
pip install .

# Build the frontend
cd frontend && npm ci && npm run build && cd ..
```

---

## 3. Startup Sequence

Ordering is enforced with Compose `depends_on: { condition: service_healthy }`
and container healthchecks:

1. **`db`** (postgres) starts; healthcheck `pg_isready` → healthy.
2. **`redis`** starts; healthcheck `redis-cli ping` → healthy.
3. **`backend`** waits for `db` + `redis` healthy, then starts uvicorn;
   healthcheck `curl /health` → healthy.
4. **`frontend`** waits for `backend` healthy, then starts `next start`;
   healthcheck fetches `/` → healthy.
5. **`nginx`** waits for `backend` + `frontend` healthy, then starts and
   proxies traffic; healthcheck `wget /health` → healthy.

Bring it up:

```bash
docker compose up -d --build
docker compose ps          # all five services should be "healthy"
```

Tear it down:

```bash
docker compose down
docker compose down -v     # also remove the postgres/redis volumes
```

---

## 4. Reverse Proxy Explanation

`nginx` is the single public entrypoint. `nginx/nginx.conf` (mounted as
`/etc/nginx/conf.d/default.conf`) routes:

| Location            | Target                | Notes                                        |
|---------------------|-----------------------|----------------------------------------------|
| `= /health`         | `backend:8000/health` | Backend liveness; also used by nginx healthcheck. |
| `/api/`             | `backend:8000`        | REST + **WebSocket** upgrades (`Upgrade`/`Connection` headers, long timeouts). |
| `/_next/static/`    | `frontend:3000`       | Long-lived `Cache-Control: immutable` caching. |
| `/` (default)      | `frontend:3000`       | Next.js app shell; WebSocket upgrade headers for HMR. |

Key proxy behaviors:

- **WebSocket support** — `proxy_set_header Upgrade $http_upgrade;` and
  `proxy_set_header Connection "upgrade";` plus `proxy_http_version 1.1` and
  extended read/send timeouts, so streaming and socket endpoints work.
- **Gzip** — `gzip on;` with a curated `gzip_types` list (JSON, JS, CSS, SVG).
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`,
  `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy` (HSTS is added
  in the TLS config, since it is only valid over HTTPS).
- **Cache headers** — frontend build assets under `/_next/static/` are cached
  for one year and marked `immutable`.
- **Request size limit** — `client_max_body_size 50M` (align with
  `MAX_UPLOAD_SIZE_MB`).

---

## 5. TLS Setup

TLS certificates are **not generated in this phase**. The HTTPS configuration
is provided as a ready-to-activate placeholder: `nginx/tls.conf.example`.

### Enable HTTPS in production

1. **Obtain certificates** (e.g. certbot / Let's Encrypt) and place them at:
   ```
   nginx/certs/fullchain.pem
   nginx/certs/privkey.pem
   ```
2. **Mount the certs** — uncomment in `docker-compose.yml`:
   ```yaml
   nginx:
     volumes:
       - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
       - ./nginx/certs:/etc/nginx/certs:ro      # <-- uncomment
     ports:
       - "80:80"
       - "443:443"                               # <-- uncomment
   ```
3. **Activate the TLS config** — mount the example over the active config
   (or merge its server block into `nginx.conf`):
   ```yaml
   # - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
   - ./nginx/tls.conf.example:/etc/nginx/conf.d/default.conf:ro
   ```
4. **Recreate nginx**:
   ```bash
   docker compose up -d nginx
   ```

### What the TLS config provides

- **HTTP → HTTPS redirect** — the port-80 server returns `301 https://$host`.
- **Certificate placeholders** — `ssl_certificate` /
  `ssl_certificate_key` point at the mounted `/etc/nginx/certs/*` paths.
- **Modern TLS** — `TLSv1.2`/`TLSv1.3`, hardened ciphers, session cache,
  OCSP stapling.
- **HSTS** — `Strict-Transport-Security: max-age=63072000; includeSubDomains;
  preload` (always).
- **Secure headers** — same header set as the HTTP config, plus HSTS.
- The same reverse-proxy routing (`/api`, `/health`, `/_next/static`, `/`)
  is preserved under the TLS listener.

> Renewal: re-issue the certificates in `nginx/certs/` and reload nginx
> (`docker compose exec nginx nginx -s reload`). Automate with certbot's
> renew hook in a later phase.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `docker compose build` fails: `COPY failed: pyproject.toml: no such file` | Backend built from the wrong context. | Ensure `backend.build.context` is `.` (repo root), not `./backend`. |
| `pip install .` fails: package `app` not found | `package-dir`/`packages` misconfigured. | Keep `package-dir = {"" = "backend"}` and the full `packages` list in `pyproject.toml`. |
| App imports fail with `ModuleNotFoundError: app` | `app` not installed / `PYTHONPATH` assumed. | Install via `pip install .`; do **not** rely on `PYTHONPATH=backend`. |
| `ModuleNotFoundError: app.services...` | `app.services` (namespace pkg) dropped from `packages`. | Keep `"app.services"` in the `packages` list. |
| Backend container restarts / unhealthy | `db` or `redis` not healthy yet, or missing secrets. | Check `docker compose logs backend db redis`; set `JWT_SECRET_KEY` etc. in `.env`. |
| nginx 502 Bad Gateway | Backend/frontend not yet healthy, or upstream name wrong. | `docker compose ps`; confirm `backend_upstream`/`frontend_upstream` names. |
| nginx won't start after enabling TLS | Cert paths missing (`/etc/nginx/certs/*`). | Mount `./nginx/certs`; verify `fullchain.pem`/`privkey.pem` exist. |
| HSTS not taking effect | Served over HTTP. | HSTS only applies over HTTPS; activate `tls.conf.example`. |
| 413 Request Entity Too Large | Upload exceeds `client_max_body_size`. | Raise `client_max_body_size` in `nginx.conf` and `MAX_UPLOAD_SIZE_MB`. |

### Useful commands

```bash
docker compose config                 # validate compose
docker compose ps                     # service/health status
docker compose logs -f backend        # backend logs
docker compose logs -f nginx          # proxy logs
docker compose exec backend alembic upgrade head   # apply migrations
curl -fsS http://localhost/health     # health through nginx
curl -fsS http://localhost:8000/health  # health direct (if port published)
```
