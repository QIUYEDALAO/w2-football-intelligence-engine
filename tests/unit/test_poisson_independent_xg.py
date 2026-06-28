from __future__ import annotations

import pytest

from w2.markets import poisson
from w2.markets.poisson import independent_xg_poisson


def test_independent_xg_poisson_changes_fair_ou_with_xg_not_market() -> None:
    low = independent_xg_poisson(
        home_xg_for=0.7,
        home_xg_against=0.8,
        away_xg_for=0.6,
        away_xg_against=0.9,
    )
    high = independent_xg_poisson(
        home_xg_for=2.2,
        home_xg_against=1.4,
        away_xg_for=1.9,
        away_xg_against=1.8,
    )

    assert low.fair_ou != high.fair_ou
    assert low.fair_ou != 2.5
    assert high.fair_ou != 2.5


def test_market_ou_is_not_an_input_to_lambda_or_scoreline(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("market OU reverse fit must not be used")

    monkeypatch.setattr(poisson, "fit_total_goals_mu", fail_if_called)

    first = independent_xg_poisson(
        home_xg_for=1.8,
        home_xg_against=0.7,
        away_xg_for=0.9,
        away_xg_against=1.5,
    )
    second = independent_xg_poisson(
        home_xg_for=1.8,
        home_xg_against=0.7,
        away_xg_for=0.9,
        away_xg_against=1.5,
    )

    assert first.lambda_home == second.lambda_home
    assert first.lambda_away == second.lambda_away
    assert first.fair_ou == second.fair_ou
    assert first.top_scorelines == second.top_scorelines


def test_strong_home_xg_tilts_top_scores_to_home_not_away() -> None:
    output = independent_xg_poisson(
        home_xg_for=2.4,
        home_xg_against=0.5,
        away_xg_for=0.6,
        away_xg_against=1.9,
    )

    assert output.lambda_home > output.lambda_away
    assert output.top_scorelines
    top = output.top_scorelines[0]
    assert int(top["home_goals"]) >= int(top["away_goals"])
    assert all(0 <= float(row["probability"]) <= 1 for row in output.top_scorelines)
    assert abs(sum(output.score_matrix.values()) - 1.0) < 1e-9


def test_different_xg_profiles_produce_different_top_scores() -> None:
    home_profile = independent_xg_poisson(
        home_xg_for=2.3,
        home_xg_against=0.6,
        away_xg_for=0.7,
        away_xg_against=1.8,
    )
    balanced_profile = independent_xg_poisson(
        home_xg_for=1.0,
        home_xg_against=1.0,
        away_xg_for=1.0,
        away_xg_against=1.0,
    )

    assert home_profile.top_scorelines != balanced_profile.top_scorelines
