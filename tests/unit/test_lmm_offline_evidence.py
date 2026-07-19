from __future__ import annotations

import json
from pathlib import Path


def test_frozen_lmm_evidence_fails_closed_without_canonical_identity_join() -> None:
    report = json.loads(
        Path("docs/operations/W2_V3_08_LMM_OFFLINE_EVALUATION_20260720.json").read_text(
            encoding="utf-8"
        )
    )
    protocol = json.loads(
        Path("config/evaluations/lmm_offline_increment.v1.json").read_text(encoding="utf-8")
    )

    assert report["conclusion"] == "INSUFFICIENT_EVIDENCE"
    assert report["input_evidence"]["team_scoped_identity_mapped_count"] == 0
    assert report["input_evidence"]["canonical_asof_safe_joined_ah_rows"] == 0
    assert report["numeric_effect_enabled"] is False
    assert report["formal_ah_enabled"] is False
    assert protocol["numeric_effect_enabled"] is False
