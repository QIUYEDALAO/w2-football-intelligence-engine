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
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! "${REVISION}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "W2_GIT_SHA must be an exact lowercase commit SHA" >&2
  exit 2
fi
if [ "${DEPLOY_MODE}" != "all" ] && [ "${DEPLOY_MODE}" != "web" ]; then
  echo "deploy mode must be all or web" >&2
  exit 2
fi
IMAGE_REF_RE='^(ghcr\.io/[a-z0-9._/-]+|127\.0\.0\.1:5000/w2/[a-z0-9._/-]+)@sha256:[0-9a-f]{64}$'
for image in "${PYTHON_IMAGE}" "${WEB_IMAGE}"; do
  if [[ ! "${image}" =~ ${IMAGE_REF_RE} ]]; then
    echo "image must be an immutable GHCR or VPS-loopback registry digest reference" >&2
    exit 2
  fi
done
REMOTE_TMP_DIR="/tmp/w2-deploy-${REVISION}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
install -m 0644 "${ROOT}/infra/compose/compose.staging.yml" "${TMP_DIR}/compose.staging.yml"
install -m 0644 "${ROOT}/infra/compose/controlled-future-refresh.override.yml" \
  "${TMP_DIR}/controlled-future-refresh.override.yml"
install -m 0644 "${ROOT}/infra/systemd/w2-staging.service" "${TMP_DIR}/w2-staging.service"
install -m 0644 "${ROOT}/infra/systemd/w2-staging-watchdog.service" \
  "${TMP_DIR}/w2-staging-watchdog.service"
install -m 0644 "${ROOT}/infra/systemd/w2-staging-watchdog.timer" \
  "${TMP_DIR}/w2-staging-watchdog.timer"
install -m 0755 "${ROOT}/scripts/watch_staging_runtime.sh" \
  "${TMP_DIR}/watch_staging_runtime.sh"
install -m 0444 "${ROOT}/scripts/check_w2_stage7h.py" \
  "${TMP_DIR}/check_w2_stage7h.py"
{
  printf 'W2_PYTHON_IMAGE=%s\n' "${PYTHON_IMAGE}"
  printf 'W2_WEB_IMAGE=%s\n' "${WEB_IMAGE}"
} >"${TMP_DIR}/release.env"

# Only deployment configuration and read-only operational assets cross the wire.
ssh "${SSH_HOST}" install -d -m 0700 "${REMOTE_TMP_DIR}"
scp "${TMP_DIR}/compose.staging.yml" "${TMP_DIR}/controlled-future-refresh.override.yml" \
  "${TMP_DIR}/w2-staging.service" \
  "${TMP_DIR}/w2-staging-watchdog.service" "${TMP_DIR}/w2-staging-watchdog.timer" \
  "${TMP_DIR}/watch_staging_runtime.sh" "${TMP_DIR}/check_w2_stage7h.py" \
  "${TMP_DIR}/release.env" "${SSH_HOST}:${REMOTE_TMP_DIR}/"

ssh "${SSH_HOST}" bash -s -- \
  "${REVISION}" "${DEPLOY_MODE}" "${PYTHON_IMAGE}" "${WEB_IMAGE}" \
  "${REMOTE_TMP_DIR}" <<'REMOTE'
set -Eeuo pipefail
REVISION="$1"
DEPLOY_MODE="$2"
PYTHON_IMAGE="$3"
WEB_IMAGE="$4"
REMOTE_TMP_DIR="$5"
if [ "${REMOTE_TMP_DIR}" != "/tmp/w2-deploy-${REVISION}" ] || \
  [ ! -d "${REMOTE_TMP_DIR}" ] || [ -L "${REMOTE_TMP_DIR}" ]; then
  echo "invalid remote deployment staging directory" >&2
  exit 2
fi
COMPOSE=(sudo docker compose -p w2-staging -f /opt/w2/deploy/compose.staging.yml
  -f /opt/w2/deploy/controlled-future-refresh.override.yml
  --env-file /opt/w2/shared/.env --env-file /opt/w2/shared/release.env)
DEPLOY_STARTED="$(date +%s)"
ACTIVATED=false

release_value() {
  sed -n "s/^$1=//p" "$2"
}

