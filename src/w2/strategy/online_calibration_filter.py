"""EV-ONLINE-01's independent, fail-closed calibration filter.

This module is intentionally separate from ``strategy.calibration`` and from
the official recommendation/materialisation path.  It reads the existing
evaluation, validation and runtime settlement-fact tables and writes only the
new ``validation_samples_calibrated`` projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.dynamic_prematch_models import (
    CalibratedValidationSampleModel,
    DynamicPrematchEvaluationModel,
    ValidationSampleModel,
)
from w2.infrastructure.persistence.models import RuntimeAhSettlementFactModel

PARAM_VERSION = "w2.ev_online.market_selection_rolling_mean.v2"
STRATIFICATION_KEY = ("market", "selection")
WARMUP_OBSERVATIONS = 50
EV_THRESHOLD = 0.0
LEGAL_STATE = "ANALYSIS_PICK_ACTIVE"


@dataclass(frozen=True)
class BiasObservation:
    market: str
    selection: str
    evaluated_at: datetime
    settlement_observed_at: datetime
    predicted_success: float
    realized_success: float


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _settlement_success(value: str | None) -> float | None:
    return {
        "WIN": 1.0,
        "HALF_WIN": 0.5,
        "PUSH": 0.0,
        "HALF_LOSS": 0.0,
        "LOSS": 0.0,
    }.get(str(value).upper()) if value is not None else None


def _predicted_success(payload: dict[str, Any]) -> float | None:
    distribution = _mapping(payload.get("model_settlement_distribution"))
    if not distribution:
        return None
    try:
        value = float(distribution.get("WIN", 0.0)) + 0.5 * float(
            distribution.get("HALF_WIN", 0.0)
        )
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def _fact_for_fixture(
    facts: dict[str, RuntimeAhSettlementFactModel], fixture_id: str,
) -> RuntimeAhSettlementFactModel | None:
    return facts.get(fixture_id) or facts.get(f"api_football:{fixture_id}")


def build_bias_pool(
    evaluations: Iterable[DynamicPrematchEvaluationModel],
    facts: dict[str, RuntimeAhSettlementFactModel],
) -> list[BiasObservation]:
    """Build only observations with a real terminal capture before evaluation.

    Missing ``settlement_observed_at`` (and markets without a corresponding
    runtime fact, currently TOTALS) are deliberately omitted rather than
    substituted with ``confirmed_at``, ``settled_at`` or a time proxy.
    """

    output: list[BiasObservation] = []
    for evaluation in evaluations:
        if evaluation.original_state != LEGAL_STATE:
            continue
        evaluated_at = _utc(evaluation.evaluated_at)
        if evaluated_at is None:
            continue
        fact = _fact_for_fixture(facts, str(evaluation.fixture_id))
        if fact is None or evaluation.market != "ASIAN_HANDICAP":
            continue
        observed_at = _utc(fact.settlement_observed_at)
        if observed_at is None or observed_at >= evaluated_at:
            continue
        predicted = _predicted_success(_mapping(evaluation.payload))
        settlement = (
            fact.home_settlement
            if evaluation.selection == "HOME"
            else fact.away_settlement
            if evaluation.selection == "AWAY"
            else None
        )
        realized = _settlement_success(settlement)
        if predicted is None or realized is None:
            continue
        output.append(
            BiasObservation(
                market=evaluation.market,
                selection=evaluation.selection,
                evaluated_at=evaluated_at,
                settlement_observed_at=observed_at,
                predicted_success=predicted,
                realized_success=realized,
            )
        )
    return output


def _prior_observations(
    *,
    market: str,
    selection: str,
    evaluated_at: datetime,
    observations: Iterable[BiasObservation],
) -> list[BiasObservation]:

    target = _utc(evaluated_at)
    if target is None:
        return []
    prior = sorted(
        (
            item
            for item in observations
            if item.market == market
            and item.selection == selection
            and item.settlement_observed_at < target
            and item.evaluated_at < target
        ),
        key=lambda item: (item.settlement_observed_at, item.evaluated_at),
    )
    return prior


def bias_at_decision(
    *,
    market: str,
    selection: str,
    evaluated_at: datetime,
    observations: Iterable[BiasObservation],
) -> float | None:
    """Return the frozen non-negative equal-weight mean bias.

    A zero return means the stratified history is still in warmup. The
    materializer keeps that semantic zero out of the stored bias column and
    records a warmup row as KEPT with a NULL stored bias.
    """

    prior = _prior_observations(
        market=market,
        selection=selection,
        evaluated_at=evaluated_at,
        observations=observations,
    )
    if len(prior) < WARMUP_OBSERVATIONS:
        return 0.0
    mean_bias = sum(item.predicted_success - item.realized_success for item in prior) / len(prior)
    # The online layer is a one-way filter. Negative empirical bias never
    # creates a new candidate or increases EV in the existing recommendation path.
    return max(0.0, min(1.0, mean_bias))


def decision_from_bias(
    *,
    raw_ev: float | None,
    decimal_odds: float,
    bias: float | None,
    observed_at: datetime | None,
    history_count: int,
) -> tuple[str, float | None, float | None, bool]:
    """Return ``decision, stored_bias, corrected_ev, warmup``.

    A real observed timestamp is required before warmup can release a row.
    This keeps missing-source records fail-closed while making the first 50
    valid observations pass through unchanged.
    """

    warmup = observed_at is not None and history_count < WARMUP_OBSERVATIONS
    if observed_at is None:
        return "FILTERED", None, None, False
    if warmup and raw_ev is not None:
        return "KEPT", None, raw_ev, True
    if bias is None or raw_ev is None:
        return "FILTERED", bias, None, False
    corrected = raw_ev - bias * decimal_odds
    return ("KEPT" if corrected >= EV_THRESHOLD else "FILTERED"), bias, corrected, False


def _sample_payload(sample: ValidationSampleModel) -> dict[str, Any]:
    return {
        "fixture_id": sample.fixture_id,
        "market": sample.market,
        "competition_id": sample.competition_id,
        "kickoff_utc": sample.kickoff_utc,
        "selection": sample.selection,
        "exact_line": sample.exact_line,
        "decimal_odds": sample.decimal_odds,
        "bookmaker_id": sample.bookmaker_id,
        "first_checkpoint": sample.first_checkpoint,
        "final_checkpoint": sample.final_checkpoint,
        "evaluation_id": sample.evaluation_id,
        "calibration_identity": sample.calibration_identity,
        "settlement": sample.settlement,
        "profit_units": sample.profit_units,
        "score": sample.score,
        "settled_at": sample.settled_at,
        "evaluated_at": sample.evaluated_at,
        "quote_captured_at": sample.quote_captured_at,
        "current_ev": sample.current_ev,
        "home_team_label": sample.home_team_label,
        "away_team_label": sample.away_team_label,
        "later_unassessed_checkpoints": sample.later_unassessed_checkpoints,
        "lifecycle_note_zh": sample.lifecycle_note_zh,
    }


def _copy_sample(sample: ValidationSampleModel, *, observed: datetime | None, bias: float | None, decision: str, ev_corrected: float | None, warmup: bool) -> CalibratedValidationSampleModel:
    values = _sample_payload(sample)
    values.update(
        settlement_observed_at=observed,
        bias_at_decision=bias,
        ev_raw=sample.current_ev,
        ev_corrected=ev_corrected,
        filter_decision=decision,
        param_version=PARAM_VERSION,
        warmup=warmup,
        projected_at=sample.projected_at,
    )
    return CalibratedValidationSampleModel(**values)


def materialize_calibrated_validation_samples(session: Session) -> dict[str, int]:
    """Reconcile the independent table from existing rows only."""

    samples = list(session.scalars(select(ValidationSampleModel)))
    evaluations = list(
        session.scalars(
            select(DynamicPrematchEvaluationModel).where(
                DynamicPrematchEvaluationModel.original_state == LEGAL_STATE
            )
        )
    )
    facts: dict[str, RuntimeAhSettlementFactModel] = {}
    for fact in session.scalars(select(RuntimeAhSettlementFactModel)):
        for fixture_id in (fact.fixture_id, fact.fixture_id.removeprefix("api_football:")):
            facts[str(fixture_id)] = fact
    pool = build_bias_pool(evaluations, facts)
    evaluation_by_id = {row.evaluation_id: row for row in evaluations}
    existing = {(row.fixture_id, row.market): row for row in session.scalars(select(CalibratedValidationSampleModel))}
    seen: set[tuple[str, str]] = set()
    kept = filtered = 0
    for sample in samples:
        evaluation = evaluation_by_id.get(sample.evaluation_id)
        evaluated_at = _utc(evaluation.evaluated_at if evaluation else sample.evaluated_at)
        prior = _prior_observations(
            market=sample.market,
            selection=sample.selection,
            evaluated_at=evaluated_at or datetime.min.replace(tzinfo=UTC),
            observations=pool,
        )
        fact = _fact_for_fixture(facts, str(sample.fixture_id))
        observed = _utc(fact.settlement_observed_at) if fact else None
        raw_ev = sample.current_ev
        bias = bias_at_decision(
            market=sample.market,
            selection=sample.selection,
            evaluated_at=evaluated_at or datetime.min.replace(tzinfo=UTC),
            observations=pool,
        )
        decision, stored_bias, corrected, warmup = decision_from_bias(
            raw_ev=raw_ev,
            decimal_odds=sample.decimal_odds,
            bias=bias,
            observed_at=observed,
            history_count=len(prior),
        )
        row = _copy_sample(sample, observed=observed, bias=stored_bias, decision=decision, ev_corrected=corrected, warmup=warmup)
        existing_row = existing.get((sample.fixture_id, sample.market))
        if existing_row is None:
            session.add(row)
        else:
            for key, value in row.__dict__.items():
                if key not in {"_sa_instance_state", "fixture_id", "market"}:
                    setattr(existing_row, key, value)
        seen.add((sample.fixture_id, sample.market))
        kept += decision == "KEPT"
        filtered += decision == "FILTERED"
    for key, row in existing.items():
        if key not in seen:
            session.delete(row)
    session.flush()
    return {"source_rows": len(samples), "kept": kept, "filtered": filtered}


def calibrated_sample_projection(row: CalibratedValidationSampleModel) -> dict[str, Any]:
    return {
        "fixture_id": row.fixture_id,
        "market": row.market,
        "competition_id": row.competition_id,
        "kickoff_utc": row.kickoff_utc,
        "selection": row.selection,
        "exact_line": row.exact_line,
        "decimal_odds": row.decimal_odds,
        "evaluation_id": row.evaluation_id,
        "settlement": row.settlement,
        "profit_units": row.profit_units,
        "score": row.score,
        "settled_at": row.settled_at,
        "evaluated_at": row.evaluated_at,
        "home_team_label": row.home_team_label or {},
        "away_team_label": row.away_team_label or {},
        "settlement_observed_at": row.settlement_observed_at,
        "bias_at_decision": row.bias_at_decision,
        "ev_raw": row.ev_raw,
        "ev_corrected": row.ev_corrected,
        "filter_decision": row.filter_decision,
        "param_version": row.param_version,
        "warmup": row.warmup,
    }


def evaluate_fast_criteria(rows: Iterable[dict[str, Any]], *, minimum_kept: int = 300) -> bool:
    """Evaluate the frozen keep/withdraw rule without using P&L as a gate.

    ``cal_gap`` must be supplied by the independent settlement evaluator; the
    projection itself intentionally does not invent a probability label from
    ``profit_units``. Missing evidence fails closed.
    """

    # All three fast criteria, including the trigger count, share this exact
    # post-warmup population. Warmup pass-through rows must never dilute the
    # evaluation of the filter that only exists after warmup.
    evaluated = [row for row in rows if row.get("warmup") is False]
    kept = [row for row in evaluated if row.get("filter_decision") == "KEPT"]
    filtered = [row for row in evaluated if row.get("filter_decision") == "FILTERED"]
    if len(kept) < minimum_kept:
        return False
    for group in {
        (row.get("market"), row.get("selection")) for row in evaluated
    }:
        group_rows = [
            row
            for row in evaluated
            if (row.get("market"), row.get("selection")) == group
        ]
        biases = [row.get("bias_at_decision") for row in group_rows]
        if not biases or any(not isinstance(value, (int, float)) or value <= 0 for value in biases):
            return False
    def positive_rate(group: list[dict[str, Any]]) -> float | None:
        profits = [row.get("profit_units") for row in group]
        if not profits or any(not isinstance(value, (int, float)) for value in profits):
            return None
        return sum(float(value) > 0 for value in profits) / len(profits)

    kept_rate = positive_rate(kept)
    filtered_rate = positive_rate(filtered)
    if kept_rate is None or filtered_rate is None or not filtered_rate < kept_rate:
        return False
    kept_gaps = [row.get("cal_gap") for row in kept]
    filtered_gaps = [row.get("cal_gap") for row in filtered]
    if not kept_gaps or not filtered_gaps or any(
        not isinstance(value, (int, float)) for value in (*kept_gaps, *filtered_gaps)
    ):
        return False
    return sum(abs(float(value)) for value in kept_gaps) / len(kept_gaps) <= sum(
        abs(float(value)) for value in filtered_gaps
    ) / len(filtered_gaps)
