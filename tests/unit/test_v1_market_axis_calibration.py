from __future__ import annotations

import pytest
from scripts.fit_v1_market_axis_calibration import (
    _effective_score,
    _lambdas,
    _least_squares,
)


def test_current_axis_formula_and_quarter_scores_are_exact() -> None:
    row = {
        "home_for": 1.8,
        "home_against": 1.0,
        "away_for": 1.2,
        "away_against": 1.4,
    }

    home, away, clamped = _lambdas(row)
    assert (home, away) == pytest.approx((1.75, 0.95))
    assert clamped is False
    assert _effective_score(0, 0.25) == 0.75
    assert _effective_score(0, -0.25) == 0.25


def test_least_squares_recovers_known_linear_coefficients() -> None:
    features = [[1.0, value] for value in (0.0, 1.0, 2.0, 3.0)]
    outcomes = [2.0 + 0.5 * value for value in (0.0, 1.0, 2.0, 3.0)]

    assert _least_squares(features, outcomes) == (2.0, 0.5)
