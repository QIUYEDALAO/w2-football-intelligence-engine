from __future__ import annotations

import pytest

from w2.dashboard.scorelines import scoreline_picks_from_card, scoreline_reference_from_card


def test_fair_estimate_drives_pick_settlement_and_scorelines_from_one_distribution() -> None:
    card = {
        "analysis_gate": {"market": "TOTALS"},
        "decision_contract": {
            "pick": {
                "market": "TOTALS",
                "selection": "OVER",
                "line": "3.25",
            }
        },
        "fair_market_estimates": [
            {
                "market": "TOTALS",
                "status": "READY",
                "model_family": "R4_1_CALIBRATED",
                "home_mu": 3.1462969750688647,
                "away_mu": 1.3672753468077237,
                "artifact_hash": "artifact-1",
                "artifact_version": "v1",
                "train_cutoff": "2025-12-08T20:00:00Z",
            }
        ],
        "pricing_shadow": {
            "simulation": {
                "status": "READY",
                "lambda_home": 1.2,
                "lambda_away": 1.0,
                "scoreline_picks": [
                    {"scoreline": "1-1", "probability": 0.99},
                ],
            }
        },
    }

    reference = scoreline_reference_from_card(card)

    assert reference is not None
    assert reference["source"] == "fair_market_estimate"
    assert all(item["scoreline"] != "1-1" for item in reference["top_scorelines"])
    assert reference["distribution_provenance"]["artifact_hash"] == "artifact-1"
    direction = reference["direction_scorelines"]
    assert [item["scoreline"] for item in direction] == ["3-1", "4-1", "3-2"]
    assert all(item["outcome"] in {"WIN", "HALF_WIN"} for item in direction)
    assert all(
        item["probability_type"] == "UNCONDITIONAL_FILTERED_BY_SETTLEMENT"
        for item in direction
    )
    assert all(item["source"] == "fair_market_estimate" for item in direction)
    settlement = reference["market_settlement"]
    assert settlement["market"] == "TOTALS"
    assert settlement["selection"] == "OVER"
    assert settlement["line"] == 3.25
    assert settlement["probabilities"]["WIN"] == pytest.approx(0.65999, abs=2e-5)
    assert settlement["probabilities"]["HALF_LOSS"] == pytest.approx(0.16795, abs=2e-5)
    assert settlement["probabilities"]["LOSS"] == pytest.approx(0.17206, abs=2e-5)


def test_fair_estimate_uses_analysis_gate_before_decision_pick_is_materialized() -> None:
    card = {
        "analysis_gate": {
            "market": "TOTALS",
            "selection": "OVER",
            "market_line": 3.25,
        },
        "fair_market_estimates": [
            {
                "market": "TOTALS",
                "status": "READY",
                "model_family": "R4_1_CALIBRATED",
                "home_mu": 3.1462969750688647,
                "away_mu": 1.3672753468077237,
            }
        ],
    }

    reference = scoreline_reference_from_card(card)

    assert reference is not None
    settlement = reference["market_settlement"]
    assert settlement["selection"] == "OVER"
    assert settlement["line"] == 3.25
    assert settlement["probabilities"]["WIN"] == pytest.approx(0.65999, abs=2e-5)
    assert all(
        int(item["home_goals"]) + int(item["away_goals"]) >= 4
        for item in reference["direction_scorelines"]
    )


@pytest.mark.parametrize(
    ("market", "selection", "line", "expected_outcomes"),
    [
        ("TOTALS", "OVER", 2.75, {"WIN", "HALF_WIN"}),
        ("TOTALS", "UNDER", 2.75, {"WIN", "HALF_WIN"}),
        ("ASIAN_HANDICAP", "HOME_AH", -0.75, {"WIN", "HALF_WIN"}),
        ("ASIAN_HANDICAP", "AWAY_AH", 0.75, {"WIN", "HALF_WIN"}),
    ],
)
def test_direction_scorelines_follow_pick_settlement_for_quarter_lines(
    market: str,
    selection: str,
    line: float,
    expected_outcomes: set[str],
) -> None:
    card = {
        "analysis_gate": {"market": market},
        "decision_tier": "ANALYSIS_PICK",
        "decision_contract": {
            "pick": {"market": market, "selection": selection, "line": line}
        },
        "fair_market_estimates": [
            {
                "market": market,
                "status": "READY",
                "model_family": "R4_1_CALIBRATED",
                "home_mu": 1.8,
                "away_mu": 1.2,
            }
        ],
    }

    reference = scoreline_reference_from_card(card)

    assert reference is not None
    assert len(reference["direction_scorelines"]) == 3
    assert {item["outcome"] for item in reference["direction_scorelines"]} <= expected_outcomes
    assert all(
        item["probability_type"] == "UNCONDITIONAL_FILTERED_BY_SETTLEMENT"
        for item in reference["direction_scorelines"]
    )


def test_visible_pick_rejects_fair_estimate_for_another_market() -> None:
    card = {
        "decision_tier": "ANALYSIS_PICK",
        "decision_contract": {
            "pick": {"market": "TOTALS", "selection": "OVER", "line": 2.5}
        },
        "fair_market_estimates": [
            {
                "market": "ASIAN_HANDICAP",
                "status": "READY",
                "model_family": "R4_1_CALIBRATED",
                "home_mu": 1.8,
                "away_mu": 1.2,
            }
        ],
    }

    assert scoreline_reference_from_card(card) is None


