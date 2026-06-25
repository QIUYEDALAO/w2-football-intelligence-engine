from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.run_gate4_dc_walkforward import REPORT, build_report

ROOT = Path(__file__).resolve().parents[2]


def test_gate4_dc_walkforward_report_is_reproducible_and_leakage_safe() -> None:
    first = build_report()
    second = build_report()
    first["generated_at"] = "NORMALIZED"
    second["generated_at"] = "NORMALIZED"

    assert first == second
    assert first["schema_version"] == "W2_GATE4_DC_WALKFORWARD_V1"
    assert first["candidate"] is False
    assert first["formal_recommendation"] is False
    assert first["gate4_decision"] == "NOT_REQUESTED"
    assert first["fold_count"] > 0
    assert first["leakage_check"]["status"] == "PASS"
    assert first["leakage_check"]["random_split_used"] is False
    assert first["leakage_check"]["closing_or_result_used_as_feature"] is False


def test_gate4_dc_walkforward_cli_writes_honest_verdict() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "scripts/run_gate4_dc_walkforward.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    delta = report["bootstrap_95ci_model_minus_market_log_loss"]
    expected = (
        "BEATEN"
        if report["model_metrics"]["log_loss"] < report["market_baseline_metrics"]["log_loss"]
        and delta["ci_high"] < 0
        and report["model_metrics"]["ece"] <= report["market_baseline_metrics"]["ece"]
        else "NOT_BEATEN"
    )
    assert report["verdict"] == expected
    assert report["verdict"] in {"BEATEN", "NOT_BEATEN"}
