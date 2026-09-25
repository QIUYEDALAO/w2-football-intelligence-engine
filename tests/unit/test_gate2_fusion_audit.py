"""Gate 2 characterization checks with arithmetic independent of W2 pricing code."""

from __future__ import annotations

from math import exp, factorial, isclose

import pytest

from w2.quant_research.track_b_lambda_level_fusion import (
    _distribution,
    expected_rebate_units,
    five_state_cashflow,
    fuse_lambda_level,
)
from w2.quant_research.track_cd_offline_presentation import single_probability_cashflow


def _pmf(mean: float, goals: int) -> float:
    return exp(-mean) * mean**goals / factorial(goals)


@pytest.mark.parametrize(
    ("line", "selection", "goals", "state"),
    [
        (2.25, "UNDER", 2, "HALF_WIN"),
        (2.25, "OVER", 2, "HALF_LOSS"),
        (2.75, "UNDER", 3, "HALF_LOSS"),
        (2.75, "OVER", 3, "HALF_WIN"),
        (-0.25, "HOME", 0, "HALF_LOSS"),
        (-0.75, "HOME", 1, "HALF_WIN"),
    ],
)
def test_quarter_line_exact_boundary_state(
    line: float, selection: str, goals: int, state: str
) -> None:
    market = "TOTALS" if selection in {"OVER", "UNDER"} else "ASIAN_HANDICAP"
    matrix = {(goals, 0): 1.0}
    assert _distribution(matrix, market, selection, line)[state] == 1.0


@pytest.mark.parametrize("line", [2.0, 2.25, 2.5, 2.75])
def test_market_under_inverse_matches_independent_poisson_formula(line: float) -> None:
    result = fuse_lambda_level(
        market="TOTALS", selection="UNDER", line=line,
        model_lambda_home=1.4, model_lambda_away=1.1,
        market_odds={"OVER": 2.0, "UNDER": 2.0},
    )
    mean = result.lambda_total_market
    below_two = _pmf(mean, 0) + _pmf(mean, 1)
    at_two = _pmf(mean, 2)
    expected = {
        2.0: below_two,
        2.25: below_two + 0.5 * at_two,
        2.5: below_two + at_two,
        2.75: below_two + at_two,
    }[line]
    # The audited matrix truncates at 12 goals and renormalizes the tail.
    assert isclose(result.effective_probability, expected, abs_tol=1e-8)
    assert isclose(result.effective_probability, 0.5, abs_tol=1e-9)


def test_push_and_quarter_lines_do_not_match_both_devig_sides() -> None:
    # The inverse fits UNDER only.  At integer/quarter lines some mass is push
    # or half settled, so both effective probabilities cannot sum to one.
    for line in (2.0, 2.25, 2.75):
        under = fuse_lambda_level(
            market="TOTALS", selection="UNDER", line=line,
            model_lambda_home=1.4, model_lambda_away=1.1,
            market_odds={"OVER": 2.0, "UNDER": 2.0},
        )
        over = fuse_lambda_level(
            market="TOTALS", selection="OVER", line=line,
            model_lambda_home=1.4, model_lambda_away=1.1,
            market_odds={"OVER": 2.0, "UNDER": 2.0},
        )
        assert isclose(under.effective_probability, 0.5, abs_tol=1e-9)
        assert over.effective_probability < 0.5


def test_zero_probability_states_and_independent_five_state_cashflow() -> None:
    distribution = {
        "WIN": 0.0, "HALF_WIN": 0.25, "PUSH": 0.25,
        "HALF_LOSS": 0.25, "LOSS": 0.25,
    }
    # At odds 3: half-win +1, half-loss -0.5, loss -1;
    # expected pure = -0.125, expected absolute profit = 0.625.
    assert isclose(expected_rebate_units(distribution, 3.0), 0.015625, abs_tol=1e-12)
    assert isclose(five_state_cashflow(distribution, 3.0), -0.109375, abs_tol=1e-12)
    for p in (0.0, 1.0):
        pure = p * 3.0 - 1.0
        rebate = 0.025 * (2.0 * p + 1.0 - p)
        assert isclose(single_probability_cashflow(p, 3.0), pure + rebate, abs_tol=1e-12)


@pytest.mark.parametrize("bad", [0.0, 1.0, float("nan"), float("inf")])
def test_invalid_or_nonfinite_odds_fail_closed(bad: float) -> None:
    with pytest.raises(ValueError):
        fuse_lambda_level(
            market="TOTALS", selection="UNDER", line=2.5,
            model_lambda_home=1.4, model_lambda_away=1.1,
            market_odds={"OVER": bad, "UNDER": 2.0},
        )


def test_extreme_valid_odds_expose_fixed_inverse_bracket() -> None:
    odds = {"OVER": 1.01, "UNDER": 1000.0}
    target_under = (1 / odds["UNDER"]) / (1 / odds["OVER"] + 1 / odds["UNDER"])
    result = fuse_lambda_level(
        market="TOTALS", selection="UNDER", line=2.5,
        model_lambda_home=1.4, model_lambda_away=1.1, market_odds=odds,
    )
    assert isclose(result.lambda_total_market, 10.0, abs_tol=1e-12)
    assert abs(result.effective_probability - target_under) > 0.001
