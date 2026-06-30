from __future__ import annotations

from w2.dashboard.scorelines import scoreline_reference_from_card


def test_scoreline_reference_exposes_midband_without_tail_or_settlement_details() -> None:
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
    assert reference["label"] == "模拟中位比分参考"
    assert [item["scoreline"] for item in reference["midband_scorelines"]] == [
        "2-1",
        "3-0",
        "0-0",
    ]
    assert all("probability" not in item for item in reference["midband_scorelines"])
    assert "top_scorelines" not in reference
    assert "high_total" not in reference
    assert "very_high_total" not in reference
    assert "ah_key_scorelines" not in reference


def test_scoreline_reference_returns_none_without_ready_simulation() -> None:
    card = {"pricing_shadow": {"simulation": {"status": "WATCH"}}}
    assert scoreline_reference_from_card(card) is None
