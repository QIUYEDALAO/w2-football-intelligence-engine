from __future__ import annotations

from dataclasses import replace

from w2.strategy.formal_recommendation import (
    _settlement_distribution_with_ev_se,
    build_formal_recommendation,
    canonical_ah_market,
    formal_recommendation_id,
    is_reverse_value_recommendation,
)
from w2.strategy.simulate import (
    READY,
    SimulationInputs,
    SimulationOutput,
    ah_expected_value_uncertainty_from_lambdas,
    run_simulation,
)


def ready_shadow(*, fair_ah: float = -1.25, leader: str = "HOME") -> dict[str, object]:
    return {
        "independent_signal_count": 4,
        "team_score": {
            "home": 0.7 if leader == "HOME" else 0.2,
            "away": 0.2 if leader == "HOME" else 0.7,
        },
        "fair_ah": fair_ah,
        "beats_market": False,
    }


def ready_analysis() -> dict[str, object]:
    return {"status": "READY", "blockers": []}


def simulation(**overrides: object):
    payload = {
        "fixture_id": "formal-home",
        "home_team_id": "home",
        "away_team_id": "away",
        "home_xg_for": 2.2,
        "home_xg_against": 0.6,
        "away_xg_for": 0.7,
        "away_xg_against": 1.8,
        "home_elo": 1750.0,
        "away_elo": 1350.0,
        "home_squad_value_eur": 900_000_000.0,
        "away_squad_value_eur": 80_000_000.0,
    }
    payload.update(overrides)
    return run_simulation(SimulationInputs(**payload))  # type: ignore[arg-type]


def reverse_value_simulation() -> SimulationOutput:
    return SimulationOutput(
        model_version="w2.formal.mc_poisson.v1",
        calibration_version="w2.formal.lambda_baseline_prior.v1",
        calibration_status="BASELINE_PRIOR",
        lambda_home=1.38,
        lambda_away=1.29,
        lambda_sigma_home=0.0,
        lambda_sigma_away=0.0,
        fair_ah=0.0,
        fair_ou=2.75,
        scoreline_picks=[
            {"scoreline": "1-1", "home_goals": 1, "away_goals": 1, "probability": 0.1261}
        ],
        score_matrix_summary={"home_win": 0.3838, "draw": 0.2647, "away_win": 0.3515},
        ah_probabilities={
            "ladder": [
                {
                    "home_line": -0.25,
                    "home_settlement_distribution": {
                        "WIN": 0.3838,
                        "HALF_WIN": 0.0,
                        "PUSH": 0.0,
                        "HALF_LOSS": 0.2647,
                        "LOSS": 0.3515,
                    },
                    "away_settlement_distribution": {
                        "WIN": 0.3515,
                        "HALF_WIN": 0.2647,
                        "PUSH": 0.0,
                        "HALF_LOSS": 0.0,
                        "LOSS": 0.3838,
                    },
                }
            ]
        },
        ou_probabilities={},
        input_readiness={"xg_ready": True},
        status=READY,
        simulations=10_000,
        seed=123,
    )


def off_ladder_simulation(*, rho: float = 0.12) -> SimulationOutput:
    return SimulationOutput(
        model_version="w2.formal.exact_dc_poisson.v1",
        calibration_version="w2.formal.lambda_baseline_prior.v1",
        calibration_status="BASELINE_PRIOR",
        lambda_home=1.4,
        lambda_away=1.2,
        lambda_sigma_home=0.35,
        lambda_sigma_away=0.35,
        fair_ah=-0.25,
        fair_ou=2.75,
        scoreline_picks=[],
        score_matrix_summary={"home_win": 0.4, "draw": 0.27, "away_win": 0.33},
        ah_probabilities={"ladder": []},
        ou_probabilities={},
        input_readiness={"xg_ready": True},
        status=READY,
        simulations=10_000,
        seed=456,
        calibration={"params": {"dixon_coles_rho": rho}},
    )


