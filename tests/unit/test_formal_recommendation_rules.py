from __future__ import annotations

from w2.strategy.formal_recommendation import build_formal_recommendation
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
