from __future__ import annotations

from w2.strategy.simulate import (
    INSUFFICIENT_INPUTS,
    READY,
    SimulationInputs,
    ah_expected_value,
    ah_settlement_distribution_from_lambdas,
    run_simulation,
)


def inputs(**overrides: object) -> SimulationInputs:
    payload = {
        "fixture_id": "fixture-sim",
        "home_team_id": "home",
        "away_team_id": "away",
        "home_xg_for": 1.2,
        "home_xg_against": 1.1,
        "away_xg_for": 1.15,
        "away_xg_against": 1.15,
        "home_elo": 1500.0,
        "away_elo": 1500.0,
        "home_squad_value_eur": 250_000_000.0,
        "away_squad_value_eur": 240_000_000.0,
    }
    payload.update(overrides)
    return SimulationInputs(**payload)  # type: ignore[arg-type]


def test_strong_home_produces_meaningful_home_fair_ah() -> None:
    output = run_simulation(
        inputs(
            fixture_id="strong-home",
            home_xg_for=2.2,
            home_xg_against=0.6,
            away_xg_for=0.7,
            away_xg_against=1.8,
            home_elo=1750.0,
            away_elo=1350.0,
            home_squad_value_eur=900_000_000.0,
            away_squad_value_eur=80_000_000.0,
        )
    )

    assert output.status == READY
    assert output.lambda_home is not None and output.lambda_away is not None
    assert output.lambda_home > output.lambda_away
    assert output.fair_ah is not None and output.fair_ah <= -1.0


def test_strong_away_produces_meaningful_away_fair_ah() -> None:
    output = run_simulation(
        inputs(
            fixture_id="strong-away",
            home_xg_for=0.7,
            home_xg_against=1.8,
            away_xg_for=2.2,
            away_xg_against=0.6,
            home_elo=1350.0,
            away_elo=1750.0,
            home_squad_value_eur=80_000_000.0,
            away_squad_value_eur=900_000_000.0,
        )
    )

    assert output.status == READY
    assert output.lambda_away is not None and output.lambda_home is not None
    assert output.lambda_away > output.lambda_home
    assert output.fair_ah is not None and output.fair_ah >= 1.0


def test_balanced_inputs_stay_near_pickem_and_deterministic() -> None:
    first = run_simulation(inputs(fixture_id="balanced"))
    second = run_simulation(inputs(fixture_id="balanced"))

    assert first.fair_ah is not None and abs(first.fair_ah) <= 0.25
    assert first.as_dict() == second.as_dict()
    assert first.model_version == "w2.formal.exact_dc_poisson.v1"
    assert first.calibration["seed_policy"] == "unused_exact_solution"


def test_exact_solution_does_not_depend_on_fixture_seed() -> None:
    first = run_simulation(inputs(fixture_id="exact-a"))
    second = run_simulation(inputs(fixture_id="exact-b"))

    assert first.seed != second.seed
    assert first.lambda_home == second.lambda_home
    assert first.lambda_away == second.lambda_away
    assert first.fair_ah == second.fair_ah
    assert first.fair_ou == second.fair_ou
    assert first.scoreline_picks == second.scoreline_picks


def test_lambda_uncertainty_defaults_to_exact_solution_and_thickens_tails() -> None:
    exact = run_simulation(inputs(fixture_id="sigma-zero"))
    explicit_zero = run_simulation(
        inputs(fixture_id="sigma-zero-other-seed", lambda_sigma_home=0.0, lambda_sigma_away=0.0)
    )
    uncertain = run_simulation(
        inputs(fixture_id="sigma-positive", lambda_sigma_home=0.45, lambda_sigma_away=0.45)
    )

    assert exact.scoreline_picks == explicit_zero.scoreline_picks
    assert exact.calibration["lambda_uncertainty_method"] == "none"
    assert uncertain.calibration["lambda_uncertainty_method"] == "deterministic_three_point"
    exact_tail = sum(
        row["over"]
        for row in exact.ou_probabilities["ladder"]
        if row["line"] == 4.0
    )
    uncertain_tail = sum(
        row["over"]
        for row in uncertain.ou_probabilities["ladder"]
        if row["line"] == 4.0
    )
    assert uncertain_tail > exact_tail


