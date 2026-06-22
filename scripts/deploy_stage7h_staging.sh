#!/usr/bin/env bash
# ============================================================================
# W2 Stage7H – Deploy Staging Release to VPS
#
# Usage:
#   bash scripts/deploy_stage7h_staging.sh <ssh-host>
#
# Example:
#   bash scripts/deploy_stage7h_staging.sh ubuntu@43.155.208.138
#
# Security:
#   - Does not write or print sensitive values
#   - Uses pre-provisioned /opt/w2/shared/.env (chmod 600)
#   - Port preflight is structural and never expands compose environment values
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

# ── Step 0: Structural port preflight ──────────────────────
echo "--- Running local structural staging port preflight ---"
python3 scripts/check_compose_staging_ports.py infra/compose/compose.staging.yml

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

# ── Step 4: Verify existing shared env permissions ─────────
echo "--- Verifying /opt/w2/shared/.env permissions (content not printed) ---"
ssh "${SSH_HOST}" "
set -euo pipefail
test -f /opt/w2/shared/.env
test \"\$(stat -c '%a' /opt/w2/shared/.env)\" = '600'
echo 'shared env present with mode 600'
"

# ── Step 5: Structural port preflight on extracted release ──
echo "--- Running remote structural staging port preflight ---"
scp scripts/check_compose_staging_ports.py "${SSH_HOST}:/tmp/check_compose_staging_ports.py" >/dev/null
ssh "${SSH_HOST}" "
set -euo pipefail
cd /opt/w2/releases/${REVISION}
python3 /tmp/check_compose_staging_ports.py infra/compose/compose.staging.yml
rm -f /tmp/check_compose_staging_ports.py
"

# ── Step 5b: Atomically switch current ──────────────────────
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

# ── Step 7: Build release images so containers run this revision ─────
echo "--- Building staging images for ${REVISION} ---"
ssh "${SSH_HOST}" "
set -euo pipefail
cd /opt/w2/current
sudo docker compose --env-file /opt/w2/shared/.env -f infra/compose/compose.staging.yml build
echo 'staging images built for current release'
"

# ── Step 8: Reload systemd (do not enable — done on first success) ──
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
