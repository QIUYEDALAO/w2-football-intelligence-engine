from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_matchday_cli_help_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "w2.matchday.cli", "--help"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Run a side-effect-free W2 matchday dry-run skeleton" in result.stdout


def test_matchday_cli_default_mode_is_dry_run() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "w2.matchday.cli",
            "--date",
            "today",
            "--env",
            "staging",
            "--json",
            "--as-of",
            "2026-07-05T00:00:00Z",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["mode"] == "dry_run"
    assert payload["status"] == "NO_FIXTURES"


def test_matchday_cli_empty_day_json_is_side_effect_free() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "w2.matchday.cli",
            "--date",
            "today",
            "--env",
            "staging",
            "--dry-run",
            "--json",
            "--as-of",
            "2026-07-05T00:00:00Z",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["status"] == "NO_FIXTURES"
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_enqueue"] is False
    assert payload["decision_cards_summary"]["would_generate"] == 0


def test_matchday_cli_fixture_kickoff_mismatch_exits_nonzero() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "w2.matchday.cli",
            "--date",
            "today",
            "--env",
            "staging",
            "--dry-run",
            "--json",
            "--fixture-id",
            "fixture-1",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "--fixture-id and --kickoff-utc counts must match" in result.stderr


def test_matchday_cli_one_fixture_with_market_outputs_refresh_plan() -> None:
    env = os.environ.copy()
    env["W2_PROVIDER_ENDPOINT_ALLOWLIST"] = "status,fixtures,odds,lineups,statistics"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "w2.matchday.cli",
            "--date",
            "today",
            "--env",
            "staging",
            "--dry-run",
            "--json",
            "--as-of",
            "2026-07-05T00:00:00Z",
            "--competition-id",
            "allsvenskan",
            "--fixture-id",
            "fixture-1",
            "--kickoff-utc",
            "2026-07-05T04:00:00Z",
            "--home-team",
            "Home",
            "--away-team",
            "Away",
            "--market",
            "ASIAN_HANDICAP",
            "--line",
            "-0.25",
            "--odds",
            "1.95",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    payload = json.loads(result.stdout)

    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_enqueue"] is False
    assert payload["fixture_count"] == 1
    assert payload["refresh_plan_summary"]["endpoint_allowlist"] == [
        "status",
        "fixtures",
        "odds",
        "lineups",
    ]
    assert payload["refresh_plan_summary"]["skipped_endpoints"] == ["statistics"]
    assert payload["next_refresh_tick"] is not None


def test_matchday_cli_controlled_run_outputs_required_approvals() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "w2.matchday.cli",
            "--date",
            "today",
            "--env",
            "staging",
            "--mode",
            "controlled-run",
            "--json",
            "--as-of",
            "2026-07-05T00:00:00Z",
            "--competition-id",
            "allsvenskan",
            "--fixture-id",
            "fixture-1",
            "--kickoff-utc",
            "2026-07-05T04:00:00Z",
            "--home-team",
            "Home",
            "--away-team",
            "Away",
            "--market",
            "ASIAN_HANDICAP",
            "--line",
            "-0.25",
            "--odds",
            "1.95",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["mode"] == "controlled_run"
    assert payload["status"] == "APPROVAL_REQUIRED"
    assert "PROVIDER_CALLS" in payload["required_approvals"]
    assert "DB_WRITE" in payload["required_approvals"]
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["would_enqueue"] is False
    assert payload["would_call_provider"] is False


def test_matchday_cli_controlled_run_provider_approval_still_defers_execution() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "w2.matchday.cli",
            "--date",
            "today",
            "--env",
            "staging",
            "--mode",
            "controlled-run",
            "--json",
            "--approve-provider-calls",
            "--approve-db-writes",
            "--as-of",
            "2026-07-05T00:00:00Z",
            "--competition-id",
            "allsvenskan",
            "--fixture-id",
            "fixture-1",
            "--kickoff-utc",
            "2026-07-05T04:00:00Z",
            "--market",
            "ASIAN_HANDICAP",
            "--line",
            "-0.25",
            "--odds",
            "1.95",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["status"] == "EXECUTION_DEFERRED"
    assert payload["required_approvals"] == []
    assert payload["execution_plan"]["would_execute"] is False
    assert payload["provider_calls"] == 0


def test_matchday_cli_invalid_mode_exits_nonzero() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "w2.matchday.cli",
            "--mode",
            "real-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "invalid choice" in result.stderr
