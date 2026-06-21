from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage8_replay_tables_are_registered() -> None:
    for table in {
        "replay_run",
        "replay_event",
        "replay_checkpoint",
        "prediction_snapshot",
        "evaluation_record",
        "ablation_run",
    }:
        assert table in Base.metadata.tables
