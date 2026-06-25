from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "markets" / "W2_1X2_AGGREGATE_SEMANTICS_V1.md"


def test_gate3_1x2_aggregate_semantics_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_gate3_1x2_aggregate_semantics.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_gate3_1x2_aggregate_doc_keeps_gate_partial_and_source_scoped() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "aggregate market baseline backtests" in text
    assert "as-of samples" in text
    assert "This limitation is source-specific" in text
    assert "Gate3 remains `PARTIAL`" in text
    assert "UNKNOWN_PREMATCH_AGGREGATE_NOT_AS_OF" in text
