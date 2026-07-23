from __future__ import annotations

from w2.infrastructure import persistence as _persistence
from w2.infrastructure.database import Base


def test_stage14a_tables_are_registered() -> None:
    assert _persistence.LeagueProfileModel is not None
    expected = {
        "league_profile",
        "league_season",
        "league_readiness_audit",
    }
    assert expected.issubset(Base.metadata.tables)
