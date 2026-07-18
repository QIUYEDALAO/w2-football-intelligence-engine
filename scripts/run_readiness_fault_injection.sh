#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${W2_READINESS_FAULT_PROJECT:-w2-readiness-fault}"
IMAGE_PREFIX="${W2_READINESS_FAULT_IMAGE_PREFIX:?isolated image prefix is required}"
PORT="${W2_READINESS_FAULT_PORT:-28001}"
RUNTIME_SOURCE="${W2_READINESS_FAULT_RUNTIME_SOURCE:-${ROOT}/runtime}"
NETWORK="${PROJECT}-network"
POSTGRES="${PROJECT}-postgres"
REDIS="${PROJECT}-redis"
API="${PROJECT}-api"
VOLUME="${PROJECT}-postgres-data"
TMP_DIR="$(mktemp -d)"
MANIFEST="${TMP_DIR}/staging.v1.json"
READY_BODY="${TMP_DIR}/ready.json"
LEGACY_BODY="${TMP_DIR}/legacy-ready.json"
LEGACY_HEADERS="${TMP_DIR}/legacy-ready.headers"
RUNTIME_MODE="$(stat -c '%a' "${RUNTIME_SOURCE}")"

for container in "${POSTGRES}" "${REDIS}" "${API}"; do
  if docker container inspect "${container}" >/dev/null 2>&1; then
    echo "isolated container already exists: ${container}" >&2
    exit 2
  fi
done
if docker volume inspect "${VOLUME}" >/dev/null 2>&1; then
  echo "isolated volume already exists: ${VOLUME}" >&2
  exit 2
fi

cleanup() {
  chmod "${RUNTIME_MODE}" "${RUNTIME_SOURCE}" >/dev/null 2>&1 || true
  docker rm -f "${API}" "${REDIS}" "${POSTGRES}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
  docker volume rm "${VOLUME}" >/dev/null 2>&1 || true
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

cp "${ROOT}/config/readiness/staging.v1.json" "${MANIFEST}"
docker network create "${NETWORK}" >/dev/null
docker volume create "${VOLUME}" >/dev/null
docker run -d --name "${POSTGRES}" --network "${NETWORK}" \
  -e POSTGRES_DB=w2 \
  -e POSTGRES_USER=w2_user \
  -e POSTGRES_PASSWORD=readiness_fault_password \
  -v "${VOLUME}:/var/lib/postgresql/data" \
  postgres:16-alpine >/dev/null
docker run -d --name "${REDIS}" --network "${NETWORK}" redis:7-alpine >/dev/null

wait_postgres() {
  for _ in $(seq 1 30); do
    docker exec "${POSTGRES}" pg_isready -U w2_user -d w2 >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

wait_redis() {
  for _ in $(seq 1 30); do
    [[ "$(docker exec "${REDIS}" redis-cli ping 2>/dev/null)" == "PONG" ]] && return 0
    sleep 1
  done
  return 1
}

http_status() {
  local path="$1"
  local output="$2"
  curl -sS -o "${output}" -w '%{http_code}' "http://127.0.0.1:${PORT}${path}"
}

expect_ready() {
  local status
  status="$(http_status /ready "${READY_BODY}")"
  [[ "${status}" == "200" ]]
  jq -e '.status == "READY"' "${READY_BODY}" >/dev/null
}

expect_not_ready() {
  local expected_check="$1"
  local status
  status="$(http_status /ready "${READY_BODY}")"
  [[ "${status}" == "503" ]]
  jq -e --arg check "${expected_check}" \
    '.status == "NOT_READY" and .checks[$check].status == "FAIL"' \
    "${READY_BODY}" >/dev/null
}

wait_postgres
wait_redis
docker run --rm --network "${NETWORK}" \
  -e W2_ENVIRONMENT=staging \
  -e W2_DATABASE_URL="postgresql+psycopg://w2_user:readiness_fault_password@${POSTGRES}:5432/w2" \
  "${IMAGE_PREFIX}-migration:latest" \
  uv run alembic upgrade head >/dev/null

docker run -d --name "${API}" --network "${NETWORK}" \
  -p "127.0.0.1:${PORT}:8000" \
  -e W2_ENVIRONMENT=staging \
  -e W2_DATABASE_URL="postgresql+psycopg://w2_user:readiness_fault_password@${POSTGRES}:5432/w2" \
  -e W2_REDIS_URL="redis://${REDIS}:6379/0" \
  -e W2_PROVIDER_CALLS_DISABLED=true \
  -e W2_PROVIDER_SCHEDULER_ENABLED=false \
  -e W2_API_FOOTBALL_API_KEY=readiness-fault-fake-key \
  -e W2_READINESS_RELEASE_ROOT=/app \
  -e W2_READINESS_MANIFEST_PATH=/app/readiness-test.json \
  -v "${ROOT}/config:/app/config:ro" \
  -v "${ROOT}/migrations:/app/migrations:ro" \
  -v "${RUNTIME_SOURCE}:/app/runtime:ro" \
  -v "${MANIFEST}:/app/readiness-test.json:ro" \
  "${IMAGE_PREFIX}-api:latest" >/dev/null

for _ in $(seq 1 30); do
  expect_ready >/dev/null 2>&1 && break
  sleep 1
done
expect_ready

legacy_status="$(curl -sS -D "${LEGACY_HEADERS}" -o "${LEGACY_BODY}" -w '%{http_code}' \
  "http://127.0.0.1:${PORT}/v1/ready")"
[[ "${legacy_status}" == "200" ]]
cmp -s "${READY_BODY}" "${LEGACY_BODY}"
grep -qi '^Deprecation: true' "${LEGACY_HEADERS}"
grep -qi '^Link: </ready>; rel="canonical"' "${LEGACY_HEADERS}"

docker stop "${POSTGRES}" >/dev/null
[[ "$(http_status /health "${TMP_DIR}/health.json")" == "200" ]]
expect_not_ready database
docker start "${POSTGRES}" >/dev/null
wait_postgres
expect_ready

docker stop "${REDIS}" >/dev/null
expect_not_ready redis
docker start "${REDIS}" >/dev/null
wait_redis
expect_ready

docker exec "${POSTGRES}" psql -U w2_user -d w2 -v ON_ERROR_STOP=1 -q \
  -c "update alembic_version set version_num='0022_extend_recommendation_lock_snapshot'"
expect_not_ready schema
docker exec "${POSTGRES}" psql -U w2_user -d w2 -v ON_ERROR_STOP=1 -q \
  -c "update alembic_version set version_num='0023_create_checkpoint_refresh_schedule'"
expect_ready

sed -E -i '0,/"sha256": "[0-9a-f]{64}"/s//"sha256": "0000000000000000000000000000000000000000000000000000000000000000"/' \
  "${MANIFEST}"
expect_not_ready artifacts
cp "${ROOT}/config/readiness/staging.v1.json" "${MANIFEST}"
expect_ready

chmod 0000 "${RUNTIME_SOURCE}"
expect_not_ready mounts
chmod "${RUNTIME_MODE}" "${RUNTIME_SOURCE}"
expect_ready

echo "canonical_readiness_fault_injection PASS"
