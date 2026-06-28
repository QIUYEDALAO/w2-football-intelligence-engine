from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_real_mode_cli_writes_report_shape(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_w2_handicap_walkforward.py",
            "--mode",
            "real",
            "--from",
            "2026-06-01",
            "--to",
            "2026-07-31",
            "--output-report",
            str(report_path),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload == json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "real"
    assert payload["sample"]["included"] == payload["samples"]
    assert payload["s2_gate"]["beats_market"] is False
    assert payload["calibration"]["calibration_version"] == "UNVALIDATED"
