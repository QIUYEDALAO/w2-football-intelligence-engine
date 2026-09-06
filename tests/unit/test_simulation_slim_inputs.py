from dataclasses import replace

from w2.strategy.simulate import SimulationInputs, run_simulation


def test_retired_enhancements_cannot_change_simulation():
    base = SimulationInputs(
        fixture_id="slim", home_team_id="home", away_team_id="away",
        home_xg_for=1.5, home_xg_against=1.0,
        away_xg_for=1.2, away_xg_against=1.4,
    )
    enhanced = replace(
        base, home_elo=2000, away_elo=1000,
        home_squad_value_eur=1_000_000_000, away_squad_value_eur=1000,
        lineup_strength_adjustment=1.0, lineup_ah_adjustment=0.25,
        lineup_totals_adjustment=0.3, lineup_ah_evidence_enabled=True,
        lineup_totals_evidence_enabled=True,
    )
    expected = run_simulation(base)
    actual = run_simulation(enhanced)
    assert actual.lambda_home == expected.lambda_home
    assert actual.lambda_away == expected.lambda_away
    assert actual.ah_probabilities == expected.ah_probabilities
    assert actual.ou_probabilities == expected.ou_probabilities
    assert actual.input_readiness["ratings_used_in_lambda"] is False
    assert actual.input_readiness["squad_value_used_in_lambda"] is False
