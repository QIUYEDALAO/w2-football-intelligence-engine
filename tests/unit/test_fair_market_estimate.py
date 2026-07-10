from __future__ import annotations

from w2.models.fair_market_estimate import fair_lines_from_lambdas
from w2.models.r4_1_features import r4_1_prediction_from_lambdas


def test_fair_lines_use_one_score_distribution_for_ah_and_totals() -> None:
    fair_ah, fair_ou, ah_probabilities, ou_probabilities = fair_lines_from_lambdas(
        home_mu=1.8,
        away_mu=0.9,
        rho=-0.05,
    )

    assert fair_ah < 0
    assert fair_ou in {quarter / 4 for quarter in range(2, 33)}
    assert set(ah_probabilities) == {"HOME", "AWAY"}
    assert set(ou_probabilities) == {"OVER", "UNDER"}


def test_r4_1_prediction_exposes_same_lambda_ah_and_ou_estimates() -> None:
    prediction = r4_1_prediction_from_lambdas(home_mu=1.6, away_mu=1.1, rho=0.0)

    assert prediction.fair_ah < 0
    assert prediction.fair_ou >= 0.5
    assert prediction.home_mu == 1.6
    assert prediction.away_mu == 1.1
