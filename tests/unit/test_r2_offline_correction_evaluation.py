from __future__ import annotations

import json
from pathlib import Path

import pytest

from w2.models.correction_evaluation import (
    CorrectionEvaluationConfig,
    evaluate_r2_corrections,
    load_fixed_snapshot,
    stable_evaluation_hash,
)

FIXTURE = Path("tests/fixtures/gate4/dixon_coles_matches.json")


def test_r2_evaluation_is_deterministic_and_keeps_candidate_in_shadow() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = load_fixed_snapshot(raw)
    config = CorrectionEvaluationConfig(bootstrap_samples=100)

    first = evaluate_r2_corrections(records, config=config)
    second = evaluate_r2_corrections(records, config=config)

    assert stable_evaluation_hash(first) == stable_evaluation_hash(second)
    assert first["evaluation_status"] == "SHADOW_CANDIDATE_ONLY"
    assert first["promotion"] == {
        "champion_changed": False,
        "recommend_lock_changed": False,
        "production_changed": False,
    }
    assert first["split"]["train_count"] == 12
    assert first["split"]["validation_count"] == 12
    assert first["coverage"] == {"baseline": 1.0, "candidate": 1.0}


def test_r2_evaluation_exposes_feature_fix_without_claiming_metric_gain() -> None:
    records = load_fixed_snapshot(json.loads(FIXTURE.read_text(encoding="utf-8")))
    report = evaluate_r2_corrections(
        records,
        config=CorrectionEvaluationConfig(bootstrap_samples=100),
    )

    assert report["feature_change"]["rolling_form_rows_changed"] > 0
    assert report["feature_change"]["prediction_rows_changed"] == 0
    assert set(report["metrics"]["candidate_minus_baseline"].values()) == {0.0}
    assert all(
        interval == {"mean_delta": 0.0, "ci_low": 0.0, "ci_high": 0.0}
        for interval in report["paired_bootstrap"].values()
    )
    assert report["interpretation"]["not_production_hit_rate"] is True
    assert "hit rate" not in report["interpretation"]["claim"].lower()


def test_r2_evaluation_rejects_identity_and_split_errors() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="unique"):
        load_fixed_snapshot([raw[0], raw[0]])
    records = load_fixed_snapshot(raw)
    with pytest.raises(ValueError, match="train_size"):
        evaluate_r2_corrections(
            records,
            config=CorrectionEvaluationConfig(train_size=len(records)),
        )
