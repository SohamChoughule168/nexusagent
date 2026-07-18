# Secrets Management

How NexusAgent AI generates, stores, rotates, backs up, and recovers the
secrets it depends on (Milestone 7, Phase 6). Companion to
[`aws-secrets.md`](aws-secrets.md) (the AWS-specific procedure).

---

## 1. Secrets the application uses

| Secret | Used for | Generator | Required in prod? |
|--------|----------|-----------|-------------------|
| `JWT_SECRET_KEY` | Signing access tokens | `openssl rand -hex 32` | **Yes** |
| `JWT_REFRESH_SECRET_KEY` | Signing refresh tokens | `openssl rand -hex 32` (different) | **Yes** |
| `SECURITY_PASSWORD_SALT` | Password-hash salt | `openssl rand -hex 16` | **Yes** |
| `POSTGRES_PASSWORD` | RDS / Postgres login | `openssl rand -base64 24` | **Yes** |
| `OPENROUTER_API_KEY` | LLM provider | OpenRouter dashboard | No (offline fallback) |
| `OPENAI_API_KEY` | LLM provider (opt.) | OpenAI dashboard | No |
| `ANTHROPIC_API_KEY` | LLM provider (opt.) | Anthropic console | No |

Non-secret, environment-specific values (not secrets): `RDS_ENDPOINT`,
`ELASTICACHE_ENDPOINT`, `BACKEND_CORS_ORIGINS`, `NEXT_PUBLIC_API_BASE_URL`,
`APP_VERSION`.

> The application **never logs secret values**. `config.py` derives required
> config and warns (does not raise) on the insecure `change-me-in-production`
> defaults. Keep that guard; do not weaken it.

---

## 2. Generation

Run these on a **trusted, offline** machine (not the build host, not committed):

```bash
openssl rand -hex 32        # JWT_SECRET_KEY
openssl rand -hex 32        # JWT_REFRESH_SECRET_KEY  (use a DIFFERENT value)
openssl rand -hex 16        # SECURITY_PASSWORD_SALT
openssl rand -base64 24     # POSTGRES_PASSWORD
```

Paste each into `.env.production` (AWS) or `.env` (local), replacing the
`replace-with-*` placeholders from the `*.example` templates. Never reuse the
`change-me-in-production` defaults shipped in the local compose file.

API keys for LLM providers come from the provider dashboards. Treat them like
the DB/JWT secrets — they grant metered spend.

---

## 3. Storage

### Local / single-host (MVP)
- Secrets live in `.env.production` on the EC2 host, **gitignored**
  (`.gitignore` excludes `.env` and `.env.*`).
- File mode `600`, owned by the deploy user:
  ```bash
  chmod 600 /opt/nexusagent/.env.production
  ```
- They are supplied to the container at runtime via `--env-file` — **never**
  baked into the image.

### AWS Secrets Manager (recommended)
Store each secret as a SecureString or as one JSON secret, then render
`.env.production` from it at deploy time (see [`aws-secrets.md`](aws-secrets.md)
§3). Grant the instance role `secretsmanager:GetSecretValue` scoped to
`arn:aws:secretsmanager:*:*:secret:nexusagent/prod*`. This keeps plaintext
secrets off the filesystem between deploys.

### What NOT to do
- Never commit real secrets (the `.gitignore` blocks `.env*`, but verify before
  `git add`).
- Never put JWT/DB secrets in the image (they arrive via env at runtime).
- Never store `.env.production` inside the EBS backup tarball unencrypted.

---

## 4. Rotation

Rotation cadence (baseline): **JWT keys every 90 days** (or on suspected
exposure), **DB password every 180 days** (or on suspected exposure), **LLM API
keys on provider compromise**.

- **JWT keys** — changing them invalidates all issued tokens (users re-login).
  Rotate during a maintenance window: update `JWT_SECRET_KEY` /
  `JWT_REFRESH_SECRET_KEY` in the secret store, then
  `deploy/rolling-restart.sh backend`. Consider a dual-key (sign with new,
  accept both) rollout for zero-downtime rotation in a later phase.
- **DB password** — rotate in RDS first, then update `POSTGRES_PASSWORD` and
  restart the backend so it picks up the new connection string.
- **LLM API keys** — update the secret and restart the backend. No token impact.

---

## 5. Backup

- Back up the secret *values* (not the running container):
  - AWS Secrets Manager versions are retained by the service.
  - For local `.env.production`, back it up to a password manager or an
    encrypted store (e.g. `gpg -e .env.production`), **not** the unencrypted EBS
    tarball.
- Document which secret maps to which generator (§2) so a total loss is
  recoverable without guessing.

---

## 6. Recovery

- **Lost `.env.production`** — re-render from AWS Secrets Manager, or regenerate
  all four base secrets (JWT ×2, salt, DB password) using §2 and re-apply.
  Regenerating JWT keys logs every user out; regenerating the DB password
  requires a matching RDS rotation.
- **Suspected JWT key compromise** — rotate both JWT keys immediately (§4) and
  restart.
- **Suspected DB password compromise** — rotate in RDS, update the secret,
  restart backend, and review RDS logs for anomalous connections.
- Keep a printed/Offline-password-manager copy of the generators so a complete
  secrets loss is reconstructable.

---

## 7. Local development guidance

- Copy `.env.example` → `.env` and fill in throwaway values. Local defaults in
  `docker-compose.yml` let the stack run with an empty `.env` for a quick demo,
  but **production values must never be the `change-me-in-production` defaults**.
- Use low-entropy, obviously-fake secrets locally (e.g. `JWT_SECRET_KEY=dev-only`)
  so they are never mistaken for production secrets.
- Never reuse a production secret in a local `.env`.
