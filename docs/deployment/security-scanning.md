# Security Scanning

Tooling and CI integration for dependency, container, and code security
(Milestone 7, Phase 6). All scans live in
`.github/workflows/security.yml` and run on every push to `main` and every PR
targeting `main`.

---

## 1. What runs in CI

| Job | Tool | Scope | Fails on |
|-----|------|-------|----------|
| `python-audit` | `pip-audit` | Python dependency tree (`pyproject.toml`) | Any known vulnerability in installed packages |
| `npm-audit` | `npm audit` | Frontend lockfile (`frontend/package-lock.json`) | Moderate+ severity |
| `dependency-review` | GitHub Dependency Review | PR dependency diff | Introduced `high`+ vulnerability |
| `bandit` | Bandit | `backend/app` (excl. tests) | HIGH severity finding |
| `trivy` (fs) | Trivy | Repo source + IaC/config (Dockerfiles, compose, nginx) | HIGH/CRITICAL secret, misconfig, or dep CVE |
| `trivy` (image) | Trivy | Built `backend` / `frontend` images | CRITICAL, unfixed image CVE |

> Node modules and Python virtualenvs are **excluded** from the Trivy
> filesystem scan — JS/Python dependency CVEs are covered by `npm audit` /
> `pip-audit`, so the Trivy fs scan focuses on its unique value: **secret** and
> **misconfiguration** detection in our own code and config.

---

## 2. Running locally

### Python dependency audit
```bash
python -m pip install pip-audit==2.7.3
python -m pip install fastapi==0.110.0 uvicorn==0.27.0 pydantic==2.7.0 \
  pydantic-settings==2.3.0 sqlalchemy==2.0.30 psycopg2-binary==2.9.9 \
  redis==5.0.0 prometheus-client==0.21.1 structlog==24.1.0 python-dotenv==1.0.0 \
  "python-jose[cryptography]==3.3.0" argon2-cffi==23.1.0 passlib==1.7.4 httpx==0.27.0
python -m pip_audit
```

### Frontend audit
```bash
cd frontend && npm ci && npm audit --audit-level=moderate
```

### Bandit (Python SAST)
```bash
pip install "bandit==1.7.9"
bandit -r backend/app -x backend/app/tests -l high -ll
```

### Trivy (filesystem + image)
```bash
# install: https://trivy.dev/latest/getting-started/ (or:
#   curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin)
trivy fs --scanners vuln,secret,config --severity HIGH,CRITICAL \
  --exclude '**/node_modules/**' --exclude '**/.git/**' \
  --exclude '**/.venv/**' --exclude '**/__pycache__/**' --exclude '**/.next/**' .

docker build -f backend/Dockerfile -t nexusagent-backend:ci .
trivy image --severity CRITICAL --ignore-unfixed nexusagent-backend:ci

docker build -f frontend/Dockerfile -t nexusagent-frontend:ci ./frontend
trivy image --severity CRITICAL --ignore-unfixed nexusagent-frontend:ci
```

---

## 3. Tuning the gates

- **Bandit** currently fails on HIGH only (`-l high`). Once the baseline is
  clean, tighten to `-l medium` and add a baseline file (`bandit -f txt`) to
  allowlist accepted findings.
- **Trivy image** fails on CRITICAL, unfixed CVEs (`--ignore-unfixed`) so
  transient base-image noise does not block deploys. Fixable CRITICALs still
  fail and should prompt a base-image bump (e.g. `python:3.11-slim` → a newer
  digest). Add `--severity HIGH,CRITICAL` once the base images are current.
- **pip-audit / npm audit** — add `--ignore-vuln <id>` only with a documented
  reason and an expiry; never silence a finding silently.

---

## 4. Dependency review notes

- Pin versions: `pyproject.toml` uses `==` pins; `frontend/package-lock.json`
  is committed so `npm ci` is reproducible. Avoid floating ranges at deploy time.
- New dependencies must clear the `dependency-review` gate (no introduced
  `high`+ vulnerability) before merge.

---

## 5. Accepted risks / known gaps

- **In-memory rate limiter** is per-process, not shared — multiple backend
  replicas would each enforce their own budget. Enforce at nginx (`limit_req`)
  or move to Redis for horizontal scale.
- **`requests` / SSRF**: outbound calls to LLM providers use configured base
  URLs only; no user-supplied URLs are fetched. Re-scan if a webhook/fetch tool
  is added.
- **Base-image CVEs** may appear as `unfixed`; review periodically and bump
  image tags/digests.
