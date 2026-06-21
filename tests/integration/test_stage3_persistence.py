from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import (
    BookmakerModel,
    CompetitionModel,
    FixtureModel,
    OddsObservationModel,
    ProviderEntityMappingModel,
    RawPayloadReferenceModel,
    RecommendationLockModel,
    RecommendationModel,
    ResultModel,
    SeasonModel,
    SettlementModel,
    StageModel,
    TeamModel,
)

NOW = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)
DIGEST = "b" * 64


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def _fixture_graph(session: Session) -> tuple[FixtureModel, BookmakerModel]:
    competition = CompetitionModel(name="synthetic competition")
    home = TeamModel(name="synthetic home")
    away = TeamModel(name="synthetic away")
    session.add_all([competition, home, away])
    session.flush()
    season = SeasonModel(
        competition_id=competition.id,
        name="synthetic season",
        start_date=NOW,
        end_date=NOW,
    )
    session.add(season)
    session.flush()
    stage = StageModel(season_id=season.id, name="synthetic stage", order_index=1)
    bookmaker = BookmakerModel(name="synthetic bookmaker")
    session.add_all([stage, bookmaker])
    session.flush()
    fixture = FixtureModel(
        competition_id=competition.id,
        season_id=season.id,
        stage_id=stage.id,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_at=NOW,
        status="SCHEDULED",
    )
    session.add(fixture)
    session.flush()
    return fixture, bookmaker


def test_relationships_and_unique_constraints(session: Session) -> None:
    fixture, bookmaker = _fixture_graph(session)
    odds = OddsObservationModel(
        fixture_id=fixture.id,
        bookmaker_id=bookmaker.id,
        market="TOTALS",
        selection="OVER",
        line=Decimal("2.25"),
        decimal_odds=Decimal("1.9000"),
        suspended=False,
        live=False,
        stale=False,
        provider_updated_at=NOW,
        captured_at=NOW,
        raw_label="O 2.25",
        canonical_selection="OVER",
        settlement_rule="total_goals",
    )
    session.add(odds)
    session.commit()
    assert session.get(FixtureModel, fixture.id).odds_observations[0].canonical_selection == "OVER"

    duplicate = OddsObservationModel(
        fixture_id=fixture.id,
        bookmaker_id=bookmaker.id,
        market="TOTALS",
        selection="OVER",
        line=Decimal("2.25"),
        decimal_odds=Decimal("1.9000"),
        suspended=False,
        live=False,
        stale=False,
        provider_updated_at=NOW,
        captured_at=NOW,
        raw_label="O 2.25",
        canonical_selection="OVER",
        settlement_rule="total_goals",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()


def test_provider_mapping_unique_constraint(session: Session) -> None:
    mapping = ProviderEntityMappingModel(
        entity_type="team",
        entity_id="00000000-0000-0000-0000-000000000001",
        provider="synthetic",
        external_id="external-1",
        source="provider payload",
        confidence=Decimal("0.9000"),
        valid_from=NOW,
    )
    duplicate = ProviderEntityMappingModel(
        entity_type="team",
        entity_id="00000000-0000-0000-0000-000000000002",
        provider="synthetic",
        external_id="external-1",
        source="provider payload",
        confidence=Decimal("0.9000"),
        valid_from=NOW,
    )
    session.add_all([mapping, duplicate])
    with pytest.raises(IntegrityError):
        session.commit()


def test_raw_payload_and_recommendation_lock_are_not_updatable(session: Session) -> None:
    raw = RawPayloadReferenceModel(
        provider="synthetic",
        object_uri="object://payload",
        sha256=DIGEST,
        captured_at=NOW,
        immutable=True,
    )
    session.add(raw)
    session.commit()
    raw.object_uri = "object://changed"
    with pytest.raises(ValueError):
        session.commit()
    session.rollback()

    fixture, _bookmaker = _fixture_graph(session)
    recommendation = RecommendationModel(
        fixture_id=fixture.id,
        prediction_id=None,
        status="LOCKED",
        created_at=NOW,
    )
    session.add(recommendation)
    session.flush()
    lock = RecommendationLockModel(
        recommendation_id=recommendation.id,
        status="LOCKED",
        locked_at=NOW,
        reason="synthetic",
    )
    session.add(lock)
    session.commit()
    lock.reason = "changed"
    with pytest.raises(ValueError):
        session.commit()


def test_settlement_requires_existing_result_and_recommendation(session: Session) -> None:
    fixture, _bookmaker = _fixture_graph(session)
    recommendation = RecommendationModel(
        fixture_id=fixture.id,
        prediction_id=None,
        status="LOCKED",
        created_at=NOW,
    )
    result = ResultModel(fixture_id=fixture.id, home_goals=1, away_goals=1, confirmed_at=NOW)
    session.add_all([recommendation, result])
    session.flush()
    settlement = SettlementModel(
        recommendation_id=recommendation.id,
        result_id=result.id,
        outcome="PUSH",
        settled_at=NOW,
    )
    session.add(settlement)
    session.commit()
    assert session.get(SettlementModel, settlement.id).result.home_goals == 1
