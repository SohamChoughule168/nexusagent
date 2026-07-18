# AWS Deployment

NexusAgent AI — deploy to AWS with Docker containers on a single EC2 instance
(Milestone 7, Phase 4).

This document covers the **AWS production deployment**: EC2, Amazon RDS for
PostgreSQL, Amazon ElastiCache for Redis, an EBS volume for uploaded documents,
the nginx reverse proxy, deployment scripts, health/rollback, and a cost
estimate. It assumes the packaging from
[`production.md`](production.md) (container images, nginx, TLS prep) is in place.

> **Scope:** single-instance production only. This phase explicitly does **not**
> cover Kubernetes, Helm, Terraform, Auto Scaling, Load Balancers, multi-region,
> or Blue/Green. Those are out of scope by design.

---

## 1. Architecture

One EC2 instance runs the application containers; stateful services are managed
AWS offerings. The instance security group only needs to open **22** (or SSM),
**80**, and **443**.

```
                          ┌──────────────────────────────────────────────────┐
   Browser / API client ─▶│  EC2 (Amazon Linux / Ubuntu)  sg: nexusagent-ec2  │
   (https://your-domain)  │                                                    │
                          │   ┌────────────────────────────────────────────┐  │
                          │   │  nginx :80/:443  (public entrypoint only)  │  │
                          │   │   /api/*   → backend:8000                   │  │
                          │   │   /health  → backend:8000/health            │  │
                          │   │   /        → frontend:3000                  │  │
                          │   └───────┬───────────────────┬────────────────┘  │
                          │           │ (internal net)    │                    │
                          │   ┌───────▼──────┐   ┌────────▼─────────┐          │
                          │   │ backend :8000│   │ frontend :3000   │          │
                          │   │ (FastAPI)    │   │ (Next.js)        │          │
                          │   └───┬───────┬──┘   └──────────────────┘          │
                          │       │       │                                    │
                          │       │       └── uploads ─▶ /data (EBS volume)   │
                          │       │                                            │
                          └───────┼────────────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────────────┐
              │                   │                            │
      ┌───────▼────────┐  ┌───────▼─────────┐         ┌────────▼─────────┐
      │ RDS PostgreSQL │  │ ElastiCache     │         │ (optional) S3    │
      │ (sg: rds,      │  │ Redis           │         │ uploads bucket   │
      │  allow ec2)    │  │ (sg: redis,     │         │ (future; app     │
      │               │  │  allow ec2)      │         │  uses local EBS) │
      └────────────────┘  └─────────────────┘         └──────────────────┘
```

| Component        | AWS service                         | Notes                                   |
|------------------|-------------------------------------|-----------------------------------------|
| Compute          | EC2 (t3.small / t3.medium)          | Docker + Compose; one host.             |
| Reverse proxy    | nginx container (on EC2)            | Sole public entrypoint (80/443).        |
| App / API        | backend container (FastAPI)         | Internal port 8000, not published.      |
| Web UI           | frontend container (Next.js)        | Internal port 3000, not published.      |
| Database         | Amazon RDS for PostgreSQL 16        | Managed, Multi-AZ optional.             |
| Cache / broker   | Amazon ElastiCache (Redis 7)        | Or a redis container on the host.       |
| Document storage | EBS volume mounted at `/data`       | `UPLOAD_STORAGE_DIR=/data/nexusagent/uploads`. |
| Secrets          | `.env.production` on host           | AWS Secrets Manager is a documented upgrade. |
| IAM              | EC2 instance role                   | Optional; SSM + CloudWatch/Loptional S3/ECR. See [aws-iam.md](aws-iam.md). |
| DNS / TLS        | Route 53 + ACM (or certbot)         | Terminate TLS at nginx.                 |

---

## 2. Required AWS Resources

| Resource                        | Recommendation (small prod)            | Purpose                          |
|---------------------------------|----------------------------------------|----------------------------------|
| VPC + public subnet             | Default VPC is fine for MVP            | Network isolation                |
| EC2 instance                    | t3.medium (2 vCPU / 4 GiB)             | Runs the containers              |
| EBS volume (data)               | gp3, 30 GiB, attached as `/dev/nvme1n1`| Uploads + backups (persistent)   |
| RDS PostgreSQL 16               | db.t4g.micro, 20 GiB gp3, Single-AZ    | Application database             |
| ElastiCache Redis 7             | cache.t4g.micro                        | Cache + Celery broker/results    |
| Security group `nexusagent-ec2` | allow 22/80/443 from 0.0.0.0/0 (or your IP) | Public ingress             |
| Security group `nexusagent-rds` | allow 5432 from `nexusagent-ec2`       | DB access                        |
| Security group `nexusagent-redis`| allow 6379 from `nexusagent-ec2`     | Redis access                     |
| IAM instance role (optional)    | policy in `deploy/iam-policy.json`     | SSM / CloudWatch / optional S3/ECR |
| Elastic IP (optional)           | one attached to the instance           | Stable public IP                 |
| Route 53 hosted zone + ACM cert | your domain + public cert              | TLS termination at nginx         |

> **Cheaper alternative:** run Redis **inside a container on the EC2 host**
> (re-add a `redis` service to the compose file) and use a **t3.small** instead
> of t3.medium. This drops the ElastiCache line item (~$9/mo) at the cost of
> managing Redis yourself and tying it to the instance lifecycle.

---

## 3. Deployment Steps

### 3.1 Launch the EC2 instance
1. Launch an Ubuntu 22.04/24.04 LTS instance (t3.medium) in your VPC/subnet.
2. Attach the `nexusagent-ec2` security group (22/80/443).
3. Attach a second EBS volume (gp3, 30 GiB) for `/data`.
4. (Optional) Attach the instance role from `deploy/iam-policy.json`.
5. Paste `deploy/user-data.sh` as **user data** (cloud-init). Adjust
   `DATA_DEV` if your instance is Xen-based (`/dev/xvdf`) rather than Nitro
   (`/dev/nvme1n1`). Set `REPO_URL` to your fork.

Wait for the instance to reach "running" and the user-data script to finish
(check `/var/log/cloud-init-output.log`).

### 3.2 Configure environment
SSH in as `deploy` (or use SSM Session Manager):

```bash
cd /opt/nexusagent
cp env.production.example .env.production
vi .env.production          # fill in RDS_ENDPOINT, ELASTICACHE_ENDPOINT, secrets, domain
```

See [aws-secrets.md](aws-secrets.md) for how to generate and store the secrets,
and the inline comments in `env.production.example` for every variable.

### 3.3 Initial deploy
```bash
./deploy/init-deploy.sh
```

This builds the images, starts the containers, applies Alembic migrations
against RDS, and waits for the backend health endpoint. Open
`http://<ec2-public-dns>/` to verify.

### 3.4 DNS + TLS (production)
1. Point your domain's A record at the instance (Elastic IP) via Route 53.
2. Obtain a cert (ACM + import into the host, or `certbot` on the host) and
   place it at `nginx/certs/fullchain.pem` + `nginx/certs/privkey.pem`.
3. In `docker-compose.aws.yml`, uncomment the `443` port and the certs volume,
   and mount `nginx/tls.conf.example` as the active config (see
   [production.md §5](production.md)). Recreate nginx:
   ```bash
   docker compose -f docker-compose.aws.yml --env-file .env.production up -d nginx
   ```
4. Set `NEXT_PUBLIC_API_BASE_URL` and `BACKEND_CORS_ORIGINS` to your `https://`
   origin and rebuild the frontend (`deploy/update-containers.sh`).

---

## 4. RDS PostgreSQL Configuration

- **Engine:** PostgreSQL 16 (match the container image `postgres:16-alpine`).
- **Instance class:** `db.t4g.micro` (burstable, Graviton) for MVP.
- **Storage:** gp3, 20 GiB (auto-scaling optional).
- **Multi-AZ:** off for MVP; enable for higher availability (costs ~2x).
- **Credentials:** create the `nexusagent` user/db; put the password in
  `.env.production` as `POSTGRES_PASSWORD`. Generate with `openssl rand -base64 24`.
- **Networking:** place RDS in a private subnet; security group `nexusagent-rds`
  allows **5432 inbound only from `nexusagent-ec2`**.
- **Backups:** enable automated snapshots (e.g. 7-day retention).
- **Connection:** the backend uses the **synchronous** `psycopg2` driver
  (`postgresql+psycopg2://...@${RDS_ENDPOINT}:5432/...`) — set automatically in
  `docker-compose.aws.yml`. Alembic normalizes async→sync for migrations.

> **IAM DB auth (optional):** instead of a password, enable IAM database
> authentication and grant `rds-db:connect` in the instance role. Out of scope
> for the MVP; documented for hardening.

---

## 5. Redis (ElastiCache)

- **Engine:** Redis 7 (matches `redis:7-alpine`).
- **Node type:** `cache.t4g.micro` (the smallest Graviton node).
- **Deployment:** cache cluster (no replication needed for MVP) in a private
  subnet; security group `nexusagent-redis` allows **6379 inbound only from
  `nexusagent-ec2`**.
- **Usage:** `REDIS_URL` (cache), `CELERY_BROKER_URL` (db 1), `CELERY_RESULT_BACKEND`
  (db 2) all point at `${ELASTICACHE_ENDPOINT}:6379`.
- **No auth:** for MVP, leave Redis unauthenticated but network-isolated behind
  the security group. Add `requirepass` + `REDIS_PASSWORD` if you expose it
  further (not needed here).

### Redis options
- **Option A (recommended):** ElastiCache as above — managed, durable, separate
  from the instance lifecycle.
- **Option B (cheaper):** run Redis as a container on the EC2 host. Re-add a
  `redis` service (copy it from `docker-compose.yml`), set
  `ELASTICACHE_ENDPOINT=redis` in `.env.production`, and remove the external
  dependency. Trade-off: Redis state is lost on instance failure unless you
  mount a volume and accept recovery from RDB/AOF.

---

## 6. S3 for Uploaded Documents

The application's storage abstraction writes uploaded documents to a **local
directory** (`UPLOAD_STORAGE_DIR`, default `storage/uploads`). In this AWS
deployment that directory is bound to the **EBS volume** at
`/data/nexusagent/uploads`, so uploads persist independently of container and
image lifecycles. No application code change is required.

A managed **S3 bucket** is a natural future upgrade (durability, decoupling from
the instance) but requires the app to gain an S3-aware storage backend — that
is out of scope for this phase (we do not modify application code). When you
adopt S3 later:
- Create `nexusagent-uploads-prod` (private, versioned, lifecycle to Glacier).
- Grant the instance role `s3:GetObject/PutObject/DeleteObject/ListBucket`
  (see `deploy/iam-policy.json` > `S3Uploads*` statements, currently optional).
- Point the storage backend at the bucket (application change, future milestone).

Until then, back up `/data/nexusagent/uploads` with `deploy/backup.sh`.

---

## 7. Health, Startup & Recovery

### Health endpoints
| Endpoint            | Served by        | Meaning                                  |
|---------------------|------------------|------------------------------------------|
| `GET /health`       | backend (FastAPI)| `{ "status": "healthy" }` — liveness.    |
| `GET /`             | backend / frontend | version / app shell.                   |
| `nginx /health`     | nginx → backend  | backend health through the proxy.        |

Container healthchecks: backend `curl /health`; frontend fetches `/`; nginx
`wget /health`. All use `restart: unless-stopped`.

### Startup sequence
1. EC2 boots; `user-data.sh` mounts EBS at `/data`, installs Docker.
2. `init-deploy.sh` builds images, then `docker compose up -d`.
3. `db-migrate.sh` runs `alembic upgrade head` against RDS.
4. `healthcheck.sh` polls backend `/health` until healthy.
5. nginx depends on backend+frontend `service_healthy`, then proxies traffic.

### Failure recovery
- **Container crash:** `restart: unless-stopped` brings it back; healthchecks
  gate nginx traffic.
- **Backend unhealthy after deploy:** `deploy/rolling-restart.sh backend`.
- **RDS unreachable:** check the `nexusagent-rds` security group and that the
  endpoint in `.env.production` is correct; the backend will keep restarting
  until the DB is reachable (DB connections are lazy; `/health` stays healthy).
- **Lost uploads volume:** restore from `deploy/restore.sh` (uploads tarball) or
  the S3 backup if configured.
- **Host failure:** relaunch the instance from the same AMI/snapshot, re-run
  `init-deploy.sh`; RDS/ElastiCache persist independently.

### Rollback procedure
Images are built from git, so a rollback is a redeploy of the last-good commit:

```bash
cd /opt/nexusagent
git fetch --all
git checkout <last-good-commit>        # or: git pull; git reset --hard <sha>
./deploy/update-containers.sh          # rebuild + migrate + recreate
```

If a migration is not backward-compatible, restore the DB from the pre-deploy
backup first (`deploy/restore.sh <ts>`), then redeploy the old code. Because
migrations target shared RDS, **always back up before `update-containers.sh`**.

---

## 8. Upgrade Process

Routine upgrade = ship new code:

```bash
./deploy/update-containers.sh           # pull -> build -> migrate -> recreate -> health-gate
```

Pre-upgrade checklist:
1. `./deploy/backup.sh` (capture DB + uploads).
2. Note the current commit SHA (`git rev-parse HEAD`) for rollback.
3. Review the new migration's compatibility with the running version.

Post-upgrade:
1. `curl -fsS http://<host>/health` returns `{"status":"healthy"}`.
2. `docker compose -f docker-compose.aws.yml --env-file .env.production ps`
   shows all services `healthy`.

---

## 9. Cost Estimate (small production, us-east-1, on-demand, single-AZ)

| Resource                 | Type              | ~Monthly (USD) |
|--------------------------|-------------------|----------------|
| EC2                      | t3.medium         | ~$30           |
| RDS PostgreSQL           | db.t4g.micro + 20GiB gp3 | ~$13              |
| ElastiCache Redis        | cache.t4g.micro   | ~$9            |
| EBS (root 8GiB + data 30GiB gp3) | gp3   | ~$3            |
| Data transfer (modest)   | —                 | ~$1–5          |
| Elastic IP (attached)    | —                 | ~$0 (free when attached) |
| **Total (ElastiCache)**  |                   | **~$56–60**    |
| **Cheaper (on-host redis, t3.small)** |     | **~$35–40**    |

Estimates only; vary by region, instance purchasing option (Savings Plans/
Reserved cut EC2/RDS ~40–60%), and traffic. Not including Route 53 / ACM
(nominal) or a NAT gateway (not needed if RDS/ElastiCache are publicly
accessible or in the same VPC with correct routing).

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `docker compose ... config` fails: `JWT_SECRET_KEY` empty | Required var missing in `.env.production`. | Fill all `replace-with-*` values; see [aws-secrets.md](aws-secrets.md). |
| Backend container restart loop | RDS endpoint wrong / SG blocks 5432 / bad password. | Verify `RDS_ENDPOINT`, `nexusagent-rds` SG, `POSTGRES_PASSWORD`. |
| Backend healthy but 502 at `/` | Frontend not healthy, or nginx config out of date. | `docker compose ps`; `docker compose logs nginx`. |
| `pg_dump`/restore connection refused | SG blocks 5432 from host, or wrong endpoint. | Check `nexusagent-rds` SG includes the EC2 SG; verify `RDS_ENDPOINT`. |
| Uploads lost after recreate | Bind mount missing / wrong path. | Ensure `/data/nexusagent/uploads` exists and is in the compose `volumes`. |
| Redis connection errors | ElastiCache endpoint wrong / SG blocks 6379. | Verify `ELASTICACHE_ENDPOINT`, `nexusagent-redis` SG. |
| TLS not served | Certs not mounted / config not switched. | Mount `nginx/certs`, activate `tls.conf.example`, `up -d nginx`. |
| Migrations fail / version drift | Ran `update-containers.sh` without backup. | `deploy/restore.sh <ts>` then redeploy last-good commit. |

### Useful commands
```bash
docker compose -f docker-compose.aws.yml --env-file .env.production config
docker compose -f docker-compose.aws.yml --env-file .env.production ps
docker compose -f docker-compose.aws.yml --env-file .env.production logs -f backend
docker compose -f docker-compose.aws.yml --env-file .env.production exec -T backend alembic current
curl -fsS http://<host>/health
```

---

## 11. References
- [production.md](production.md) — packaging, nginx, TLS prep (Phase 3).
- [aws-secrets.md](aws-secrets.md) — secrets generation & storage.
- [aws-iam.md](aws-iam.md) — instance-role IAM policy.
- `deploy/` — all deployment scripts + `iam-policy.json`.
- `env.production.example` — production environment template.
- `docker-compose.aws.yml` — this deployment's compose file.