def ev_gate_simulation(
    *,
    lambda_sigma_home: float = 0.0,
    lambda_sigma_away: float = 0.0,
    lambda_home: float | None = 1.4,
    lambda_away: float | None = 1.2,
) -> SimulationOutput:
    return SimulationOutput(
        model_version="w2.formal.exact_dc_poisson.v1",
        calibration_version="w2.formal.lambda_baseline_prior.v1",
        calibration_status="BASELINE_PRIOR",
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        lambda_sigma_home=lambda_sigma_home,
        lambda_sigma_away=lambda_sigma_away,
        fair_ah=0.0,
        fair_ou=2.75,
        scoreline_picks=[],
        score_matrix_summary={"home_win": 0.4, "draw": 0.27, "away_win": 0.35},
        ah_probabilities={
            "ladder": [
                {
                    "home_line": 0.0,
                    "home_settlement_distribution": {
                        "WIN": 0.518,
                        "HALF_WIN": 0.0,
                        "PUSH": 0.0,
                        "HALF_LOSS": 0.0,
                        "LOSS": 0.482,
                    },
                    "away_settlement_distribution": {
                        "WIN": 0.482,
                        "HALF_WIN": 0.0,
                        "PUSH": 0.0,
                        "HALF_LOSS": 0.0,
                        "LOSS": 0.518,
                    },
                }
            ]
        },
        ou_probabilities={},
        input_readiness={"xg_ready": True},
        status=READY,
        simulations=10_000,
        seed=789,
        calibration={"params": {"dixon_coles_rho": 0.12}},
    )


def test_formal_home_when_simulation_and_price_are_self_consistent() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(),
        current_odds={"ah": {"home_line": 0.5, "home_price": 1.95, "away_price": 1.95}},
        pricing_shadow=ready_shadow(),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "FORMAL"
    assert result.recommendation is not None
    assert result.recommendation["formal_recommendation"] is True
    assert result.recommendation["selection"] == "HOME_AH"
    assert result.recommendation["beats_market_required"] is False
    assert result.recommendation["ev_se"] == 0.0


def test_formal_recommendation_id_is_stable_for_same_payload() -> None:
    recommendation = {
        "tier": "FORMAL",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "line": "-0.5",
        "odds": "1.91",
        "expected_value": 0.112465,
        "ev_se": 0.0,
    }

    first = formal_recommendation_id(fixture_id="fixture-1", recommendation=recommendation)
    second = formal_recommendation_id(fixture_id="fixture-1", recommendation=recommendation)
    changed = formal_recommendation_id(
        fixture_id="fixture-1",
        recommendation={**recommendation, "selection": "AWAY_AH"},
    )

    assert first == second
    assert len(first) == 36
    assert first != changed


def test_formal_ev_se_uses_lambda_uncertainty() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(lambda_sigma_home=0.35, lambda_sigma_away=0.35),
        current_odds={"ah": {"home_line": 0.5, "home_price": 2.20, "away_price": 1.65}},
        pricing_shadow=ready_shadow(),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "FORMAL"
    assert result.recommendation is not None
    assert result.recommendation["ev_se"] is not None
    assert result.recommendation["ev_se"] > 0.0


def test_ev_se_zero_keeps_existing_threshold_behavior() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=ev_gate_simulation(),
        current_odds={"ah": {"home_line": 0.0, "home_price": 2.0, "away_price": 2.0}},
        pricing_shadow={**ready_shadow(fair_ah=0.0, leader="HOME"), "market_ah": 0.0},
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "FORMAL"
    assert result.recommendation is not None
    assert result.recommendation["expected_value"] == 0.036
    assert result.recommendation["ev_se"] == 0.0


def test_ev_within_uncertainty_band_returns_watch() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=ev_gate_simulation(lambda_sigma_home=0.35, lambda_sigma_away=0.35),
        current_odds={"ah": {"home_line": 0.0, "home_price": 2.0, "away_price": 2.0}},
        pricing_shadow={**ready_shadow(fair_ah=0.0, leader="HOME"), "market_ah": 0.0},
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "EV_WITHIN_UNCERTAINTY_BAND" in result.blockers
    assert result.recommendation is None


