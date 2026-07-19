# Phase 5 — Cloud Deployment Plan

**Status:** Recommendation · AWS EC2 single-instance (Docker Compose)
**Branch:** `phase/3b-repository-health`
**Scope:** Phase 5 — Cloud Deployment & Observability (Step 1: Cloud Platform Audit)

---

## 1. Recommendation

**Deploy NexusAgent on a single Amazon EC2 instance running Docker Compose, with
stateful services on managed AWS offerings (Amazon RDS for PostgreSQL, Amazon
ElastiCache for Redis), nginx as the only public entrypoint, and a separate
monitoring stack (Prometheus + Grafana + Alertmanager).**

This is the platform the repository is **already built for**: `docker-compose.aws.yml`,
`deploy/user-data.sh`, the full `deploy/` script suite, `nginx/` configs, and the
`monitoring/` stack all target exactly this topology. Adopting a different platform
would throw away working, tested deployment code and reintroduce risk for no
compelling gain at this stage.

> **One platform: AWS EC2.** Everything else in this document is the rationale and
> the comparison that rules the alternatives out for *this* phase.

---

## 2. Constraints We Are Designing Under

These come directly from the Phase 5 brief and the repository's stated scope:

| Constraint | Implication |
|------------|-------------|
| **Prefer AWS** unless another platform has a compelling technical advantage | AWS is the default; only a strong technical reason flips it. |
| **Portable, avoid vendor lock-in** | Deployment unit = Docker images; infra choices must be swappable. |
| **Use Docker as the deployment unit** | No raw AMIs-as-artifact; containers everywhere. |
| **No Kubernetes in this phase** | ECS/Fargate *orchestration* is off the table by policy. |
| **Single-node production that can later scale horizontally** | Design stateless app tier; keep state in managed services. |
| **Do not redesign architecture / add AI features** | Reuse what exists. |

---

## 3. Platform Comparison

Ten candidate platforms evaluated against the constraints. The decisive axes are:
**AWS preference**, **Docker as unit**, **no-Kubernetes rule**, **single-node-today /
horizontal-later**, and **operational simplicity for a small team**.

### AWS family

| Platform | Fit | Verdict |
|----------|-----|---------|
| **AWS EC2 (Docker Compose)** | Full control, Docker unit, managed RDS/Redis, no K8s, single host that scales by adding instances behind a load balancer later. Matches repo exactly. | ✅ **Chosen** |
| AWS ECS (Fargate) | AWS-native containers, but orchestration layer adds task defs, services, ALB, and breaks the "no orchestration in this phase" simplicity; compose file would need rewriting to task definitions. | ➖ Over-engineered for single-node MVP |
| AWS App Runner | Great DX for one container behind a URL, but it expects a *single* service per App Runner service; NexusAgent needs backend + frontend + nginx + background workers, and App Runner's pricing/limits and lack of a co-located nginx make routing/custom-domain/TLS awkward. | ➖ Wrong shape for a multi-container app |
| AWS Lightsail | Cheap, simple VPS; supports containers. But limited managed Postgres/Redis options, weaker IAM/networking integration, and fewer knobs for the hardening we already did (SGs, Secrets Manager). | ➖ Too thin for the managed-service story |
| AWS Elastic Beanstalk | Wraps EC2 + LB + ASG; closer, but opinionated about structure and fights our hand-rolled compose + nginx + certbot flow. | ➖ Friction with existing deploy scripts |

### Other clouds / PaaS

