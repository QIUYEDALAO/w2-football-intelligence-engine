from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.models.dixon_coles import tau_correction

MARKET_ASIAN_HANDICAP = "ASIAN_HANDICAP"
MARKET_TOTALS = "TOTALS"
STATUS_READY = "READY"
STATUS_INSUFFICIENT = "INSUFFICIENT"
STATUS_INVALID = "INVALID"


@dataclass(frozen=True, kw_only=True)
class FairMarketEstimate:
    market: str
    status: str
    model_family: str
    fair_line: float | None
    probabilities: Mapping[str, float]
    home_mu: float | None
    away_mu: float | None
    feature_as_of: str | None
    train_cutoff: str | None
    artifact_hash: str | None = None
    artifact_version: str | None = None
    fallback_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def fair_lines_from_lambdas(
    *,
    home_mu: float,
    away_mu: float,
    rho: float = 0.0,
) -> tuple[float, float, dict[str, float], dict[str, float]]:
    matrix = score_distribution(home_mu=home_mu, away_mu=away_mu, rho=rho)
    fair_ah = _balanced_line(matrix, market=MARKET_ASIAN_HANDICAP)
    fair_ou = _balanced_line(matrix, market=MARKET_TOTALS)
    return (
        fair_ah,
        fair_ou,
        _outcome_probabilities(matrix, market=MARKET_ASIAN_HANDICAP, line=fair_ah),
        _outcome_probabilities(matrix, market=MARKET_TOTALS, line=fair_ou),
    )


def score_distribution(
    *,
    home_mu: float,
    away_mu: float,
    rho: float = 0.0,
    max_goals: int = 12,
) -> dict[tuple[int, int], float]:
    if home_mu <= 0 or away_mu <= 0:
        raise ValueError("goal lambdas must be positive")
    matrix: dict[tuple[int, int], float] = {}
    for home_goals in range(max_goals + 1):
        home_probability = _poisson(home_mu, home_goals)
        for away_goals in range(max_goals + 1):
            probability = home_probability * _poisson(away_mu, away_goals)
            probability *= tau_correction(home_goals, away_goals, home_mu, away_mu, rho)
            matrix[(home_goals, away_goals)] = max(probability, 0.0)
    total = sum(matrix.values())
    if total <= 0:
        raise ValueError("score distribution has no probability mass")
    return {score: probability / total for score, probability in matrix.items()}


def _balanced_line(matrix: Mapping[tuple[int, int], float], *, market: str) -> float:
    if market == MARKET_ASIAN_HANDICAP:
        candidates = [quarter / 4 for quarter in range(-16, 17)]
        selection = "HOME"
    elif market == MARKET_TOTALS:
        candidates = [quarter / 4 for quarter in range(2, 33)]
        selection = "OVER"
    else:
        raise ValueError(f"unsupported market: {market}")
    return min(
        candidates,
        key=lambda line: (
            abs(_expected_settlement_score(matrix, market=market, selection=selection, line=line)),
            abs(line),
            line,
        ),
    )


def _expected_settlement_score(
    matrix: Mapping[tuple[int, int], float],
    *,
    market: str,
    selection: str,
    line: float,
) -> float:
    total = 0.0
    decimal_line = Decimal(str(line))
    for (home_goals, away_goals), probability in matrix.items():
        if market == MARKET_ASIAN_HANDICAP:
            outcome = settle_asian_handicap(
                home_goals,
                away_goals,
                selection,
                decimal_line,
            )
        else:
            outcome = settle_total_goals(
                home_goals + away_goals,
                selection,
                decimal_line,
            )
        total += probability * _settlement_score(outcome)
    return total


def _outcome_probabilities(
    matrix: Mapping[tuple[int, int], float],
    *,
    market: str,
    line: float,
) -> dict[str, float]:
    selections = ("HOME", "AWAY") if market == MARKET_ASIAN_HANDICAP else ("OVER", "UNDER")
    probabilities: dict[str, float] = {}
    for selection in selections:
        expected = _expected_settlement_score(
            matrix,
            market=market,
            selection=selection,
            line=line,
        )
        probabilities[selection] = round((expected + 1.0) / 2.0, 8)
    return probabilities


def _settlement_score(outcome: SettlementOutcome) -> float:
    return {
        SettlementOutcome.WIN: 1.0,
        SettlementOutcome.HALF_WIN: 0.5,
        SettlementOutcome.PUSH: 0.0,
        SettlementOutcome.HALF_LOSS: -0.5,
        SettlementOutcome.LOSS: -1.0,
    }[outcome]


def _poisson(mu: float, goals: int) -> float:
    return math.exp(-mu) * mu**goals / math.factorial(goals)
