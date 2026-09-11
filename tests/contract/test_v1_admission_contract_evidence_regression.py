from __future__ import annotations

import json
from pathlib import Path

from w2.domain.admission_contract import economic_admission_pass

ROOT = Path(__file__).resolve().parents[2]
AUDIT = (
    ROOT
    / "docs/review_packages/V1_RECALIBRATION_EVIDENCE_01"
    / "ADMISSION_RELATIVE_ACCURACY_AUDIT.json"
)


def test_unified_cashflow_contract_resolves_the_two_persisted_drift_rows() -> None:
    rows = json.loads(AUDIT.read_text(encoding="utf-8"))["rows"]
    candidates = [row for row in rows if row["candidate"]]
    rejected = {
        row["evaluation_id"]
        for row in candidates
        if not economic_admission_pass(
            expected_value=float(row["ev"]),
            ev_minus_se=float(row["ev_minus_se"]),
            cashflow_price_edge=float(row["cashflow_price_edge"]),
        )
    }

    assert len(candidates) == 110
    assert sum(float(row["delta"]) >= 0.05 for row in candidates) == 110
    assert len(candidates) - len(rejected) == 108
    assert rejected == {
        "dqe-ada31d6b49b987dbf5afc6ada76174a178988f4eaafc999a72b173d1028a311c",
        "dqe-2d64ca9de9c6556c67e592b5a90cb189023e16cb1e9dc2daf17c4f36ecb0adbe",
    }
