from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.factor_model.remediation import (
    PROVIDER_PRIMARY_READY,
    FactorModelRemediationConfig,
    FactorModelRemediationService,
    history_rows_from_fixture,
    provider_teams_from_fixtures,
    stable_w2_team_id,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence import (  # noqa: F401
    CanonicalTeamMatchHistoryModel,
    CanonicalTeamModel,
    MatchdayFixtureIdentityModel,
    ProviderTeamIdentityCrosswalkModel,
    TeamRatingSnapshotModel,
)
from w2.matchday.intake_v2 import stable_hash


def test_provider_primary_identity_seeds_canonical_teams_and_updates_fixtures() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 21, tzinfo=UTC)
    with Session(engine) as session:
        session.add(_fixture("1494224", "367", "377", "BK Hacken", "AIK Stockholm", now))
        session.add(_fixture("1494218", "363", "370", "Hammarby FF", "Sirius", now))
        session.commit()

    result = FactorModelRemediationService(
        engine=engine,
        config=FactorModelRemediationConfig(),
        now=now,
    ).seed_provider_primary_identity()

    assert result == {
        "canonical_team_count": 4,
        "provider_crosswalk_count": 4,
        "fixture_identity_ready_count": 2,
    }
    with Session(engine) as session:
        teams = session.scalars(select(CanonicalTeamModel)).all()
        assert {team.w2_team_id for team in teams} == {
            stable_w2_team_id("367"),
            stable_w2_team_id("377"),
            stable_w2_team_id("363"),
            stable_w2_team_id("370"),
        }
        fixture = session.get(MatchdayFixtureIdentityModel, "api_football:1494224")
        assert fixture is not None
        assert fixture.team_identity_status == PROVIDER_PRIMARY_READY
        assert fixture.home_w2_team_id == stable_w2_team_id("367")
        crosswalk = session.get(
            ProviderTeamIdentityCrosswalkModel,
            "api_football:367:allsvenskan:2026",
        )
        assert crosswalk is not None
        assert crosswalk.identity_status == PROVIDER_PRIMARY_READY


def test_provider_team_extraction_uses_fixture_identity_hashes_as_evidence() -> None:
    now = datetime(2026, 7, 21, tzinfo=UTC)
    fixture = _fixture("1494224", "367", "377", "BK Hacken", "AIK Stockholm", now)

    teams = provider_teams_from_fixtures([fixture])

    assert teams[0]["provider_team_id"] == "367"
    assert teams[0]["display_name"] == "BK Hacken"
    assert teams[0]["evidence_hashes"] == [fixture.identity_hash]


def test_history_rows_are_provider_primary_and_rating_materializes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 21, tzinfo=UTC)
    service = FactorModelRemediationService(
        engine=engine,
        config=FactorModelRemediationConfig(),
        now=now,
    )
    with Session(engine) as session:
        session.add(_fixture("1494224", "367", "377", "BK Hacken", "AIK Stockholm", now))
        session.commit()
    service.seed_provider_primary_identity()
    mapping = {"367": stable_w2_team_id("367"), "377": stable_w2_team_id("377")}
    rows = []
    for index in range(2):
        rows.extend(
            history_rows_from_fixture(
                _finished_fixture(
                    str(9000 + index),
                    "367",
                    "377",
                    now - timedelta(days=7 + index),
                    2,
                    index,
                ),
                competition_id="allsvenskan",
                season="2026",
                source_raw_hash="a" * 64,
                endpoint_capture_id=None,
                captured_at=now,
                provider_to_w2=mapping,
            )
        )
    with Session(engine) as session:
        session.add_all(CanonicalTeamMatchHistoryModel(**row) for row in rows)
        session.commit()

    assert service.materialize_ratings() == 2
    with Session(engine) as session:
        ratings = session.scalars(select(TeamRatingSnapshotModel)).all()
        assert len(ratings) == 2
        assert {rating.source for rating in ratings} == {"internal_elo_v1"}


def _fixture(
    provider_fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    home_name: str,
    away_name: str,
    now: datetime,
) -> MatchdayFixtureIdentityModel:
    payload = {
        "fixture": {"id": int(provider_fixture_id), "date": now.isoformat()},
        "teams": {
            "home": {"id": int(home_team_id), "name": home_name},
            "away": {"id": int(away_team_id), "name": away_name},
        },
    }
    identity_hash = stable_hash(payload)
    return MatchdayFixtureIdentityModel(
        fixture_id=f"api_football:{provider_fixture_id}",
        provider="api_football",
        provider_fixture_id=provider_fixture_id,
        competition_id="allsvenskan",
        provider_league_id="113",
        season="2026",
        kickoff_utc=now + timedelta(days=1),
        fixture_status="NS",
        home_provider_team_id=home_team_id,
        away_provider_team_id=away_team_id,
        home_w2_team_id=None,
        away_w2_team_id=None,
        team_identity_status="REVIEW_REQUIRED",
        raw_payload_sha256=identity_hash,
        endpoint_capture_id=None,
        captured_at=now,
        identity_hash=identity_hash,
        payload=payload,
    )


def _finished_fixture(
    provider_fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    kickoff: datetime,
    home_goals: int,
    away_goals: int,
) -> dict[str, object]:
    return {
        "fixture": {
            "id": int(provider_fixture_id),
            "date": kickoff.isoformat().replace("+00:00", "Z"),
            "status": {"short": "FT"},
        },
        "teams": {
            "home": {"id": int(home_team_id), "name": home_team_id},
            "away": {"id": int(away_team_id), "name": away_team_id},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }
