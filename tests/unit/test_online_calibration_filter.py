from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pytest import approx

from w2.strategy.online_calibration_filter import (
    BiasObservation,
    LEGAL_STATE,
    WARMUP_OBSERVATIONS,
    bias_at_decision,
    build_bias_pool,
    decision_from_bias,
    evaluate_fast_criteria,
)
from w2.api.routers import FORWARD_START_UTC as ROUTER_FORWARD_START_UTC
from w2.domain.ev_online_contract import FORWARD_START_UTC as CONTRACT_FORWARD_START_UTC
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CalibratedValidationSampleModel,
    ValidationSampleModel,
)
from w2.prematch.candidate_notifications import validation_samples_snapshot


def _dt(minutes: int) -> datetime:
    return datetime(2026, 9, 23, 12, tzinfo=UTC) + timedelta(minutes=minutes)


def test_bias_pool_is_fail_closed_and_has_no_time_leakage() -> None:
    class Evaluation:
        def __init__(self, fixture_id: str, evaluated_at: datetime, state: str, market: str = "ASIAN_HANDICAP"):
            self.fixture_id = fixture_id
            self.evaluated_at = evaluated_at
            self.original_state = state
            self.market = market
            self.selection = "HOME"
            self.payload = {"model_settlement_distribution": {"WIN": 0.8, "HALF_WIN": 0.0}}

    class Fact:
        def __init__(self, fixture_id: str, observed: datetime, settlement: str = "LOSS"):
            self.fixture_id = fixture_id
            self.settlement_observed_at = observed
            self.home_settlement = settlement
            self.away_settlement = "LOSS"

    rows = [
        Evaluation("past", _dt(20), LEGAL_STATE),
        Evaluation("future", _dt(10), LEGAL_STATE),
        Evaluation("blocked", _dt(20), "NO_EDGE_CURRENT"),
        Evaluation("totals", _dt(20), LEGAL_STATE, market="TOTALS"),
    ]
    facts = {
        "past": Fact("past", _dt(5)),
        "future": Fact("future", _dt(30)),
        "blocked": Fact("blocked", _dt(5)),
        # A TOTALS result has no real settlement-observed source in the current schema.
        "totals": Fact("totals", _dt(5)),
    }
    sample_rows = [type("Sample", (), {"fixture_id": row.fixture_id, "market": row.market,
                                        "selection": row.selection, "evaluation_id": row.fixture_id,
                                        "calibration_identity": None, "kickoff_utc": _dt(25),
                                        "settlement": facts[row.fixture_id].home_settlement})()
                   for row in rows]
    evaluations = [type("Eval", (), {"evaluation_id": row.fixture_id, "fixture_id": row.fixture_id,
                                      "market": row.market, "selection": row.selection,
                                      "original_state": row.original_state,
                                      "evaluated_at": row.evaluated_at, "payload": row.payload})()
                   for row in rows]
    pool = build_bias_pool(
        sample_rows,
        evaluations,
        {key: value.settlement_observed_at for key, value in facts.items()},
    )
    assert {item.fixture_id for item in pool} == {"future"}
    assert all(item.evaluated_at < _dt(25) < item.settlement_observed_at for item in pool)


def test_bias_warmup_and_market_selection_partition_are_frozen() -> None:
    observations = [
        BiasObservation(
            market="ASIAN_HANDICAP",
            selection="HOME",
            evaluated_at=_dt(index),
            settlement_observed_at=_dt(index - 1),
            predicted_success=0.8,
            realized_success=0.2,
        )
        for index in range(1, WARMUP_OBSERVATIONS + 1)
    ]
    assert bias_at_decision(
        market="ASIAN_HANDICAP",
        selection="HOME",
        evaluated_at=_dt(WARMUP_OBSERVATIONS + 2),
        observations=observations,
    ) is not None
    assert bias_at_decision(
        market="TOTALS",
        selection="OVER",
        evaluated_at=_dt(WARMUP_OBSERVATIONS + 2),
        observations=observations,
    ) == 0.0


def test_bias_after_warmup_is_equal_weight_mean_and_non_negative() -> None:
    observations = [
        BiasObservation(
            market="ASIAN_HANDICAP",
            selection="HOME",
            evaluated_at=_dt(index),
            settlement_observed_at=_dt(index - 1),
            predicted_success=0.7 if index % 2 else 0.5,
            realized_success=0.5,
        )
        for index in range(1, WARMUP_OBSERVATIONS + 1)
    ]
    # 25 observations contribute +0.2 and 25 contribute 0.0.
    assert bias_at_decision(
        market="ASIAN_HANDICAP",
        selection="HOME",
        evaluated_at=_dt(WARMUP_OBSERVATIONS + 2),
        observations=observations,
    ) == approx(0.1)


