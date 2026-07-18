#!/usr/bin/env bash
# Staging-safe runtime recovery helper.
#
# Defaults to a systemd restart plus probes. Optional pruning removes only
# unused build cache or dangling images; it never deletes Docker volumes.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/recover_staging_runtime.sh <ssh-host> [--prune-build-cache] [--prune-images]

Options:
  --prune-build-cache   Run docker builder prune -f before restart.
  --prune-images        Run docker image prune -f before restart.

Safety:
  - staging only
  - does not read or print .env
  - does not call providers
  - does not run migrations
  - never deletes Docker volumes
EOF
}

SSH_HOST="${1:-}"
if [[ -z "${SSH_HOST}" || "${SSH_HOST}" == "-h" || "${SSH_HOST}" == "--help" ]]; then
  usage
  exit 0
fi
shift

PRUNE_BUILD_CACHE=false
PRUNE_IMAGES=false
for arg in "$@"; do
  case "${arg}" in
    --prune-build-cache) PRUNE_BUILD_CACHE=true ;;
    --prune-images) PRUNE_IMAGES=true ;;
    *) echo "Unknown option: ${arg}" >&2; usage >&2; exit 2 ;;
  esac
done

REMOTE_SCRIPT="$(cat <<'REMOTE'
set -euo pipefail

cd /opt/w2/current

echo "== pre-recovery =="
date -u
uptime
systemctl is-active w2-staging.service || true
sudo docker system df || true

if [[ "${PRUNE_BUILD_CACHE}" == "true" ]]; then
  echo "== prune build cache =="
  sudo docker builder prune -f
fi

if [[ "${PRUNE_IMAGES}" == "true" ]]; then
  echo "== prune dangling images =="
  sudo docker image prune -f
fi

echo "== restart staging service =="
sudo systemctl restart w2-staging.service

echo "== post-restart compose =="
sudo docker compose \
  --env-file /opt/w2/shared/.env \
  --env-file /opt/w2/shared/release.env \
  -f infra/compose/compose.staging.yml \
  ps

echo "== stability probes =="
for attempt in 1 2 3 4 5 6; do
  echo "probe_attempt=${attempt}"
  api_ok=false
  web_ok=false
  if curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/ready >/tmp/w2-ready.json; then
    api_ok=true
  fi
  if curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1/meta.json >/tmp/w2-meta.json; then
    web_ok=true
  fi
  echo "api_ready=${api_ok} web_meta=${web_ok}"
  if [[ "${api_ok}" == "true" && "${web_ok}" == "true" ]]; then
    echo "staging_recovery=PASS"
    exit 0
  fi
  sleep 10
done

echo "staging_recovery=FAIL" >&2
exit 1
REMOTE
)"

ssh "${SSH_HOST}" \
  "PRUNE_BUILD_CACHE='${PRUNE_BUILD_CACHE}' PRUNE_IMAGES='${PRUNE_IMAGES}' bash -s" \
  <<<"${REMOTE_SCRIPT}"
