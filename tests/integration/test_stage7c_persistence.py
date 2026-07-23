from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage7c_tables_are_registered() -> None:
    assert "forward_market_snapshot" in Base.metadata.tables
