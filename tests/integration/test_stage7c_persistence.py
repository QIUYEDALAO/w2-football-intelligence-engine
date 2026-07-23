from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage7c_tables_are_registered() -> None:
    for table in {
        "forward_market_snapshot",
        "forward_gate_audit",
        "forward_cycle_run",
    }:
        assert table in Base.metadata.tables
