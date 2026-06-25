from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.models.dixon_coles import (
    DixonColesMatch,
    fit_dixon_coles,
    one_x_two_from_matrix,
    predict_score_matrix,
    tau_correction,
)


def dc_match(index: int, home_goals: int, away_goals: int) -> DixonColesMatch:
    return DixonColesMatch(
        fixture_id=f"m-{index}",
        kickoff_utc=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        home_team="Alpha" if index % 2 else "Beta",
        away_team="Gamma" if index % 2 else "Delta",
        home_goals=home_goals,
        away_goals=away_goals,
        market_probabilities={"HOME": 0.4, "DRAW": 0.3, "AWAY": 0.3},
    )


def test_tau_correction_adjusts_only_low_scores() -> None:
    assert tau_correction(0, 0, 1.3, 0.9, -0.1) > 1.0
    assert tau_correction(1, 1, 1.3, 0.9, -0.1) > 1.0
    assert tau_correction(2, 1, 1.3, 0.9, -0.1) == 1.0


def test_fit_dixon_coles_outputs_normalized_prediction_matrix() -> None:
    matches = [
        dc_match(1, 2, 0),
        dc_match(2, 1, 1),
        dc_match(3, 0, 1),
        dc_match(4, 3, 1),
        dc_match(5, 1, 0),
    ]

    params = fit_dixon_coles(matches)
    matrix = predict_score_matrix(params, "Alpha", "Gamma", max_goals=6)
    one_x_two = one_x_two_from_matrix(matrix)

    assert params.fitted_match_count == len(matches)
    assert -0.2 <= params.rho <= 0.2
    assert sum(matrix.values()) == pytest.approx(1.0)
    assert sum(one_x_two.values()) == pytest.approx(1.0)
