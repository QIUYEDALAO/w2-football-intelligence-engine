from __future__ import annotations

from w2.dashboard.scorelines import scoreline_reference_from_card


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
    assert reference["source"] == "formal_simulation"
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
        "decision_simulation_direction_top3",
        "decision_simulation_direction_top3",
        "decision_simulation_direction_top3",
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


def test_scoreline_reference_direction_top3_accepts_analysis_pick_and_plus_half() -> None:
    card = {
        "simulation": {
            "status": "READY",
            "lambda_home": 0.8,
            "lambda_away": 1.7,
            "scoreline_picks": [
                {"scoreline": "0-1", "probability": 0.25},
                {"scoreline": "0-2", "probability": 0.21},
                {"scoreline": "1-1", "probability": 0.18},
            ],
            "ou_probabilities": {"ladder": []},
        },
    }

    reference = scoreline_reference_from_card(
        card,
        recommendation={
            "tier": "ANALYSIS_PICK",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": "+0.5",
        },
    )

    assert reference is not None
    direction_top3 = reference["direction_top3"]
    assert len(direction_top3) == 3
    assert all(item["home_goals"] >= item["away_goals"] for item in direction_top3)
    assert {item["scoreline"] for item in direction_top3}.isdisjoint({"0-1", "0-2"})


def test_scoreline_reference_direction_top3_filters_totals_pick() -> None:
    card = {
        "simulation": {
            "status": "READY",
            "lambda_home": 1.8,
            "lambda_away": 1.2,
            "scoreline_picks": [],
            "ou_probabilities": {"ladder": []},
        },
    }

    reference = scoreline_reference_from_card(
        card,
        recommendation={
            "tier": "RECOMMEND",
            "market": "TOTALS",
            "selection": "OVER",
            "line": "2.5",
        },
    )

    assert reference is not None
    direction_top3 = reference["direction_top3"]
    assert len(direction_top3) == 3
    assert all(item["home_goals"] + item["away_goals"] >= 3 for item in direction_top3)


def test_scoreline_reference_returns_none_without_ready_simulation() -> None:
    card = {"pricing_shadow": {"simulation": {"status": "WATCH"}}}
    assert scoreline_reference_from_card(card) is None
