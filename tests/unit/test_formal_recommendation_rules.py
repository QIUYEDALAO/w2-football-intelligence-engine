from __future__ import annotations

from w2.strategy.formal_recommendation import (
    build_formal_recommendation,
    canonical_ah_market,
)
from w2.strategy.simulate import SimulationInputs, run_simulation


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
        "source": None,
        "as_of": None,
        "bookmaker_count": None,
        "validation_status": "READY",
        "blocker": None,
    }


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
