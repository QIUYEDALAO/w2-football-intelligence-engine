from __future__ import annotations

import json

from archive.scripts.run_gate3_ou_multiphase_backtest import REPORT, build_report, main


def test_gate3_ou_multiphase_backtest_report_schema() -> None:
    assert main() == 0
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report == build_report() | {"generated_at": report["generated_at"]}
    assert report["schema_version"] == "W2_GATE3_OU_MULTIPHASE_BACKTEST_V1"
    assert report["candidate"] is False
    assert report["formal_recommendation"] is False
    assert report["market"] == "TOTALS"
    assert report["leakage_check"]["status"] == "PASS"
    assert report["leakage_check"]["closing_rows_in_non_closing_phases"] == 0
    phases = report["phases"]
    assert any(item["phase"] != "Closing" for item in phases)
    assert any(item["phase"] == "Closing" for item in phases)
    assert all(
        item["status"] in {"SETTLED_DATA_AVAILABLE", "NO_SETTLED_DATA"} for item in phases
    )
    assert all(
        item["settled_observation_count"] > 0 or item["blocker"] == "NO_OU_SETTLED_ROWS_FOR_PHASE"
        for item in phases
    )
    assert report["summary"]["non_closing_phase_count"] > 0
