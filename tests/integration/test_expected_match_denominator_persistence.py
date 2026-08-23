from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import (
    ExpectedMatchFixtureMaterializationModel,
    ExpectedMatchFixtureObservationModel,
    RawPayloadModel,
)
from w2.infrastructure.persistence.league_models import LeagueSeasonModel
from w2.ingestion.expected_match_materialization import (
    add_expected_match_fixture_materialization,
)
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.matchday.repository import MatchdayRuntimeRepository

AS_OF = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _configure(monkeypatch: Any, tmp_path: Path):  # type: ignore[no-untyped-def]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'expected-match.db'}"
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            LeagueSeasonModel(
                id="premier-league-2026",
                competition_id="premier_league",
                season="2026",
                lifecycle="ACTIVE",
                payload={"enabled": True, "provider_league_id": "39"},
            )
        )
        session.commit()
    return engine


def _payload(
    fixture_id: int,
    kickoff: datetime,
    status: str,
    *,
    season: int = 2026,
    home_team_id: int = 10,
    away_team_id: int = 20,
) -> dict[str, object]:
    return {
        "response": [
            {
                "fixture": {
                    "id": fixture_id,
                    "date": kickoff.isoformat(),
                    "status": {"short": status},
                },
                "league": {"id": 39, "season": season},
                "teams": {
                    "home": {"id": home_team_id},
                    "away": {"id": away_team_id},
                },
                "goals": {
                    "home": 1 if status == "FT" else None,
                    "away": 0 if status == "FT" else None,
                },
            }
        ]
    }


