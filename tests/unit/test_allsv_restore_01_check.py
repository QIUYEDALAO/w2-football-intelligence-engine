from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_allsv_restore_01",
    ROOT / "scripts/check_allsv_restore_01.py",
)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
EVIDENCE = (
    ROOT / "docs/review_packages/ALLSV_RESTORE_01" / "ALLSV_RESTORE_01_EVIDENCE_20260824.json"
)


def test_check_accepts_frozen_evidence() -> None:
    CHECKER.check(EVIDENCE)


def test_check_rejects_single_field_1e6_mutation(tmp_path: Path) -> None:
    evidence = json.loads(EVIDENCE.read_text())
    evidence["current_30d_health"]["coverage_percent"] += 0.000001
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(evidence))

    with pytest.raises(AssertionError, match="EVIDENCE_SHA256_MISMATCH"):
        CHECKER.check(mutated)
