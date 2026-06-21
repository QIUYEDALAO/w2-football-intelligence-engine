from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage7b_tables_are_registered() -> None:
    for table in {
        "challenger_model",
        "forward_holdout_run",
        "forward_prediction_lock",
        "forward_evaluation",
    }:
        assert table in Base.metadata.tables
