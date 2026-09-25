"""Offline Track B lambda-level market fusion.

This module is deliberately side-effect free.  It is not wired into the operational
recommendation or settlement paths.  Track B weights are frozen by preregistration and
are constants here; callers cannot tune them at runtime.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import exp, factorial, floor, isfinite, log

from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.domain.profit import REBATE_FORMULA_VERSION, REBATE_RATE
from w2.models.dixon_coles import poisson_pmf, tau_correction

OUTCOME_ORDER = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
FROZEN_W_AH = 0.9
FROZEN_W_TOTALS = 0.0
_MIN_LAMBDA = 0.05
MARKET_TOTAL_INFER_V1_VERSION = "w2.market_total_infer.v1"
MARKET_TOTAL_INFER_LOWER = 0.5
MARKET_TOTAL_INFER_UPPER = 6.0
MARKET_TOTAL_INFER_TOLERANCE = 1e-6
# 宁偏松防误杀，只拦 capture_id 复用/时间戳漂移类硬异常。
AH_QUOTE_CAPTURE_MAX_SKEW_SECONDS = 1800


class AhQuoteSideMissing(ValueError):
    """One side (HOME or AWAY) of an AH quote pair is absent.

    Deliberately distinct from ``QUOTE_PAIR_MISMATCH``: a missing side is a market
    availability signal, whereas a mismatch is a data integrity failure.
    """


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
    marker: str | None = None

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


def expected_rebate_units(
    distribution: Mapping[str, float], decimal_odds: float
) -> Decimal:
    """Return expected ABS_PROFIT_V2 rebate for a five-state distribution.

    The rebate is earned on the absolute realized unit profit of each state:
    wins rebate net profit, losses rebate the staked unit, and PUSH earns zero.
    """
    _validate_distribution(distribution, decimal_odds)
    odds = Decimal(str(decimal_odds))
    half = Decimal("0.5")
    winning_exposure = Decimal(str(distribution["WIN"])) + half * Decimal(
        str(distribution["HALF_WIN"])
    )
    losing_exposure = Decimal(str(distribution["LOSS"])) + half * Decimal(
        str(distribution["HALF_LOSS"])
    )
    return REBATE_RATE * (
        (odds - Decimal("1")) * winning_exposure + losing_exposure
    )


def five_state_cashflow(
    distribution: Mapping[str, float], decimal_odds: float
) -> Decimal:
    """Return expected cashflow using the canonical five-state settlement map.

    ``REBATE_FORMULA_VERSION`` is deliberately fixed to ``ABS_PROFIT_V2``;
    callers cannot inject a second rebate convention at runtime.
    """
    if REBATE_FORMULA_VERSION != "ABS_PROFIT_V2":
        raise RuntimeError("unsupported rebate formula version")
    _validate_distribution(distribution, decimal_odds)
    odds = Decimal(str(decimal_odds))
    half = Decimal("0.5")
    pure_cashflow = (
        (odds - Decimal("1"))
        * (Decimal(str(distribution["WIN"])) + half * Decimal(str(distribution["HALF_WIN"])))
        - Decimal(str(distribution["LOSS"]))
        - half * Decimal(str(distribution["HALF_LOSS"]))
    )
    return pure_cashflow + expected_rebate_units(
        distribution, decimal_odds
    )


def _validate_distribution(
    distribution: Mapping[str, float], decimal_odds: float
) -> None:
    if not isfinite(decimal_odds) or decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be finite and greater than 1")
    if set(distribution) != set(OUTCOME_ORDER):
        raise ValueError("complete five-state distribution is required")
    if any(
        not isfinite(float(distribution[key])) or float(distribution[key]) < 0
        for key in OUTCOME_ORDER
    ):
        raise ValueError("distribution probabilities must be finite and non-negative")
    if abs(sum(float(distribution[key]) for key in OUTCOME_ORDER) - 1.0) > 1e-9:
        raise ValueError("distribution probabilities must sum to one")


def fuse_lambda_level(
    *,
    market: str,
    selection: str,
    line: float,
    model_lambda_home: float,
    model_lambda_away: float,
    market_odds: Mapping[str, object],
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
    probabilities = _proportional_devig(market_odds, market_key, selection_key, line)
    model_total = model_lambda_home + model_lambda_away
    model_delta = model_lambda_home - model_lambda_away

    if market_key == "TOTALS":
        market_total = _solve_market_total_lambda_v1(
            line=line,
            target_under=probabilities["UNDER"],
        )
        marker = None
        if market_total is None:
            market_total = model_total
            fused_total = model_total
            marker = "MARKET_TOTAL_INFER_NO_SOLUTION"
        else:
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
        marker = None
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
        marker=marker,
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
    odds: Mapping[str, object], market: str, selection: str, line: float
) -> dict[str, float]:
    required = ("OVER", "UNDER") if market == "TOTALS" else ("HOME", "AWAY")
    if market == "ASIAN_HANDICAP":
        prices = _validate_ah_quote_pair(odds, selection=selection, line=line)
    else:
        try:
            prices = {side: float(odds[side]) for side in required}
        except (KeyError, TypeError, ValueError) as exc:
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


def _validate_ah_quote_pair(
    odds: Mapping[str, object],
    *,
    selection: str,
    line: float,
) -> dict[str, float]:
    """Validate a paired AH quote before any probability is computed.

    The quote identity is a pair identity, not a side observation id.  Both sides
    must therefore carry the same bookmaker, capture and pair identity while their
    canonical lines are opposites.
    """
    if not isinstance(odds, Mapping):
        raise ValueError("QUOTE_PAIR_MISMATCH: malformed AH quote pair")
    if "HOME" not in odds or "AWAY" not in odds:
        raise AhQuoteSideMissing("AH quote pair is missing HOME or AWAY side")
    try:
        home = odds["HOME"]
        away = odds["AWAY"]
        if not isinstance(home, Mapping) or not isinstance(away, Mapping):
            raise TypeError("AH quote sides must be mappings")
        home_line = float(home["line"])
        away_line = float(away["line"])
        home_price = float(home["price"])
        away_price = float(away["price"])
        home_identity = home["quote_identity"]
        away_identity = away["quote_identity"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("QUOTE_PAIR_MISMATCH: malformed AH quote pair") from exc
    expected_home_line = line if selection == "HOME" else -line
    if (
        not isfinite(home_line)
        or not isfinite(away_line)
        or abs(home_line + away_line) > 0.01
        or abs(home_line - expected_home_line) > 0.01
        or not isfinite(home_price)
        or not isfinite(away_price)
        or home_price <= 1.0
        or away_price <= 1.0
        or not isinstance(home_identity, Mapping)
        or not isinstance(away_identity, Mapping)
    ):
        raise ValueError("QUOTE_PAIR_MISMATCH: line or quote identity invalid")
    identity_fields = ("provider_fixture_id", "bookmaker_id", "capture_id")
    if any(
        not home_identity.get(field)
        or not away_identity.get(field)
        or home_identity.get(field) != away_identity.get(field)
        for field in identity_fields
    ):
        raise ValueError("QUOTE_PAIR_MISMATCH: quote identity differs")
    try:
        captured_at = {}
        for side, identity in (("HOME", home_identity), ("AWAY", away_identity)):
            value = identity["captured_at"]
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("captured_at must be timezone-aware")
            captured_at[side] = parsed.astimezone(UTC)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("QUOTE_PAIR_MISMATCH: captured_at missing or invalid") from exc
    if (
        abs((captured_at["HOME"] - captured_at["AWAY"]).total_seconds())
        > AH_QUOTE_CAPTURE_MAX_SKEW_SECONDS
    ):
        raise ValueError("QUOTE_PAIR_MISMATCH: captured_at skew exceeds threshold")
    for side, quote, identity, side_line in (
        ("HOME", home, home_identity, home_line),
        ("AWAY", away, away_identity, away_line),
    ):
        try:
            identity_line = float(identity["line"])
            identity_price = float(identity["price"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("QUOTE_PAIR_MISMATCH: side identity incomplete") from exc
        if (
            identity.get("selection") != side
            or identity.get("market") != "ASIAN_HANDICAP"
            or not identity.get("observation_id")
            or abs(identity_line - side_line) > 0.01
            or identity_price != float(quote["price"])
        ):
            raise ValueError("QUOTE_PAIR_MISMATCH: side identity inconsistent")
    return {"HOME": home_price, "AWAY": away_price}


def _solve_market_total_lambda_v1(
    *, line: float, target_under: float
) -> float | None:
    """Infer market total under the separately versioned MARKET_TOTAL_INFER_V1.

    This is the market quote inversion used by Track B; it is intentionally named
    separately from TOTAL_INFER_V1, which is the frozen model-total audit formula.
    If a target is outside the finite bracket, return no solution so the caller
    can label the model-total fallback explicitly.
    """
    lo, hi = MARKET_TOTAL_INFER_LOWER, MARKET_TOTAL_INFER_UPPER
    lo_value = _market_under_probability(lo, line)
    hi_value = _market_under_probability(hi, line)
    if not hi_value <= target_under <= lo_value:
        return None
    while hi - lo > MARKET_TOTAL_INFER_TOLERANCE:
        mid = (lo + hi) / 2.0
        value = _market_under_probability(mid, line)
        if value > target_under:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _market_under_probability(total: float, line: float) -> float:
    """Poisson market inverse using the TOTAL_INFER_V2 draft settlement map.

    This is still the separately registered market-quote inverse, not the
    historical TOTAL_INFER_V1 model-total grid fit.  Only integer pushes are
    conditioned away; fractional lines use effective wins.
    """
    distribution = _poisson_total_five_state(total, "UNDER", line)
    if line == floor(line):
        non_push = distribution["WIN"] + distribution["LOSS"]
        if non_push <= 0:
            raise ValueError("market total has no executable probability")
        return distribution["WIN"] / non_push
    return distribution["WIN"] + 0.5 * distribution["HALF_WIN"]


def _poisson_total_five_state(
    total: float, selection: str, line: float
) -> dict[str, float]:
    """Analytic Poisson five states from W2_TOTAL_INFER_V2 (DRAFT), section 1.

    In particular, UNDER x.25 at its integer boundary is HALF_WIN; OVER x.25
    at that boundary is HALF_LOSS.  The frozen V1 text is retained as history.
    """
    n = floor(line)

    def cdf(k: int) -> float:
        return sum(exp(-total) * total**goals / factorial(goals) for goals in range(k + 1))

    p_below = cdf(n - 1)
    p_at = exp(-total) * total**n / factorial(n) if n >= 0 else 0.0
    fraction = round((line - n) * 4)
    if fraction == 0:
        under = (p_below, 0.0, p_at, 0.0, 1.0 - cdf(n))
        over = (1.0 - cdf(n), 0.0, p_at, 0.0, p_below)
    elif fraction == 1:
        under = (p_below, p_at, 0.0, 0.0, 1.0 - cdf(n))
        over = (1.0 - cdf(n), 0.0, 0.0, p_at, p_below)
    elif fraction == 2:
        under = (cdf(n), 0.0, 0.0, 0.0, 1.0 - cdf(n))
        over = (1.0 - cdf(n), 0.0, 0.0, 0.0, cdf(n))
    elif fraction == 3:
        p_next = exp(-total) * total ** (n + 1) / factorial(n + 1) if n + 1 >= 0 else 0.0
        under = (cdf(n), 0.0, 0.0, p_next, 1.0 - cdf(n + 1))
        over = (1.0 - cdf(n + 1), p_next, 0.0, 0.0, cdf(n))
    else:
        raise ValueError("line must be a quarter-line increment")
    if selection not in {"UNDER", "OVER"}:
        raise ValueError("TOTALS selection must be OVER or UNDER")
    return dict(zip(OUTCOME_ORDER, under if selection == "UNDER" else over, strict=True))


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
