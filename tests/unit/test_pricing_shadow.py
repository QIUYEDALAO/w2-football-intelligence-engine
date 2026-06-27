from __future__ import annotations

from w2.pricing.shadow import build_pricing_shadow


def test_pricing_shadow_is_uncalibrated_and_never_beats_market() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-1",
        model_probabilities={"HOME": 0.62, "DRAW": 0.20, "AWAY": 0.18},
        market_probabilities={"HOME": 0.44, "DRAW": 0.29, "AWAY": 0.27},
        current_odds={
            "ah": {"home_line": "0.25"},
            "ou": {"line": "2.5"},
        },
    )

    assert shadow["status"] == "RULE_BASED_UNCALIBRATED"
    assert shadow["calibration_version"] == "UNVALIDATED"
    assert shadow["fair_ah"] < 0
    assert shadow["fair_ou"] == 2.5
    assert shadow["market_ah"] == 0.25
    assert shadow["coverage"] == 1.0
    assert shadow["beats_market"] is False
    assert shadow["formal_enabled"] is False
    assert shadow["candidate_enabled"] is False
    assert shadow["s2_gate"] == {"n_min": 200, "beats_market": False}
    assert {factor["id"] for factor in shadow["factors"]} == {
        "F3_MODEL_HOME_PROBABILITY",
        "F4_MODEL_AWAY_PROBABILITY",
        "F5_DRAW_SUPPRESSION",
        "F6_MARKET_HOME_BASELINE",
        "F7_MARKET_AWAY_BASELINE",
        "F8_PRICE_COVERAGE",
        "F9_MODEL_MARKET_DIVERGENCE",
    }


def test_pricing_shadow_reports_missing_inputs_without_fabricating_values() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-2",
        model_probabilities=None,
        market_probabilities=None,
    )

    assert {factor["id"]: factor["status"] for factor in shadow["factors"]} == {
        "F3_MODEL_HOME_PROBABILITY": "READY",
        "F4_MODEL_AWAY_PROBABILITY": "READY",
        "F5_DRAW_SUPPRESSION": "READY",
        "F6_MARKET_HOME_BASELINE": "READY",
        "F7_MARKET_AWAY_BASELINE": "READY",
        "F8_PRICE_COVERAGE": "READY",
        "F9_MODEL_MARKET_DIVERGENCE": "READY",
    }
    assert shadow["coverage"] == 0.0
    assert shadow["status"] == "WATCH"
    assert shadow["asof_market_snapshot_id"] is None
    assert shadow["devig_method"] is None
    assert shadow["settlement_outcome"] is None


def test_pricing_shadow_watches_when_edge_is_too_small() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-3",
        model_probabilities={"HOME": 0.45, "DRAW": 0.30, "AWAY": 0.25},
        market_probabilities={"HOME": 0.44, "DRAW": 0.29, "AWAY": 0.27},
        current_odds={
            "ah": {"home_line": "0"},
            "ou": {"line": "2.5"},
        },
    )

    assert abs(shadow["edge_ah"]) < 0.25
    assert shadow["status"] == "WATCH"
    assert shadow["beats_market"] is False