def test_missing_ev_uncertainty_returns_watch() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=ev_gate_simulation(lambda_home=None),
        current_odds={"ah": {"home_line": 0.0, "home_price": 2.0, "away_price": 2.0}},
        pricing_shadow={**ready_shadow(fair_ah=0.0, leader="HOME"), "market_ah": 0.0},
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "EV_UNCERTAINTY_MISSING" in result.blockers
    assert result.recommendation is None


def test_off_ladder_formal_fallback_uses_scenario_ev_uncertainty() -> None:
    formal_simulation = off_ladder_simulation()

    distribution, ev, ev_se = _settlement_distribution_with_ev_se(
        formal_simulation,
        "HOME",
        -3.5,
        1.91,
    )
    scenario_distribution, scenario_ev, scenario_ev_se = (
        ah_expected_value_uncertainty_from_lambdas(
            lambda_home=1.4,
            lambda_away=1.2,
            lambda_sigma_home=0.35,
            lambda_sigma_away=0.35,
            rho=0.12,
            selection="HOME",
            line=-3.5,
            decimal_price=1.91,
        )
    )

    assert distribution == scenario_distribution
    assert ev == scenario_ev
    assert ev_se == scenario_ev_se
    assert ev_se is not None and ev_se > 0.0
    assert distribution is not None
    assert abs(sum(distribution.values()) - 1.0) < 0.02


def test_off_ladder_formal_fallback_uses_simulation_rho() -> None:
    zero_rho_distribution, _, _ = _settlement_distribution_with_ev_se(
        off_ladder_simulation(rho=0.0),
        "HOME",
        -0.25,
        1.91,
    )
    dc_distribution, _, _ = _settlement_distribution_with_ev_se(
        off_ladder_simulation(rho=0.12),
        "HOME",
        -0.25,
        1.91,
    )

    assert zero_rho_distribution is not None
    assert dc_distribution is not None
    assert any(
        abs(zero_rho_distribution[outcome] - dc_distribution[outcome]) > 0.000001
        for outcome in zero_rho_distribution
    )


def test_formal_away_when_simulation_and_price_are_self_consistent() -> None:
    away_simulation = simulation(
        fixture_id="formal-away",
        home_xg_for=0.7,
        home_xg_against=1.8,
        away_xg_for=2.2,
        away_xg_against=0.6,
        home_elo=1350.0,
        away_elo=1750.0,
        home_squad_value_eur=80_000_000.0,
        away_squad_value_eur=900_000_000.0,
    )

    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=away_simulation,
        current_odds={"ah": {"home_line": -0.5, "home_price": 1.95, "away_price": 1.95}},
        pricing_shadow=ready_shadow(fair_ah=1.25, leader="AWAY"),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "FORMAL"
    assert result.recommendation is not None
    assert result.recommendation["selection"] == "AWAY_AH"


def test_scoreline_reverse_value_sets_reverse_flag_without_changing_ev_gate() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=reverse_value_simulation(),
        current_odds={
            "ah": {
                "home_line": -0.25,
                "away_line": 0.25,
                "home_price": 1.85,
                "away_price": 2.05,
            }
        },
        pricing_shadow={**ready_shadow(fair_ah=0.0, leader="HOME"), "market_ah": -0.25},
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "FORMAL"
    assert result.recommendation is not None
    assert result.recommendation["selection"] == "AWAY_AH"
    assert result.recommendation["reverse_factor_value"] is True
    assert result.recommendation["expected_value"] >= 0.08


