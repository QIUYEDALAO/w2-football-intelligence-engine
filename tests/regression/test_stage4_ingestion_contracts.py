from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_stage4_checker_passes() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/check_w2_stage4_ingestion.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_offline_replay_script_passes_without_live() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/replay_provider_fixture.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert '"gate2_status": "PROVISIONAL"' in result.stdout
