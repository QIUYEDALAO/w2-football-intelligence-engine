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
from w2.infrastructure.persistence.recommendation_lock_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    build_recommendation_lock_snapshot,
)

NOW = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 6, 22, 3, 0, tzinfo=UTC)
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
        kickoff_at=KICKOFF,
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


def test_recommendation_lock_can_store_reproducible_prematch_snapshot(
    session: Session,
) -> None:
    fixture, _bookmaker = _fixture_graph(session)
    recommendation = RecommendationModel(
        fixture_id=fixture.id,
        prediction_id=None,
        status="LOCKED",
        created_at=NOW,
    )
    session.add(recommendation)
    session.flush()
    card = _formal_card(fixture.id, fixture.kickoff_at)
    lock = build_recommendation_lock_snapshot(
        recommendation_id=recommendation.id,
        card=card,
        locked_at=NOW,
        reason="T-30m formal lock",
        release_sha="release-sha",
    )
    session.add(lock)
    session.commit()

    stored = session.get(RecommendationLockModel, lock.id)
    assert stored.recommendation.id == recommendation.id
    assert stored.fixture_id == fixture.id
    assert stored.reproducible is True
    assert stored.legacy_marker_only is False
    assert stored.snapshot_schema_version == SNAPSHOT_SCHEMA_VERSION
    assert stored.snapshot_payload_json["recommendation"]["selection"] == "HOME_AH"
    assert len(stored.snapshot_payload_hash) == 64
    assert stored.release_sha == "release-sha"
    assert stored.market_timeline_json["label"] == "盘口时间线 · 参照 · 未验证"
    assert stored.ah_settlement_distribution_json["win"] == 0.52
    assert stored.scoreline_top3_json[0]["scoreline"] == "1-0"
    assert stored.data_profile == "real-db"


def test_legacy_recommendation_lock_defaults_to_non_reproducible_marker(
    session: Session,
) -> None:
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
        reason="legacy marker",
    )
    session.add(lock)
    session.commit()

    stored = session.get(RecommendationLockModel, lock.id)
    assert stored.reproducible is False
    assert stored.legacy_marker_only is True
    assert stored.as_of is None
    assert stored.pick_side is None


def test_settlement_requires_existing_result_recommendation_and_can_bind_lock(
    session: Session,
) -> None:
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
    lock = RecommendationLockModel(
        recommendation_id=recommendation.id,
        fixture_id=fixture.id,
        status="LOCKED",
        locked_at=NOW,
        as_of=NOW,
        kickoff_utc=fixture.kickoff_at,
        reason="synthetic",
        tier="FORMAL",
        pick_side="HOME_AH",
        pick_line=Decimal("0.00"),
        market_ah=Decimal("0.00"),
        home_price=Decimal("1.5900"),
        away_price=Decimal("2.3800"),
        reproducible=True,
        legacy_marker_only=False,
        snapshot_schema_version="w2.recommendation_lock_snapshot.v1",
    )
    session.add(lock)
    session.flush()
    settlement = SettlementModel(
        recommendation_id=recommendation.id,
        lock_id=lock.id,
        result_id=result.id,
        outcome="PUSH",
        settled_at=NOW,
        matched_recommendation=True,
        tier="FORMAL",
        movement_pattern="JUMP_LINE",
    )
    session.add(settlement)
    session.commit()
    stored = session.get(SettlementModel, settlement.id)
    assert stored.result.home_goals == 1
    assert stored.lock.id == lock.id
    assert stored.matched_recommendation is True
    assert stored.tier == "FORMAL"

    settlement.outcome = "WIN"
    with pytest.raises(ValueError):
        session.commit()
    session.rollback()

    session.delete(settlement)
    with pytest.raises(ValueError):
        session.commit()


def test_settlement_is_append_only(session: Session) -> None:
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

    settlement.outcome = "WIN"
    with pytest.raises(ValueError):
        session.commit()


def _formal_card(fixture_id: str, kickoff_utc: datetime) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "generated_at": NOW.isoformat().replace("+00:00", "Z"),
        "kickoff_utc": kickoff_utc.isoformat().replace("+00:00", "Z"),
        "home_team_name": "Synthetic Home",
        "away_team_name": "Synthetic Away",
        "competition_name": "Synthetic Cup",
        "formal_recommendation": True,
        "recommendation": {
            "tier": "FORMAL",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "selection_label_cn": "Synthetic Home 让球",
            "line": "-0.25",
            "odds": "1.91",
            "expected_value": "0.112465",
            "ah_settlement_distribution": {
                "win": 0.52,
                "half_win": 0.0,
                "push": 0.12,
                "loss": 0.36,
            },
            "reverse_factor_value": False,
        },
        "current_odds": {
            "ah": {
                "home_price": "1.91",
                "away_price": "1.93",
            },
        },
        "pricing_shadow": {
            "fair_ah": "-0.50",
            "market_ah": "-0.25",
            "edge_ah": "0.25",
            "devig_method": "POWER",
            "team_score_home": "6.2",
            "team_score_away": "5.9",
            "factors": [{"id": "F9_TRUE_XG", "status": "READY"}],
            "independent_signal_count": 4,
            "independent_signal_groups": ["xg", "market", "rest", "importance"],
            "missing_independent_sources": ["h2h"],
            "model_version": "w2.formal.mc_poisson.v1",
            "calibration_version": "w2.formal.lambda_baseline_prior.v1",
            "coherent": True,
        },
        "scoreline_reference": {
            "direction_top3": [{"scoreline": "1-0", "probability": 0.108751}],
        },
        "market_timeline": {
            "label": "盘口时间线 · 参照 · 未验证",
            "verified": False,
            "direction_allowed": False,
            "pattern": "STABLE",
        },
        "data_refresh": {
            "lineups_status": "PARTIAL",
            "xg_status": "READY",
        },
        "data_profile": "real-db",
    }