def test_reverse_value_threshold_includes_ev_uncertainty_penalty() -> None:
    uncertain_reverse = replace(
        reverse_value_simulation(),
        lambda_sigma_home=0.35,
        lambda_sigma_away=0.35,
    )

    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=uncertain_reverse,
        current_odds={
            "ah": {
                "home_line": -0.25,
                "away_line": 0.25,
                "home_price": 1.85,
                "away_price": 2.20,
            }
        },
        pricing_shadow={**ready_shadow(fair_ah=0.0, leader="HOME"), "market_ah": -0.25},
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "REVERSE_FACTOR_VALUE_NOT_STRONG_ENOUGH" in result.blockers
    assert result.recommendation is None


def test_reverse_value_helper_detects_scoreline_dominant_opposite_side() -> None:
    assert (
        is_reverse_value_recommendation(
            selected_side="AWAY",
            fair_ah=0.0,
            score_matrix_summary={"home_win": 0.3838, "draw": 0.2647, "away_win": 0.3515},
            factor_side="NEUTRAL",
        )
        is True
    )


def test_reverse_value_helper_ignores_tiny_scoreline_noise() -> None:
    assert (
        is_reverse_value_recommendation(
            selected_side="AWAY",
            fair_ah=0.0,
            score_matrix_summary={"home_win": 0.371, "draw": 0.27, "away_win": 0.349},
            factor_side="NEUTRAL",
        )
        is False
    )


def test_simulation_insufficient_returns_watch() -> None:
    insufficient = simulation(home_xg_for=None)

    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=insufficient,
        current_odds={"ah": {"home_line": 0.5, "home_price": 1.95, "away_price": 1.95}},
        pricing_shadow=ready_shadow(),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "SIMULATION_NOT_READY" in result.blockers


def test_market_missing_returns_watch() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(),
        current_odds={},
        pricing_shadow=ready_shadow(),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "MISSING_AH_MARKET" in result.blockers