def test_fixture_raw_write_materializes_denominator_in_same_transaction(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    repository = MatchdayRuntimeRepository(engine=engine)

    assert repository.save_raw_payload(
        sha256="f" * 64,
        endpoint="fixtures",
        captured_at=AS_OF,
        payload=_payload(999, AS_OF - timedelta(days=1), "FT"),
    )

    with Session(engine) as session:
        assert session.get(ExpectedMatchFixtureMaterializationModel, "f" * 64) is not None
        observation = session.scalar(
            select(ExpectedMatchFixtureObservationModel)
        )
        assert observation is not None
        assert observation.canonical_fixture_id == "api_football:999"


def test_fixture_identity_conflict_across_saved_raw_is_rejected(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    repository = MatchdayRuntimeRepository(engine=engine)
    payload = _payload(997, AS_OF - timedelta(days=1), "FT")

    assert repository.save_raw_payload(
        sha256="a" * 64,
        endpoint="fixtures",
        captured_at=AS_OF - timedelta(hours=1),
        payload=payload,
    )
    assert repository.save_raw_payload(
        sha256="b" * 64,
        endpoint="fixtures",
        captured_at=AS_OF,
        payload=_payload(
            997,
            AS_OF - timedelta(days=1),
            "FT",
            away_team_id=21,
        ),
    )

    with Session(engine) as session:
        observations = list(session.scalars(select(ExpectedMatchFixtureObservationModel)))
        state = session.get(ExpectedMatchFixtureMaterializationModel, "b" * 64)

    assert len(observations) == 1
    assert observations[0].away_provider_team_id == "20"
    assert state is not None
    assert state.status == "REJECTED"
    assert state.rejection_samples == [
        {
            "reason": "CANONICAL_PROVIDER_FIXTURE_IDENTITY_CONFLICT",
            "sample": "997",
        }
    ]


def test_unknown_source_insertion_time_is_rejected_not_backdated(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    raw = RawPayloadModel(
        sha256="e" * 64,
        endpoint="fixtures",
        captured_at=AS_OF - timedelta(days=30),
        inserted_at=None,
        storage_uri="db://raw_payload/unknown-inserted-at",
        payload=_payload(998, AS_OF - timedelta(days=31), "FT"),
    )
    with Session(engine) as session:
        session.add(raw)
        added, rejected = add_expected_match_fixture_materialization(
            session,
            raw,
            materialized_at=AS_OF,
        )
        session.commit()
        state = session.get(ExpectedMatchFixtureMaterializationModel, "e" * 64)

    assert (added, rejected) == (0, 1)
    assert state is not None
    assert state.status == "REJECTED"
    assert state.source_inserted_at is None
    assert state.rejection_samples == [{"reason": "SOURCE_INSERTED_AT_UNAVAILABLE"}]


def _insert_observation(
    engine: Any,
    *,
    fixture_id: int,
    kickoff: datetime,
    status: str,
    captured_at: datetime,
    inserted_at: datetime,
    season: int = 2026,
) -> None:
    digest = f"{fixture_id:064x}"[-64:]
    with Session(engine) as session:
        raw = RawPayloadModel(
            sha256=digest,
            endpoint="fixtures",
            captured_at=captured_at,
            inserted_at=inserted_at,
            storage_uri=f"db://raw_payload/{digest}",
            payload=_payload(fixture_id, kickoff, status, season=season),
        )
        session.add(raw)
        add_expected_match_fixture_materialization(
            session,
            raw,
            materialized_at=inserted_at,
        )
        session.commit()


def test_latest_twenty_cross_season_boundary_without_reset(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    for offset in (30, 40, 50):
        _insert_observation(
            engine,
            fixture_id=3000 + offset,
            kickoff=AS_OF - timedelta(days=offset),
            status="FT",
            captured_at=AS_OF - timedelta(days=offset - 1),
            inserted_at=AS_OF - timedelta(days=offset - 1),
            season=2025,
        )
    repository = FutureRefreshDbRepository(engine=engine)

    result = repository.expected_match_denominators_for_teams(
        ["10"],
        before=AS_OF,
        competition_id="premier_league",
        season="2026",
    )[0]

    assert result["status"] == "AVAILABLE"
    assert result["expected_match_count"] == 3


def test_saved_raw_materialization_is_bounded_and_provider_zero(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    for fixture_id in (4001, 4002):
        with Session(engine) as session:
            session.add(
                RawPayloadModel(
                    sha256=f"{fixture_id:064x}",
                    endpoint="fixtures",
                    captured_at=AS_OF - timedelta(days=2),
                    inserted_at=AS_OF - timedelta(days=2),
                    storage_uri=f"db://raw_payload/{fixture_id}",
                    payload=_payload(fixture_id, AS_OF - timedelta(days=3), "FT"),
                )
            )
            session.commit()
    repository = FutureRefreshDbRepository(engine=engine)

    first = repository.materialize_saved_expected_match_fixtures(
        as_of=AS_OF,
        limit=1,
    )
    second = repository.materialize_saved_expected_match_fixtures(
        as_of=AS_OF,
        limit=1,
    )

    assert first == {
        "raw_payloads": 1,
        "observations": 1,
        "rejections": 0,
        "provider_calls": 0,
    }
    assert second == first


def test_disabled_competition_denominator_is_fail_closed(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    with Session(engine) as session:
        league = session.scalar(select(LeagueSeasonModel))
        assert league is not None
        league.payload = {**league.payload, "enabled": False}
        session.commit()
    repository = FutureRefreshDbRepository(engine=engine)

    result = repository.expected_match_denominators_for_teams(
        ["10"],
        before=AS_OF,
        competition_id="premier_league",
        season="2026",
    )[0]

    assert result["status"] == "UNAVAILABLE_FAIL_CLOSED"
    assert result["reason"] == "COMPETITION_NOT_ENABLED"


def test_late_insert_cannot_change_prior_denominator(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    for offset in (3, 4, 5):
        _insert_observation(
            engine,
            fixture_id=1000 + offset,
            kickoff=AS_OF - timedelta(days=offset),
            status="FT",
            captured_at=AS_OF - timedelta(days=offset - 1),
            inserted_at=AS_OF - timedelta(days=offset - 1),
        )
    repository = FutureRefreshDbRepository(engine=engine)
    before = repository.expected_match_denominators_for_teams(
        ["10"],
        before=AS_OF,
        competition_id="premier_league",
        season="2026",
    )[0]

    _insert_observation(
        engine,
        fixture_id=1099,
        kickoff=AS_OF - timedelta(days=1),
        status="FT",
        captured_at=AS_OF - timedelta(hours=1),
        inserted_at=AS_OF + timedelta(hours=1),
    )
    replay = repository.expected_match_denominators_for_teams(
        ["10"],
        before=AS_OF,
        competition_id="premier_league",
        season="2026",
    )[0]

    assert before["status"] == "AVAILABLE"
    assert replay["canonical_fixture_ids"] == before["canonical_fixture_ids"]
    assert "api_football:1099" not in replay["canonical_fixture_ids"]


def test_result_not_visible_at_as_of_is_fail_closed(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    engine = _configure(monkeypatch, tmp_path)
    for offset in (3, 4, 5):
        _insert_observation(
            engine,
            fixture_id=2000 + offset,
            kickoff=AS_OF - timedelta(days=offset),
            status="FT",
            captured_at=AS_OF - timedelta(days=offset - 1),
            inserted_at=AS_OF - timedelta(days=offset - 1),
        )
    _insert_observation(
        engine,
        fixture_id=2099,
        kickoff=AS_OF - timedelta(days=1),
        status="NS",
        captured_at=AS_OF - timedelta(days=2),
        inserted_at=AS_OF - timedelta(days=2),
    )
    repository = FutureRefreshDbRepository(engine=engine)

    result = repository.expected_match_denominators_for_teams(
        ["10"],
        before=AS_OF,
        competition_id="premier_league",
        season="2026",
    )[0]

    assert result["status"] == "UNAVAILABLE_FAIL_CLOSED"
    assert result["reason"] == "EXPECTED_MATCH_RESULT_NOT_VISIBLE_AT_AS_OF"
    assert result["high_confidence_allowed"] is False
