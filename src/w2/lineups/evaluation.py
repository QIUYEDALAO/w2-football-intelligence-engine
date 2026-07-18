from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class PairedEvaluationRow:
    fixture_id: str
    competition_id: str
    kickoff_epoch: int
    baseline_probability: float
    candidate_probability: float
    outcome: int
    baseline_rps: float
    candidate_rps: float
    baseline_covered: bool = True
    candidate_covered: bool = True


@dataclass(frozen=True, kw_only=True)
class MarketEvaluationGate:
    enabled: bool
    sample_count: int
    competition_count: int
    log_loss_delta: float | None
    log_loss_ci_low: float | None
    log_loss_ci_high: float | None
    rps_delta: float | None
    coverage_delta: float | None
    blockers: tuple[str, ...]


def evaluate_market_adjustment(
    rows: Iterable[PairedEvaluationRow],
    *,
    bootstrap_samples: int = 2_000,
    minimum_samples: int = 500,
    minimum_competitions: int = 3,
) -> MarketEvaluationGate:
    ordered = sorted(rows, key=lambda row: (row.kickoff_epoch, row.fixture_id))
    validation = ordered[math.floor(len(ordered) * 0.70) :]
    blockers: list[str] = []
    competitions = len({row.competition_id for row in validation})
    if len(validation) < minimum_samples:
        blockers.append("INSUFFICIENT_VALIDATION_FIXTURES")
    if competitions < minimum_competitions:
        blockers.append("INSUFFICIENT_COMPETITIONS")
    if not validation:
        return MarketEvaluationGate(
            enabled=False,
            sample_count=0,
            competition_count=0,
            log_loss_delta=None,
            log_loss_ci_low=None,
            log_loss_ci_high=None,
            rps_delta=None,
            coverage_delta=None,
            blockers=tuple(blockers),
        )
    deltas = [
        _log_loss(row.candidate_probability, row.outcome)
        - _log_loss(row.baseline_probability, row.outcome)
        for row in validation
    ]
    log_loss_delta = sum(deltas) / len(deltas)
    rps_delta = sum(row.candidate_rps - row.baseline_rps for row in validation) / len(validation)
    baseline_coverage = sum(row.baseline_covered for row in validation) / len(validation)
    candidate_coverage = sum(row.candidate_covered for row in validation) / len(validation)
    coverage_delta = candidate_coverage - baseline_coverage
    ci_low, ci_high = _bootstrap_mean_interval(deltas, samples=bootstrap_samples)
    if ci_high >= 0.0:
        blockers.append("LOG_LOSS_CI_NOT_IMPROVED")
    if rps_delta > 0.001:
        blockers.append("RPS_DEGRADED")
    if coverage_delta < -0.02:
        blockers.append("COVERAGE_DEGRADED")
    return MarketEvaluationGate(
        enabled=not blockers,
        sample_count=len(validation),
        competition_count=competitions,
        log_loss_delta=round(log_loss_delta, 8),
        log_loss_ci_low=round(ci_low, 8),
        log_loss_ci_high=round(ci_high, 8),
        rps_delta=round(rps_delta, 8),
        coverage_delta=round(coverage_delta, 8),
        blockers=tuple(blockers),
    )


def _log_loss(probability: float, outcome: int) -> float:
    probability = min(max(float(probability), 1e-9), 1.0 - 1e-9)
    return -(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability))


def _bootstrap_mean_interval(values: list[float], *, samples: int) -> tuple[float, float]:
    randomizer = random.Random(20260719)  # noqa: S311 - deterministic bootstrap, not security
    means = []
    for _ in range(samples):
        draw = [values[randomizer.randrange(len(values))] for _ in values]
        means.append(sum(draw) / len(draw))
    means.sort()
    low_index = max(0, math.floor(samples * 0.025))
    high_index = min(samples - 1, math.ceil(samples * 0.975) - 1)
    return means[low_index], means[high_index]
