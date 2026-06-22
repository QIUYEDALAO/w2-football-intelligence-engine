from __future__ import annotations

from w2.infrastructure import persistence as _persistence
from w2.infrastructure.database import Base


def test_stage9a_tables_are_registered() -> None:
    assert _persistence.ShadowStrategyRunModel is not None
    expected = {
        "shadow_strategy_run",
        "shadow_strategy_candidate",
        "shadow_strategy_lock",
        "shadow_strategy_event",
        "shadow_strategy_settlement",
        "shadow_strategy_evaluation",
    }
    assert expected.issubset(Base.metadata.tables)