def test_neutral_site_does_not_apply_home_advantage_to_lambdas() -> None:
    neutral = run_simulation(
        inputs(
            fixture_id="neutral-balanced",
            home_xg_for=1.2,
            home_xg_against=1.1,
            away_xg_for=1.2,
            away_xg_against=1.1,
            home_elo=None,
            away_elo=None,
            home_squad_value_eur=None,
            away_squad_value_eur=None,
            neutral_site=True,
        )
    )
    nominal_home = run_simulation(
        inputs(
            fixture_id="nominal-home-balanced",
            home_xg_for=1.2,
            home_xg_against=1.1,
            away_xg_for=1.2,
            away_xg_against=1.1,
            home_elo=None,
            away_elo=None,
            home_squad_value_eur=None,
            away_squad_value_eur=None,
            neutral_site=False,
        )
    )

    assert neutral.lambda_home == neutral.lambda_away
    assert neutral.calibration["params"]["applied_home_advantage_goals"] == 0.0
    assert neutral.input_readiness["home_advantage_applied"] is False
    assert nominal_home.lambda_home is not None and nominal_home.lambda_away is not None
    assert nominal_home.lambda_home > nominal_home.lambda_away
    assert nominal_home.calibration["params"]["applied_home_advantage_goals"] == 0.12


def test_proxy_elo_is_excluded_from_lambda_inputs() -> None:
    no_elo = run_simulation(
        inputs(
            fixture_id="proxy-elo-baseline",
            home_xg_for=1.2,
            home_xg_against=1.1,
            away_xg_for=1.2,
            away_xg_against=1.1,
            home_elo=None,
            away_elo=None,
            home_squad_value_eur=None,
            away_squad_value_eur=None,
            neutral_site=True,
        )
    )
    proxy_elo = run_simulation(
        inputs(
            fixture_id="proxy-elo-excluded",
            home_xg_for=1.2,
            home_xg_against=1.1,
            away_xg_for=1.2,
            away_xg_against=1.1,
            home_elo=1900.0,
            away_elo=1100.0,
            home_elo_source="rolling_xg_proxy",
            away_elo_source="rolling_xg_proxy",
            home_elo_collection_status="PROXY_ONLY",
            away_elo_collection_status="PROXY_ONLY",
            home_squad_value_eur=None,
            away_squad_value_eur=None,
            neutral_site=True,
        )
    )

    assert proxy_elo.lambda_home == no_elo.lambda_home
    assert proxy_elo.lambda_away == no_elo.lambda_away
    assert proxy_elo.input_readiness["elo_ready"] is False
    assert proxy_elo.input_readiness["ratings_used_in_lambda"] is False
    assert proxy_elo.input_readiness["proxy_elo_excluded"] is True


def test_market_odds_are_not_simulation_inputs() -> None:
    first = run_simulation(inputs(fixture_id="same-real-inputs"))
    second = run_simulation(inputs(fixture_id="same-real-inputs"))

    assert first.fair_ah == second.fair_ah
    assert first.lambda_home == second.lambda_home
    assert first.lambda_away == second.lambda_away


def test_missing_xg_blocks_simulation() -> None:
    output = run_simulation(inputs(home_xg_for=None))

    assert output.status == INSUFFICIENT_INPUTS
    assert output.fair_ah is None
    assert output.scoreline_picks == []


def test_fair_ou_and_scorelines_change_with_lambdas() -> None:
    low_total = run_simulation(
        inputs(
            fixture_id="low-total",
            home_xg_for=0.8,
            home_xg_against=0.7,
            away_xg_for=0.7,
            away_xg_against=0.8,
        )
    )
    high_total = run_simulation(
        inputs(
            fixture_id="high-total",
            home_xg_for=2.2,
            home_xg_against=1.7,
            away_xg_for=2.0,
            away_xg_against=1.9,
        )
    )

    assert low_total.fair_ou != high_total.fair_ou
    assert low_total.scoreline_picks != high_total.scoreline_picks


def test_ah_ladder_exposes_settlement_distribution_for_ev() -> None:
    output = run_simulation(inputs(fixture_id="ah-distribution"))

    row = next(item for item in output.ah_probabilities["ladder"] if item["home_line"] == -0.5)
    home_distribution = row["home_settlement_distribution"]
    away_distribution = row["away_settlement_distribution"]

    assert set(home_distribution) == {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
    assert set(away_distribution) == {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
    assert abs(sum(home_distribution.values()) - 1.0) < 0.01
    assert ah_expected_value(home_distribution, decimal_price=1.95) is not None


def test_ah_settlement_distribution_from_lambdas_supports_lines_outside_ladder() -> None:
    distribution = ah_settlement_distribution_from_lambdas(
        lambda_home=2.1,
        lambda_away=0.7,
        selection="HOME",
        line=-3.5,
    )

    assert distribution is not None
    assert set(distribution) == {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
    assert abs(sum(distribution.values()) - 1.0) < 0.02
    assert ah_expected_value(distribution, decimal_price=1.85) is not None
