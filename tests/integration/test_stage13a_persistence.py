from __future__ import annotations

from w2.infrastructure import persistence as _persistence
from w2.infrastructure.database import Base


def test_stage13a_tables_are_registered() -> None:
    assert _persistence.TournamentProfileModel is not None
    expected = {
        "tournament_profile",
        "tournament_operations_plan",
        "tournament_readiness_audit",
    }
    assert expected.issubset(Base.metadata.tables)
