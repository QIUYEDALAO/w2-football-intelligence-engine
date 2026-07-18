from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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
        "team": {"id": team_id, "name": f"Team {team_id}"},
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
    assert (
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=captured_at,
            raw_sha256="a" * 64,
            payload=payload,
        )
        == 2
    )
    assert (
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=captured_at,
            raw_sha256="a" * 64,
            payload=payload,
        )
        == 0
    )
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


def test_saved_lineup_materializer_is_bounded_provider_free_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    payload = {
        "endpoint": "lineups",
        "parameters": {"fixture": "fixture-saved"},
        "response": [_team(10, 100), _team(20, 200)],
    }
    repository.save_raw_payload(
        sha256="e" * 64,
        endpoint="lineups",
        captured_at=captured_at,
        payload=payload,
    )
    repository.save_raw_payload(
        sha256="f" * 64,
        endpoint="lineups",
        captured_at=captured_at,
        payload={"endpoint": "lineups", "response": [_team(10, 100), _team(20, 200)]},
    )
    assert repository.stored_lineup_materialization_candidates(limit=0) == []
    assert len(repository.stored_lineup_materialization_candidates(limit=10)) == 1
    first = repository.materialize_stored_lineup_payloads(limit=10)
    second = repository.materialize_stored_lineup_payloads(limit=10)
    assert first == {
        "candidate_payload_count": 1,
        "materialized_snapshot_count": 2,
        "skipped_incomplete_count": 0,
        "provider_calls": 0,
    }
    assert second == {
        "candidate_payload_count": 1,
        "materialized_snapshot_count": 0,
        "skipped_incomplete_count": 0,
        "provider_calls": 0,
    }


def test_transfermarkt_snapshot_enables_team_scoped_identity_and_value_gate() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    observed_at = datetime(2026, 7, 18, tzinfo=UTC)
    rows = []
    for team_id, offset in ((10, 100), (20, 200)):
        for index in range(11):
            rows.append(
                {
                    "transfermarkt_player_id": f"tm-{offset + index}",
                    "player_name": f"Player {offset + index}",
                    "normalized_name": f"player{offset + index}",
                    "current_club_id": f"club-{team_id}",
                    "current_club_name": f"Team {team_id}",
                    "competition_code": "GB1",
                    "position": "Goalkeeper" if index == 0 else "Midfield",
                    "sub_position": None,
                    "market_value_eur": Decimal("1000000"),
                    "source_sha256": "c" * 64,
                    "observed_at": observed_at,
                }
            )
    import_args = {
        "source_url": "https://example.invalid/players.csv.gz",
        "source_sha256": "c" * 64,
        "observed_at": observed_at,
        "rows": rows,
    }
    assert repository.import_transfermarkt_player_snapshot(**import_args) == 22
    assert repository.import_transfermarkt_player_snapshot(**import_args) == 0
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    repository.save_lineup_snapshots(
        fixture_id="fixture-mapped",
        captured_at=captured_at,
        raw_sha256="d" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
    )
    evidence = repository.lineup_gate_evidence(fixture_id="fixture-mapped", as_of=captured_at)
    assert evidence["status"] == "COMPLETE"
    assert evidence["uniquely_mapped_starters"] == 22
    assert evidence["valued_starters"] == 22
