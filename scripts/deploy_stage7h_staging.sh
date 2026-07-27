#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: $0 <ssh-host> <python-image@sha256:digest> <web-image@sha256:digest> [all|web]" >&2
  exit 2
fi

SSH_HOST="$1"
PYTHON_IMAGE="$2"
WEB_IMAGE="$3"
DEPLOY_MODE="${4:-all}"
REVISION="${W2_GIT_SHA:-$(git rev-parse HEAD)}"
BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! "${REVISION}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "W2_GIT_SHA must be an exact lowercase commit SHA" >&2
  exit 2
fi
if [ "${DEPLOY_MODE}" != "all" ] && [ "${DEPLOY_MODE}" != "web" ]; then
  echo "deploy mode must be all or web" >&2
  exit 2
fi
for image in "${PYTHON_IMAGE}" "${WEB_IMAGE}"; do
  if [[ ! "${image}" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]; then
    echo "image must be an immutable GHCR digest reference" >&2
    exit 2
  fi
done

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
install -m 0644 "${ROOT}/infra/compose/compose.staging.yml" "${TMP_DIR}/compose.staging.yml"
install -m 0644 "${ROOT}/infra/systemd/w2-staging.service" "${TMP_DIR}/w2-staging.service"
install -m 0644 "${ROOT}/infra/systemd/w2-staging-watchdog.service" \
  "${TMP_DIR}/w2-staging-watchdog.service"
install -m 0644 "${ROOT}/infra/systemd/w2-staging-watchdog.timer" \
  "${TMP_DIR}/w2-staging-watchdog.timer"
install -m 0755 "${ROOT}/scripts/watch_staging_runtime.sh" \
  "${TMP_DIR}/watch_staging_runtime.sh"
{
  printf 'W2_GIT_SHA=%s\n' "${REVISION}"
  printf 'W2_RELEASE_ID=%s\n' "${REVISION}"
  printf 'W2_BUILD_TIME=%s\n' "${BUILD_TIME}"
  printf 'VITE_GIT_SHA=%s\n' "${REVISION}"
  printf 'VITE_RELEASE_ID=%s\n' "${REVISION}"
  printf 'VITE_BUILD_TIME=%s\n' "${BUILD_TIME}"
  printf 'W2_PYTHON_IMAGE=%s\n' "${PYTHON_IMAGE}"
  printf 'W2_WEB_IMAGE=%s\n' "${WEB_IMAGE}"
} >"${TMP_DIR}/release.env"

# Only deployment configuration crosses the wire; application source is already in the images.
scp "${TMP_DIR}/compose.staging.yml" "${TMP_DIR}/w2-staging.service" \
  "${TMP_DIR}/w2-staging-watchdog.service" "${TMP_DIR}/w2-staging-watchdog.timer" \
  "${TMP_DIR}/watch_staging_runtime.sh" "${TMP_DIR}/release.env" "${SSH_HOST}:/tmp/"

ssh "${SSH_HOST}" bash -s -- "${REVISION}" "${DEPLOY_MODE}" <<'REMOTE'
set -euo pipefail
REVISION="$1"
DEPLOY_MODE="$2"
COMPOSE=(sudo docker compose -p w2-staging -f /opt/w2/deploy/compose.staging.yml
  --env-file /opt/w2/shared/.env --env-file /opt/w2/shared/release.env)
DEPLOY_STARTED="$(date +%s)"
ACTIVATED=false

rollback() {
  status=$?
  if [ "${ACTIVATED}" = true ] && [ -f /opt/w2/shared/release.previous.env ]; then
    rollback_started="$(date +%s)"
    sudo install -o root -g root -m 0644 \
      /opt/w2/shared/release.previous.env /opt/w2/shared/release.env
    "${COMPOSE[@]}" pull migration api worker web </dev/null
    "${COMPOSE[@]}" run --rm migration </dev/null
    "${COMPOSE[@]}" up -d --remove-orphans api worker web </dev/null
    rollback_seconds="$(( $(date +%s) - rollback_started ))"
    echo "rollback=PASS duration_seconds=${rollback_seconds} target_seconds=120"
  else
    echo "rollback=UNAVAILABLE no_previous_digest_set" >&2
  fi
  exit "${status}"
}
trap rollback ERR

sudo install -d -o root -g root -m 0755 /opt/w2/deploy
sudo install -d -o root -g root -m 0755 /opt/w2/shared/releases
sudo install -d -o 10001 -g 10001 -m 0775 /opt/w2/shared/runtime
sudo install -d -o 10001 -g 10001 -m 0775 \
  /opt/w2/shared/runtime/market_timeline_snapshots \
  /opt/w2/shared/runtime/reports/public \
  /opt/w2/shared/runtime/independent_signal_backfill/raw_payloads
sudo install -o root -g root -m 0644 /tmp/compose.staging.yml /opt/w2/deploy/compose.staging.yml
sudo install -o root -g root -m 0755 \
  /tmp/watch_staging_runtime.sh /opt/w2/deploy/watch_staging_runtime.sh
sudo install -o root -g root -m 0644 /tmp/w2-staging.service /etc/systemd/system/w2-staging.service
sudo install -o root -g root -m 0644 /tmp/w2-staging-watchdog.service \
  /etc/systemd/system/w2-staging-watchdog.service
sudo install -o root -g root -m 0644 /tmp/w2-staging-watchdog.timer \
  /etc/systemd/system/w2-staging-watchdog.timer
if [ -f /opt/w2/shared/release.env ]; then
  sudo install -o root -g root -m 0644 \
    /opt/w2/shared/release.env /opt/w2/shared/release.previous.env
fi
sudo install -o root -g root -m 0644 /tmp/release.env /opt/w2/shared/release.env
ACTIVATED=true

if [ "${DEPLOY_MODE}" = "web" ]; then
  "${COMPOSE[@]}" pull web </dev/null
  "${COMPOSE[@]}" up -d --no-deps web </dev/null
  TARGET_SECONDS=180
else
  "${COMPOSE[@]}" pull migration api worker web </dev/null
  "${COMPOSE[@]}" run --rm migration </dev/null
  "${COMPOSE[@]}" up -d --remove-orphans api worker web </dev/null
  TARGET_SECONDS=300
fi

sudo systemctl daemon-reload
sudo systemctl enable --now w2-staging-watchdog.timer >/dev/null
for attempt in $(seq 1 24); do
  if curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/ready >/dev/null \
    && curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18080/meta.json >/dev/null; then
    break
  fi
  if [ "${attempt}" = 24 ]; then
    echo "health_check=FAIL" >&2
    false
  fi
  sleep 5
done

DEPLOY_SECONDS="$(( $(date +%s) - DEPLOY_STARTED ))"
if [ "${DEPLOY_SECONDS}" -gt "${TARGET_SECONDS}" ]; then
  echo "deployment=FAIL duration_seconds=${DEPLOY_SECONDS} target_seconds=${TARGET_SECONDS}" >&2
  false
fi
PYTHON_IMAGE="$(sed -n 's/^W2_PYTHON_IMAGE=//p' /opt/w2/shared/release.env)"
WEB_IMAGE="$(sed -n 's/^W2_WEB_IMAGE=//p' /opt/w2/shared/release.env)"
python3 - "${REVISION}" "${DEPLOY_MODE}" "${DEPLOY_SECONDS}" \
  "${PYTHON_IMAGE}" "${WEB_IMAGE}" <<'PY' | sudo tee \
  "/opt/w2/shared/releases/${REVISION}.json" >/dev/null
import json
import sys
from datetime import UTC, datetime

revision, mode, duration, python_image, web_image = sys.argv[1:]
print(json.dumps({
    "schema_version": "w2.release_record.v1",
    "revision": revision,
    "mode": mode,
    "duration_seconds": int(duration),
    "python_image": python_image,
    "web_image": web_image,
    "status": "PASS",
    "recorded_at": datetime.now(UTC).isoformat(),
}, sort_keys=True))
PY
echo "deployment=PASS mode=${DEPLOY_MODE} duration_seconds=${DEPLOY_SECONDS} target_seconds=${TARGET_SECONDS}"
REMOTE
