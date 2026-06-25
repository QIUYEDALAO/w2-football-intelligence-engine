from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.run_gate5_retrospective_replay import REPORT, run_replay

ROOT = Path(__file__).resolve().parents[2]


def test_gate5_retrospective_replay_machine_contract() -> None:
    report = run_replay()

    assert report["schema_version"] == "W2_GATE5_RETROSPECTIVE_REPLAY_V1"
    assert report["mode"] == "RETROSPECTIVE"
    assert report["retrospective_not_forward"] is True
    assert report["gate5_acceptance"] == "NOT_REQUESTED_FORWARD_EVIDENCE_REQUIRED"
    assert report["candidate"] is False
    assert report["formal_recommendation"] is False
    assert report["recommendation_emitted"] is False
    assert report["watch_count"] >= 1
    assert report["skip_count"] >= 1
    assert report["lock_immutability_verified"] is True
    assert report["settlement_replay_verified"] is True
    assert report["shadow_db_audit"]["status"] == "PASS"
    assert report["shadow_db_audit"]["dirty_write_count"] == 0
    assert all(item["recommendation"] is None for item in report["fixtures"])
    assert all(item["retrospective_not_forward"] is True for item in report["fixtures"])


def test_gate5_retrospective_replay_cli_writes_report() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "scripts/run_gate5_retrospective_replay.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "RECOMMENDATION_EMITTED=false" in result.stdout
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["mode"] == "RETROSPECTIVE"
    assert report["recommendation_emitted"] is False