def test_canonical_ah_uses_pricing_shadow_market_line_with_real_prices() -> None:
    market = canonical_ah_market(
        current_odds={
            "ah": {
                "home_line": -1.5,
                "away_line": 1.5,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": -1.5},
    )

    assert market is not None
    assert market.as_dict() | {"source": None, "as_of": None, "bookmaker_count": None} == {
        "home_line": -1.5,
        "away_line": 1.5,
        "home_price": 1.91,
        "away_price": 1.97,
        "display_line_cn": "主队 -1.5",
        "home_display_line_cn": "主队 -1.5",
        "away_display_line_cn": "客队 +1.5",
        "source": None,
        "as_of": None,
        "bookmaker_count": None,
        "validation_status": "READY",
        "blocker": None,
        "raw_home_line": -1.5,
        "raw_away_line": 1.5,
        "raw_abs_line": None,
        "canonical_home_line": -1.5,
        "canonical_away_line": 1.5,
        "line_normalization_status": "READY",
        "line_normalization_warning": None,
    }


def test_canonical_ah_normalizes_raw_away_line_sign_without_blocking() -> None:
    market = canonical_ah_market(
        current_odds={
            "ah": {
                "line": 1.5,
                "home_line": -1.5,
                "away_line": -1.5,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": -1.5},
    )

    assert market is not None
    payload = market.as_dict()
    assert payload["home_line"] == -1.5
    assert payload["away_line"] == 1.5
    assert payload["raw_away_line"] == -1.5
    assert payload["canonical_away_line"] == 1.5
    assert payload["display_line_cn"] == "主队 -1.5"
    assert payload["home_display_line_cn"] == "主队 -1.5"
    assert payload["away_display_line_cn"] == "客队 +1.5"
    assert payload["line_normalization_warning"] == "AH_RAW_AWAY_LINE_SIGN_NORMALIZED"
    assert payload["validation_status"] == "READY"
    assert payload["blocker"] is None


def test_canonical_ah_normalizes_raw_home_line_sign_without_blocking() -> None:
    market = canonical_ah_market(
        current_odds={
            "ah": {
                "line": 1.5,
                "home_line": 1.5,
                "away_line": 1.5,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": -1.5},
    )

    assert market is not None
    payload = market.as_dict()
    assert payload["home_line"] == -1.5
    assert payload["away_line"] == 1.5
    assert payload["raw_home_line"] == 1.5
    assert payload["canonical_home_line"] == -1.5
    assert payload["display_line_cn"] == "主队 -1.5"
    assert payload["home_display_line_cn"] == "主队 -1.5"
    assert payload["away_display_line_cn"] == "客队 +1.5"
    assert payload["line_normalization_warning"] == "AH_RAW_HOME_LINE_SIGN_NORMALIZED"
    assert payload["validation_status"] == "READY"
    assert payload["blocker"] is None


def test_canonical_ah_display_contract_uses_home_team_view_for_away_favorite() -> None:
    market = canonical_ah_market(
        current_odds={
            "ah": {
                "line": 0.5,
                "home_line": 0.5,
                "away_line": -0.5,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": 0.5},
    )

    assert market is not None
    payload = market.as_dict()
    assert payload["home_line"] == 0.5
    assert payload["away_line"] == -0.5
    assert payload["display_line_cn"] == "客队 -0.5"
    assert payload["home_display_line_cn"] == "主队 +0.5"
    assert payload["away_display_line_cn"] == "客队 -0.5"


def test_canonical_ah_blocks_raw_home_line_magnitude_mismatch() -> None:
    market = canonical_ah_market(
        current_odds={
            "ah": {
                "line": 1.5,
                "home_line": -2.0,
                "away_line": 1.5,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": -1.5},
    )

    assert market is not None
    assert market.as_dict()["validation_status"] == "BLOCKED"
    assert market.as_dict()["blocker"] == "AH_MARKET_HOME_LINE_MAGNITUDE_MISMATCH"


def test_canonical_ah_blocks_raw_away_line_magnitude_mismatch() -> None:
    market = canonical_ah_market(
        current_odds={
            "ah": {
                "line": 1.5,
                "home_line": -1.5,
                "away_line": 2.0,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": -1.5},
    )

    assert market is not None
    assert market.as_dict()["validation_status"] == "BLOCKED"
    assert market.as_dict()["blocker"] == "AH_MARKET_LINE_MAGNITUDE_MISMATCH"


def test_canonical_ah_blocks_raw_abs_line_mismatch() -> None:
    market = canonical_ah_market(
        current_odds={
            "ah": {
                "line": 2.0,
                "home_line": -1.5,
                "away_line": 1.5,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": -1.5},
    )

    assert market is not None
    assert market.as_dict()["validation_status"] == "BLOCKED"
    assert market.as_dict()["blocker"] == "AH_MARKET_ABS_LINE_MISMATCH"


def test_formal_does_not_report_missing_ah_when_shadow_line_and_prices_exist() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(),
        current_odds={
            "ah": {
                "home_line": 0.5,
                "away_line": -0.5,
                "home_price": 1.95,
                "away_price": 1.95,
            }
        },
        pricing_shadow={**ready_shadow(), "market_ah": 0.5},
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert "MISSING_AH_MARKET" not in result.blockers


def test_config_off_suppresses_formal_without_changing_eligibility() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(),
        current_odds={"ah": {"home_line": 0.5, "home_price": 1.95, "away_price": 1.95}},
        pricing_shadow=ready_shadow(),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=False,
    )

    assert result.tier == "WATCH"
    assert result.formal_eligible is True
    assert result.formal_suppressed is True
    assert result.formal_suppressed_reason == "W2_FORMAL_RECOMMENDATION_ENABLED=false"


def test_reverse_value_requires_explicit_price_value_copy() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(),
        current_odds={"ah": {"home_line": -2.5, "home_price": 1.95, "away_price": 1.95}},
        pricing_shadow=ready_shadow(leader="HOME"),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "FORMAL"
    assert result.recommendation is not None
    assert result.recommendation["reverse_factor_value"] is True
    assert "盘口价值" in result.recommendation["reasons"][0]


def test_neutral_fair_line_allows_price_value_on_receiving_side() -> None:
    balanced = simulation(
        fixture_id="formal-neutral-value",
        home_xg_for=1.35,
        home_xg_against=1.25,
        away_xg_for=1.25,
        away_xg_against=1.35,
        home_elo=1600.0,
        away_elo=1595.0,
        home_squad_value_eur=420_000_000.0,
        away_squad_value_eur=400_000_000.0,
    )

    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=balanced,
        current_odds={
            "ah": {
                "home_line": -0.5,
                "away_line": 0.5,
                "home_price": 1.91,
                "away_price": 1.97,
            }
        },
        pricing_shadow={**ready_shadow(fair_ah=0.0, leader="HOME"), "market_ah": -0.5},
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert abs(balanced.fair_ah or 0.0) < 0.25
    assert result.tier == "FORMAL"
    assert result.recommendation is not None
    assert result.recommendation["selection"] == "AWAY_AH"
    assert result.recommendation["selection_label_cn"] == "Away 受让"
    assert result.recommendation["formal_recommendation"] is True
    assert result.recommendation["beats_market_required"] is False
    assert result.recommendation["expected_value"] > 0
    assert "ah_settlement_distribution" in result.recommendation


def test_formal_blocks_implausible_ah_prices_from_alternate_or_wrong_market() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(),
        current_odds={
            "ah": {
                "home_line": -1.0,
                "away_line": 1.0,
                "home_price": 5.30,
                "away_price": 12.50,
            }
        },
        pricing_shadow={**ready_shadow(fair_ah=-0.25, leader="HOME"), "market_ah": -1.0},
        analysis_readiness=ready_analysis(),
        home_team_name="Brazil",
        away_team_name="Japan",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "AH_MARKET_PRICE_OUT_OF_RANGE" in result.blockers
    assert result.recommendation is None


def test_formal_blocks_underround_prices_even_when_cover_probability_looks_large() -> None:
    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=simulation(),
        current_odds={
            "ah": {
                "home_line": -0.5,
                "away_line": 0.5,
                "home_price": 2.87,
                "away_price": 3.75,
            }
        },
        pricing_shadow={**ready_shadow(fair_ah=0.0, leader="HOME"), "market_ah": -0.5},
        analysis_readiness=ready_analysis(),
        home_team_name="Netherlands",
        away_team_name="Morocco",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "AH_MARKET_UNDERROUND_OR_OVERROUND" in result.blockers
    assert result.canonical_ah_market is not None
    assert result.canonical_ah_market["blocker"] == "AH_MARKET_UNDERROUND_OR_OVERROUND"
    assert result.recommendation is None


def test_formal_computes_ah_settlement_distribution_when_ladder_line_missing() -> None:
    strong = simulation()

    result = build_formal_recommendation(
        fixture_status="UPCOMING",
        simulation=strong,
        current_odds={
            "ah": {
                "home_line": -3.5,
                "away_line": 3.5,
                "home_price": 1.85,
                "away_price": 1.95,
            }
        },
        pricing_shadow={**ready_shadow(fair_ah=-1.25, leader="HOME"), "market_ah": -3.5},
        analysis_readiness=ready_analysis(),
        home_team_name="Germany",
        away_team_name="Paraguay",
        enabled=True,
    )

    assert "MISSING_AH_SETTLEMENT_DISTRIBUTION" not in result.blockers
    if result.recommendation is not None:
        distribution = result.recommendation["ah_settlement_distribution"]
        assert set(distribution) == {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}
        assert abs(sum(distribution.values()) - 1.0) < 0.02


def test_finished_fixture_never_emits_new_formal() -> None:
    result = build_formal_recommendation(
        fixture_status="FINISHED",
        simulation=simulation(),
        current_odds={"ah": {"home_line": 0.5, "home_price": 1.95, "away_price": 1.95}},
        pricing_shadow=ready_shadow(),
        analysis_readiness=ready_analysis(),
        home_team_name="Home",
        away_team_name="Away",
        enabled=True,
    )

    assert result.tier == "WATCH"
    assert "FIXTURE_NOT_PREMATCH" in result.blockers
