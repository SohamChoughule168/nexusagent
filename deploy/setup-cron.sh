#!/usr/bin/env bash
# NexusAgent AI - install cron jobs for backup + certificate renewal.
#
# Idempotent: it rebuilds the crontab, removing any prior nexusagent-managed
# lines before re-adding them, so repeated runs are safe. Requires the
# deploy user's crontab (run as the `deploy` user, not root, ideally).
#
# Jobs installed:
#   * Nightly 03:00  -> deploy/backup.sh            (DB + uploads; prune + S3)
#   * 02:23 & 14:23  -> deploy/renew-cert.sh        (Let's Encrypt renewal)
#
# All output is appended to /data/nexusagent/backups/cron.log.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="/data/nexusagent/backups/cron.log"

mkdir -p "$(dirname "$LOG")"

# Strip any existing nexusagent-managed lines, then add the current set.
NEW_CRON="$(crontab -l 2>/dev/null | grep -v '# nexusagent-' || true)"

NEW_CRON="$NEW_CRON
0 3 * * * $REPO_ROOT/deploy/backup.sh >> $LOG 2>&1 # nexusagent-backup
23 2,14 * * * $REPO_ROOT/deploy/renew-cert.sh >> $LOG 2>&1 # nexusagent-certbot"

printf '%s\n' "$NEW_CRON" | crontab -

echo "==> Cron installed:"
crontab -l | grep '# nexusagent-'
echo "    Logs: $LOG"
