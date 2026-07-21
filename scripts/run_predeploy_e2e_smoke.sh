#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/infra/compose/compose.staging.yml"
PROJECT_NAME="${W2_PREDEPLOY_E2E_PROJECT:-w2-predeploy-e2e}"
FIXTURE_ID="${W2_PREDEPLOY_E2E_FIXTURE_ID:-predeploy-world-cup-fixture}"
PREDEPLOY_API_PORT="${W2_PREDEPLOY_E2E_API_PORT:-28000}"

if ! command -v docker >/dev/null 2>&1; then
  echo "predeploy_e2e SKIP docker is not available"
  exit 0
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "predeploy_e2e SKIP docker compose is not available"
  exit 0
fi

run_python() {
  if command -v uv >/dev/null 2>&1; then
    uv run --python 3.12 python "$@"
  else
    python3 "$@"
  fi
}

TMP_DIR="$(mktemp -d)"
ENV_FILE="${TMP_DIR}/predeploy-e2e.env"
OVERRIDE_FILE="${TMP_DIR}/predeploy-e2e.override.yml"
CURRENT_REVISION="$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || true)"
RUNTIME_MODE_BEFORE=""
if [ -e "${ROOT}/runtime" ]; then
  RUNTIME_MODE_BEFORE="$(stat -c '%a' "${ROOT}/runtime" 2>/dev/null || stat -f '%Lp' "${ROOT}/runtime" 2>/dev/null || true)"
fi
cleanup() {
  cd "${ROOT}"
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" down -v --remove-orphans >/dev/null 2>&1 || true
  if [ -n "${RUNTIME_MODE_BEFORE}" ] && [ -e "${ROOT}/runtime" ]; then
    chmod "${RUNTIME_MODE_BEFORE}" "${ROOT}/runtime" >/dev/null 2>&1 || true
  elif [ -e "${ROOT}/runtime" ]; then
    chmod 0755 "${ROOT}/runtime" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

cat >"${ENV_FILE}" <<'EOF'
POSTGRES_PASSWORD=predeploy_e2e_password
W2_API_FOOTBALL_API_KEY=predeploy-e2e-fake-key
EOF
{
  printf 'W2_GIT_SHA=%s\n' "${CURRENT_REVISION}"
  printf 'W2_RELEASE_ID=%s\n' "${CURRENT_REVISION}"
  printf 'VITE_GIT_SHA=%s\n' "${CURRENT_REVISION}"
  printf 'VITE_RELEASE_ID=%s\n' "${CURRENT_REVISION}"
} >>"${ENV_FILE}"

cat >"${OVERRIDE_FILE}" <<'EOF'
services:
  api:
    ports: !override
      - "127.0.0.1:${W2_PREDEPLOY_E2E_API_PORT:-28000}:8000"
    environment:
      W2_FUTURE_REFRESH_PERSISTENCE: db
      W2_PROVIDER_CALLS_DISABLED: "true"
      W2_PROVIDER_SCHEDULER_ENABLED: "false"
      W2_PROVIDER_ENDPOINT_ALLOWLIST: status,fixtures,odds,lineups
      W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS: "900"
      W2_PROVIDER_REFRESH_TICK_HARD_CAP: "30"
  worker:
    environment:
      W2_FUTURE_REFRESH_PERSISTENCE: db
      W2_PROVIDER_CALLS_DISABLED: "true"
      W2_PROVIDER_SCHEDULER_ENABLED: "false"
      W2_PROVIDER_ENDPOINT_ALLOWLIST: status,fixtures,odds,lineups
      W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS: "900"
      W2_PROVIDER_REFRESH_TICK_HARD_CAP: "30"
  scheduler:
    environment:
      W2_FUTURE_REFRESH_PERSISTENCE: db
      W2_FUTURE_FIXTURE_REFRESH_ENABLED: "false"
      W2_PROVIDER_CALLS_DISABLED: "true"
      W2_PROVIDER_SCHEDULER_ENABLED: "false"
      W2_PROVIDER_ENDPOINT_ALLOWLIST: status,fixtures,odds,lineups
      W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS: "900"
      W2_PROVIDER_REFRESH_TICK_HARD_CAP: "30"
    healthcheck:
      test: ["CMD", "uv", "run", "python", "-c", "from apps.scheduler.main import heartbeat; assert 'heartbeat' in heartbeat()"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
EOF

cd "${ROOT}"
mkdir -p runtime
chmod 0555 runtime || true

run_python scripts/check_compose_staging_ports.py infra/compose/compose.staging.yml
run_python scripts/check_w2_future_refresh_staging_contract.py

docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" up -d --build --wait postgres redis
docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" run --rm migration
docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" up -d --build api worker scheduler

services_ready=false
for attempt in $(seq 1 24); do
  all_healthy=true
  for service in api worker scheduler; do
    container_id="$(docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" ps -q "${service}")"
    test -n "${container_id}"
    state="$(docker inspect --format='{{.State.Status}}' "${container_id}")"
    health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_id}")"
    echo "predeploy_startup attempt=${attempt} service=${service} state=${state} health=${health}"
    if [ "${state}" = "exited" ] || [ "${state}" = "dead" ]; then
      docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" logs --no-color --tail=120 "${service}" >&2
      exit 1
    fi
    if [ "${health}" != "healthy" ]; then
      all_healthy=false
    fi
  done
  if [ "${all_healthy}" = true ]; then
    services_ready=true
    break
  fi
  sleep 5
