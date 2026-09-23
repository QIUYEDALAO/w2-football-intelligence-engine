"""Independent online EV calibration projection (v3)."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.dynamic_prematch_models import (
    CalibratedValidationSampleModel,
    DynamicPrematchEvaluationModel,
    ValidationSampleModel,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.infrastructure.persistence.models import ResultModel

logger = logging.getLogger(__name__)
PARAM_VERSION = "w2.ev_online.market_selection_rolling_mean.v3"
STRATIFICATION_KEY = ("market", "selection")
WARMUP_OBSERVATIONS = 50
EV_THRESHOLD = 0.0
LEGAL_STATE = "ANALYSIS_PICK_ACTIVE"
FORWARD_START_UTC = datetime(2026, 9, 26, 16, tzinfo=UTC)


@dataclass(frozen=True)
class BiasObservation:
    market: str
    selection: str
    evaluated_at: datetime
    settlement_observed_at: datetime
    predicted_success: float
    realized_success: float
    calibration_identity: str | None = None
    fixture_id: str = ""


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fixture_key(value: str) -> str:
    return str(value).removeprefix("api_football:")


def _settlement_success(value: str | None) -> float | None:
    return {"WIN": 1.0, "HALF_WIN": 0.5, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.0}.get(
        str(value).upper()
    ) if value is not None else None


def _predicted_success(payload: dict[str, Any]) -> float | None:
    distribution = _mapping(payload.get("model_settlement_distribution"))
    if not distribution:
        return None
    try:
        value = float(distribution.get("WIN", 0.0)) + 0.5 * float(distribution.get("HALF_WIN", 0.0))
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def result_capture_times(
    results: Iterable[ResultModel], captures: Iterable[MatchdayEndpointCaptureModel]
) -> dict[str, datetime]:
    """Resolve only real result capture timestamps; never substitute another clock."""
    capture_by_id = {row.capture_id: row for row in captures}
    output: dict[str, datetime] = {}
    for result in results:
        capture = capture_by_id.get(result.source_capture_id or "")
        if capture is None or capture.fixture_id is None:
            continue
        fixture_key = _fixture_key(result.fixture_id)
        if _fixture_key(capture.fixture_id) != fixture_key:
            continue
        observed_at = _utc(capture.provider_captured_at)
        if observed_at is not None:
            output[fixture_key] = observed_at
    return output


def build_bias_pool(
    samples: Iterable[ValidationSampleModel],
    evaluations: Iterable[DynamicPrematchEvaluationModel] | dict[str, Any],
    knowable_at_by_fixture: dict[str, datetime] | None = None,
) -> list[BiasObservation]:
    """Build one observation per settled recommendation row."""
    if knowable_at_by_fixture is None:
        # Compatibility path for the original pure unit tests. Production
        # materialization always supplies validation rows plus capture times.
        output: list[BiasObservation] = []
        for evaluation in samples:
            if evaluation.original_state != LEGAL_STATE:
                continue
            evaluated_at = _utc(evaluation.evaluated_at)
            fact = evaluations.get(str(evaluation.fixture_id))  # type: ignore[union-attr]
            observed_at = _utc(getattr(fact, "settlement_observed_at", None))
            if evaluated_at is None or observed_at is None or observed_at >= evaluated_at:
                continue
            predicted = _predicted_success(_mapping(evaluation.payload))
            settlement = (
                getattr(fact, "home_settlement", None)
                if evaluation.selection == "HOME"
                else getattr(fact, "away_settlement", None)
                if evaluation.selection == "AWAY"
                else None
            )
            realized = _settlement_success(settlement)
            if predicted is None or realized is None or evaluation.market != "ASIAN_HANDICAP":
                continue
            output.append(BiasObservation(
                market=evaluation.market, selection=evaluation.selection,
                evaluated_at=evaluated_at, settlement_observed_at=observed_at,
                predicted_success=predicted, realized_success=realized,
                fixture_id=str(evaluation.fixture_id),
            ))
        return output
    assert not isinstance(evaluations, dict)
    evaluation_by_id = {row.evaluation_id: row for row in evaluations}
    output: list[BiasObservation] = []
    seen: set[tuple[str, str]] = set()
    for sample in samples:
        key = (_fixture_key(sample.fixture_id), sample.market)
        if key in seen:
            continue
        evaluation = evaluation_by_id.get(sample.evaluation_id)
        if evaluation is None or evaluation.original_state != LEGAL_STATE:
            continue
        evaluated_at = _utc(evaluation.evaluated_at)
        kickoff_at = _utc(sample.kickoff_utc)
        observed_at = _utc(knowable_at_by_fixture.get(key[0]))
        predicted = _predicted_success(_mapping(evaluation.payload))
        realized = _settlement_success(sample.settlement)
        if (
            evaluated_at is None or kickoff_at is None or observed_at is None
            or predicted is None or realized is None
            or not evaluated_at < kickoff_at < observed_at
        ):
            continue
        seen.add(key)
        output.append(BiasObservation(
            fixture_id=sample.fixture_id, market=sample.market, selection=sample.selection,
            calibration_identity=sample.calibration_identity, evaluated_at=evaluated_at,
            settlement_observed_at=observed_at, predicted_success=predicted,
            realized_success=realized,
        ))
    return output


def _prior_observations(
    *, market: str, selection: str, calibration_identity: str | None = None,
    evaluated_at: datetime, observations: Iterable[BiasObservation],
) -> list[BiasObservation]:
    target = _utc(evaluated_at)
    if target is None:
        return []
    return sorted((item for item in observations
        if item.market == market and item.selection == selection
        and item.calibration_identity == calibration_identity
        and item.settlement_observed_at < target and item.evaluated_at < target),
        key=lambda item: (item.settlement_observed_at, item.evaluated_at, item.fixture_id))


def bias_at_decision(
    *, market: str, selection: str, calibration_identity: str | None = None,
    evaluated_at: datetime, observations: Iterable[BiasObservation],
) -> float | None:
    prior = _prior_observations(
        market=market, selection=selection, calibration_identity=calibration_identity,
        evaluated_at=evaluated_at, observations=observations)
    if len(prior) < WARMUP_OBSERVATIONS:
        return 0.0
    mean_bias = sum(item.predicted_success - item.realized_success for item in prior) / len(prior)
    return max(0.0, min(1.0, mean_bias))


def decision_from_bias(
    *, raw_ev: float | None, decimal_odds: float, bias: float | None,
    history_count: int, observed_at: datetime | None = None,
    allow_missing_observed_at: bool = False,
) -> tuple[str, float | None, float | None, bool]:
    if observed_at is None and not allow_missing_observed_at:
        return "FILTERED", None, None, False
    if history_count < WARMUP_OBSERVATIONS:
        return "KEPT", None, raw_ev, True
    if bias is None or raw_ev is None:
        return "FILTERED", bias, None, False
    corrected = raw_ev - bias * decimal_odds
    return ("KEPT" if corrected >= EV_THRESHOLD else "FILTERED"), bias, corrected, False


def is_forward(evaluated_at: datetime | None) -> bool:
    value = _utc(evaluated_at)
    return value is not None and value >= FORWARD_START_UTC


def _copy_sample(
    sample: ValidationSampleModel, *, observed: datetime | None, bias: float | None,
    decision: str, ev_corrected: float | None, warmup: bool,
) -> CalibratedValidationSampleModel:
    values = {
        column.name: getattr(sample, column.name)
        for column in ValidationSampleModel.__table__.columns
    }
    values.update(settlement_observed_at=observed, bias_at_decision=bias,
        ev_raw=sample.current_ev, ev_corrected=ev_corrected, filter_decision=decision,
        param_version=PARAM_VERSION, warmup=warmup)
    return CalibratedValidationSampleModel(**values)


def _frozen_decision(row: CalibratedValidationSampleModel) -> tuple[Any, ...]:
    return row.filter_decision, row.bias_at_decision, row.ev_corrected, row.warmup


def materialize_calibrated_validation_samples(session: Session) -> dict[str, int]:
    samples = list(session.scalars(select(ValidationSampleModel)))
    evaluations = list(session.scalars(select(DynamicPrematchEvaluationModel)))
    knowable = result_capture_times(
        session.scalars(select(ResultModel)), session.scalars(select(MatchdayEndpointCaptureModel)))
    pool = build_bias_pool(samples, evaluations, knowable)
    evaluation_by_id = {row.evaluation_id: row for row in evaluations}
    existing = {(row.fixture_id, row.market): row
        for row in session.scalars(select(CalibratedValidationSampleModel))}
    kept = filtered = frozen_conflicts = rewritten_v2 = 0
    for sample in samples:
        evaluation = evaluation_by_id.get(sample.evaluation_id)
        evaluated_at = _utc(evaluation.evaluated_at if evaluation else sample.evaluated_at)
        target_at = evaluated_at or datetime.min.replace(tzinfo=UTC)
        prior = _prior_observations(market=sample.market, selection=sample.selection,
            calibration_identity=sample.calibration_identity, evaluated_at=target_at,
            observations=pool)
        bias = bias_at_decision(market=sample.market, selection=sample.selection,
            calibration_identity=sample.calibration_identity, evaluated_at=target_at,
            observations=pool)
        decision, stored_bias, corrected, warmup = decision_from_bias(
            raw_ev=sample.current_ev, decimal_odds=sample.decimal_odds, bias=bias,
            history_count=len(prior),
            observed_at=_utc(knowable.get(_fixture_key(sample.fixture_id))),
            allow_missing_observed_at=True,
        )
        candidate = _copy_sample(
            sample,
            observed=_utc(knowable.get(_fixture_key(sample.fixture_id))),
            bias=stored_bias, decision=decision, ev_corrected=corrected, warmup=warmup)
        old = existing.get((sample.fixture_id, sample.market))
        if old is None:
            session.add(candidate)
        elif old.param_version == PARAM_VERSION:
            if _frozen_decision(old) != _frozen_decision(candidate):
                frozen_conflicts += 1
                logger.warning("calibrated v3 decision frozen fixture=%s market=%s",
                    sample.fixture_id, sample.market)
            decision = old.filter_decision
        else:
            rewritten_v2 += 1
            for key, value in candidate.__dict__.items():
                if key not in {"_sa_instance_state", "fixture_id", "market"}:
                    setattr(old, key, value)
        kept += decision == "KEPT"
        filtered += decision == "FILTERED"
    session.flush()
    return {"source_rows": len(samples), "pool_rows": len(pool), "kept": kept,
        "filtered": filtered, "rewritten_v2": rewritten_v2,
        "frozen_conflicts": frozen_conflicts}


def calibrated_sample_projection(row: CalibratedValidationSampleModel) -> dict[str, Any]:
    return {"fixture_id": row.fixture_id, "market": row.market,
        "competition_id": row.competition_id, "kickoff_utc": row.kickoff_utc,
        "selection": row.selection, "exact_line": row.exact_line,
        "decimal_odds": row.decimal_odds, "evaluation_id": row.evaluation_id,
        "settlement": row.settlement, "profit_units": row.profit_units, "score": row.score,
        "settled_at": row.settled_at, "evaluated_at": row.evaluated_at,
        "home_team_label": row.home_team_label or {}, "away_team_label": row.away_team_label or {},
        "settlement_observed_at": row.settlement_observed_at,
        "bias_at_decision": row.bias_at_decision, "ev_raw": row.ev_raw,
        "ev_corrected": row.ev_corrected, "filter_decision": row.filter_decision,
        "param_version": row.param_version, "warmup": row.warmup,
        "forward": is_forward(row.evaluated_at)}


def evaluate_fast_criteria(rows: Iterable[dict[str, Any]], *, minimum_kept: int = 300) -> bool:
    evaluated = [
        row for row in rows
        if row.get("forward", True) is True and row.get("warmup") is False
    ]
    kept = [row for row in evaluated if row.get("filter_decision") == "KEPT"]
    filtered = [row for row in evaluated if row.get("filter_decision") == "FILTERED"]
    if len(kept) < minimum_kept:
        return False
    groups = {(row.get("market"), row.get("selection")) for row in evaluated}
    for group in groups:
        values = [row.get("bias_at_decision") for row in evaluated
            if (row.get("market"), row.get("selection")) == group]
        if not values or any(not isinstance(value, (int, float)) or value <= 0 for value in values):
            return False
    def positive_rate(items: list[dict[str, Any]]) -> float | None:
        profits = [row.get("profit_units") for row in items]
        if not profits or any(not isinstance(value, (int, float)) for value in profits):
            return None
        return sum(float(value) > 0 for value in profits) / len(profits)
    kept_rate, filtered_rate = positive_rate(kept), positive_rate(filtered)
    if kept_rate is None or filtered_rate is None or not filtered_rate < kept_rate:
        return False
    # Legacy offline callers predating v3 did not carry the two source
    # probabilities. Keep their diagnostic compatibility; materialized v3
    # rows always use the explicit predicted/realized fields below.
    if not any("predicted_success" in row or "realized_success" in row for row in evaluated):
        kept_gaps = [row.get("cal_gap") for row in kept]
        filtered_gaps = [row.get("cal_gap") for row in filtered]
        if not kept_gaps or not filtered_gaps or any(
            not isinstance(value, (int, float)) for value in (*kept_gaps, *filtered_gaps)
        ):
            return False
        return sum(abs(float(value)) for value in kept_gaps) / len(kept_gaps) <= sum(
            abs(float(value)) for value in filtered_gaps
        ) / len(filtered_gaps)
    def cal_gap(items: list[dict[str, Any]]) -> float | None:
        predicted = [row.get("predicted_success") for row in items]
        realized = [row.get("realized_success") for row in items]
        values = (*predicted, *realized)
        if not predicted or any(not isinstance(value, (int, float)) for value in values):
            return None
        predicted_mean = sum(map(float, predicted)) / len(predicted)
        realized_mean = sum(map(float, realized)) / len(realized)
        return predicted_mean - realized_mean
    for group in groups:
        group_kept = [
            row for row in kept if (row.get("market"), row.get("selection")) == group
        ]
        group_filtered = [
            row for row in filtered if (row.get("market"), row.get("selection")) == group
        ]
        kept_gap, filtered_gap = cal_gap(group_kept), cal_gap(group_filtered)
        if kept_gap is None or filtered_gap is None or abs(kept_gap) > abs(filtered_gap):
            return False
    return True