image_label() {
  sudo docker image inspect --format "{{index .Config.Labels \"$2\"}}" "$1"
}

repo_digest_ref() {
  sudo docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$1" |
    grep -Fx "$1" | head -1
}

verify_runtime() {
  env_file="$1"
  expected_python_ref="$(release_value W2_PYTHON_IMAGE "${env_file}")"
  expected_web_ref="$(release_value W2_WEB_IMAGE "${env_file}")"
  expected_python_id="$(release_value W2_API_IMAGE_ID "${env_file}")"
  expected_registry_digest="$(release_value W2_API_REGISTRY_DIGEST "${env_file}")"

  curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/ready >/dev/null &&
    version_json="$(
      curl -fsS --connect-timeout 3 --max-time 8 http://127.0.0.1:18000/v1/version
    )" &&
    curl -fsS --connect-timeout 3 --max-time 8 \
      http://127.0.0.1:18080/meta.json >/dev/null || return 1

  printf '%s' "${version_json}" |
    python3 -c '
import json
import sys

image = json.load(sys.stdin)["release_identity"]["image"]
expected_id, expected_digest = sys.argv[1:]
assert image["image_id"] == {"status": "AVAILABLE", "value": expected_id}
assert image["oci_digest"] == {"status": "AVAILABLE", "value": expected_digest}
assert image["registry_digest"] == {"status": "AVAILABLE", "value": expected_digest}
' "${expected_python_id}" "${expected_registry_digest}" || return 1

  expected_web_id="$(sudo docker image inspect --format '{{.Id}}' "${expected_web_ref}")"
  for service in api worker scheduler; do
    container_id="$("${COMPOSE[@]}" ps -q "${service}")"
    [ -n "${container_id}" ] || return 1
    [ "$(sudo docker inspect --format '{{.Image}}' "${container_id}")" = \
      "${expected_python_id}" ] || return 1
    [ "$(sudo docker inspect --format '{{.Config.Image}}' "${container_id}")" = \
      "${expected_python_ref}" ] || return 1
  done
  web_id="$("${COMPOSE[@]}" ps -q web)"
  [ -n "${web_id}" ] || return 1
  [ "$(sudo docker inspect --format '{{.Image}}' "${web_id}")" = \
    "${expected_web_id}" ] || return 1
  [ "$(sudo docker inspect --format '{{.Config.Image}}' "${web_id}")" = \
    "${expected_web_ref}" ] || return 1
  [ "$("${COMPOSE[@]}" ps --status running -q scheduler | wc -l)" -eq 1 ]
}

wait_for_runtime() {
  for attempt in $(seq 1 24); do
    if verify_runtime /opt/w2/shared/release.env; then
      return 0
    fi
    [ "${attempt}" -lt 24 ] && sleep 5
  done
  return 1
}

rollback() {
  original_status=$?
  trap - ERR
  if [ "${ACTIVATED}" != true ]; then
    echo "activation=SKIPPED preactivation_verification_failed" >&2
    exit "${original_status}"
  fi
  if [ ! -f /opt/w2/shared/release.previous.env ]; then
    echo "rollback=FAIL no_previous_digest_set" >&2
    exit "${original_status}"
  fi

  rollback_started="$(date +%s)"
  sudo install -o root -g root -m 0644 \
    /opt/w2/shared/release.previous.env /opt/w2/shared/release.env
  if "${COMPOSE[@]}" pull migration api worker scheduler web </dev/null &&
    "${COMPOSE[@]}" run --rm migration </dev/null &&
    "${COMPOSE[@]}" up -d --remove-orphans api worker scheduler web </dev/null &&
    wait_for_runtime; then
    rollback_seconds="$(( $(date +%s) - rollback_started ))"
    echo "rollback=PASS duration_seconds=${rollback_seconds} target_seconds=120"
  else
    echo "rollback=FAIL health_or_digest_mismatch" >&2
    exit 1
  fi
  exit "${original_status}"
}
trap rollback ERR

sudo install -d -o root -g root -m 0755 /opt/w2/deploy
sudo install -d -o root -g root -m 0755 /opt/w2/shared/releases
sudo install -d -o 10001 -g 10001 -m 0775 /opt/w2/shared/runtime
sudo install -d -o 10001 -g 10001 -m 0775 \
  /opt/w2/shared/runtime/market_timeline_snapshots \
  /opt/w2/shared/runtime/reports/public \
  /opt/w2/shared/runtime/independent_signal_backfill/raw_payloads
