from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from w2.backtest.s2_calibration_validation import (
    S2CalibrationValidationInputs,
    build_s2_calibration_validation_report,
)


def dashboard_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"generated_at": "2026-07-02T00:00:00Z", "all": rows}


def match_row(index: int, *, result: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "fixture_id": f"fixture-{index}",
        "home_team_name": "Alpha" if index % 2 else "Beta",
        "away_team_name": "Gamma" if index % 2 else "Delta",
        "kickoff_utc": (
            datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)
        ).isoformat().replace("+00:00", "Z"),
        "result": result,
        "market_probabilities": {"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3},
        "pricing_shadow": {
            "simulation": {
                "lambda_home": 0.15 if index == 1 else 1.25,
                "lambda_away": 1.1,
                "calibration_version": "w2.formal.lambda_baseline_prior.v1",
                "calibration": {
                    "params": {"minimum_lambda": 0.15, "maximum_lambda": 4.25}
                },
            }
        },
    }


def test_s2_validation_blocks_when_settled_sample_is_insufficient() -> None:
    report = build_s2_calibration_validation_report(
        S2CalibrationValidationInputs(
            payload=dashboard_payload([match_row(1, result={"home_goals": 1, "away_goals": 0})])
        )
    )

    assert report["status"] == "BLOCKED"
    assert report["online_model_changed"] is False
    assert report["provider_calls"] == 0
    assert report["db_writes"] == 0
    assert "INSUFFICIENT_DIXON_COLES_SETTLED_SAMPLE" in report["blockers"]
    assert report["lambda_clipping"]["status"] == "OBSERVED"
    assert report["lambda_clipping"]["rows"][0]["clipped_sides"] == ["home_minimum_lambda"]


def test_s2_validation_fits_dixon_coles_when_sample_available() -> None:
    rows = [
        match_row(1, result={"home_goals": 2, "away_goals": 0}),
        match_row(2, result={"home_goals": 1, "away_goals": 1}),
        match_row(3, result={"home_goals": 0, "away_goals": 1}),
        match_row(4, result={"home_goals": 3, "away_goals": 1}),
    ]

    report = build_s2_calibration_validation_report(
        S2CalibrationValidationInputs(payload=dashboard_payload(rows))
    )

    assert report["dixon_coles"]["status"] == "FIT_READY_FOR_OFFLINE_COMPARISON"
    assert report["dixon_coles"]["fit_sample"] == 4
    assert -0.2 <= report["dixon_coles"]["rho"] <= 0.2
    assert report["dixon_coles"]["log_loss"] is not None
    assert report["simulation_logic_changed"] is False
    assert "INSUFFICIENT_S2_WALK_FORWARD_SAMPLE" in report["blockers"]


def test_s2_validation_cli_input_is_read_only(tmp_path: Path) -> None:
    payload_path = tmp_path / "dashboard.json"
    payload_path.write_text(
        json.dumps(dashboard_payload([match_row(1, result=None)])),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/debug_w2_s2_calibration_validation.py",
            "--input",
            str(payload_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads(result.stdout)

    assert report["read_only"] is True
    assert report["provider_calls"] == 0
    assert report["db_writes"] == 0
    assert report["status"] == "BLOCKED"
