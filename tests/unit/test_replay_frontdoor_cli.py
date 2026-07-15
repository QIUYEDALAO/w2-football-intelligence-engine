from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_w2_replay_frontdoor.py"


def test_replay_frontdoor_cli_no_inputs_returns_no_replay_inputs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--football-day",
            "2026-07-05",
            "--env",
            "staging",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["replay_status"] == "NO_REPLAY_INPUTS"
    assert payload["provider_calls"] == 0
    assert payload["db_reads"] == 0
    assert payload["db_writes"] == 0
    assert payload["checkpoint_write"] is False
    assert payload["settlement_write"] is False


def test_replay_frontdoor_cli_with_day_view_json_returns_cards(tmp_path: Path) -> None:
    day_view_path = tmp_path / "day_view.json"
    outcomes_path = tmp_path / "outcomes.json"
    day_view_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-05T00:00:00Z",
                "environment": "staging",
                "cards": [
                    {
                        "fixture_id": "fixture-1",
                        "decision_tier": "ANALYSIS_PICK",
                        "data_status": "READY",
                        "outcome_tracked": True,
                        "card_hash": "h",
                        "expected_card_hash": "h",
                        "capture_hash": "capture-1",
                        "pick": {
                            "market": "TOTALS",
                            "selection": "OVER",
                            "estimate_id": "fme-1",
                            "quote_id": "mq-1",
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    outcomes_path.write_text(
        json.dumps(
            [
                {
                    "fixture_id": "fixture-1",
                    "market": "TOTALS",
                    "selection": "OVER",
                    "recommendation_scope": "VALIDATION",
                    "strategy_version": "DECISION_CONTRACT_V2",
                    "estimate_id": "fme-1",
                    "quote_id": "mq-1",
                    "source_capture_hash": "capture-1",
                    "result_status": "FINAL",
                    "score": "1-0",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--football-day",
            "2026-07-05",
            "--env",
            "staging",
            "--day-view-json",
            str(day_view_path),
            "--outcomes-json",
            str(outcomes_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["replay_status"] == "READY"
    assert payload["cards"][0]["fixture_id"] == "fixture-1"
    assert payload["cards"][0]["hash_status"] == "PASS"
    assert payload["cards"][0]["outcome"]["score"] == "1-0"