def test_parallel_projection_has_the_legacy_columns_and_new_decision_columns() -> None:
    legacy = set(ValidationSampleModel.__table__.columns.keys())
    calibrated = set(CalibratedValidationSampleModel.__table__.columns.keys())
    assert legacy <= calibrated
    assert {
        "settlement_observed_at",
        "bias_at_decision",
        "ev_raw",
        "ev_corrected",
        "filter_decision",
        "param_version",
        "warmup",
    } <= calibrated


def test_warmup_is_kept_with_null_bias_and_explicit_marker() -> None:
    decision, bias, corrected, warmup = decision_from_bias(
        raw_ev=0.12,
        decimal_odds=2.0,
        bias=0.0,
        history_count=WARMUP_OBSERVATIONS - 1,
    )
    assert (decision, bias, corrected, warmup) == ("KEPT", None, 0.12, True)


def test_missing_observed_time_does_not_change_warmup_decision() -> None:
    decision, bias, corrected, warmup = decision_from_bias(
        raw_ev=0.12,
        decimal_odds=2.0,
        bias=None,
        history_count=0,
    )
    assert (decision, bias, corrected, warmup) == ("KEPT", None, 0.12, True)


def test_parallel_component_does_not_change_legacy_snapshot_bytes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ValidationSampleModel.__table__.create(engine)
    with Session(engine) as session:
        session.add(
            ValidationSampleModel(
                fixture_id="fixture-1",
                market="TOTALS",
                selection="OVER",
                exact_line="2.5",
                decimal_odds=2.0,
                evaluation_id="eval-1",
                settlement="PENDING",
                projected_at=_dt(0),
            )
        )
        session.commit()
        before = json.dumps(validation_samples_snapshot(session), sort_keys=True, default=str)
        # Running the pure online decision path has no handle to the legacy table.
        _ = bias_at_decision(
            market="TOTALS", selection="OVER", evaluated_at=_dt(10), observations=[]
        )
        after = json.dumps(validation_samples_snapshot(session), sort_keys=True, default=str)
    assert before == after


def test_fast_criteria_is_frozen_and_pnl_is_only_a_group_rate() -> None:
    rows = []
    for index in range(300):
        rows.append({
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "warmup": False,
            "filter_decision": "KEPT",
                "bias_at_decision": 0.05,
                "profit_units": 1.0,
                "predicted_success": 0.6, "realized_success": 0.5,
        })
    rows.extend(
        {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "warmup": False,
            "filter_decision": "FILTERED",
                "bias_at_decision": 0.05,
                "profit_units": -1.0,
                "predicted_success": 0.8, "realized_success": 0.2,
        }
        for _ in range(10)
    )
    assert evaluate_fast_criteria(rows)
    rows[0]["bias_at_decision"] = -0.01
    assert not evaluate_fast_criteria(rows)


def test_warmup_rows_do_not_count_toward_trigger_or_any_fast_criterion() -> None:
    non_warmup = [
        {
            "market": "TOTALS",
            "selection": "UNDER",
            "warmup": False,
            "filter_decision": "KEPT",
            "bias_at_decision": 0.04,
            "profit_units": 1.0,
            "predicted_success": 0.6, "realized_success": 0.5,
        }
        for _ in range(299)
    ]
    non_warmup.extend(
        {
            "market": "TOTALS",
            "selection": "UNDER",
            "warmup": False,
            "filter_decision": "FILTERED",
            "bias_at_decision": 0.04,
            "profit_units": -1.0,
            "predicted_success": 0.8, "realized_success": 0.2,
        }
        for _ in range(10)
    )
    warmup_rows = [
        {
            "market": "TOTALS",
            "selection": "UNDER",
            "warmup": True,
            "filter_decision": "KEPT",
            # These deliberately violate all three criteria and must be ignored.
            "bias_at_decision": -1.0,
            "profit_units": -1.0,
            "predicted_success": 0.0, "realized_success": 1.0,
        }
        for _ in range(500)
    ]
    assert not evaluate_fast_criteria(non_warmup + warmup_rows)
    non_warmup.append(
        {
            "market": "TOTALS",
            "selection": "UNDER",
            "warmup": False,
            "filter_decision": "KEPT",
            "bias_at_decision": 0.04,
            "profit_units": 1.0,
            "predicted_success": 0.6, "realized_success": 0.5,
        }
    )
    assert evaluate_fast_criteria(non_warmup + warmup_rows)


def test_b5_forward_start_is_single_domain_object() -> None:
    from w2.strategy.online_calibration_filter import FORWARD_START_UTC

    assert FORWARD_START_UTC is ROUTER_FORWARD_START_UTC is CONTRACT_FORWARD_START_UTC


def test_b7_build_bias_pool_requires_knowable_mapping() -> None:
    try:
        build_bias_pool([], [])  # type: ignore[call-arg]
    except TypeError:
        return
    raise AssertionError("legacy two-argument build_bias_pool call must fail")
