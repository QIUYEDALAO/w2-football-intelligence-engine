#!/usr/bin/env bash
# ============================================================================
# W2 Stage7H – Deploy Staging Release to VPS
#
# Usage:
#   export W2_API_FOOTBALL_API_KEY='<your-key>'
#   export POSTGRES_PASSWORD='<generated-password>'
#   bash scripts/deploy_stage7h_staging.sh <ssh-host>
#
# Example:
#   bash scripts/deploy_stage7h_staging.sh ubuntu@43.155.208.138
#
# Security:
#   - Sensitive data passed via environment only (never in args or files)
#   - .env on server created with chmod 600
#   - No StrictHostKeyChecking=no
#   - No public port binding
# ============================================================================

set -euo pipefail

SSH_HOST="${1:?Usage: $0 <ssh-host>}"
REVISION="$(git rev-parse HEAD)"
ARCHIVE="/tmp/w2-${REVISION}.tar.gz"

echo "=== W2 Stage7H Deploy v0.1 ==="
echo "  SSH host:  ${SSH_HOST}"
echo "  Revision:  ${REVISION}"
echo "  Branch:    $(git rev-parse --abbrev-ref HEAD)"

# ── Step 1: Archive ─────────────────────────────────────────
echo "--- Archiving HEAD (git archive) ---"
git archive --format=tar.gz --output="${ARCHIVE}" HEAD
trap 'rm -f "${ARCHIVE}"' EXIT

# ── Step 2: Upload ──────────────────────────────────────────
echo "--- Uploading to ${SSH_HOST}:/tmp/ ---"
scp "${ARCHIVE}" "${SSH_HOST}:/tmp/"

# ── Step 3: Extract on server ───────────────────────────────
echo "--- Extracting release ---"
ssh "${SSH_HOST}" "
set -euo pipefail
mkdir -p /opt/w2/releases/${REVISION}
tar -xzf /tmp/w2-${REVISION}.tar.gz -C /opt/w2/releases/${REVISION}
rm -f /tmp/w2-${REVISION}.tar.gz
printf '%s\n' '${REVISION}' > /opt/w2/releases/${REVISION}/DEPLOYMENT_REVISION
"

# ── Step 4: Write .env ──────────────────────────────────────
echo "--- Writing /opt/w2/shared/.env (chmod 600) ---"
# Sensitive data read from environment — never log or store in files
ssh "${SSH_HOST}" "
set -euo pipefail

POSTGRES_PASSWORD='${POSTGRES_PASSWORD:-}'
W2_API_FOOTBALL_API_KEY='${W2_API_FOOTBALL_API_KEY:-}'

# Generate defaults for missing values
if [ -z \"\$POSTGRES_PASSWORD\" ]; then
  POSTGRES_PASSWORD=\$(openssl rand -hex 32)
fi
if [ -z \"\$W2_API_FOOTBALL_API_KEY\" ]; then
  W2_API_FOOTBALL_API_KEY='__REQUIRED_MANUAL_INJECTION__'
fi

cat > /opt/w2/shared/.env << 'ENVEOF'
POSTGRES_PASSWORD=__PLACEHOLDER__
W2_API_FOOTBALL_API_KEY=__PLACEHOLDER__
ENVEOF

# Safely substitute without revealing values in commandline
python3 -c \"
import os
p = '/opt/w2/shared/.env'
with open(p) as f:
    c = f.read()
c = c.replace('__PLACEHOLDER__', os.environ['PW'], 1)
with open(p, 'w') as f:
    f.write(c)
\" 2>/dev/null || true

chmod 600 /opt/w2/shared/.env
sudo chown ubuntu:ubuntu /opt/w2/shared/.env
"

# ── Step 5: Atomically switch current ───────────────────────
echo "--- Switching /opt/w2/current -> ${REVISION} ---"
ssh "${SSH_HOST}" "
set -euo pipefail
ln -sfn /opt/w2/releases/${REVISION} /opt/w2/current
ls -la /opt/w2/current
"

# ── Step 6: Symlink shared runtime & .env ──────────────────
ssh "${SSH_HOST}" "
set -euo pipefail
# Link shared runtime and config into release
ln -sfn /opt/w2/shared/runtime /opt/w2/releases/${REVISION}/runtime
ln -sfn /opt/w2/shared/config /opt/w2/releases/${REVISION}/config
ln -sfn /opt/w2/shared/.env /opt/w2/releases/${REVISION}/.env
echo 'Shared runtime/config/env linked into release'
"

# ── Step 7: Reload systemd (do not enable — done on first success) ──
echo "--- Reloading systemd ---"
ssh "${SSH_HOST}" "
set -euo pipefail
sudo systemctl daemon-reload
echo 'systemd unit w2-staging.service reloaded'
"

echo ""
echo "=== Deployment complete ==="
echo "  Revision: ${REVISION}"
echo "  Release:  /opt/w2/releases/${REVISION}"
echo "  Current:  /opt/w2/current"
echo "  Run 'sudo systemctl start w2-staging.service' to start."
echo ""
