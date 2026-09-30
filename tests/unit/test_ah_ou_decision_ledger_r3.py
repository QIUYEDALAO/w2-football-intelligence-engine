"""R3 原子事务 + cohort 幂等 + SKIP 落库单测。"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AhOuCohortModel,
    AhOuDecisionLedgerModel,
)
from w2.strategy.ah_ou_decision_ledger import (
    write_ah_ou_decision,
    write_ah_ou_decision_batch,
)

DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _decision(*, market: str, fixture_id: str = "FIX1", selected: bool = False,
              skip_reason: str | None = None, input_hash: str = "i" * 64) -> dict:
    return {
        "fixture_id": fixture_id,
        "market": market,
        "decision_at": DECISION_AT,
        "model_version": "m1",
        "calibration_version": "c1",
        "input_hash": input_hash,
        "full_distribution": {"market": market},
        "quote_identity_hash": "q" * 64,
        "source_capture_sha256": "s" * 64,
        "capture_id": f"cap-{market}",
        "source_id": f"cap-{market}",
        "home_team_id": "H",
        "away_team_id": "A",
        "selected": selected,
        "direction": None,
        "score": 0.0,
        "skip_reason": skip_reason,
        "created_at": DECISION_AT,
    }


def _cohort(**overrides) -> dict:
    base = {
        "cohort_id": "c" * 64,
        "fixture_id": "FIX1",
        "decision_at": DECISION_AT,
        "home_team_id": "H",
        "away_team_id": "A",
        "ah_capture_id": "cap-ASIAN_HANDICAP",
        "ah_source_capture_sha256": "s" * 64,
        "ou_capture_id": "cap-TOTALS",
        "ou_source_capture_sha256": "s" * 64,
        "model_version": "m1",
        "calibration_version": "c1",
        "frozen_identity": "f" * 64,
        "created_at": DECISION_AT,
    }
    base.update(overrides)
    return base


def test_batch_is_atomic_on_ou_conflict() -> None:
    engine = _engine()
    # 预写一条 OU 账本占 slot（模拟已有版本，input_hash 不同 → 不同 decision_id）
    with Session(engine) as session:
        with session.begin():
            write_ah_ou_decision(session, **_decision(market="TOTALS", input_hash="x" * 64))

    # batch：cohort + AH + OU，其中 OU 冲突 → 整个 batch rollback
    with pytest.raises(ValueError, match="AH_OU_DECISION_SLOT_CONFLICT"):
        with Session(engine) as session:
            with session.begin():
                write_ah_ou_decision_batch(
                    session,
                    cohort=_cohort(),
                    decisions=[
                        _decision(market="ASIAN_HANDICAP"),
                        _decision(market="TOTALS"),
                    ],
                )

    with Session(engine) as session:
        ah_rows = session.scalars(
            select(AhOuDecisionLedgerModel).where(
                AhOuDecisionLedgerModel.market == "ASIAN_HANDICAP"
            )
        ).all()
        cohorts = session.scalars(select(AhOuCohortModel)).all()
    # 无单边 AH，无漏记 cohort（原子回滚）
    assert ah_rows == []
    assert cohorts == []


def test_batch_commits_cohort_and_both_markets() -> None:
    engine = _engine()
    with Session(engine) as session:
        with session.begin():
            write_ah_ou_decision_batch(
                session,
                cohort=_cohort(),
                decisions=[
                    _decision(market="ASIAN_HANDICAP"),
                    _decision(market="TOTALS"),
                ],
            )

    with Session(engine) as session:
        markets = {
            row.market
            for row in session.scalars(select(AhOuDecisionLedgerModel))
        }
        cohorts = session.scalars(select(AhOuCohortModel)).all()
    assert markets == {"ASIAN_HANDICAP", "TOTALS"}
    assert len(cohorts) == 1
    assert cohorts[0].frozen_identity == "f" * 64


def test_cohort_rerun_is_one_row() -> None:
    engine = _engine()
    cohort = _cohort()
    decisions = [
        _decision(market="ASIAN_HANDICAP"),
        _decision(market="TOTALS"),
    ]
    with Session(engine) as session:
        with session.begin():
            write_ah_ou_decision_batch(session, cohort=cohort, decisions=decisions)
    # 重跑同一 identity：一行 cohort，无重复
    with Session(engine) as session:
        with session.begin():
            write_ah_ou_decision_batch(session, cohort=cohort, decisions=decisions)
    with Session(engine) as session:
        cohorts = session.scalars(select(AhOuCohortModel)).all()
        ledgers = session.scalars(select(AhOuDecisionLedgerModel)).all()
    assert len(cohorts) == 1
    assert len(ledgers) == 2


def test_conflicting_cohort_on_same_slot_is_refused() -> None:
    engine = _engine()
    with Session(engine) as session:
        with session.begin():
            write_ah_ou_decision_batch(
                session,
                cohort=_cohort(),
                decisions=[
                    _decision(market="ASIAN_HANDICAP"),
                    _decision(market="TOTALS"),
                ],
            )
    # 同 slot 不同 cohort_id → 冲突，且不落任何新行
    with pytest.raises(ValueError, match="AH_OU_COHORT_SLOT_CONFLICT"):
        with Session(engine) as session:
            with session.begin():
                write_ah_ou_decision_batch(
                    session,
                    cohort=_cohort(cohort_id="d" * 64),
                    decisions=[_decision(market="ASIAN_HANDICAP")],
                )


def test_skip_reason_is_persisted() -> None:
    engine = _engine()
    with Session(engine) as session:
        with session.begin():
            write_ah_ou_decision_batch(
                session,
                cohort=_cohort(),
                decisions=[
                    _decision(market="ASIAN_HANDICAP", skip_reason="AH_SIDE_PRICES_INCOMPLETE"),
                    _decision(market="TOTALS", skip_reason="OU_SIDE_PRICES_INCOMPLETE"),
                ],
            )
    with Session(engine) as session:
        rows = {
            row.market: row
            for row in session.scalars(select(AhOuDecisionLedgerModel))
        }
    assert rows["ASIAN_HANDICAP"].skip_reason == "AH_SIDE_PRICES_INCOMPLETE"
    assert rows["ASIAN_HANDICAP"].selected is False
    assert rows["TOTALS"].skip_reason == "OU_SIDE_PRICES_INCOMPLETE"
