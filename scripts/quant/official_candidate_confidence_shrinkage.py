"""GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1.

One accuracy candidate, offline only. It changes how confident a five-state
distribution is and nothing else: not the side, not the market, not the line,
not the odds, not the factor verdict, not the settlement, not the recorded
result. Production never imports this module.

Where it differs from the incumbent rolling temperature already in the evidence
package: this one pools every market into a single global fit rather than
fitting AH and TOTALS on separate axes, and its grid starts at 1.00, so the
candidate can only soften a distribution, never sharpen one. The recorded
overconfidence runs one way -- predicted graded win rate about 21pp above
actual -- and a grid that could sharpen would let the search answer a question
nobody asked.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from w2.domain.five_state_pricing import (
    PROBABILITY_TOLERANCE,
    SettlementDistribution,
    expected_value,
)

CANDIDATE_ID = "GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1"
CANDIDATE_SCHEMA = "w2.official_candidate_confidence_shrinkage.v1"
STATES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
GRADE = {"WIN": 1.0, "HALF_WIN": 0.5, "HALF_LOSS": 0.0, "LOSS": 0.0}
MIN_TRAINING_ROWS = 20
OBJECTIVE_PENALTY = 0.10
PROBABILITY_FLOOR = 1e-12
# Frozen before any result was looked at: 1.00 to 2.00 inclusive, step 0.01.
T_GRID = tuple(round(1.00 + i * 0.01, 2) for i in range(101))
NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE = "NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE"
NOT_ESTIMABLE_MISSING_EV_SE = "NOT_ESTIMABLE_MISSING_EV_SE"
NOT_ESTIMABLE_MISSING_DISTRIBUTION = "NOT_ESTIMABLE_MISSING_DISTRIBUTION"
NOT_ESTIMABLE_MISSING_ODDS = "NOT_ESTIMABLE_MISSING_ODDS"


def utc(value: object) -> datetime | None:
    """Parse a timestamp to an aware UTC datetime, or None when it is unusable.

    The corpus does not spell its two time fields the same way: a settlement
    time arrives from a Postgres timestamptz as ``2026-08-20 02:36:31.442008+00``
    and an evaluation time as ``2026-08-20T00:22:32.149069Z``. Compared as text
    those differ at index 10, ``' '`` (0x20) against ``'T'`` (0x54), so every
    space-separated settlement would sort before every T-separated evaluation
    whatever the instants were. Timestamps are never compared as strings here.

    A naive value is read as UTC -- every timestamp in this corpus comes from a
    UTC column. Anything unparseable returns None and the caller fails closed.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_FAR_FUTURE = datetime.max.replace(tzinfo=UTC)


def temporal_key(row: dict[str, Any]) -> tuple[datetime, datetime, str]:
    """Chronological order by parsed instant, never by text."""
    return (
        utc(row.get("evaluated_at")) or _FAR_FUTURE,
        utc(row.get("kickoff_utc")) or _FAR_FUTURE,
        str(row.get("evaluation_id") or ""),
    )


def is_training_evidence(other: dict[str, Any], row: dict[str, Any]) -> bool:
    """Whether `other` may train the temperature applied to `row`.

    Unlike the incumbent this does not require a matching market: the candidate
    fits one global temperature. What it does require is that `other` was
    authoritatively settled strictly before `row` was evaluated. A result
    landing at the same instant is not yet knowledge, and an unknown or
    unparseable time is not evidence of anything, so both are excluded.
    """
    available = utc(other.get("result_available_at"))
    evaluated = utc(row.get("evaluated_at"))
    if available is None or evaluated is None:
        return False
    return available < evaluated


def temper(dist: dict[str, float], temperature: float) -> dict[str, float]:
    """q_j(T) = exp(log(max(p_j, 1e-12)) / T) / sum_k exp(...), renormalised."""
    if temperature <= 0:
        raise ValueError("TEMPERATURE_MUST_BE_POSITIVE")
    logits = [
        math.log(max(float(dist.get(state, 0.0)), PROBABILITY_FLOOR)) / temperature
        for state in STATES
    ]
    peak = max(logits)
    weights = [math.exp(value - peak) for value in logits]
    total = sum(weights)
    if total <= 0:
        raise ValueError("TEMPERED_DISTRIBUTION_COLLAPSED")
    return {state: weight / total for state, weight in zip(STATES, weights, strict=True)}


def multiclass_log_loss(dist: dict[str, float], settlement: str) -> float:
    return -math.log(max(float(dist.get(settlement, 0.0)), PROBABILITY_FLOOR))