sudo install -o root -g root -m 0644 "${REMOTE_TMP_DIR}/compose.staging.yml" \
  /opt/w2/deploy/compose.staging.yml
sudo install -o root -g root -m 0644 \
  "${REMOTE_TMP_DIR}/controlled-future-refresh.override.yml" \
  /opt/w2/deploy/controlled-future-refresh.override.yml
sudo install -o root -g root -m 0755 \
  "${REMOTE_TMP_DIR}/watch_staging_runtime.sh" /opt/w2/deploy/watch_staging_runtime.sh
sudo install -o root -g root -m 0444 \
  "${REMOTE_TMP_DIR}/check_w2_stage7h.py" /opt/w2/deploy/check_w2_stage7h.py
sudo install -o root -g root -m 0644 "${REMOTE_TMP_DIR}/w2-staging.service" \
  /etc/systemd/system/w2-staging.service
sudo install -o root -g root -m 0644 "${REMOTE_TMP_DIR}/w2-staging-watchdog.service" \
  /etc/systemd/system/w2-staging-watchdog.service
sudo install -o root -g root -m 0644 "${REMOTE_TMP_DIR}/w2-staging-watchdog.timer" \
  /etc/systemd/system/w2-staging-watchdog.timer

if sudo docker image inspect "${PYTHON_IMAGE}" >/dev/null 2>&1 &&
  sudo docker image inspect "${WEB_IMAGE}" >/dev/null 2>&1; then
  TIMING_SCOPE="$(
    [ "${DEPLOY_MODE}" = "web" ] && printf WEB_WARM_SWITCH || printf WARM_SWITCH
  )"
else
  TIMING_SCOPE=COLD_PULL_END_TO_END
fi

sudo docker pull "${PYTHON_IMAGE}" </dev/null
sudo docker pull "${WEB_IMAGE}" </dev/null

PYTHON_REVISION="$(image_label "${PYTHON_IMAGE}" org.opencontainers.image.revision)"
PYTHON_CREATED="$(image_label "${PYTHON_IMAGE}" org.opencontainers.image.created)"
PYTHON_RELEASE_ID="$(image_label "${PYTHON_IMAGE}" w2.release.id)"
WEB_REVISION="$(image_label "${WEB_IMAGE}" org.opencontainers.image.revision)"
WEB_CREATED="$(image_label "${WEB_IMAGE}" org.opencontainers.image.created)"
WEB_RELEASE_ID="$(image_label "${WEB_IMAGE}" w2.release.id)"
PYTHON_ACTUAL_REF="$(repo_digest_ref "${PYTHON_IMAGE}")"
WEB_ACTUAL_REF="$(repo_digest_ref "${WEB_IMAGE}")"
PYTHON_IMAGE_ID="$(sudo docker image inspect --format '{{.Id}}' "${PYTHON_IMAGE}")"
WEB_IMAGE_ID="$(sudo docker image inspect --format '{{.Id}}' "${WEB_IMAGE}")"
PYTHON_REGISTRY_DIGEST="${PYTHON_ACTUAL_REF##*@}"
WEB_REGISTRY_DIGEST="${WEB_ACTUAL_REF##*@}"

