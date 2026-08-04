from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import CURRENT_SERIALIZER_VERSION
from w2.domain.recommendation_decision_v4 import (
    RECOMMENDATION_SCHEMA_VERSION,
    build_recommendation_decision_v4,
    candidate_identity_hash,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import (
    CompetitionModel,
    FixtureModel,
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
from w2.tracking.formal_results import capture_formal_locks

NOW = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 6, 22, 3, 0, tzinfo=UTC)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def _fixture_graph(session: Session) -> FixtureModel:
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
    session.add(stage)
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
    return fixture


def test_recommendation_lock_is_not_updatable(session: Session) -> None:
    fixture = _fixture_graph(session)
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
    fixture = _fixture_graph(session)
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
    fixture = _fixture_graph(session)
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


def test_formal_tracking_db_capture_uses_reproducible_lock_builder(session: Session) -> None:
    fixture = _fixture_graph(session)
    recommendation = RecommendationModel(
        fixture_id=fixture.id,
        prediction_id=None,
        status="LOCKED",
        created_at=NOW,
    )
    session.add(recommendation)
    session.flush()
    card = _formal_card(fixture.id, fixture.kickoff_at)
    card["recommendation"]["recommendation_id"] = recommendation.id

    result = capture_formal_locks(
        [card],
        session=session,
        now=NOW,
        release_sha="release-sha",
    )
    session.commit()

    assert result["written"] == 1
    stored = session.get(RecommendationLockModel, result["results"][0]["lock_id"])
    assert stored.reproducible is True
    assert stored.legacy_marker_only is False
    assert stored.release_sha == "release-sha"
    assert stored.snapshot_payload_hash == result["results"][0]["snapshot_payload_hash"]


def test_formal_tracking_db_capture_blocks_missing_recommendation_id(session: Session) -> None:
    fixture = _fixture_graph(session)
    card = _formal_card(fixture.id, fixture.kickoff_at)

    result = capture_formal_locks(
        [card],
        session=session,
        now=NOW,
        release_sha="release-sha",
    )

    assert result["written"] == 0
    assert result["blockers"]["MISSING_RECOMMENDATION_ID"] == 1


def test_formal_tracking_capture_does_not_fabricate_recommendation_for_payload_id(
    session: Session,
) -> None:
    fixture = _fixture_graph(session)
    card = _formal_card(fixture.id, fixture.kickoff_at)
    recommendation_id = "11111111-1111-5111-8111-111111111111"
    card["recommendation"]["recommendation_id"] = recommendation_id  # type: ignore[index]
    card["recommendation"]["id"] = recommendation_id  # type: ignore[index]

    result = capture_formal_locks(
        [card],
        session=session,
        now=NOW,
        release_sha="release-sha",
    )
    assert result["written"] == 0
    assert result["blockers"]["MISSING_RECOMMENDATION"] == 1
    marker = session.get(RecommendationModel, recommendation_id)
    assert marker is None


def test_settlement_requires_existing_result_recommendation_and_can_bind_lock(
    session: Session,
) -> None:
    fixture = _fixture_graph(session)
    recommendation = RecommendationModel(
        fixture_id=fixture.id,
        prediction_id=None,
        status="LOCKED",
        created_at=NOW,
    )
    result = _result_model(fixture.id, 1, 1)
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
    fixture = _fixture_graph(session)
    recommendation = RecommendationModel(
        fixture_id=fixture.id,
        prediction_id=None,
        status="LOCKED",
        created_at=NOW,
    )
    result = _result_model(fixture.id, 1, 1)
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
    decision_v4 = _formal_decision_v4(fixture_id, kickoff_utc)
    return {
        "fixture_id": fixture_id,
        "generated_at": NOW.isoformat().replace("+00:00", "Z"),
        "kickoff_utc": kickoff_utc.isoformat().replace("+00:00", "Z"),
        "home_team_name": "Synthetic Home",
        "away_team_name": "Synthetic Away",
        "competition_name": "Synthetic Cup",
        "formal_recommendation": True,
        "recommendation_decision_v3": {"outcome": "NOT_READY"},
        "recommendation_decision_v4": decision_v4,
        "recommendation": {
            "tier": "FORMAL",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "selection_label_cn": "Synthetic Home 让球",
            "line": "-0.25",
            "odds": "1.91",
            "expected_value": "0.112465",
            "quote_identity": _quote_identity(decision_v4),
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


def _formal_decision_v4(fixture_id: str, kickoff_utc: datetime) -> dict[str, object]:
    payload: dict[str, object] = {
            "fixture_id": fixture_id,
            "competition_id": "synthetic_cup",
            "season": "2026",
            "kickoff_utc": kickoff_utc.isoformat().replace("+00:00", "Z"),
            "kickoff_revision_or_fixture_identity_hash": "d" * 64,
            "provider": "api-football",
            "bookmaker_id": "unibet",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "exact_line": "-0.25",
            "capture_id": "capture-1",
            "captured_at": NOW.isoformat().replace("+00:00", "Z"),
            "quote_observation_ids": {
                "home": "observation-home",
                "away": "observation-away",
            },
            "raw_payload_sha256": "a" * 64,
            "source_revision": "e" * 40,
            "model_version": "model-v1",
            "calibration_version": "calibration-v1",
            "serializer_version": CURRENT_SERIALIZER_VERSION.value,
            "recommendation_schema_version": RECOMMENDATION_SCHEMA_VERSION,
            "quote_schema_version": "w2.quote_identity.v1",
            "model_input_manifest_hash": "b" * 64,
            "decimal_odds": "1.91",
            "canonical_mainline_identity": {
                "market": "ASIAN_HANDICAP",
                "line": "-0.25",
                "selected_side_line": "-0.25",
                "candidate_role": "MARKET_MAINLINE",
                "quote_identity_hash": "c" * 64,
            },
            "settlement_distribution": {
                "WIN": "0.5",
                "HALF_WIN": "0.1",
                "PUSH": "0.1",
                "HALF_LOSS": "0.1",
                "LOSS": "0.2",
            },
            "fair_odds": "1.4545",
            "expected_value": "0.2505",
            "uncertainty": "0.01",
            "readiness": {
                "status": "READY",
                "quote_identity_status": "COMPLETE",
                "quote_freshness_status": "COMPLETE",
                "model_status": "READY",
            },
            "capability_status": "FORMAL_ENABLED",
            "formal_admission": {
                "status": "PASSED",
                "readiness_hash": "f" * 64,
                "approval_hash": "1" * 64,
                "candidate_identity_hash": None,
            },
        }
    admission = payload["formal_admission"]
    assert isinstance(admission, dict)
    admission["candidate_identity_hash"] = candidate_identity_hash(payload)
    return build_recommendation_decision_v4(payload).as_dict()


def _quote_identity(decision: dict[str, object]) -> dict[str, object]:
    authoritative = decision["authoritative_input"]
    mainline = authoritative["canonical_mainline_identity"]
    return {
        "provider": authoritative["provider"],
        "bookmaker_id": authoritative["bookmaker_id"],
        "capture_id": authoritative["capture_id"],
        "captured_at": authoritative["captured_at"],
        "observation_ids": authoritative["quote_observation_ids"],
        "raw_payload_sha256": authoritative["raw_payload_sha256"],
        "source_revision": authoritative["source_revision"],
        "quote_identity_hash": mainline["quote_identity_hash"],
    }


def _result_model(fixture_id: str, home_goals: int, away_goals: int) -> ResultModel:
    identity = f"{fixture_id}:{home_goals}:{away_goals}"
    return ResultModel(
        fixture_id=fixture_id,
        home_goals=home_goals,
        away_goals=away_goals,
        result_status="FT",
        confirmed_at=NOW,
        source_payload_sha256=sha256(identity.encode()).hexdigest(),
        source_capture_id=None,
        result_hash=sha256(f"result:{identity}".encode()).hexdigest(),
    )
