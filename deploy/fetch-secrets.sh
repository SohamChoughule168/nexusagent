#!/usr/bin/env bash
# NexusAgent AI - render .env.production from an AWS Secrets Manager secret.
#
# Stores secrets outside the host filesystem (Option B in
# docs/deployment/aws-secrets.md). The secret must be a JSON object whose
# key/value pairs map 1:1 to the .env.production variables (e.g.
# {"POSTGRES_PASSWORD":"...","JWT_SECRET_KEY":"...", ...}). AWS Secrets Manager
# returns the JSON as a single string, which is exactly the format
# docker-compose reads via --env-file.
#
# Requires:
#   * aws cli on PATH (installed by user-data.sh) and, on EC2, an instance role
#     with secretsmanager:GetSecretValue on the secret ARN (see iam-policy.json
#     or aws-secrets.md).
#   * AWS_SECRETS_MANAGER_SECRET_NAME set in the environment or .env.production.
#
# Usage: AWS_SECRETS_MANAGER_SECRET_NAME=nexusagent/prod ./deploy/fetch-secrets.sh
#   -> writes .env.production (mode 600) at the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"

# Allow the secret name to come from a sibling .env.production if present.
[ -f "$ENV_FILE" ] && { set -a; . ./"$ENV_FILE"; set +a; }

SECRET_NAME="${AWS_SECRETS_MANAGER_SECRET_NAME:?Set AWS_SECRETS_MANAGER_SECRET_NAME (e.g. nexusagent/prod)}"
REGION="${AWS_REGION:-us-east-1}"
OUT="${1:-$ENV_FILE}"

echo "==> Fetching secret '$SECRET_NAME' from AWS Secrets Manager ($REGION)"
aws secretsmanager get-secret-value \
  --secret-id "$SECRET_NAME" \
  --region "$REGION" \
  --query SecretString --output text > "$OUT"

chmod 600 "$OUT"
echo "==> Wrote $OUT (mode 600)."
