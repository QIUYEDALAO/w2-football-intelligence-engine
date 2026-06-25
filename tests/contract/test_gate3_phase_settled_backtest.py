from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/W2_GATE3_PHASE_SETTLED_BACKTEST.json"


def test_gate3_phase_settled_backtest_report_schema() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_gate3_phase_settled_backtest.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "W2_GATE3_PHASE_SETTLED_BACKTEST_V1"
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["leakage_check"]["status"] == "PASS"
    assert payload["phase_count"] == len(payload["phases"])
    assert payload["phases"]
    for phase in payload["phases"].values():
        assert phase["status"] in {"SETTLED_DATA_AVAILABLE", "NO_SETTLED_DATA"}
        if phase["settled_observation_count"] == 0:
            assert phase["status"] == "NO_SETTLED_DATA"
        else:
            assert phase["settlement_distribution"]