def test_scoreline_reference_exposes_tail_when_top_scores_are_low() -> None:
    card = {
        "pricing_shadow": {
            "simulation": {
                "status": "READY",
                "lambda_home": 1.911992,
                "lambda_away": 0.704658,
                "scoreline_picks": [
                    {"scoreline": "1-0", "probability": 0.1436, "probability_label": "14%"},
                    {"scoreline": "2-0", "probability": 0.1255, "probability_label": "13%"},
                    {"scoreline": "1-1", "probability": 0.1057, "probability_label": "11%"},
                ],
                "score_matrix_summary": {
                    "home_win": 0.6525,
                    "draw": 0.2198,
                    "away_win": 0.1277,
                },
                "ou_probabilities": {
                    "ladder": [
                        {"line": 3.5, "over": 0.2592},
                        {"line": 4.5, "over": 0.1232},
                    ],
                },
            },
        },
    }

    reference = scoreline_reference_from_card(
        card,
        recommendation={
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY_AH",
            "line": "1.75",
        },
    )

    assert reference is not None
    assert reference["source"] == "legacy_baseline_simulation"
    assert reference["source_status"] == "LEGACY_BASELINE_NOT_DECISION_SOURCE"
    assert reference["direction_top3"] == []
    assert "midband_scorelines" not in reference
    assert "_midband_scorelines" not in reference
    assert [item["scoreline"] for item in reference["top_scorelines"]] == [
        "1-0",
        "2-0",
        "1-1",
    ]
    assert reference["high_total"]["threshold"] == 4
    assert reference["high_total"]["probability"] == 0.2592
    assert reference["high_total"]["probability_label"] == "26%"
    assert reference["high_total"]["representative_scoreline"]["source"] == (
        "exact_poisson_from_lambda"
    )
    assert reference["very_high_total"] == {
        "threshold": 5,
        "probability": 0.1232,
        "probability_label": "12%",
    }
    assert reference["ah_key_scorelines"] == [
        {
            "outcome": "WIN",
            "label": "全赢",
            "scoreline": "1-0",
            "home_goals": 1,
            "away_goals": 0,
            "representative_probability": 0.139666,
            "representative_probability_label": "14%",
            "settlement_probability": 0.597114,
            "settlement_probability_label": "60%",
            "source": "exact_poisson_from_lambda",
        },
        {
            "outcome": "HALF_LOSS",
            "label": "半输",
            "scoreline": "2-0",
            "home_goals": 2,
            "away_goals": 0,
            "representative_probability": 0.13352,
            "representative_probability_label": "13%",
            "settlement_probability": 0.204542,
            "settlement_probability_label": "20%",
            "source": "exact_poisson_from_lambda",
        },
        {
            "outcome": "LOSS",
            "label": "全输",
            "scoreline": "3-0",
            "home_goals": 3,
            "away_goals": 0,
            "representative_probability": 0.085096,
            "representative_probability_label": "9%",
            "settlement_probability": 0.197517,
            "settlement_probability_label": "20%",
            "source": "exact_poisson_from_lambda",
        },
    ]


def test_scoreline_reference_direction_top3_filters_by_formal_home_ah_direction() -> None:
    card = {
        "pricing_shadow": {
            "simulation": {
                "status": "READY",
                "lambda_home": 1.9,
                "lambda_away": 0.7,
                "scoreline_picks": [
                    {"scoreline": "1-0", "probability": 0.14},
                    {"scoreline": "2-0", "probability": 0.13},
                    {"scoreline": "1-1", "probability": 0.10},
                ],
                "ou_probabilities": {"ladder": []},
            },
        },
    }

    reference = scoreline_reference_from_card(
        card,
        recommendation={
            "tier": "FORMAL",
            "formal_recommendation": True,
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": "-0.5",
        },
    )

    assert reference is not None
    direction_top3 = reference["direction_top3"]
    assert len(direction_top3) == 3
    assert [item["source"] for item in direction_top3] == [
        "formal_simulation_direction_top3",
        "formal_simulation_direction_top3",
        "formal_simulation_direction_top3",
    ]
    assert all(item["home_goals"] > item["away_goals"] for item in direction_top3)
    assert [item["probability"] for item in direction_top3] == sorted(
        [item["probability"] for item in direction_top3],
        reverse=True,
    )
    assert all(item["probability_label"] for item in direction_top3)
    assert "midband_scorelines" not in reference


def test_scoreline_reference_direction_top3_filters_by_formal_away_ah_direction() -> None:
    card = {
        "pricing_shadow": {
            "simulation": {
                "status": "READY",
                "lambda_home": 0.7,
                "lambda_away": 1.9,
                "scoreline_picks": [
                    {"scoreline": "0-1", "probability": 0.14},
                    {"scoreline": "0-2", "probability": 0.13},
                    {"scoreline": "1-1", "probability": 0.10},
                ],
                "ou_probabilities": {"ladder": []},
            },
        },
    }

    reference = scoreline_reference_from_card(
        card,
        recommendation={
            "tier": "FORMAL",
            "formal_recommendation": True,
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY_AH",
            "line": "-0.5",
        },
    )

    assert reference is not None
    direction_top3 = reference["direction_top3"]
    assert len(direction_top3) == 3
    assert all(item["away_goals"] > item["home_goals"] for item in direction_top3)
    assert all(item["selection"] == "AWAY_AH" for item in direction_top3)


def test_scoreline_reference_returns_none_without_ready_simulation() -> None:
    card = {"pricing_shadow": {"simulation": {"status": "WATCH"}}}
    assert scoreline_reference_from_card(card) is None


def test_visible_pick_never_falls_back_to_legacy_simulation() -> None:
    card = {
        "decision_tier": "ANALYSIS_PICK",
        "pricing_shadow": {
            "simulation": {
                "status": "READY",
                "lambda_home": 1.4,
                "lambda_away": 1.1,
            }
        },
    }

    assert scoreline_reference_from_card(card) is None
    assert scoreline_picks_from_card(card) == []
