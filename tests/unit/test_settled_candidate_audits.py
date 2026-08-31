from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.audit_settled_candidate_direction_rescore import (
    _direction_from_evaluation,
    _replay_row,
)
from scripts.audit_settled_candidate_inputs import audit


def _evaluation() -> dict[str, object]:
    return {
        "exact_line": 0.5,
        "decimal_odds": 2.0,
        "current_ev": 0.2,
        "model_forecast_capture_identity_hash": "capture-hash",
        "model_input_hash": "input-hash",
        "model_settlement_distribution": {
            "WIN": 0.6,
            "HALF_WIN": 0.0,
            "PUSH": 0.0,
            "HALF_LOSS": 0.0,
            "LOSS": 0.4,
        },
    }


def test_evaluation_distribution_reproduces_direction_and_ev() -> None:
    replay = _direction_from_evaluation("HOME", _evaluation())

    assert replay["higher_probability_side"] == "HOME"
    assert replay["recomputed_ev"] == 0.2
    assert replay["ev_matches"] is True


def test_capture_ladder_cannot_replace_frozen_evaluation_distribution() -> None:
    capture = {
        "capture_identity_hash": "capture-hash",
        "model_input_manifest_hash": "input-hash",
        "ah_settlement_distributions": {
            "ladder": [
                {
                    "home_line": 0.5,
                    "home_settlement_distribution": {
                        "WIN": 0.1,
                        "HALF_WIN": 0.0,
                        "PUSH": 0.0,
                        "HALF_LOSS": 0.0,
                        "LOSS": 0.9,
                    },
                    "away_settlement_distribution": {
                        "WIN": 0.9,
                        "HALF_WIN": 0.0,
                        "PUSH": 0.0,
                        "HALF_LOSS": 0.0,
                        "LOSS": 0.1,
                    },
                }
            ]
        },
    }
    row = _replay_row(
        {
            "evaluation_id": "evaluation-1",
            "fixture_id": "fixture-1",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "evaluated_at": "2026-08-30T12:00:00Z",
            "home_goals": "2",
            "away_goals": "0",
            "result_status": "WIN",
            "evaluation_payload": json.dumps(_evaluation()),
            "model_capture_payload": json.dumps(capture),
        }
    )

    assert row["frozen_evaluation_replay"]["predicted"]["higher_probability_side"] == "HOME"
    assert row["frozen_evaluation_replay"]["predicted"]["ev_matches"] is True


def test_latest_checkpoint_fields_are_explicitly_non_authoritative(tmp_path: Path) -> None:
    checkpoint = {
        "analysis_card": {
            "simulation": {
                "lambda_home": 9.9,
                "lambda_away": 0.1,
                "input_readiness": {"xg_status": "READY"},
                "calibration": {"simulation_input_hash": "later-hash"},
            },
            "feature_contributions": [{"id": "F1", "status": "READY"}],
        }
    }
    capture = {
        "capture_identity_hash": "capture-hash",
        "model_input_manifest_hash": "input-hash",
        "source_artifact_hashes": {"simulation_input_hash": "frozen-hash"},
    }
    source = tmp_path / "settled.csv"
    fields = {
        "evaluation_id": "evaluation-1",
        "fixture_id": "fixture-1",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME",
        "evaluated_at": "2026-08-30T12:00:00Z",
        "capture_at": "2026-08-30T11:59:00Z",
        "home_goals": "2",
        "away_goals": "0",
        "result_status": "WIN",
        "confirmed_at": "2026-08-30T15:00:00Z",
        "checkpoint_created_at": "2026-08-30T12:30:00Z",
        "source_evaluation_id": "later-evaluation",
        "evaluation_payload": json.dumps(_evaluation()),
        "checkpoint_payload": json.dumps(checkpoint),
        "model_capture_payload": json.dumps(capture),
    }
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerow(fields)

    row = audit(source)["rows"][0]

    assert "lambda_home" not in row
    assert "input_readiness" not in row
    assert row["latest_checkpoint_non_authoritative"]["lambda_home"] == 9.9
    assert row["latest_checkpoint_non_authoritative"]["input_readiness"] == {
        "xg_status": "READY"
    }
