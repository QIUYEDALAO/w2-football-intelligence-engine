from __future__ import annotations

from scripts.debug_w2_formal_recommendations import build_report


def _formal_card(
    *,
    selection: str = "AWAY_AH",
    home_line: float = -0.25,
    reverse_factor_value: bool = False,
    score_summary: dict[str, float] | None = None,
    simulations: int = 10_000,
) -> dict[str, object]:
    score_summary = score_summary or {"home_win": 0.38, "draw": 0.26, "away_win": 0.36}
    return {
        "fixture_id": "fixture-1",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "formal_recommendation": True,
        "recommendation": {
            "market": "ASIAN_HANDICAP",
            "selection": selection,
            "selection_label_cn": "Away 受让" if selection == "AWAY_AH" else "Home 受让",
            "line": "0.25",
            "odds": "2.05",
            "expected_value": 0.12,
            "risk_adjusted_ev": "12pct",
            "model_probability": 0.48,
            "devig_probability": 0.47,
            "reverse_factor_value": reverse_factor_value,
            "ah_settlement_distribution": {
                "WIN": 0.35,
                "HALF_WIN": 0.26,
                "PUSH": 0.0,
                "HALF_LOSS": 0.0,
                "LOSS": 0.39,
            },
        },
        "pricing_shadow": {
            "canonical_ah_market": {
                "home_line": home_line,
                "away_line": -home_line,
                "home_price": 1.85,
                "away_price": 2.05,
                "source": "market_timeline_snapshots",
                "validation_status": "READY",
                "blocker": None,
            },
            "simulation_status": "READY",
            "simulation": {
                "status": "READY",
                "model_version": "w2.formal.mc_poisson.v1",
                "calibration_version": "w2.formal.lambda_baseline_prior.v1",
                "calibration_status": "BASELINE_PRIOR",
                "lambda_home": 1.4,
                "lambda_away": 1.3,
                "simulations": simulations,
                "seed": 123,
                "scoreline_picks": [
                    {
                        "scoreline": "1-1",
                        "home_goals": 1,
                        "away_goals": 1,
                        "probability": 0.12,
                    }
                ],
                "score_matrix_summary": score_summary,
            },
        },
        "scoreline_readiness": {
            "status": "READY",
            "source": "formal_simulation",
            "model_version": "w2.formal.mc_poisson.v1",
        },
        "scoreline_picks": [{"scoreline": "1-1", "home_goals": 1, "away_goals": 1}],
    }


def test_report_counts_formal_underdog_bias_and_10000_simulation_evidence() -> None:
    report = build_report(
        {"all": [_formal_card(score_summary={"home_win": 0.31, "draw": 0.38, "away_win": 0.31})]}
    )

    assert report["summary"]["formal_count"] == 1
    assert report["summary"]["formal_selection_counts"] == {"AWAY_AH": 1}
    assert report["summary"]["formal_underdog_count"] == 1
    assert report["summary"]["simulation_10000_evidence_count"] == 1
    row = report["formal_explanations"][0]
    assert row["simulation_evidence"]["has_10000_simulation_evidence"] is True
    assert row["simulation_evidence"]["simulations"] == 10_000
    assert row["market"]["selected_side_line"] == 0.25
    assert "比分只作为模拟参考" in row["explanation_cn"]
    assert row["findings"] == []


def test_reverse_scoreline_without_reverse_flag_is_flagged() -> None:
    report = build_report(
        {
            "all": [
                _formal_card(
                    selection="AWAY_AH",
                    home_line=-1.75,
                    reverse_factor_value=False,
                    score_summary={"home_win": 0.62, "draw": 0.2, "away_win": 0.18},
                )
            ]
        }
    )

    row = report["formal_explanations"][0]
    assert row["scoreline_alignment"]["status"] == "REVERSE_VALUE"
    assert "REVERSE_SCORELINE_WITHOUT_REVERSE_FACTOR_FLAG" in row["findings"]
    assert "REVERSE_SCORELINE_WITHOUT_REVERSE_FACTOR_FLAG" in report["summary"]["audit_findings"]


def test_tiny_scoreline_noise_does_not_trigger_reverse_finding() -> None:
    report = build_report(
        {
            "all": [
                _formal_card(
                    selection="AWAY_AH",
                    home_line=-0.25,
                    reverse_factor_value=False,
                    score_summary={"home_win": 0.371, "draw": 0.28, "away_win": 0.349},
                )
            ]
        }
    )

    row = report["formal_explanations"][0]
    assert row["scoreline_alignment"]["status"] == "SPREAD_VALUE_OVER_DRAWISH_GAME"
    assert "REVERSE_SCORELINE_WITHOUT_REVERSE_FACTOR_FLAG" not in row["findings"]
    assert (
        "REVERSE_SCORELINE_WITHOUT_REVERSE_FACTOR_FLAG"
        not in report["summary"]["audit_findings"]
    )


def test_real_scoreline_reverse_still_requires_reverse_flag() -> None:
    report = build_report(
        {
            "all": [
                _formal_card(
                    selection="AWAY_AH",
                    home_line=-0.25,
                    reverse_factor_value=False,
                    score_summary={"home_win": 0.3838, "draw": 0.2647, "away_win": 0.3515},
                )
            ]
        }
    )

    row = report["formal_explanations"][0]
    assert row["scoreline_alignment"]["status"] == "REVERSE_VALUE"
    assert "REVERSE_SCORELINE_WITHOUT_REVERSE_FACTOR_FLAG" in row["findings"]


def test_missing_simulation_count_is_flagged() -> None:
    report = build_report({"all": [_formal_card(simulations=5000)]})

    row = report["formal_explanations"][0]
    assert row["simulation_evidence"]["has_10000_simulation_evidence"] is False
    assert "MISSING_10000_SIMULATION_EVIDENCE" in row["findings"]
