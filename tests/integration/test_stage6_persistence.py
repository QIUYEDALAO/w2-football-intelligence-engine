from __future__ import annotations

from w2.infrastructure.database import Base


def test_stage6_market_tables_are_registered() -> None:
    for table in {
        "market_consensus",
        "market_baseline_run",
        "market_fit_diagnostic",
        "market_quality_assessment",
    }:
        assert table in Base.metadata.tables