[ "${PYTHON_REVISION}" = "${REVISION}" ]
[ "${WEB_REVISION}" = "${REVISION}" ]
[ "${PYTHON_RELEASE_ID}" = "${REVISION}" ]
[ "${WEB_RELEASE_ID}" = "${REVISION}" ]
[ -n "${PYTHON_CREATED}" ]
[ -n "${WEB_CREATED}" ]
[[ "${PYTHON_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "${WEB_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "${PYTHON_REGISTRY_DIGEST}" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "${WEB_REGISTRY_DIGEST}" =~ ^sha256:[0-9a-f]{64}$ ]]

if [ -f /opt/w2/shared/release.env ]; then
  sudo install -o root -g root -m 0644 \
    /opt/w2/shared/release.env /opt/w2/shared/release.previous.env
fi
sudo install -o root -g root -m 0644 "${REMOTE_TMP_DIR}/release.env" \
  /opt/w2/shared/release.env
ACTIVATED=true

{
  printf 'W2_PYTHON_IMAGE=%s\n' "${PYTHON_ACTUAL_REF}"
  printf 'W2_WEB_IMAGE=%s\n' "${WEB_ACTUAL_REF}"
  printf 'W2_GIT_SHA=%s\n' "${PYTHON_REVISION}"
  printf 'W2_BUILD_TIME=%s\n' "${PYTHON_CREATED}"
  printf 'W2_RELEASE_ID=%s\n' "${PYTHON_RELEASE_ID}"
  printf 'W2_API_IMAGE_ID=%s\n' "${PYTHON_IMAGE_ID}"
  printf 'W2_API_OCI_DIGEST=%s\n' "${PYTHON_REGISTRY_DIGEST}"
  printf 'W2_API_REGISTRY_DIGEST=%s\n' "${PYTHON_REGISTRY_DIGEST}"
} | sudo tee /opt/w2/shared/release.env >/dev/null

if [ "${DEPLOY_MODE}" = "web" ]; then
  "${COMPOSE[@]}" pull web </dev/null
  "${COMPOSE[@]}" up -d --no-deps web </dev/null
  TARGET_SECONDS=180
else
  "${COMPOSE[@]}" pull migration api worker scheduler web </dev/null
  "${COMPOSE[@]}" run --rm migration </dev/null
  "${COMPOSE[@]}" up -d --remove-orphans api worker scheduler web </dev/null
  TARGET_SECONDS=300
fi

sudo systemctl daemon-reload
sudo systemctl enable --now w2-staging-watchdog.timer >/dev/null
wait_for_runtime

DEPLOY_SECONDS="$(( $(date +%s) - DEPLOY_STARTED ))"
if [ "${DEPLOY_SECONDS}" -gt "${TARGET_SECONDS}" ]; then
  echo "${TIMING_SCOPE}=FAIL duration_seconds=${DEPLOY_SECONDS} target_seconds=${TARGET_SECONDS}" >&2
  false
fi

python3 - \
  "${PYTHON_REVISION}" "${DEPLOY_MODE}" "${TIMING_SCOPE}" "${DEPLOY_SECONDS}" \
  "${PYTHON_ACTUAL_REF}" "${PYTHON_IMAGE_ID}" "${PYTHON_REGISTRY_DIGEST}" \
  "${PYTHON_CREATED}" "${PYTHON_RELEASE_ID}" \
  "${WEB_ACTUAL_REF}" "${WEB_IMAGE_ID}" "${WEB_REGISTRY_DIGEST}" \
  "${WEB_CREATED}" "${WEB_REVISION}" "${WEB_RELEASE_ID}" <<'PY' | sudo tee \
  "/opt/w2/shared/releases/${REVISION}.json" >/dev/null
import json
import sys
from datetime import UTC, datetime

(
    revision,
    mode,
    timing_scope,
    duration,
    python_image,
    python_image_id,
    python_digest,
    python_created,
    python_release_id,
    web_image,
    web_image_id,
    web_digest,
    web_created,
    web_revision,
    web_release_id,
) = sys.argv[1:]
print(json.dumps({
    "schema_version": "w2.release_record.v1",
    "revision": revision,
    "mode": mode,
    "timing_scope": timing_scope,
    "duration_seconds": int(duration),
    "python_image": python_image,
    "python_identity": {
        "image_id": python_image_id,
        "oci_digest": python_digest,
        "registry_digest": python_digest,
        "revision": revision,
        "created": python_created,
        "release_id": python_release_id,
    },
    "web_image": web_image,
    "web_identity": {
        "image_id": web_image_id,
        "oci_digest": web_digest,
        "registry_digest": web_digest,
        "revision": web_revision,
        "created": web_created,
        "release_id": web_release_id,
    },
    "status": "PASS",
    "recorded_at": datetime.now(UTC).isoformat(),
}, sort_keys=True))
PY
echo "${TIMING_SCOPE}=PASS duration_seconds=${DEPLOY_SECONDS} target_seconds=${TARGET_SECONDS}"
REMOTE
