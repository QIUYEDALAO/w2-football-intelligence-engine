from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage10a_read_api_tables_registered() -> None:
    expected = {
        "read_model_checkpoint",
        "future_refresh_task_audit",
        "future_refresh_run_audit",
        "raw_payload",
        "shadow_strategy_run",
        "shadow_strategy_lock",
        "shadow_strategy_evaluation",
    }
    assert expected.issubset(Base.metadata.tables)
