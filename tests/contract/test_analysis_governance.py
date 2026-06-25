from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_analysis_governance_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_w2_analysis_governance.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "analysis governance PASS" in result.stdout
