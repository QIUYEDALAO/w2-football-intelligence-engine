"""Manual V4 writers refuse the request before opening a database."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _invoke(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, *args], cwd=ROOT,
        env={**os.environ, "W2_DATABASE_URL": "postgresql+psycopg://invalid:invalid@127.0.0.1:1/none"},
        capture_output=True, text=True, check=False,
    )


def test_old_validation_backfill_default_refuses_before_database_access() -> None:
    result = _invoke("scripts/backfill_validation_samples.py")
    assert result.returncode == 2
    assert "LEGACY_AH_OU_VALIDATION_WRITER_RETIRED" in result.stderr
    assert "Connection refused" not in result.stderr


def test_old_outcome_cli_write_refuses_before_database_access() -> None:
    result = _invoke("scripts/run_w2_forward_outcome_ledger.py", "--write-db", "--no-dry-run")
    assert result.returncode == 2
    assert "LEGACY_AH_OU_OUTCOME_WRITER_RETIRED" in result.stderr
    assert "Connection refused" not in result.stderr
