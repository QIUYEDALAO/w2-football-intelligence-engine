from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import (
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
)
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository


def _team(team_id: int, offset: int) -> dict[str, object]:
    return {
        "team": {"id": team_id},
        "formation": "4-3-3",
        "startXI": [
            {
                "player": {
                    "id": offset + index,
                    "name": f"Player {offset + index}",
                    "number": index + 1,
                    "pos": "G" if index == 0 else "M",
                    "grid": f"{index // 4 + 1}:{index % 4 + 1}",
                }
            }
            for index in range(11)
        ],
        "substitutes": [],
    }


def test_lineup_materialization_is_atomic_structured_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    payload = {"response": [_team(10, 100), _team(20, 200)]}
    assert repository.save_lineup_snapshots(
        fixture_id="fixture-1",
        captured_at=captured_at,
        raw_sha256="a" * 64,
        payload=payload,
    ) == 2
    assert repository.save_lineup_snapshots(
        fixture_id="fixture-1",
        captured_at=captured_at,
        raw_sha256="a" * 64,
        payload=payload,
    ) == 0
    with Session(engine) as session:
        snapshots = session.scalars(select(StructuredLineupSnapshotModel)).all()
        player_count = session.scalar(select(func.count(StructuredLineupPlayerModel.id)))
    assert len(snapshots) == 2
    assert all(snapshot.confirmed for snapshot in snapshots)
    assert player_count == 22


def test_lineup_materialization_rejects_one_team_without_visible_partial_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    try:
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=datetime(2026, 7, 19, tzinfo=UTC),
            raw_sha256="b" * 64,
            payload={"response": [_team(10, 100)]},
        )
    except Exception as exc:
        assert str(exc) == "LINEUP_TEAMS_INCOMPLETE"
    else:
        raise AssertionError("incomplete two-team lineup must fail closed")
    with Session(engine) as session:
        assert session.scalar(select(func.count(StructuredLineupSnapshotModel.id))) == 0
