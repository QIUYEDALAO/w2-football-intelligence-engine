from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sc19_package_is_self_checking() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_sc19_team_identity_and_date_strip.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "SC19 team identity and date strip check PASS" in result.stdout
