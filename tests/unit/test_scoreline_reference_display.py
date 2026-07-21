from __future__ import annotations

from w2.dashboard.scorelines import scoreline_reference_from_card
from w2.strategy.simulate import SimulationInputs, run_simulation


def _ready_simulation_card() -> dict[str, object]:
    simulation = run_simulation(
        SimulationInputs(
            fixture_id="fixture-scoreline-contract",
            home_team_id="home",
            away_team_id="away",
            home_xg_for=1.4,
            home_xg_against=1.0,
            away_xg_for=1.5,
            away_xg_against=1.1,
            lambda_sigma_home=0.15,
            lambda_sigma_away=0.12,
            lambda_uncertainty_method="empirical_xg_standard_error.v1",
            lambda_uncertainty_status="ANALYSIS_READY",
        )
    ).as_dict()
    return {
        "fixture_id": "fixture-scoreline-contract",
        "pricing_shadow": {"simulation": simulation},
    }


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


def test_scoreline_projection_is_seeded_deterministic_and_completes_10000() -> None:
    card = _ready_simulation_card()
    candidate = {
        "market": "TOTALS",
        "selection": "UNDER",
        "line": "3.5",
    }

    first = scoreline_reference_from_card(
        card, recommendation=candidate, decision_hash="decision-1"
    )
    second = scoreline_reference_from_card(
        card, recommendation=candidate, decision_hash="decision-1"
    )
    changed = scoreline_reference_from_card(
        card, recommendation=candidate, decision_hash="decision-2"
    )

    assert first is not None and second is not None and changed is not None
    first_projection = first["scoreline_projection"]
    assert first_projection == second["scoreline_projection"]
    assert first_projection["simulations_completed"] == 10_000
    assert first_projection["simulation_method"] == "seeded_joint_score_sampling"
    assert first_projection["seed"] != changed["scoreline_projection"]["seed"]
    assert all(
        item["sample_count"] / 10_000 == item["unconditional_probability"]
        for item in first_projection["top3"]
    )


def test_scoreline_projection_uses_quarter_ah_and_secondary_total_settlement() -> None:
    card = _ready_simulation_card()
    card["secondary_picks"] = [
        {"market": "TOTALS", "selection": "UNDER", "line": "3.5"}
    ]
    reference = scoreline_reference_from_card(
        card,
        recommendation={
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY",
            "line": "-0.75",
            "quote_identity": {"line": "-0.75"},
        },
        decision_hash="decision-quarter",
    )

    assert reference is not None
    projection = reference["scoreline_projection"]
    assert projection["status"] == "READY"
    assert projection["secondary_constraints"] == [
        {"market": "TOTALS", "selection": "UNDER", "line": "3.5"}
    ]
    assert projection["top3"]
    assert all(
        item["away_goals"] > item["home_goals"]
        and item["home_goals"] + item["away_goals"] <= 3
        and item["primary_settlement"] in {"WIN", "HALF_WIN"}
        and item["secondary_settlements"] == ["WIN"]
        for item in projection["top3"]
    )


def test_scoreline_projection_fails_closed_on_selected_quote_line_mismatch() -> None:
    reference = scoreline_reference_from_card(
        _ready_simulation_card(),
        recommendation={
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "line": "-0.75",
            "quote_identity": {"line": "-0.5"},
        },
        decision_hash="decision-mismatch",
    )

    assert reference is not None
    assert reference["scoreline_projection"]["status"] == "NOT_READY"
    assert reference["scoreline_projection"]["reason"] == (
        "AH_SELECTED_SIDE_LINE_MISMATCH"
    )
    assert reference["scoreline_projection"]["top3"] == []


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
