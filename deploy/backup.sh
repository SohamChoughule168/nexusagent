#!/usr/bin/env bash
# NexusAgent AI - backup (RDS database + uploaded documents)
#
# Produces two timestamped, gzipped archives under the backup directory on the
# EBS volume (/data/nexusagent/backups by default):
#   * nexusagent-db-<ts>.sql.gz       - pg_dump of the RDS PostgreSQL database
#   * nexusagent-uploads-<ts>.tar.gz  - tar of /data/nexusagent/uploads
# Old backups beyond RETENTION_DAYS are pruned.
#
# Requires `pg_dump` (postgresql-client, installed by user-data.sh) and network
# access from the EC2 host to the RDS endpoint (security group).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-/data/nexusagent/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found." >&2
  exit 1
fi

# Load DB connection vars (no unquoted secrets printed).
set -a; . ./"$ENV_FILE"; set +a

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DB_DUMP="$BACKUP_DIR/nexusagent-db-$TS.sql.gz"
UPLOADS_TAR="$BACKUP_DIR/nexusagent-uploads-$TS.tar.gz"

echo "==> Dumping RDS database -> $DB_DUMP"
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -h "$RDS_ENDPOINT" -p "${RDS_PORT:-5432}" \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --no-owner --clean --if-exists --verbose \
  | gzip > "$DB_DUMP"

echo "==> Archiving uploads -> $UPLOADS_TAR"
tar -czf "$UPLOADS_TAR" -C /data/nexusagent uploads

echo "==> Backup artifacts:"
ls -lh "$DB_DUMP" "$UPLOADS_TAR"

echo "==> Pruning backups older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -type f -name 'nexusagent-*' -mtime +"$RETENTION_DAYS" -delete

# Off-host copy hint (optional): sync to S3 if a bucket is configured.
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  echo "==> Syncing backups to s3://$BACKUP_S3_BUCKET"
  aws s3 sync "$BACKUP_DIR" "s3://$BACKUP_S3_BUCKET/nexusagent-backups/"
fi

echo "==> Backup complete."
