from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal

from w2.settlement.settle import LockedPrediction, MatchResult, settle_prediction

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def prediction() -> LockedPrediction:
    return LockedPrediction(
        fixture_id="1489404",
        market="TOTALS",
        selection="OVER",
        line="2.5",
        locked_decimal_odds=Decimal("1.95"),
        model_probability=Decimal("0.54"),
        locked_at=NOW,
        prediction_hash="pred-hash",
    )


def result() -> MatchResult:
    return MatchResult(
        fixture_id="1489404",
        home_goals_90=2,
        away_goals_90=1,
        final_at=NOW,
    )


def test_settlement_does_not_mutate_locked_prematch_prediction() -> None:
    locked = prediction()
    before = deepcopy(locked.as_dict())

    evaluation = settle_prediction(
        locked,
        result(),
        closing_decimal_odds=Decimal("1.88"),
        evaluated_at=NOW,
    )

    assert locked.as_dict() == before
    assert evaluation.outcome == "WIN"
    assert evaluation.candidate is False
    assert evaluation.formal_recommendation is False


def test_same_input_replays_to_same_settlement_hash() -> None:
    locked = prediction()
    first = settle_prediction(
        locked,
        result(),
        closing_decimal_odds=Decimal("1.88"),
        evaluated_at=NOW,
    )
    second = settle_prediction(
        locked,
        result(),
        closing_decimal_odds=Decimal("1.88"),
        evaluated_at=NOW,
    )

    assert first.as_dict() == second.as_dict()
    assert first.replay_hash == second.replay_hash


def test_evaluation_outputs_clv_field() -> None:
    evaluation = settle_prediction(
        prediction(),
        result(),
        closing_decimal_odds=Decimal("1.88"),
        evaluated_at=NOW,
    )

    assert evaluation.clv_decimal == Decimal("-0.07")
    assert evaluation.as_dict()["clv_decimal"] == "-0.07"
