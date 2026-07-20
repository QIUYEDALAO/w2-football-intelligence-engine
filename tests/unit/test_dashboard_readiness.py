from __future__ import annotations

from w2.dashboard.readiness import build_analysis_readiness


def _candidate() -> dict[str, object]:
    return {
        "quote_status": "COMPLETE",
        "analysis_evidence": {
            "status": "COMPLETE",
            "model_probability": {"status": "READY"},
            "comparison": {"analysis_direction_allowed": True},
        },
    }


def test_market_candidates_are_authoritative_for_new_readiness_card() -> None:
    readiness = build_analysis_readiness(
        {
            "competition_id": "allsvenskan",
            "data_readiness": {
                "market_observations": 2,
                "bookmakers": 1,
                "odds_snapshots": 2,
                "xg": True,
                "lineups": False,
            },
            "current_odds": {"ah": {"home": 1.9}},
            "market_candidates": {"ah": _candidate()},
            "markets": [
                {"market": "ASIAN_HANDICAP", "decision": "ANALYSIS_PICK"},
                {"market": "SCORE", "scores": [{"score": "1-0"}]},
            ],
        },
        fixture_status="UPCOMING",
        result=None,
        scoreline_picks=[{"score": "1-0"}],
    )

    assert readiness["status"] == "READY"
    assert "MISSING_MODEL_PROBABILITIES" not in readiness["blockers"]
    assert "MISSING_MARKET_PROBABILITIES" not in readiness["blockers"]
    assert "MISSING_LINEUPS" not in readiness["blockers"]
    assert readiness["advisory_warnings"] == ["LINEUPS_NOT_CONFIRMED_ADVISORY"]


def test_top_five_lineups_missing_remains_strict() -> None:
    readiness = build_analysis_readiness(
        {
            "competition_id": "premier_league",
            "data_readiness": {
                "market_observations": 2,
                "bookmakers": 1,
                "odds_snapshots": 2,
                "xg": True,
                "lineups": False,
            },
            "current_odds": {"ah": {"home": 1.9}},
            "market_candidates": {"ah": _candidate()},
            "markets": [
                {"market": "ASIAN_HANDICAP", "decision": "ANALYSIS_PICK"},
                {"market": "SCORE", "scores": [{"score": "1-0"}]},
            ],
        },
        fixture_status="UPCOMING",
        result=None,
        scoreline_picks=[{"score": "1-0"}],
    )

    assert "MISSING_LINEUPS" in readiness["blockers"]
