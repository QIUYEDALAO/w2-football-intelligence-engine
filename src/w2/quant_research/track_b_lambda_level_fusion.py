"""Offline Track B lambda-level market fusion.

This module is deliberately side-effect free.  It is not wired into the operational
recommendation or settlement paths.  Track B weights are frozen by preregistration and
are constants here; callers cannot tune them at runtime.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import exp, isfinite, log

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.models.dixon_coles import poisson_pmf, tau_correction

OUTCOME_ORDER = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
FROZEN_W_AH = 0.9
FROZEN_W_TOTALS = 0.0
_MIN_LAMBDA = 0.05


@dataclass(frozen=True)
class FusionResult:
    market: str
    selection: str
    line: float
    lambda_home: float
    lambda_away: float
    lambda_total_model: float
    lambda_total_market: float
    delta_model: float
    delta_market: float
    distribution: dict[str, float]

    @property
    def effective_probability(self) -> float:
        return self.distribution["WIN"] + 0.5 * self.distribution["HALF_WIN"]

    @property
    def probability_sum(self) -> float:
        return sum(self.distribution.values())

    @property
    def weights(self) -> tuple[float, float]:
        if self.market == "ASIAN_HANDICAP":
            return (FROZEN_W_AH, 1.0 - FROZEN_W_AH)
        return (FROZEN_W_TOTALS, 1.0 - FROZEN_W_TOTALS)


def five_state_cashflow(
    distribution: Mapping[str, float], decimal_odds: float, *, rebate: float = 0.0
) -> float:
    """Return expected unit cashflow using the canonical five-state settlement map."""
    if not isfinite(decimal_odds) or decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be finite and greater than 1")
    if not isfinite(rebate):
        raise ValueError("rebate must be finite")
    if set(distribution) != set(OUTCOME_ORDER):
        raise ValueError("complete five-state distribution is required")
    if any(
        not isfinite(float(distribution[key])) or float(distribution[key]) < 0
        for key in OUTCOME_ORDER
    ):
        raise ValueError("distribution probabilities must be finite and non-negative")
    if abs(sum(float(distribution[key]) for key in OUTCOME_ORDER) - 1.0) > 1e-9:
        raise ValueError("distribution probabilities must sum to one")
    return (
        (decimal_odds - 1.0)
        * (float(distribution["WIN"]) + 0.5 * float(distribution["HALF_WIN"]))
        - float(distribution["LOSS"])
        - 0.5 * float(distribution["HALF_LOSS"])
        + rebate
    )


def fuse_lambda_level(
    *,
    market: str,
    selection: str,
    line: float,
    model_lambda_home: float,
    model_lambda_away: float,
    market_odds: Mapping[str, float],
    rho: float = 0.0,
    max_goals: int = 12,
) -> FusionResult:
    """Fuse a model lambda pair with a two-sided market quote.

    ``market_odds`` must contain both sides for the same line.  Proportional de-vig is
    used, and the returned distribution is always the complete five-state settlement
    distribution for the requested selection and line.
    """
    market_key = market.strip().upper()
    selection_key = selection.strip().upper()
    _validate_inputs(
        market_key,
        selection_key,
        line,
        model_lambda_home,
        model_lambda_away,
        rho,
        max_goals,
    )
    probabilities = _proportional_devig(market_odds, market_key, selection_key)
    model_total = model_lambda_home + model_lambda_away
    model_delta = model_lambda_home - model_lambda_away

    if market_key == "TOTALS":
        market_total = _solve_total_lambda(
            line=line,
            target_under=probabilities["UNDER"],
            delta=model_delta,
            rho=rho,
            max_goals=max_goals,
        )
        fused_total = _geometric_mix(model_total, market_total, FROZEN_W_TOTALS)
        fused_delta = model_delta
    elif market_key == "ASIAN_HANDICAP":
        market_delta = _solve_handicap_delta(
            line=line,
            selection=selection_key,
            target=probabilities[selection_key],
            total=model_total,
            rho=rho,
            max_goals=max_goals,
        )
        fused_total = model_total
        fused_delta = FROZEN_W_AH * model_delta + (1.0 - FROZEN_W_AH) * market_delta
        market_total = model_total
    else:
        raise ValueError(f"unsupported market: {market!r}")

    lambda_home, lambda_away = _split_total_delta(fused_total, fused_delta)
    matrix = _score_matrix(lambda_home, lambda_away, rho=rho, max_goals=max_goals)
    distribution = _distribution(matrix, market_key, selection_key, line)
    return FusionResult(
        market=market_key,
        selection=selection_key,
        line=float(line),
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        lambda_total_model=model_total,
        lambda_total_market=market_total,
        delta_model=model_delta,
        delta_market=(model_delta if market_key == "TOTALS" else market_delta),
        distribution=distribution,
    )


def _validate_inputs(
    market: str,
    selection: str,
    line: float,
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int,
) -> None:
    if market == "TOTALS" and selection not in {"OVER", "UNDER"}:
        raise ValueError("TOTALS selection must be OVER or UNDER")
    if market == "ASIAN_HANDICAP" and selection not in {"HOME", "AWAY"}:
        raise ValueError("ASIAN_HANDICAP selection must be HOME or AWAY")
    if not isfinite(line) or round(line * 4) != line * 4:
        raise ValueError("line must be a finite quarter-line increment")
    if min(lambda_home, lambda_away) < _MIN_LAMBDA:
        raise ValueError("model lambdas must be at least 0.05")
    if not isfinite(rho) or max_goals < 6:
        raise ValueError("invalid rho or max_goals")


def _proportional_devig(
    odds: Mapping[str, float], market: str, selection: str
) -> dict[str, float]:
    required = ("OVER", "UNDER") if market == "TOTALS" else ("HOME", "AWAY")
    try:
        prices = {side: float(odds[side]) for side in required}
    except KeyError as exc:
        raise ValueError("both market sides are required") from exc
    if any(not isfinite(price) or price <= 1.0 for price in prices.values()):
        raise ValueError("decimal odds must be finite and greater than 1")
    implied = {side: 1.0 / price for side, price in prices.items()}
    total = sum(implied.values())
    probabilities = {side: value / total for side, value in implied.items()}
    if abs(sum(probabilities.values()) - 1.0) > 1e-12:
        raise AssertionError("proportional devig did not normalize")
    return probabilities


def _geometric_mix(model: float, market: float, weight: float) -> float:
    if model <= 0 or market <= 0:
        raise ValueError("lambda values must be positive")
    return exp(weight * log(model) + (1.0 - weight) * log(market))


def _split_total_delta(total: float, delta: float) -> tuple[float, float]:
    limit = total - 2.0 * _MIN_LAMBDA
    bounded_delta = min(max(delta, -limit), limit)
    return (total + bounded_delta) / 2.0, (total - bounded_delta) / 2.0


def _score_matrix(
    lambda_home: float,
    lambda_away: float,
    *,
    rho: float,
    max_goals: int,
) -> dict[tuple[int, int], float]:
    matrix = {
        (home, away): max(
            poisson_pmf(lambda_home, home)
            * poisson_pmf(lambda_away, away)
            * tau_correction(home, away, lambda_home, lambda_away, rho),
            0.0,
        )
        for home in range(max_goals + 1)
        for away in range(max_goals + 1)
    }
    total = sum(matrix.values())
    if total <= 0:
        raise ValueError("score matrix has no positive probability")
    return {score: probability / total for score, probability in matrix.items()}


def _distribution(
    matrix: Mapping[tuple[int, int], float],
    market: str,
    selection: str,
    line: float,
) -> dict[str, float]:
    line_value = _decimal_line(line)
    result = {key: 0.0 for key in OUTCOME_ORDER}
    for (home, away), probability in matrix.items():
        if market == "TOTALS":
            outcome = settle_total_goals(home + away, selection, line_value)
        else:
            outcome = settle_asian_handicap(home, away, selection, line_value)
        result[outcome.value] += probability
    total = sum(result.values())
    if total <= 0:
        raise ValueError("empty settlement distribution")
    normalized = {key: value / total for key, value in result.items()}
    if abs(sum(normalized.values()) - 1.0) > 1e-9:
        raise AssertionError("five-state distribution does not sum to one")
    return normalized


def _decimal_line(line: float):
    from decimal import Decimal

    return Decimal(str(line))


def _effective_probability(
    matrix: Mapping[tuple[int, int], float],
    market: str,
    selection: str,
    line: float,
) -> float:
    distribution = _distribution(matrix, market, selection, line)
    return distribution["WIN"] + 0.5 * distribution["HALF_WIN"]


def _solve_total_lambda(
    *, line: float, target_under: float, delta: float, rho: float, max_goals: int
) -> float:
    # The market total is inferred from the UNDER effective probability.  The same
    # score matrix and quarter-line settlement semantics are used for inversion.
    lo, hi = _MIN_LAMBDA * 2.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        home, away = _split_total_delta(mid, delta)
        value = _effective_probability(
            _score_matrix(home, away, rho=rho, max_goals=max_goals),
            "TOTALS",
            "UNDER",
            line,
        )
        if value > target_under:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _solve_handicap_delta(
    *,
    line: float,
    selection: str,
    target: float,
    total: float,
    rho: float,
    max_goals: int,
) -> float:
    limit = max(total - 2.0 * _MIN_LAMBDA, 0.0)
    lo, hi = -limit, limit
    for _ in range(80):
        mid = (lo + hi) / 2.0
        home, away = _split_total_delta(total, mid)
        value = _effective_probability(
            _score_matrix(home, away, rho=rho, max_goals=max_goals),
            "ASIAN_HANDICAP",
            selection,
            line,
        )
        if selection == "HOME":
            if value < target:
                lo = mid
            else:
                hi = mid
        else:
            if value > target:
                lo = mid
            else:
                hi = mid
    return (lo + hi) / 2.0
