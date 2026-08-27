from __future__ import annotations

from scripts.run_factor_v2_gate1_calibration_recovery import (
    _bounded_temperature,
    _temperature_matrix,
)

from w2.strategy.simulate import exact_score_matrix_from_lambdas


def test_temperature_keeps_exact_score_matrix_valid() -> None:
    matrix = exact_score_matrix_from_lambdas(
        lambda_home=1.4,
        lambda_away=0.9,
        rho=0.0,
        max_goals=12,
    )

    calibrated = _temperature_matrix(matrix, 0.85)

    assert len(calibrated) == 169
    assert all(value >= 0 for value in calibrated.values())
    assert abs(sum(calibrated.values()) - 1) <= 1e-9


def test_temperature_selection_is_bounded_and_deterministic() -> None:
    predictions = [
        (
            exact_score_matrix_from_lambdas(
                lambda_home=home,
                lambda_away=away,
                rho=0.0,
                max_goals=12,
            ),
            actual,
        )
        for home, away, actual in (
            (1.8, 0.7, "HOME"),
            (1.1, 1.1, "DRAW"),
            (0.8, 1.6, "AWAY"),
        )
    ]

    first = _bounded_temperature(predictions)
    second = _bounded_temperature(predictions)

    assert first == second
    assert 0.5 <= first[0] <= 2.0
