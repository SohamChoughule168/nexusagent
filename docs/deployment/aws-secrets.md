# AWS Secrets Documentation

How to generate, store, and rotate the secrets used by the NexusAgent AWS
deployment (Milestone 7, Phase 4). Companion to
[`aws.md`](aws.md).

---

## 1. Secrets in this deployment

All secrets live in `.env.production` on the EC2 host (gitignored). The file is
read by `docker-compose.aws.yml` via `--env-file .env.production`. Required
secrets have **no default** in the compose file, so deployment fails fast if
they are missing or left as placeholders.

| Secret                  | Where used            | How to generate                              |
|-------------------------|-----------------------|----------------------------------------------|
| `POSTGRES_PASSWORD`     | RDS login             | `openssl rand -base64 24`                    |
| `JWT_SECRET_KEY`        | Access-token signing  | `openssl rand -hex 32`                       |
| `JWT_REFRESH_SECRET_KEY`| Refresh-token signing | `openssl rand -hex 32` (different value)    |
| `SECURITY_PASSWORD_SALT`| Password hashing salt | `openssl rand -hex 16`                       |
| `OPENROUTER_API_KEY`    | LLM provider          | From OpenRouter dashboard (or leave blank)   |
| `OPENAI_API_KEY`        | LLM provider (opt.)   | From OpenAI (or leave blank)                 |
| `ANTHROPIC_API_KEY`     | LLM provider (opt.)   | From Anthropic (or leave blank)              |

Non-secret but environment-specific values: `RDS_ENDPOINT`, `RDS_PORT`,
`ELASTICACHE_ENDPOINT`, `REDIS_PORT`, `BACKEND_CORS_ORIGINS`,
`NEXT_PUBLIC_API_BASE_URL`, `APP_VERSION`.

---

## 2. Generating secrets

Run these on a trusted machine (not committed anywhere):

```bash
openssl rand -base64 24     # POSTGRES_PASSWORD
openssl rand -hex 32        # JWT_SECRET_KEY
openssl rand -hex 32        # JWT_REFRESH_SECRET_KEY
openssl rand -hex 16        # SECURITY_PASSWORD_SALT
```

Paste each into `.env.production`, replacing the `replace-with-*` placeholders
from `env.production.example`.

---

## 3. Storage options

### Option A — local `.env.production` (MVP, default)
- File lives at the repo root on the EC2 host, mode `600`, owned by `deploy`.
- Gitignored (`.gitignore` excludes `.env` and `.env.*`).
- Back it up to a password manager or AWS Secrets Manager — **not** to the EBS
  volume tarball (which is not encrypted at rest by default).

```bash
chmod 600 /opt/nexusagent/.env.production
```

### Option B — AWS Secrets Manager (recommended hardening)
Store each secret as a SecureString (or one JSON secret) and export into the
env at deploy time. Example using the AWS CLI:

```bash
# Store
aws secretsmanager create-secret --name nexusagent/prod \
  --secret-string file:///tmp/nexusagent-secrets.json

# At deploy time, render .env.production from the secret:
aws secretsmanager get-secret-value --secret-id nexusagent/prod \
  --query SecretString --output text > /opt/nexusagent/.env.production
chmod 600 /opt/nexusagent/.env.production
```

Grant the instance role `secretsmanager:GetSecretValue` on
`arn:aws:secretsmanager:*:*:secret:nexusagent/prod*`. This keeps plaintext
secrets out of the filesystem between deploys.

> Do **not** commit `.env.production` or any real secret to git. The repo only
> ships `env.production.example` (placeholders) — never the real values.

---

## 4. What NOT to do
- Never commit real secrets (the `.gitignore` blocks `.env*`, but double-check
  before `git add`).
- Don't reuse the `change-me-in-production` defaults from the local compose.
- Don't put the JWT/DB secrets in the image (they come from the env file at
  runtime, not baked in).
- Don't store `.env.production` inside the EBS backup tarball unencrypted.

---

## 5. Rotation
- **JWT keys:** changing them invalidates all existing tokens (users re-login).
  Rotate during a maintenance window; update `.env.production` and run
  `deploy/rolling-restart.sh backend`.
- **DB password:** rotate in RDS, update `POSTGRES_PASSWORD` in
  `.env.production`, then restart backend.
- **API keys:** update and restart backend; no token impact.

See [`aws.md`](aws.md) §7 (rollback) and §8 (upgrade) for the surrounding
procedures.
