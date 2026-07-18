#!/usr/bin/env bash
# NexusAgent AI - restore (RDS database + uploaded documents)
#
# Restores a previously created backup set identified by its timestamp.
# Example:
#   deploy/restore.sh 20260718T123000Z
# matches:
#   /data/nexusagent/backups/nexusagent-db-20260718T123000Z.sql.gz
#   /data/nexusagent/backups/nexusagent-uploads-20260718T123000Z.tar.gz
#
# DESTRUCTIVE: overwrites the target database and uploads. Requires an explicit
# "RESTORE" confirmation typed at the prompt.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-/data/nexusagent/backups}"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <timestamp>   (timestamp from a nexusagent-db-<ts>.sql.gz backup)" >&2
  echo "Available backups:" >&2
  ls -1 "$BACKUP_DIR"/nexusagent-db-*.sql.gz 2>/dev/null \
    | sed 's#.*/nexusagent-db-##; s#\.sql\.gz##' >&2 || true
  exit 1
fi

TS="$1"
DB_DUMP="$BACKUP_DIR/nexusagent-db-$TS.sql.gz"
UPLOADS_TAR="$BACKUP_DIR/nexusagent-uploads-$TS.tar.gz"

[ -f "$DB_DUMP" ] || { echo "ERROR: $DB_DUMP not found" >&2; exit 1; }

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found." >&2
  exit 1
fi
set -a; . ./"$ENV_FILE"; set +a

echo "WARNING: this will OVERWRITE database '$POSTGRES_DB' on $RDS_ENDPOINT" >&2
echo "         and replace /data/nexusagent/uploads." >&2
read -r -p "Type the word RESTORE to continue: " CONFIRM
if [ "${CONFIRM:-}" != "RESTORE" ]; then
  echo "Aborted."
  exit 1
fi

echo "==> Restoring database from $DB_DUMP"
gunzip -c "$DB_DUMP" \
  | PGPASSWORD="$POSTGRES_PASSWORD" psql \
      -h "$RDS_ENDPOINT" -p "${RDS_PORT:-5432}" \
      -U "$POSTGRES_USER" -d "$POSTGRES_DB"

if [ -f "$UPLOADS_TAR" ]; then
  echo "==> Restoring uploads from $UPLOADS_TAR"
  sudo install -d -o 1001 -g 1001 /data/nexusagent/uploads
  tar -xzf "$UPLOADS_TAR" -C /data/nexusagent
  sudo chown -R 1001:1001 /data/nexusagent/uploads
else
  echo "==> No uploads tarball for $TS; skipping uploads restore." >&2
fi

echo "==> Restore complete. Reload the backend to pick up changes:"
echo "    deploy/rolling-restart.sh backend"
