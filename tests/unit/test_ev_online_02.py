from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from w2.strategy.online_calibration_filter import (
    FORWARD_START_UTC,
    LEGAL_STATE,
    BiasObservation,
    bias_at_decision,
    build_bias_pool,
    decision_from_bias,
    evaluate_fast_criteria,
)


def _t(minutes: int) -> datetime:
    return datetime(2026, 9, 27, tzinfo=UTC) + timedelta(minutes=minutes)


def _sample(
    index: int, *, market: str = "ASIAN_HANDICAP", settlement: str = "LOSS"
) -> SimpleNamespace:
    return SimpleNamespace(
        fixture_id=f"fixture-{index}", market=market, selection="HOME", settlement=settlement,
        kickoff_utc=_t(index + 1), calibration_identity="v1", evaluation_id=f"eval-{index}",
    )


def _evaluation(index: int, *, market: str = "ASIAN_HANDICAP") -> SimpleNamespace:
    return SimpleNamespace(
        evaluation_id=f"eval-{index}", fixture_id=f"fixture-{index}", market=market,
        selection="HOME", original_state=LEGAL_STATE, evaluated_at=_t(index),
        payload={"model_settlement_distribution": {"WIN": 0.8, "HALF_WIN": 0.0}},
    )


def test_t1_real_time_order_accumulates_and_releases_at_observation_51() -> None:
    samples = [_sample(index) for index in range(51)]
    evaluations = [_evaluation(index) for index in range(51)]
    knowable = {f"fixture-{index}": _t(index + 2) for index in range(51)}
    pool = build_bias_pool(samples, evaluations, knowable)
    assert len(pool) == 51
    assert bias_at_decision(
        market="ASIAN_HANDICAP", selection="HOME", calibration_identity="v1",
        evaluated_at=_t(52), observations=pool,
    ) == 0.8


def test_t3_totals_use_the_same_observation_contract() -> None:
    samples = [_sample(index, market="TOTALS") for index in range(51)]
    evaluations = [_evaluation(index, market="TOTALS") for index in range(51)]
    knowable = {f"fixture-{index}": _t(index + 2) for index in range(51)}
    assert len(build_bias_pool(samples, evaluations, knowable)) == 51


def test_t4_duplicate_checkpoints_are_one_observation() -> None:
    sample = _sample(1)
    duplicate = _sample(1)
    evaluations = [_evaluation(1)]
    pool = build_bias_pool([sample, duplicate], evaluations, {"fixture-1": _t(3)})
    assert len(pool) == 1


def test_t5_calibration_identity_restarts_warmup() -> None:
    observations = [BiasObservation(
        market="ASIAN_HANDICAP", selection="HOME", calibration_identity="v1",
        evaluated_at=_t(index), settlement_observed_at=_t(index + 1),
        predicted_success=0.8, realized_success=0.0,
    ) for index in range(51)]
    assert bias_at_decision(
        market="ASIAN_HANDICAP", selection="HOME", calibration_identity="v2",
        evaluated_at=_t(100), observations=observations,
    ) == 0.0


def test_t6_missing_target_knowable_time_does_not_force_filter_after_warmup() -> None:
    decision = decision_from_bias(
        raw_ev=0.1, decimal_odds=2.0, bias=0.2, history_count=0,
        observed_at=None, allow_missing_observed_at=True,
    )
    assert decision == ("KEPT", None, 0.1, True)


def _criteria_rows() -> list[dict[str, object]]:
    rows = [{
        "market": "ASIAN_HANDICAP", "selection": "HOME", "forward": True,
        "warmup": False, "filter_decision": "KEPT", "bias_at_decision": 0.1,
        "profit_units": 1.0, "predicted_success": 0.6, "realized_success": 0.5,
    } for _ in range(300)]
    rows += [{
        "market": "ASIAN_HANDICAP", "selection": "HOME", "forward": True,
        "warmup": False, "filter_decision": "FILTERED", "bias_at_decision": 0.1,
        "profit_units": -1.0, "predicted_success": 0.8, "realized_success": 0.2,
    } for _ in range(10)]
    return rows


def test_t8_fast_criteria_uses_forward_groups_and_source_cal_gap() -> None:
    rows = _criteria_rows()
    assert evaluate_fast_criteria(rows)
    rows[0]["bias_at_decision"] = -0.1
    assert not evaluate_fast_criteria(rows)
    rows = _criteria_rows()
    for row in rows[:200]:
        row["profit_units"] = -1.0
    for row in rows[300:]:
        row["profit_units"] = 1.0
    assert not evaluate_fast_criteria(rows)
    rows = _criteria_rows()
    for row in rows[:300]:
        row["predicted_success"] = 0.99
    for row in rows[300:]:
        row["predicted_success"] = 0.68
    assert not evaluate_fast_criteria(rows)


def test_t10_capture_without_runtime_ah_fact_enters_pool() -> None:
    sample = _sample(1)
    evaluation = _evaluation(1)
    pool = build_bias_pool([sample], [evaluation], {"fixture-1": _t(3)})
    assert len(pool) == 1


def test_forward_start_is_frozen() -> None:
    assert FORWARD_START_UTC == datetime(2026, 9, 26, 16, tzinfo=UTC)
