from __future__ import annotations

from w2.pricing.shadow import build_pricing_shadow


def test_pricing_shadow_is_uncalibrated_and_never_beats_market() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-1",
        model_probabilities={"HOME": 0.45, "DRAW": 0.30, "AWAY": 0.25},
        market_probabilities={"HOME": 0.44, "DRAW": 0.29, "AWAY": 0.27},
    )

    assert shadow["status"] == "RULE_BASED_UNCALIBRATED"
    assert shadow["calibration_version"] == "UNVALIDATED"
    assert shadow["fair_ah"] is None
    assert shadow["fair_ou"] is None
    assert shadow["edge_ah"] is None
    assert shadow["edge_ou"] is None
    assert shadow["beats_market"] is False
    assert shadow["coverage"] == {
        "model_probabilities": True,
        "market_probabilities": True,
        "fair_line": False,
        "edge": False,
    }


def test_pricing_shadow_reports_missing_inputs_without_fabricating_values() -> None:
    shadow = build_pricing_shadow(
        fixture_id="fixture-2",
        model_probabilities=None,
        market_probabilities=None,
    )

    assert {factor["id"]: factor["status"] for factor in shadow["factors"]} == {
        "model_probabilities": "MISSING",
        "market_probabilities": "MISSING",
        "s2_calibration_gate": "NOT_EVALUATED",
    }
    assert shadow["asof_market_snapshot_id"] is None
    assert shadow["devig_method"] is None
    assert shadow["settlement_outcome"] is None
