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
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ARCHIVE="/tmp/w2-${REVISION}.tar.gz"
START_AFTER_DEPLOY="${W2_STAGING_START_AFTER_DEPLOY:-false}"
PRUNE_BUILD_CACHE="${W2_STAGING_PRUNE_BUILD_CACHE:-false}"

echo "=== W2 Stage7H Deploy v0.1 ==="
echo "  SSH host:  ${SSH_HOST}"
echo "  Revision:  ${REVISION}"
echo "  Branch:    $(git rev-parse --abbrev-ref HEAD)"

# ── Step 0: Structural port preflight ──────────────────────
echo "--- Running local structural staging port preflight ---"
if python3 -c "import yaml" >/dev/null 2>&1; then
  python3 scripts/check_compose_staging_ports.py infra/compose/compose.staging.yml
else
  uv run --with pyyaml --python 3.12 python scripts/check_compose_staging_ports.py infra/compose/compose.staging.yml
fi

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
if python3 -c \"import yaml\" >/dev/null 2>&1; then
  python3 /tmp/check_compose_staging_ports.py infra/compose/compose.staging.yml
else
  uv run --with pyyaml --python 3.12 python /tmp/check_compose_staging_ports.py infra/compose/compose.staging.yml
fi
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
sudo install -d -o 10001 -g 10001 -m 0775 /opt/w2/shared/runtime
sudo install -d -o 10001 -g 10001 -m 0775 /opt/w2/shared/runtime/market_timeline_snapshots
sudo install -d -o 10001 -g 10001 -m 0775 /opt/w2/shared/runtime/independent_signal_backfill/raw_payloads
sudo chown 10001:10001 /opt/w2/shared/runtime
sudo chown -R 10001:10001 /opt/w2/shared/runtime/market_timeline_snapshots
sudo chown -R 10001:10001 /opt/w2/shared/runtime/independent_signal_backfill
sudo chmod u+rwX,g+rwX /opt/w2/shared/runtime
sudo chmod -R u+rwX,g+rwX /opt/w2/shared/runtime/market_timeline_snapshots
sudo chmod -R u+rwX,g+rwX /opt/w2/shared/runtime/independent_signal_backfill
ln -sfn /opt/w2/shared/runtime /opt/w2/releases/${REVISION}/runtime
ln -sfn /opt/w2/shared/config /opt/w2/releases/${REVISION}/config
ln -sfn /opt/w2/shared/.env /opt/w2/releases/${REVISION}/.env
echo 'Shared runtime/config/env linked into release'
"

# ── Step 6b: Persist public release metadata for compose/systemd ───────
echo "--- Writing public release metadata ---"
ssh "${SSH_HOST}" "
set -euo pipefail
install -d -m 0755 /opt/w2/shared
umask 022
cat > /opt/w2/shared/release.env <<'EOF'
W2_GIT_SHA=${REVISION}
W2_RELEASE_ID=${REVISION}
W2_BUILD_TIME=${BUILD_TIME}
VITE_GIT_SHA=${REVISION}
VITE_RELEASE_ID=${REVISION}
VITE_BUILD_TIME=${BUILD_TIME}
EOF
test \"\$(stat -c '%a' /opt/w2/shared/release.env)\" = '644'
echo 'release env written with mode 644'
"

# ── Step 7: Build release images so containers run this revision ─────
echo "--- Building staging images for ${REVISION} ---"
ssh "${SSH_HOST}" "
set -euo pipefail
cd /opt/w2/current
echo '--- Pre-build resource snapshot ---'
uptime
free -h | sed -n '1,2p'
df -h / /opt /var/lib/docker 2>/dev/null || df -h / /opt
sudo docker system df || true
export W2_GIT_SHA='${REVISION}'
export W2_BUILD_TIME='${BUILD_TIME}'
export W2_RELEASE_ID='${REVISION}'
sudo --preserve-env=W2_GIT_SHA,W2_BUILD_TIME,W2_RELEASE_ID docker compose --env-file /opt/w2/shared/.env --env-file /opt/w2/shared/release.env -f infra/compose/compose.staging.yml build
echo 'staging images built for current release'
if [ '${PRUNE_BUILD_CACHE}' = 'true' ]; then
  echo '--- Pruning unused Docker build cache (no volumes) ---'
  sudo docker builder prune -f