done
if [ "${services_ready}" != true ]; then
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" logs --no-color --tail=120 api worker scheduler >&2
  echo "predeploy_e2e services did not become healthy within 120 seconds" >&2
  exit 1
fi

docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T api /app/.venv/bin/python - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

assert os.getuid() == 10001, f"api uid must be 10001, got {os.getuid()}"
assert Path("/app/config").is_dir()
assert Path("/app/config/competitions/world_cup_2026.v1.json").is_file()
assert Path("/app/config/policies/future_fixture_refresh.v1.json").is_file()
assert Path("/app/runtime").is_dir()
print("predeploy_e2e api mount checks PASS")
PY

docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T worker /app/.venv/bin/python - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

assert os.getuid() == 10001, f"worker uid must be 10001, got {os.getuid()}"
assert Path("/app/config/competitions/world_cup_2026.v1.json").is_file()
assert Path("/app/config/policies/future_fixture_refresh.v1.json").is_file()
assert Path("/app/runtime").is_dir()
print("predeploy_e2e worker mount checks PASS")
PY

docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T api /app/.venv/bin/python - <<PY
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
FIXTURE_ID = "${FIXTURE_ID}"


class FakeLiveApiFootballPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=1,
            payload=self.payload(endpoint, params),
            headers={
                "x-ratelimit-requests-remaining": "7000",
                "x-ratelimit-remaining": "299",
            },
            captured_at=NOW,
        )

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            return {"response": {"requests": {"remaining": 7000}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": FIXTURE_ID,
                            "date": "2026-06-26T18:00:00+00:00",
                            "status": {"short": "NS"},
                            "venue": {"name": "Predeploy Venue"},
                        },
                        "league": {"id": 1, "name": "World Cup", "round": "Group Stage - 3"},
                        "teams": {
                            "home": {"id": 10, "name": "Predeploy Home"},
                            "away": {"id": 20, "name": "Predeploy Away"},
                        },
                    }
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": params["fixture"]},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Book A",
                                "bets": [
                                    {
                                        "id": 4,
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Home -0.5", "odd": "1.91"},
                                            {"value": "Away +0.5", "odd": "1.93"},
                                        ],
                                    },
                                    {
                                        "id": 5,
                                        "name": "Goals Over/Under",
                                        "values": [
                                            {"value": "Over 2.5", "odd": "2.01"},
                                            {"value": "Under 2.5", "odd": "1.82"},
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        if endpoint == "lineups":
            def team_lineup(team_id: int, offset: int) -> dict[str, Any]:
                return {
                    "team": {"id": team_id, "name": f"Predeploy Team {team_id}"},
                    "formation": "4-3-3",
                    "startXI": [
                        {
                            "player": {
                                "id": offset + index,
                                "name": f"Predeploy Player {offset + index}",
                                "number": index + 1,
                                "pos": "G" if index == 0 else "M",
                                "grid": f"{index // 4 + 1}:{index % 4 + 1}",
                            }
                        }
                        for index in range(11)
                    ],
                    "substitutes": [],
                }
            return {
                "response": [
                    team_lineup(10, 100),
                    team_lineup(20, 200),
                ]
            }
        raise AssertionError(endpoint)


fake = FakeLiveApiFootballPort()
key = deterministic_task_key(
    competition_id="world_cup_2026",
    season="2026",
    now=NOW,
    interval_seconds=900,
)
audit = run_future_refresh_task(
    task_id=f"{key}:predeploy-e2e",
    key=key,
    queued_at=NOW,
    competition_id="world_cup_2026",
    runtime_root=Path("/app/runtime/future_refresh"),
    client=fake,
    now=NOW,
    persistence="db",
)

assert audit.status == "COMPLETED", audit
assert audit.result["fixture_count"] == 1
assert audit.result["market_snapshot_count"] == 1
assert audit.result["feature_enrichment_payload_count"] == 1
assert audit.result["candidate"] is False
assert audit.result["formal_recommendation"] is False
assert [endpoint for endpoint, _ in fake.calls] == [
    "status",
    "fixtures",
    "odds",
    "lineups",
]
assert "statistics" not in [endpoint for endpoint, _ in fake.calls]
assert "injuries" not in [endpoint for endpoint, _ in fake.calls]
print("predeploy_e2e fake future refresh PASS")
PY

docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T api \
  /app/.venv/bin/python - "${FIXTURE_ID}" <<'PY'
from __future__ import annotations

import sys
from datetime import UTC, datetime

from w2.api.frozen_analysis import (
    AnalysisCardCanaryMaterializer,
    write_frozen_analysis_artifacts,
)
from w2.api.repository import ReadModelRepository
from w2.infrastructure.database import create_engine

fixture_id = sys.argv[1]
artifact = AnalysisCardCanaryMaterializer(ReadModelRepository()).build(
    fixture_id,
    evaluated_at=datetime(2026, 6, 25, 12, 0, tzinfo=UTC),
)
write_frozen_analysis_artifacts(create_engine(), [artifact])
print(f"predeploy_e2e frozen artifact PASS {artifact.artifact_hash}")
PY

python3 - <<PY
from __future__ import annotations

import json
import sys
import time
import urllib.request

fixture_id = "${FIXTURE_ID}"
url = f"http://127.0.0.1:${PREDEPLOY_API_PORT}/v1/fixtures/{fixture_id}/analysis-card"
last_error: Exception | None = None
payload: dict[str, object] | None = None
for _ in range(20):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.status == 200, response.status
            payload = json.loads(response.read().decode("utf-8"))
            break
    except Exception as exc:
        last_error = exc
        time.sleep(1)
if payload is None:
    raise SystemExit(f"analysis-card did not return 200: {last_error}")

text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
for banned in ("必中", "保证"):
    assert banned not in text, banned
assert "稳赢" not in text.replace("非稳赢", ""), text

card = payload["card"]
assert card["fixture_id"] == fixture_id
assert card["frozen_artifact_provenance"]["status"] == "VERIFIED"
assert card["frozen_artifact_provenance"]["fixture_identity"]["fixture_id"] == fixture_id
assert card["frozen_artifact_provenance"]["artifact_hash"]
assert card["candidate"] is False
assert card["formal_recommendation"] is False
assert card["lineup_provenance"]["coverage_grade"] == "C"
assert len(card["lineup_provenance"]["baseline_artifact_hashes"]) == 2
assert card["lineup_provenance"]["numeric_adjustment_enabled"] is False
assert card["disclaimer"] == "分析参考·非稳赢"
assert "bookmaker_intent" in card
assert card["risks"]
markets = card["markets"]
assert {market["market"] for market in markets} == {
    "ASIAN_HANDICAP",
    "TOTALS",
    "FIRST_HALF_GOALS",
    "SCORE",
}
for market in markets:
    assert market["candidate"] is False
    assert market["formal_recommendation"] is False
    assert market["decision"] in {"SKIP", "PICK", "WATCH"}
    assert market["risks"]
    if market["decision"] == "SKIP":
        assert any(
            "UNAVAILABLE" in reason
            or "INPUT" in reason
            or "MATRIX" in reason
            or "INSUFFICIENT" in reason
            or "EDGE" in reason
            for reason in market["reasons"]
        )
print("predeploy_e2e analysis card PASS")
PY

	chmod 0755 runtime
	mkdir -p runtime/future_refresh/read_model
	mkdir -p runtime/stage7c/raw
	chmod 000 runtime/future_refresh/read_model
	chmod 000 runtime/stage7c/raw
	chmod 0555 runtime
	python3 - <<PY
from __future__ import annotations

import json
import urllib.request

fixture_id = "${FIXTURE_ID}"
url = f"http://127.0.0.1:${PREDEPLOY_API_PORT}/v1/fixtures/{fixture_id}/analysis-card"
with urllib.request.urlopen(url, timeout=5) as response:
    assert response.status == 200, response.status
    payload = json.loads(response.read().decode("utf-8"))
assert payload["card"]["fixture_id"] == fixture_id
assert payload["card"]["candidate"] is False
assert payload["card"]["formal_recommendation"] is False
print("predeploy_e2e unreadable legacy runtime fallback PASS")
PY
	chmod 0755 runtime
	chmod 0555 runtime/future_refresh/read_model
	chmod 0555 runtime/stage7c/raw
	chmod 0555 runtime

CANONICAL_OBS_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(*) from matchday_market_observations where provider_fixture_id = '${FIXTURE_ID}';"
)"
LEGACY_OBS_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(*) from future_market_observation where fixture_id = '${FIXTURE_ID}';"
)"
RAW_ENDPOINT_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(distinct endpoint) from raw_payload where endpoint in ('statistics', 'lineups', 'injuries');"
)"
BLOCKED_ENDPOINT_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(distinct endpoint) from raw_payload where endpoint in ('statistics', 'injuries');"
)"
RUN_AUDIT_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(*) from future_refresh_run_audit where competition_id = 'world_cup_2026' and candidate = false and formal_recommendation = false;"
)"
LINEUP_SNAPSHOT_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(*) from structured_lineup_snapshots where fixture_id = '${FIXTURE_ID}' and confirmed = true;"
)"
LINEUP_STARTER_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(*) from structured_lineup_players p join structured_lineup_snapshots s on s.id = p.lineup_snapshot_id where s.fixture_id = '${FIXTURE_ID}' and p.starter = true;"
)"
LINEUP_BASELINE_COUNT="$(
  docker compose -p "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" -f "${OVERRIDE_FILE}" exec -T postgres \
    psql -U w2_user -d w2 -tAc "select count(*) from team_lineup_baselines;"
)"
if [ "${CANONICAL_OBS_COUNT}" -lt 1 ]; then
  echo "predeploy_e2e FAIL missing canonical DB market observations" >&2
  exit 1
