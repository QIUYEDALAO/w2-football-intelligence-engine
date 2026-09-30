"""任务 8：POSTMORTEM 追加事件 + 累计监测分层报告 单测。"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.forward_evidence_models import (
    RecommendationReviewLedgerModel,
)
from w2.tracking.forward_evidence import append_postmortem_in_session
from w2.tracking.forward_ledger_performance import (
    _five_state_of,
    _market_breakdown,
    _odds_bucket,
    _ou_all_over,
    _rps_five_state,
)

# --- POSTMORTEM ---

def _review_row(
    evaluation_id: str,
    event_type: str,
    payload: dict,
    *,
    digest: str,
) -> RecommendationReviewLedgerModel:
    return RecommendationReviewLedgerModel(
        review_event_id=digest,
        evaluation_id=evaluation_id,
        event_type=event_type,
        evaluated_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
        pit_status="PROVABLE",
        payload=payload,
        payload_sha256=digest,
        created_at=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    )


def _seed_lost_evaluation(session: Session, evaluation_id: str) -> None:
    session.add(
        _review_row(
            evaluation_id,
            "DECISION_SNAPSHOT",
            {
                "candidate_kind": "TRACK_D_FADE",
                "market": "TOTALS",
                "selection": "OVER",
                "exact_line": "3.0",
                "evaluated_at": "2026-07-08T10:00:00+00:00",
            },
            digest="1" * 64,
        )
    )
    session.add(
        _review_row(
            evaluation_id,
            "SETTLEMENT_OBSERVED",
            {
                "candidate_kind": "TRACK_D_FADE",
                "market": "TOTALS",
                "selection": "OVER",
                "settlement": "LOSS",
                "profit_units_channel": -1.0,
            },
            digest="2" * 64,
        )
    )
    session.commit()


def test_postmortem_appends_without_touching_frozen_snapshot() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    RecommendationReviewLedgerModel.__table__.create(engine)
    with Session(engine) as session:
        _seed_lost_evaluation(session, "eval-1")
        snapshot_before = session.scalar(
            select(RecommendationReviewLedgerModel).where(
                RecommendationReviewLedgerModel.evaluation_id == "eval-1",
                RecommendationReviewLedgerModel.event_type == "DECISION_SNAPSHOT",
            )
        ).payload_sha256

        row = append_postmortem_in_session(
            session,
            evaluation_id="eval-1",
            reason="模型逆市场看多 OVER",
            hypothesis="F6 样本稀疏致 OVER 上偏",
            new_version="v2",
            new_window="2026-10 forward cohort",
            reviewed_at=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
        )
        session.commit()

        assert row.event_type == "POSTMORTEM"
        assert row.payload["reason"] == "模型逆市场看多 OVER"
        assert row.payload["new_version"] == "v2"
        assert row.payload["settlement"] == "LOSS"

        # 冻结决定 hash 未被改写
        snapshot_after = session.scalar(
            select(RecommendationReviewLedgerModel).where(
                RecommendationReviewLedgerModel.evaluation_id == "eval-1",
                RecommendationReviewLedgerModel.event_type == "DECISION_SNAPSHOT",
            )
        ).payload_sha256
        assert snapshot_after == snapshot_before


def test_postmortem_is_idempotent_and_conflict_free() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    RecommendationReviewLedgerModel.__table__.create(engine)
    with Session(engine) as session:
        _seed_lost_evaluation(session, "eval-2")
        first = append_postmortem_in_session(
            session, evaluation_id="eval-2", reason="r", hypothesis="h",
            new_version="v2", new_window="w",
            reviewed_at=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
        )
        session.commit()
        second = append_postmortem_in_session(
            session, evaluation_id="eval-2", reason="r", hypothesis="h",
            new_version="v2", new_window="w",
            reviewed_at=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
        )
        assert second.review_event_id == first.review_event_id


def test_postmortem_refuses_non_miss() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    RecommendationReviewLedgerModel.__table__.create(engine)
    with Session(engine) as session:
        session.add(_review_row("eval-win", "DECISION_SNAPSHOT",
                                {"candidate_kind": "TRACK_D_FADE"}, digest="3" * 64))
        session.add(_review_row("eval-win", "SETTLEMENT_OBSERVED",
                                {"candidate_kind": "TRACK_D_FADE", "settlement": "WIN"},
                                digest="4" * 64))
        session.commit()
        with pytest.raises(ValueError, match="POSTMORTEM_NOT_A_MISS"):
            append_postmortem_in_session(
                session, evaluation_id="eval-win", reason="r", hypothesis="h",
                new_version="v2", new_window="w",
            )


def test_postmortem_requires_snapshot_and_settlement() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    RecommendationReviewLedgerModel.__table__.create(engine)
    with Session(engine) as session:
        with pytest.raises(ValueError, match="POSTMORTEM_DECISION_SNAPSHOT_NOT_FOUND"):
            append_postmortem_in_session(
                session, evaluation_id="missing", reason="r", hypothesis="h",
                new_version="v2", new_window="w",
            )


# --- 累计监测分层报告 ---

def test_five_state_of_normalizes_aliases() -> None:
    assert _five_state_of({"settlement_outcome": "WIN"}) == "WIN"
    assert _five_state_of({"settlement_outcome": "HIT"}) == "WIN"
    assert _five_state_of({"settlement_outcome": "MISS"}) == "LOSS"
    assert _five_state_of({"settlement_outcome": "HALF_WIN"}) == "HALF_WIN"
    assert _five_state_of({"settlement_outcome": "VOID"}) is None


def test_rps_five_state_bounds() -> None:
    distribution = {"WIN": 0.4, "HALF_WIN": 0.2, "PUSH": 0.2, "HALF_LOSS": 0.1, "LOSS": 0.1}
    perfect = _rps_five_state(distribution, "WIN")
    assert perfect is not None and 0.0 <= perfect <= 1.0
    # 预测完全正确时 RPS 最小；预测 LOSS 但实际 WIN 时 RPS 更大
    wrong = _rps_five_state(distribution, "LOSS")
    assert wrong is not None and wrong > 0.0


def test_odds_bucket_boundaries() -> None:
    assert _odds_bucket(1.69) == "lt1.7"
    assert _odds_bucket(1.7) == "1.7_1.9"
    assert _odds_bucket(1.9) == "1.9_2.1"
    assert _odds_bucket(2.1) == "gt2.1"


def test_ou_all_over_computes_over_baseline() -> None:
    candidates = {
        "f1": {
            "kickoff_utc": "2026-07-08T01:00:00+00:00",
            "captured_at": "2026-07-07T00:00:00+00:00",
            "current_odds": {
                "ou": {"line": "3.0", "over_price": "2.0", "under_price": "1.8"}
            },
        }
    }
    # 总进球 2 < 3.0 → OVER LOSS（-1 单位）
    rows = [
        {
            "fixture_id": "f1",
            "market": "TOTALS",
            "final_score": {"home": 1, "away": 1, "status": "FT"},
        }
    ]
    result = _ou_all_over(rows, candidates)
    assert result["n"] == 1
    assert result["five_state"]["LOSS"] == 1
    assert result["flat_units"] == -1.0


def test_market_breakdown_reports_five_state_and_units() -> None:
    candidates = {
        "f1": {
            "kickoff_utc": "2026-07-08T01:00:00+00:00",
            "captured_at": "2026-07-07T00:00:00+00:00",
            "current_odds": {
                "ah": {"home_line": "-1", "home_price": "2.0", "away_price": "1.8"}
            },
        }
    }
    rows = [
        {
            "fixture_id": "f1",
            "market": "ASIAN_HANDICAP",
            "settlement_outcome": "WIN",
            "entry_price": "2.0",
            "settled_at": "2026-07-08T03:00:00+00:00",
            "final_score": {"home": 2, "away": 0, "status": "FT"},
        }
    ]
    breakdown = _market_breakdown(rows, candidates)
    ah = breakdown["ASIAN_HANDICAP"]
    assert ah["n"] == 1
    assert ah["five_state"]["WIN"] == 1
    assert ah["flat_units"] == 1.0
    assert "by_month" in ah and "by_odds_bucket" in ah and "by_quote_age" in ah
    assert "all_over" in breakdown["TOTALS"]
