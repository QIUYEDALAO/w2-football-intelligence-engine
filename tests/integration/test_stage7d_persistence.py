from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage7d_operational_tables_registered() -> None:
    expected = {
        "forward_cycle_checkpoint",
        "forward_scheduler_run",
        "forward_state_transition",
        "forward_operational_alert",
    }
    assert expected.issubset(Base.metadata.tables)