fi
if [ "${LEGACY_OBS_COUNT}" -ne 0 ]; then
  echo "predeploy_e2e FAIL legacy market observations were written" >&2
  exit 1
fi
if [ "${RAW_ENDPOINT_COUNT}" -ne 1 ]; then
  echo "predeploy_e2e FAIL missing feature enrichment raw payload endpoints" >&2
  exit 1
fi
if [ "${BLOCKED_ENDPOINT_COUNT}" -ne 0 ]; then
  echo "predeploy_e2e FAIL disabled feature enrichment endpoints were persisted" >&2
  exit 1
fi
if [ "${RUN_AUDIT_COUNT}" -lt 1 ]; then
  echo "predeploy_e2e FAIL missing future refresh run audit" >&2
  exit 1
fi
if [ "${LINEUP_SNAPSHOT_COUNT}" -ne 2 ] || [ "${LINEUP_STARTER_COUNT}" -ne 22 ]; then
  echo "predeploy_e2e FAIL structured lineup materialization incomplete" >&2
  exit 1
fi
if [ "${LINEUP_BASELINE_COUNT}" -ne 2 ]; then
  echo "predeploy_e2e FAIL lineup baselines were not materialized" >&2
  exit 1
fi
echo "predeploy_e2e db assertions PASS"

echo "predeploy_e2e PASS"
