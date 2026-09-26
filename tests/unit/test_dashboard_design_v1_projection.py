from datetime import date, datetime
from decimal import Decimal

from w2.dashboard.design_v1_projection import (
    performance_summary,
    replay_display_row,
    review_row,
    today_recommendations,
)
from w2.domain.profit import rebate_units


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
        _row("v2", "2026-08-01", "WIN", 0.5),
        _row("v2", "2026-08-02", "PENDING", 12.0),
    ]
    summary = performance_summary(rows, anchor=date(2026, 9, 23), calibration_identity="v2")
    assert summary["status"] == "AVAILABLE"
    assert summary["last_7_days"] == {
        "match_count": 1, "hit_rate": 1.0, "profit_units": 0.9
    }
    assert summary["last_30_days"]["match_count"] == 2
    assert summary["last_30_days"]["hit_rate"] == 0.5
    assert summary["total_profit_units"] == 0.4
    assert summary["total_profit_units_with_rebate"] == 0.46
    assert summary["calibration_identity"] == "v2"


def test_rebate_uses_absolute_profit_per_settled_bet() -> None:
    assert rebate_units([1.0]) == Decimal("0.025")  # WIN
    assert rebate_units([-1.0]) == Decimal("0.025")  # LOSS
    assert rebate_units([0.0]) == Decimal("0")  # PUSH
    assert rebate_units([0.45]) == Decimal("0.01125")  # HALF_WIN
    assert rebate_units([-0.5]) == Decimal("0.0125")  # HALF_LOSS
    assert rebate_units([1.0, -1.0, 0.0, 0.45, -0.5]) == Decimal("0.07375")


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
    assert projected["display_state"] == "RECOMMENDATION"


def test_settled_totals_review_row_preserves_original_recommendation() -> None:
    row = _row("v2", "2026-09-23", "WIN", 0.9)
    row.update({"market": "TOTALS", "selection": "OVER", "exact_line": "2.5"})

    projected = review_row(row)

    # 历史已结算 TOTALS 行保留原始方向/盘口，不再覆盖为市场观点。
    assert projected["display_state"] == "RECOMMENDATION"
    assert projected["display_notice"] is None
    assert projected["recommendation"] == "大 2.5"


def test_pending_totals_review_row_is_market_view() -> None:
    row = _row("v2", "2026-09-23", "PENDING", 0.0)
    row.update({"market": "TOTALS", "selection": "OVER", "exact_line": "2.5"})

    projected = review_row(row)

    # 今日/未来新产出（未结算）的 TOTALS 仍是市场观点。
    assert projected["display_state"] == "MARKET_VIEW"
    assert projected["display_notice"] == "市场观点展示 · 不作投注建议"


def test_today_recommendations_excludes_historical_totals_rows() -> None:
    totals = _row("v2", "2026-09-23", "WIN", 0.9)
    totals.update({"market": "TOTALS", "selection": "OVER", "exact_line": "2.5"})
    ah = _row("v2", "2026-09-23", "WIN", 0.9)
    rows = today_recommendations(
        [], [totals, ah], anchor=date(2026, 9, 23), calibration_identity="v2"
    )

    assert len(rows) == 1
    assert rows[0]["market"] == "让球"


def test_today_recommendations_keep_persisted_settlement_and_quote() -> None:
    sample = _row("v2", "2026-09-23", "HALF_WIN", 0.45)
    sample["current_ev"] = 0.08
    match = {
        "fixture_id": sample["fixture_id"],
        "lifecycle_status": "WITHDRAWN",
        "reason_code": "QUOTE_EXPIRED",
        "pick": {"market": "ASIAN_HANDICAP", "selection": "AWAY"},
    }

    rows = today_recommendations(
        [match], [sample], anchor=date(2026, 9, 23), calibration_identity="v2"
    )

    assert len(rows) == 1
    assert rows[0]["status"] == "settled"
    assert rows[0]["selection"] == "主"
    assert rows[0]["odds"] == 1.9
    assert rows[0]["ev"] == 0.08
    assert rows[0]["result"] == "HALF_WIN"


def test_replay_display_counts_unique_evaluation_timepoints() -> None:
    match = {
        "competition_id": "140",
        "home_team_label": {"display_name": "主队"},
        "away_team_label": {"display_name": "客队"},
    }
    versions = [
        {"evaluated_at": "2026-09-23T10:00:00Z", "state": "NO_EDGE_CURRENT"},
        {"evaluated_at": "2026-09-23T10:00:00Z", "state": "NO_EDGE_CURRENT"},
        {"evaluated_at": "2026-09-23T11:00:00Z", "state": "ANALYSIS_PICK_ACTIVE",
         "market": "TOTALS", "selection": "OVER", "exact_line": "2.5",
         "decimal_odds": 1.93},
    ]

    row = replay_display_row(match, versions)

    assert row["evaluation_count"] == 2
    assert row["final_recommendation"] == "大小球 大 2.5 @1.93"


def test_replay_totals_keeps_original_final_recommendation() -> None:
    row = replay_display_row(
        {"competition_id": "140", "home_team_name": "主队", "away_team_name": "客队"},
        [{"evaluated_at": "2026-09-23T11:00:00Z", "state": "ANALYSIS_PICK_ACTIVE",
          "market": "TOTALS", "selection": "OVER", "exact_line": "2.5",
          "decimal_odds": 1.93}],
    )

    # 历史 TOTALS 候选（裁决 T1 前）保留原始方向/盘口，不再是市场观点。
    assert row["final_display_state"] == "RECOMMENDATION"
    assert row["display_notice"] is None
    assert row["final_recommendation"] == "大小球 大 2.5 @1.93"
