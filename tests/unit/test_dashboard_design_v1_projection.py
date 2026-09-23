from datetime import date, datetime

from w2.dashboard.design_v1_projection import performance_summary, review_row


def _row(identity: str, day: str, settlement: str, profit: float) -> dict:
    return {
        "fixture_id": f"fixture-{day}-{identity}",
        "competition_id": "140",
        "kickoff_utc": datetime.fromisoformat(f"{day}T16:00:00+00:00"),
        "selection": "HOME",
        "market": "ASIAN_HANDICAP",
        "exact_line": "-0.25",
        "decimal_odds": 1.9,
        "settlement": settlement,
        "profit_units": profit,
        "calibration_identity": identity,
        "home_team_label": {"display_name": "主队"},
        "away_team_label": {"display_name": "客队"},
    }


def test_performance_summary_never_mixes_old_calibration_identity() -> None:
    rows = [
        _row("v2", "2026-09-23", "WIN", 0.9),
        _row("v1", "2026-09-22", "WIN", 0.9),
        _row("v2", "2026-09-01", "LOSS", -1.0),
    ]
    summary = performance_summary(rows, anchor=date(2026, 9, 23), calibration_identity="v2")
    assert summary["status"] == "AVAILABLE"
    assert summary["last_7_days"] == {
        "match_count": 1, "hit_rate": 1.0, "profit_units": 0.9
    }
    assert summary["last_30_days"]["match_count"] == 2
    assert summary["last_30_days"]["hit_rate"] == 0.5
    assert summary["calibration_identity"] == "v2"


def test_review_row_exposes_design_columns_and_calibration_columns() -> None:
    row = _row("v2", "2026-09-23", "HALF_WIN", 0.45)
    row.update({"filter_decision": "KEPT", "ev_corrected": 0.031, "forward": True, "warmup": False})
    projected = review_row(row, calibrated=True)
    assert projected["date"] == "2026-09-23"  # football day starts at Beijing noon
    assert projected["league"]
    assert projected["match"] == "主队 vs 客队"
    assert projected["recommendation"] == "主 -0.25"
    assert projected["result"] == "HALF_WIN"
    assert projected["calibration_decision"] == "KEPT"
    assert projected["calibrated_ev"] == 0.031
