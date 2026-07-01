#!/usr/bin/env bash
# Local-on-staging watchdog target. Designed for systemd timer execution.

set -euo pipefail

STATE_DIR="${W2_STAGING_WATCHDOG_STATE_DIR:-/opt/w2/shared/runtime/watchdog}"
FAIL_FILE="${STATE_DIR}/consecutive_failures"
THRESHOLD="${W2_STAGING_WATCHDOG_FAILURE_THRESHOLD:-3}"
mkdir -p "${STATE_DIR}"

probe() {
  local name="$1"
  local url="$2"
  if curl -fsS --connect-timeout 3 --max-time 8 "${url}" >/tmp/w2-watchdog-"${name}".json; then
    echo "${name}=PASS"
    return 0
  fi
  echo "${name}=FAIL"
  return 1
}

failures=0
probe health http://127.0.0.1:18000/health || failures=$((failures + 1))
probe ready http://127.0.0.1:18000/ready || failures=$((failures + 1))
probe version http://127.0.0.1:18000/v1/version || failures=$((failures + 1))
probe web_meta http://127.0.0.1/meta.json || failures=$((failures + 1))

if [[ "${failures}" -eq 0 ]]; then
  printf '0\n' > "${FAIL_FILE}"
  echo "watchdog_status=PASS consecutive_failures=0"
  exit 0
fi

previous=0
if [[ -f "${FAIL_FILE}" ]]; then
  previous="$(cat "${FAIL_FILE}" 2>/dev/null || echo 0)"
fi
case "${previous}" in
  ''|*[!0-9]*) previous=0 ;;
esac
current=$((previous + 1))
printf '%s\n' "${current}" > "${FAIL_FILE}"
echo "watchdog_status=FAIL consecutive_failures=${current} threshold=${THRESHOLD}"

if [[ "${current}" -ge "${THRESHOLD}" ]]; then
  echo "watchdog_action=restart_staging"
  sudo systemctl restart w2-staging.service
  printf '0\n' > "${FAIL_FILE}"
fi

exit 0
