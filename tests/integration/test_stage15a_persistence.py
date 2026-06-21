from __future__ import annotations

from w2.infrastructure import persistence as _persistence
from w2.infrastructure.database import Base


def test_stage15a_tables_are_registered() -> None:
    assert _persistence.OperationsCycleModel is not None
    expected = {
        "operations_cycle",
        "operations_check_result",
        "release_candidate",
        "release_audit",
        "retention_audit",
        "dependency_risk",
    }
    assert expected.issubset(Base.metadata.tables)
