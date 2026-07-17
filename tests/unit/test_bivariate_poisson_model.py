from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.models.bivariate_poisson import (
    BivariatePoissonMatch,
    bivariate_score_probability,
    fit_bivariate_poisson,
    one_x_two_probabilities,
    predict_score_matrix,
)


def _match(index: int, home_goals: int, away_goals: int) -> BivariatePoissonMatch:
    return BivariatePoissonMatch(
        fixture_id=f"bp-{index}",
        kickoff_utc=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        home_team="alpha" if index % 2 == 0 else "bravo",
        away_team="bravo" if index % 2 == 0 else "alpha",
        home_goals=home_goals,
        away_goals=away_goals,
        market_probabilities={"HOME": 0.45, "DRAW": 0.27, "AWAY": 0.28},
        competition="fixture",
        season="2024",
        neutral_site=False,
    )


def test_bivariate_probability_boosts_shared_low_draw_mass() -> None:
    independent_draw = bivariate_score_probability(1, 1, 1.4, 1.2, 0.0)
    shared_draw = bivariate_score_probability(1, 1, 1.4, 1.2, 0.25)

    assert shared_draw > independent_draw


def test_bivariate_poisson_fit_and_projection_are_normalized() -> None:
    matches = [
        _match(0, 2, 1),
        _match(1, 1, 1),
        _match(2, 0, 1),
        _match(3, 2, 2),
        _match(4, 3, 1),
        _match(5, 1, 0),
    ]

    parameters = fit_bivariate_poisson(matches, shared_lambda_grid=(0.0, 0.1, 0.2))
    matrix = predict_score_matrix(parameters, "alpha", "bravo", max_goals=6)
    probabilities = one_x_two_probabilities(parameters, "alpha", "bravo", max_goals=6)

    assert parameters.fitted_match_count == len(matches)
    assert 0.0 <= parameters.shared_lambda <= 0.2
    assert abs(sum(matrix.values()) - 1.0) < 1e-9
    assert abs(sum(probabilities.values()) - 1.0) < 1e-9
    assert set(probabilities) == {"HOME", "DRAW", "AWAY"}
