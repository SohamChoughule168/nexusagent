#!/bin/bash
# NexusAgent AI - EC2 bootstrap (cloud-init / user-data)
#
# Runs ONCE at instance first launch. It:
#   1. Installs Docker Engine + Compose plugin and postgresql-client.
#   2. Creates a non-root `deploy` user with docker + passwordless sudo.
#   3. Formats & mounts the attached EBS data volume at /data (uploads/backups).
#   4. Clones the application to /opt/nexusagent.
#
# After launch: SSH in as `deploy`, copy env.production, then run
# `deploy/init-deploy.sh`. See docs/deployment/aws.md for the full walkthrough.
#
# NOTE on EBS device names:
#   * Xen-based instances:           /dev/xvdf
#   * Nitro-based instances (newer): /dev/nvme1n1  (the data volume)
# Adjust DATA_DEV below to match your instance type / volume attachment.

set -euo pipefail

# ---- Tunables (override via Terraform/console user-data if desired) ----
REPO_URL="${REPO_URL:-https://github.com/your-org/nexusagent.git}"
DATA_DEV="${DATA_DEV:-/dev/nvme1n1}"
DATA_MNT="/data"

export DEBIAN_FRONTEND=noninteractive

echo "[bootstrap] starting at $(date -u)"

# ---- System packages ----
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git gnupg lsb-release \
  postgresql-client cron awscli

# ---- Docker Engine + Compose plugin ----
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y --no-install-recommends \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# ---- Deploy user ----
id -u deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
usermod -aG docker deploy
# Passwordless sudo for deployment scripts. Lock this down per your policy;
# considder removing NOPASSWD and using SSM Session Manager instead of SSH.
echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
chmod 0440 /etc/sudoers.d/deploy

# ---- Mount EBS data volume at /data ----
mkdir -p "$DATA_MNT"
if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
  echo "[bootstrap] formatting $DATA_DEV as ext4"
  mkfs -t ext4 "$DATA_DEV"
fi
if ! mountpoint -q "$DATA_MNT"; then
  echo "[bootstrap] mounting $DATA_DEV -> $DATA_MNT"
  mount "$DATA_DEV" "$DATA_MNT"
fi
grep -q "$DATA_MNT " /etc/fstab || \
  echo "$DATA_DEV $DATA_MNT ext4 defaults,nofail 0 2" >> /etc/fstab

# Uploads must be writable by the backend's non-root user (uid/gid 1001).
install -d -o 1001 -g 1001 "$DATA_MNT/nexusagent/uploads"
install -d -o 1001 -g 1001 "$DATA_MNT/nexusagent/backups"

# ---- Clone application ----
APP_DIR="/opt/nexusagent"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
chown -R deploy:deploy "$APP_DIR"

systemctl enable --now docker

echo "[bootstrap] complete at $(date -u)."
echo "[bootstrap] Next: ssh deploy@<public-ip>, then run: cd /opt/nexusagent && deploy/init-deploy.sh"
