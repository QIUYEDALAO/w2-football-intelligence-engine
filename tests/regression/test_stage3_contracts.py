from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_stage3_checker_passes() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/check_w2_stage3_data_model.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_no_hardcoded_real_teams_leagues_or_fixtures() -> None:
    root = Path(__file__).resolve().parents[2]
    real_world_tokens = [
        "Manchester",
        "Liverpool",
        "Barcelona",
        "Real Madrid",
        "Premier League",
        "World Cup 2026",
    ]
    scanned_paths = [
        *root.glob("src/**/*.py"),
        *[
            path
            for path in root.glob("tests/**/*.py")
            if not path.as_posix().endswith("tests/regression/test_stage3_contracts.py")
        ],
        *root.glob("migrations/**/*.py"),
    ]
    offenders = [
        f"{path}:{token}"
        for path in scanned_paths
        for token in real_world_tokens
        if token in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []
