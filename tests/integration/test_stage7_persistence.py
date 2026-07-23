from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage7_model_tables_are_registered() -> None:
    for table in {
        "model_experiment",
        "model_artifact",
        "calibration_artifact",
        "model_evaluation",
    }:
        assert table in Base.metadata.tables
