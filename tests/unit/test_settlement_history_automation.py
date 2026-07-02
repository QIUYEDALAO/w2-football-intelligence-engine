from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import (
    RecommendationLockModel,
    RecommendationModel,
    ResultModel,
)
from w2.settlement.history import (
    WRITE_CONFIRMATION_PHRASE,
    SettlementHistoryError,
    run_settlement_history,
)

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def test_settlement_history_dry_run_produces_candidate_without_writing(session: Session) -> None:
    lock, result = _reproducible_lock_with_result(session, home_goals=2, away_goals=0)

    output = run_settlement_history(session=session, dry_run=True, write_db=False, now=NOW)

    assert output["status"] == "PASS"
    assert output["dry_run"] is True
    assert output["db_writes"] == 0
    assert output["provider_calls"] == 0
    assert output["counts"]["candidate_settlements"] == 1
    assert output["results"] == [
        {
            "status": "WOULD_WRITE",
            "lock_id": lock.id,
            "recommendation_id": lock.recommendation_id,
            "result_id": result.id,
            "fixture_id": "fixture-1",
            "outcome": "WIN",
            "selection": "HOME",
            "line": "-0.5000",
            "tier": "FORMAL",
            "movement_pattern": "STABLE",
        }
    ]
    assert session.query(ResultModel).count() == 1
    assert session.query(RecommendationLockModel).count() == 1


def test_settlement_history_skips_legacy_and_unreproducible_locks(session: Session) -> None:
    recommendation = _recommendation(session)
    session.add(
        RecommendationLockModel(
            recommendation_id=recommendation.id,
            status="LOCKED",
            locked_at=NOW,
            reason="legacy",
            fixture_id="fixture-1",
            reproducible=False,
            legacy_marker_only=True,
        )
    )
    session.commit()

    output = run_settlement_history(session=session, dry_run=True, write_db=False, now=NOW)

    assert output["counts"]["legacy_or_unreproducible_skipped"] == 1
    assert output["results"] == []


def test_settlement_history_requires_explicit_confirmation_for_write(session: Session) -> None:
    _reproducible_lock_with_result(session, home_goals=2, away_goals=0)

    with pytest.raises(
        SettlementHistoryError,
        match="SETTLEMENT_HISTORY_WRITE_REQUIRES_CONFIRMATION",
    ):
        run_settlement_history(
            session=session,
            dry_run=False,
            write_db=True,
            confirm_write=None,
            now=NOW,
        )


def test_settlement_history_write_path_binds_lock_id_when_explicitly_confirmed(
    session: Session,
) -> None:
    lock, result = _reproducible_lock_with_result(session, home_goals=1, away_goals=1)

    output = run_settlement_history(
        session=session,
        dry_run=False,
        write_db=True,
        confirm_write=WRITE_CONFIRMATION_PHRASE,
        now=NOW,
    )

    assert output["db_writes"] == 1
    assert output["results"][0]["status"] == "WRITTEN"
    settlement = lock.settlements[0]
    assert settlement.lock_id == lock.id
    assert settlement.result_id == result.id
    assert settlement.outcome == "LOSS"
    assert settlement.matched_recommendation is True
    assert settlement.tier == "FORMAL"
    assert settlement.movement_pattern == "STABLE"


def test_settlement_history_skips_already_settled_lock(session: Session) -> None:
    lock, _result = _reproducible_lock_with_result(session, home_goals=1, away_goals=1)
    run_settlement_history(
        session=session,
        dry_run=False,
        write_db=True,
        confirm_write=WRITE_CONFIRMATION_PHRASE,
        now=NOW,
    )

    output = run_settlement_history(session=session, dry_run=True, write_db=False, now=NOW)

    assert output["counts"]["already_settled"] == 1
    assert output["results"] == []
    assert len(lock.settlements) == 1


def _recommendation(session: Session) -> RecommendationModel:
    recommendation = RecommendationModel(
        fixture_id="fixture-1",
        prediction_id=None,
        status="LOCKED",
        created_at=NOW,
    )
    session.add(recommendation)
    session.flush()
    return recommendation


def _reproducible_lock_with_result(
    session: Session,
    *,
    home_goals: int,
    away_goals: int,
) -> tuple[RecommendationLockModel, ResultModel]:
    recommendation = _recommendation(session)
    result = ResultModel(
        fixture_id="fixture-1",
        home_goals=home_goals,
        away_goals=away_goals,
        confirmed_at=NOW,
    )
    lock = RecommendationLockModel(
        recommendation_id=recommendation.id,
        status="LOCKED",
        locked_at=NOW,
        reason="formal pre-match lock",
        fixture_id="fixture-1",
        as_of=NOW,
        tier="FORMAL",
        pick_side="HOME_AH",
        pick_line=Decimal("-0.5000"),
        market_timeline_json={"pattern": "STABLE"},
        reproducible=True,
        legacy_marker_only=False,
        snapshot_payload_hash="h" * 64,
        release_sha="release-sha",
        data_profile="real-db",
    )
    session.add_all([result, lock])
    session.commit()
    return lock, result
