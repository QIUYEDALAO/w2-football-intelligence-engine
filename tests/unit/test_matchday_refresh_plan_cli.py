from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_w2_matchday_refresh_plan.py"


def test_matchday_refresh_plan_cli_dry_run_json_is_side_effect_free(monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups,statistics")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--date",
            "today",
            "--env",
            "staging",
            "--dry-run",
            "--json",
            "--as-of",
            "2026-07-04T00:00:00Z",
            "--fixture-id",
            "fixture-1",
            "--kickoff-utc",
            "2026-07-05T03:00:00Z",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_enqueue"] is False
    assert payload["environment_policy"]["lock_policy"]["name"] == "staging_A"
    assert "staging-only" in payload["environment_policy"]["disclaimer"]
    assert set(payload["configured_endpoint_allowlist"]) == {
        "status",
        "fixtures",
        "odds",
        "lineups",
        "statistics",
    }
    assert payload["endpoint_allowlist"] == ["status", "fixtures", "odds", "lineups"]
    assert payload["skipped_endpoints"] == ["statistics"]
    assert "statistics" not in payload["ticks"][0]["allowed_endpoints"]
    assert payload["ledger_contract"]["planned_calls_equal_provider_request_logs_delta"] is True
    assert payload["ticks"][0]["provider_calls"] is None


def test_matchday_refresh_plan_cli_refuses_non_dry_run() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture-id",
            "fixture-1",
            "--kickoff-utc",
            "2026-07-05T03:00:00Z",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Only --dry-run is supported" in result.stderr