| Platform | Fit | Verdict |
|----------|-----|---------|
| **Google Cloud Run** | Excellent containers, scales to zero, managed Postgres/Redis (Cloud SQL / Memorystore). Strong technical fit — *but* it is not AWS, violating the stated AWS preference, and Cloud Run's per-request model plus the need for a custom nginx/TLS proxy complicates our design. | ➖ Compelling, but not AWS |
| **Azure Container Apps** | Solid managed-container + Dapr-ish model; managed Postgres/Redis available. Again, not AWS, and the KEDA/serverless surface is more than we need. | ➖ Not AWS; heavier than needed |
| **Railway** | Very fast DX, Docker-native, ephemeral-ish. Vendor-specific primitives (Railway volumes, Railway Postgres) reduce portability and the "no lock-in" goal; weaker enterprise controls. | ➖ Lock-in + thin controls |
| **Render** | Similar to Railway; managed Postgres/Redis, nice DX, but proprietary blueprints and limited network/SG control; not AWS. | ➖ Lock-in + not AWS |
| **Fly.io** | Docker images close to the edge, global regions, great for latency. But its fl/client model and per-region state story complicate a single managed-RDS topology; not AWS. | ➖ Not AWS; edge model misfits central DB |

### Why not the non-AWS options despite being "technically compelling"

Cloud Run, Container Apps, Railway, Render, and Fly.io are all *good* Docker
platforms. The brief explicitly says **prefer AWS unless another platform has a
compelling technical advantage**. None of them offers an advantage large enough to
justify (a) abandoning the already-complete AWS deployment code, or (b) violating the
AWS preference. The differentiators that *would* flip the decision — e.g. built-in
horizontal autoscaling we're explicitly deferring, or zero-ops for a no-ops team —
are out of scope for this phase.

### Why EC2 over ECS/App Runner specifically (both are AWS)

- **ECS/Fargate** introduces an orchestration control plane (task definitions,
  services, target groups, ALB) that the brief's "no Kubernetes / single-node" spirit
  discourages, and it would require rewriting `docker-compose.aws.yml` into ECS task
  definitions. We keep the Docker Compose unit intact.
- **App Runner** can't naturally host the multi-container nginx-fronted topology we
  rely on for TLS termination, WebSocket proxying, and CSP/HSTS headers.
- **EC2 + Compose** keeps the *exact* deployment unit the repo ships, gives us a
  co-located nginx for Let's Encrypt, and scales later by promoting the single host
  to a small ASG behind an ALB — a clean, well-trodden path that preserves every
  line of existing tooling.

---

## 4. Chosen Topology

```
                         ┌──────────────────────────────────────────────┐
   Browser / API client  │            EC2 (Ubuntu, t3.medium)             │
        (https://domain) │                                              │
        :80 / :443 ──────▶│   nginx :80/:443  (ONLY public entrypoint)   │
                          │     /api/*  → backend:8000                    │
                          │     /health → backend:8000/health            │
                          │     /       → frontend:3000                  │
                          │   backend:8000 (FastAPI, internal)           │
                          │   frontend:3000 (Next.js, internal)          │
                          └──────┬───────────────────┬──────────────────┘
                                 │                   │
                    ┌────────────▼─────┐   ┌─────────▼────────┐
                    │ RDS PostgreSQL 16│   │ ElastiCache Redis│
                    │ (managed, Multi- │   │ (managed, cache/ │
                    │  AZ optional)    │   │  broker/results) │
                    └──────────────────┘   └──────────────────┘
   SGs: nexusagent-ec2 (22/80/443 only) · nexusagent-rds (5432 from ec2) · nexusagent-redis (6379 from ec2)
   EBS gp3 @ /data (uploads + backups) · Let's Encrypt (certbot) TLS at nginx
```

The observation stack (Prometheus/Grafana/Alertmanager + node/postgres/redis
exporters) runs as a **second** compose project on the same host, reaching app
targets via `host.docker.internal`.

---

## 5. Why This Satisfies the Brief

