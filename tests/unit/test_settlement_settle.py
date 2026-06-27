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
        asof_market_snapshot_id="snapshot-123",
        devig_method="POWER",
        market_baseline_probability=Decimal("0.51"),
    )


def result() -> MatchResult:
    return MatchResult(
        fixture_id="1489404",
        home_goals_90=2,
        away_goals_90=1,
        final_at=NOW,
    )


def ah_prediction(*, selection: str, line: str, prediction_hash: str) -> LockedPrediction:
    return LockedPrediction(
        fixture_id="1489404",
        market="ASIAN_HANDICAP",
        selection=selection,
        line=line,
        locked_decimal_odds=Decimal("1.91"),
        model_probability=Decimal("0.52"),
        locked_at=NOW,
        prediction_hash=prediction_hash,
        asof_market_snapshot_id="snapshot-ah",
        devig_method="POWER",
        market_baseline_probability=Decimal("0.50"),
    )


def final_result(*, home_goals: int, away_goals: int) -> MatchResult:
    return MatchResult(
        fixture_id="1489404",
        home_goals_90=home_goals,
        away_goals_90=away_goals,
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
    assert evaluation.sample_included is True
    assert evaluation.win_included is True
    assert evaluation.asof_market_snapshot_id == "snapshot-123"
    assert evaluation.devig_method == "POWER"
    assert evaluation.market_baseline_probability == Decimal("0.51")
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


def test_ah_half_loss_and_push_sample_semantics() -> None:
    half_loss = settle_prediction(
        ah_prediction(selection="HOME", line="-1.25", prediction_hash="ah-half-loss"),
        final_result(home_goals=1, away_goals=0),
        closing_decimal_odds=None,
        evaluated_at=NOW,
    )
    push = settle_prediction(
        ah_prediction(selection="HOME", line="-1", prediction_hash="ah-push"),
        final_result(home_goals=1, away_goals=0),
        closing_decimal_odds=None,
        evaluated_at=NOW,
    )

    assert half_loss.outcome == "HALF_LOSS"
    assert half_loss.sample_included is True
    assert half_loss.win_included is False
    assert push.outcome == "PUSH"
    assert push.sample_included is True
    assert push.win_included is False


def test_strict_ah_quarter_line_outcomes_cover_home_and_away() -> None:
    cases = [
        ("HOME", "-0.25", 1, 1, "HALF_LOSS", False),
        ("HOME", "-0.75", 1, 0, "HALF_WIN", True),
        ("AWAY", "+0.25", 1, 1, "HALF_WIN", True),
        ("AWAY", "+0.75", 1, 0, "HALF_LOSS", False),
        ("HOME", "-1", 1, 0, "PUSH", False),
    ]

    for selection, line, home_goals, away_goals, outcome, win_included in cases:
        evaluation = settle_prediction(
            ah_prediction(
                selection=selection,
                line=line,
                prediction_hash=f"{selection}:{line}",
            ),
            final_result(home_goals=home_goals, away_goals=away_goals),
            closing_decimal_odds=None,
            evaluated_at=NOW,
        )

        assert evaluation.outcome == outcome
        assert evaluation.sample_included is True
        assert evaluation.win_included is win_included
        assert evaluation.asof_market_snapshot_id == "snapshot-ah"
        assert evaluation.devig_method == "POWER"
        assert evaluation.market_baseline_probability == Decimal("0.50")


def test_void_result_is_excluded_from_settlement_sample() -> None:
    evaluation = settle_prediction(
        prediction(),
        MatchResult(
            fixture_id="1489404",
            home_goals_90=0,
            away_goals_90=0,
            final_at=NOW,
            result_status="POSTPONED",
        ),
        closing_decimal_odds=None,
        evaluated_at=NOW,
    )

    assert evaluation.outcome == "VOID"
    assert evaluation.settled_units == Decimal("0")
    assert evaluation.sample_included is False
    assert evaluation.win_included is False