fi
echo '--- Post-build resource snapshot ---'
uptime
sudo docker system df || true
"

# ── Step 8: Reload systemd and install staging watchdog ─────────────
echo "--- Reloading systemd ---"
ssh "${SSH_HOST}" "
set -euo pipefail
sudo cp /opt/w2/current/infra/systemd/w2-staging.service /etc/systemd/system/w2-staging.service
sudo cp /opt/w2/current/infra/systemd/w2-staging-watchdog.service /etc/systemd/system/w2-staging-watchdog.service
sudo cp /opt/w2/current/infra/systemd/w2-staging-watchdog.timer /etc/systemd/system/w2-staging-watchdog.timer
sudo systemctl daemon-reload
sudo systemctl enable w2-staging-watchdog.timer >/dev/null
echo 'systemd units installed and reloaded'
"

if [ "${START_AFTER_DEPLOY}" = "true" ]; then
  echo "--- Migrating, switching API, then switching Web after stability ---"
  ssh "${SSH_HOST}" "
set -euo pipefail
cd /opt/w2/current
compose() {
  sudo docker compose \
    -p w2-staging \
    -f infra/compose/compose.staging.yml \
    --env-file /opt/w2/shared/.env \
    --env-file /opt/w2/shared/release.env \
    \"\$@\"
}

compose run --rm migration
compose up -d --no-deps api

api_consecutive=0
for attempt in \$(seq 1 18); do
  echo \"api_stability_probe_attempt=\${attempt}\"
  health=false
  ready=false
  version=false
  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/health >/tmp/w2-health.json && health=true || true
  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/ready >/tmp/w2-ready.json && ready=true || true
  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/v1/version >/tmp/w2-version.json && version=true || true
  echo \"health=\${health} ready=\${ready} version=\${version}\"
  if [ \"\${health}\" = true ] && [ \"\${ready}\" = true ] && [ \"\${version}\" = true ]; then
    api_consecutive=\$((api_consecutive + 1))
    if [ \"\${api_consecutive}\" -ge 3 ]; then
      echo 'api_stability_probe=PASS'
      break
    fi
  else
    api_consecutive=0
  fi
  sleep 5
done
if [ \"\${api_consecutive}\" -lt 3 ]; then
  echo 'api_stability_probe=FAIL' >&2
  exit 1
fi

compose up -d --no-deps web
sudo systemctl start w2-staging-watchdog.timer

release_consecutive=0
for attempt in \$(seq 1 18); do
  echo \"release_stability_probe_attempt=\${attempt}\"
  health=false
  ready=false
  version=false
  meta=false
  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1/health >/tmp/w2-health.json && health=true || true
  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1/ready >/tmp/w2-ready.json && ready=true || true
  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1/v1/version >/tmp/w2-version.json && version=true || true
  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1/meta.json >/tmp/w2-meta.json && meta=true || true
  echo \"health=\${health} ready=\${ready} version=\${version} meta=\${meta}\"
  if [ \"\${health}\" = true ] && [ \"\${ready}\" = true ] && [ \"\${version}\" = true ] && [ \"\${meta}\" = true ]; then
    release_consecutive=\$((release_consecutive + 1))
    if [ \"\${release_consecutive}\" -ge 3 ]; then
      echo 'stability_probe=PASS'
      break
    fi
  else
    release_consecutive=0
  fi
  sleep 5
done
if [ \"\${release_consecutive}\" -lt 3 ]; then
  echo 'stability_probe=FAIL' >&2
  exit 1
fi

echo 'worker_scheduler_restart=false'
"
fi

echo ""
echo "=== Deployment complete ==="
echo "  Revision: ${REVISION}"
echo "  Release:  /opt/w2/releases/${REVISION}"
echo "  Current:  /opt/w2/current"
if [ "${START_AFTER_DEPLOY}" = "true" ]; then
  echo "  API and Web switched in order; worker/scheduler untouched; stability probe passed."
else
  echo "  Run 'sudo systemctl start w2-staging.service' to start."
  echo "  Optional: W2_STAGING_START_AFTER_DEPLOY=true enables post-deploy stability probe."
fi
echo ""