def multiclass_brier(dist: dict[str, float], settlement: str) -> float:
    return sum(
        (float(dist.get(state, 0.0)) - (1.0 if state == settlement else 0.0)) ** 2
        for state in STATES
    )


def conditional_graded(dist: dict[str, float]) -> float:
    """Predicted graded win rate conditional on the bet not pushing."""
    push = float(dist.get("PUSH", 0.0))
    if push >= 1.0:
        return 0.0
    decisive = 1.0 - push
    return (float(dist.get("WIN", 0.0)) + 0.5 * float(dist.get("HALF_WIN", 0.0))) / decisive


def fit_global_temperature(training: list[dict[str, Any]]) -> float:
    """Grid search over the frozen grid with the frozen penalty and tie-break.

    Below MIN_TRAINING_ROWS there is nothing to fit and the neutral temperature
    stands. Ties resolve to the T nearest 1.00 and then to the smaller value, so
    the choice is a function of the training set alone and never of the order
    the grid happened to be walked in.
    """
    if len(training) < MIN_TRAINING_ROWS:
        return 1.00
    best: tuple[float, float] | None = None
    for temperature in T_GRID:
        losses = [
            multiclass_log_loss(temper(row["dist"], temperature), row["settlement"])
            for row in training
        ]
        objective = (
            sum(losses) / len(losses) + OBJECTIVE_PENALTY * (math.log(temperature) ** 2)
        )
        if best is None:
            best = (temperature, objective)
            continue
        incumbent_t, incumbent_objective = best
        if objective < incumbent_objective - 1e-15:
            best = (temperature, objective)
        elif abs(objective - incumbent_objective) <= 1e-15 and (
            (abs(temperature - 1.00), temperature)
            < (abs(incumbent_t - 1.00), incumbent_t)
        ):
            best = (temperature, objective)
    assert best is not None
    return best[0]


def frozen_distribution(dist: dict[str, float]) -> SettlementDistribution:
    """Freeze a tempered distribution into the canonical Decimal five-state type.

    The 1e-9 contract is checked before normalisation as well as after.
    ``normalized()`` divides by the total, so checking only afterwards would
    silently rescale any drift and the check could never fail.
    """
    incoming = sum(Decimal(str(dist[state])) for state in STATES)
    if abs(incoming - 1) > PROBABILITY_TOLERANCE:
        raise ValueError("CALIBRATED_DISTRIBUTION_FAILED_1E9_CONTRACT")
    frozen = SettlementDistribution(
        full_win_probability=Decimal(str(dist["WIN"])),
        half_win_probability=Decimal(str(dist["HALF_WIN"])),
        push_probability=Decimal(str(dist["PUSH"])),
        half_loss_probability=Decimal(str(dist["HALF_LOSS"])),
        full_loss_probability=Decimal(str(dist["LOSS"])),
    ).normalized()
    total = sum(
        (getattr(frozen, name) for name in frozen.__dataclass_fields__), Decimal(0)
    )
    if abs(total - 1) > PROBABILITY_TOLERANCE:
        raise ValueError("CALIBRATED_DISTRIBUTION_FAILED_1E9_CONTRACT")
    return frozen


def canonical_expected_value(decimal_odds: object, dist: dict[str, float]) -> float:
    """EV through the repository's sole Decimal five-state authority."""
    return float(expected_value(Decimal(str(decimal_odds)), frozen_distribution(dist)))


def apply_candidate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Walk the corpus in real chronological order, fitting T from the past only.

    Returns one enriched record per input row, in that chronological order. Each
    carries the temperature it was given, how many rows were eligible to train
    it, and the calibrated distribution -- never a distribution fitted on the
    row's own result or on anything later.
    """
    ordered = sorted(rows, key=temporal_key)
    out: list[dict[str, Any]] = []
    for index, row in enumerate(ordered):
        training = [
            {"dist": other["dist"], "settlement": other["settlement"]}
            for other in ordered[:index]
            if is_training_evidence(other, row)
        ]
        temperature = fit_global_temperature(training)
        calibrated = temper(row["dist"], temperature)
        out.append({
            **row,
            "candidate_id": CANDIDATE_ID,
            "temperature": temperature,
            "training_rows": len(training),
            "result_knowledge_cutoff": row["evaluated_at"],
            "incumbent_dist": dict(row["dist"]),
            "candidate_dist": calibrated,
        })
    return out
