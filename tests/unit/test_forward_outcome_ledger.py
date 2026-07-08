from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from w2.tracking.forward_outcome_ledger import run_forward_outcome_ledger


def _day_view() -> dict[str, object]:
    return {
        "football_day": "2026-07-07",
        "environment": "staging",
        "cards": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-07T16:00:00Z",
                "competition_id": "world_cup_2026",
                "competition_name": "World Cup",
                "home_team_name": "Argentina",
                "away_team_name": "Egypt",
                "decision_tier": "WATCH",
                "data_status": "READY",
                "reason_code": "EDGE_INSUFFICIENT",
                "action": "盯价格变动",
                "probability_source": "MARKET_DEVIG",
                "model_market_divergence": {
                    "status": "READY",
                    "magnitude": 0.03,
                    "direction_allowed": False,
                },
                "current_odds": {
                    "ah": {
                        "home_line": "-1.25",
                        "away_line": "+1.25",
                        "home_price": "1.91",
                        "away_price": "1.93",
                        "bookmaker_count": 4,
                    }
                },
                "card_hash": "hash-1",
                "outcome_tracked": False,
                "source": "decision_contract",
            }
        ],
    }


def test_forward_outcome_ledger_dry_run_does_not_write(tmp_path: Path) -> None:
    payload = run_forward_outcome_ledger(
        _day_view(),
        dry_run=True,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )

    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["lock_capture_write"] is False
    assert payload["settlement_write"] is False
    assert payload["record_count"] == 1
    assert payload["written"] == 0
    assert list(tmp_path.glob("*.jsonl")) == []


def test_forward_outcome_ledger_write_is_idempotent(tmp_path: Path) -> None:
    first = run_forward_outcome_ledger(
        _day_view(),
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 0, tzinfo=UTC),
    )
    second = run_forward_outcome_ledger(
        _day_view(),
        dry_run=False,
        write_artifacts=True,
        runtime_root=tmp_path,
        captured_at=datetime(2026, 7, 7, 12, 5, tzinfo=UTC),
    )

    output = tmp_path / "2026-07-07_staging.jsonl"
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert first["written"] == 1
    assert second["written"] == 0
    assert second["skipped_existing"] == 1
    assert len(rows) == 1
    assert rows[0]["not_a_lock"] is True
    assert rows[0]["posthoc_only"] is True
    assert rows[0]["current_odds"]["ah"]["bookmaker_count"] == 4


def test_forward_outcome_ledger_cli_reads_day_view_json(tmp_path: Path) -> None:
    day_view_path = tmp_path / "day_view.json"
    day_view_path.write_text(json.dumps(_day_view()), encoding="utf-8")
    output_root = tmp_path / "ledger"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_forward_outcome_ledger.py",
            "--day-view-json",
            str(day_view_path),
            "--runtime-root",
            str(output_root),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["provider_calls"] == 0
    assert payload["db_writes"] == 0
    assert payload["record_count"] == 1
    assert not output_root.exists()