| Phase 5 requirement | How EC2 + Compose meets it |
|---------------------|----------------------------|
| Cloud deployment | EC2 host, images built on-host from source (no external registry required). |
| HTTPS | nginx terminates TLS via Let's Encrypt (`deploy/init-letsencrypt.sh`); HSTS + modern ciphers. |
| Domain support | `DOMAIN` + Route 53 A-record; ACM alternative documented. |
| Managed PostgreSQL | Amazon RDS (PostgreSQL 16), Multi-AZ optional. |
| Managed Redis | Amazon ElastiCache (Redis 7); in-host container alternative documented. |
| Monitoring / Metrics | Prometheus scrapes `/metrics`; Grafana 7 dashboards; Alertmanager. |
| Centralized logging | structlog JSON → stdout; container `json-file` driver; request/correlation IDs. |
| Backups | `deploy/backup.sh` (pg_dump + uploads tar) → EBS + optional S3; `restore.sh`. |
| Recovery documentation | `docs/deployment/backups.md` + this phase's `BACKUP_AND_RECOVERY.md`. |
| Load testing | `deploy/loadtest/loadtest.py` + `docker stats` companion (`PHASE_5_LOAD_TEST.md`). |
| Production deployment guide | `docs/deployment/aws.md` + `PHASE_5_REPORT.md`. |
| Health checks | `/health`, `/ready`, `/liveness`, `/version`; per-container healthchecks. |
| Restart policy | `restart: unless-stopped` + systemd `nexusagent.service` on boot. |
| Scaling support | Stateless app tier; promote to ASG+ALB later without code changes. |
| Secrets / env | `.env.production` + AWS Secrets Manager path (`deploy/fetch-secrets.sh`). |
| Persistent storage | EBS volume at `/data` (uploads + backups). |

---

## 6. Portability & Lock-in Posture

- **Deployment unit is Docker.** The backend/frontend/nginx images run unchanged on
  any host with Docker + Compose (local, another cloud, on-prem).
- **State is in managed services, not the host.** Swapping RDS→Cloud SQL or
  ElastiCache→Memorystore is a connection-string change, not a code change.
- **No Terraform/CloudFormation required.** `user-data.sh` is plain cloud-init;
  infra is click-ops or a small Terraform module later. Nothing here *requires* AWS
  primitives to run.
- **Scaling path is standard.** To go multi-node: place N EC2 hosts (or an ASG)
  behind an Application Load Balancer, move Redis to a shared ElastiCache (already
  external), and front RDS with Multi-AZ. No application rewrite — the app tier is
  already stateless (sessions are JWT; uploads are on shared EBS or S3 later).

---

## 7. Resource Sizing (small production, us-east-1)

| Resource | Type | ~Monthly (USD) |
|----------|------|----------------|
| EC2 | t3.medium (2 vCPU / 4 GiB) | ~$30 |
| RDS PostgreSQL 16 | db.t4g.micro + 20 GiB gp3 | ~$13 |
| ElastiCache Redis 7 | cache.t4g.micro | ~$9 |
| EBS (root 8 + data 30 GiB gp3) | gp3 | ~$3 |
| Data transfer (modest) | — | ~$1–5 |
| **Total (ElastiCache)** | | **~$56–60 / mo** |
| *Cheaper alt (on-host redis, t3.small)* | | *~$35–40 / mo* |

(Savings Plans/Reserved cut EC2+RDS ~40–60%.) Full estimate in
`docs/deployment/aws.md` §9.

---

## 8. Decision Summary

- **Platform:** AWS EC2 single-instance, Docker Compose, managed RDS + ElastiCache.
- **Why:** Matches the existing, tested deployment code; satisfies every Phase 5
  success criterion; respects the AWS preference, Docker-unit, no-Kubernetes, and
  portability constraints; scales horizontally later without a rewrite.
- **Rejected in favor of:** ECS/Fargate (orchestration overhead), App Runner/Lightsail/
  Beanstalk (wrong shape / thin controls), and Cloud Run / Container Apps / Railway /
  Render / Fly.io (compelling but not AWS, and no decisive advantage this phase).

See `PHASE_5_REPORT.md` for the full infrastructure/deployment/monitoring/security/
performance roll-up, and `docs/deployment/aws.md` for the step-by-step walkthrough.
