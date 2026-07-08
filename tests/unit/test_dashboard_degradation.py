from __future__ import annotations

from w2.dashboard.degradation import (
    build_api_unavailable_degradation,
    build_dashboard_degradation,
)


def test_degradation_empty_day_is_info() -> None:
    degradation = build_dashboard_degradation(_day_view(counts={"total": 0}))

    assert degradation["state"] == "EMPTY_DAY"
    assert degradation["severity"] == "info"
    assert degradation["reason_code"] == "NO_FIXTURES"
    assert "今日暂无比赛" in degradation["title"]


def test_degradation_provider_budget_exhausted_is_warning() -> None:
    degradation = build_dashboard_degradation(
        _day_view(
            counts={"total": 1, "blocked": 0, "stale": 0},
            freshness={"provider_budget_status": "EXHAUSTED"},
        )
    )

    assert degradation["state"] == "PROVIDER_BUDGET_EXHAUSTED"
    assert degradation["severity"] == "warning"
    assert degradation["reason_code"] == "PROVIDER_BUDGET_EXHAUSTED"
    assert degradation["provider_budget_status"] == "EXHAUSTED"


def test_degradation_all_blocked_day_is_blocked() -> None:
    degradation = build_dashboard_degradation(
        _day_view(counts={"total": 2, "blocked": 2, "stale": 0})
    )

    assert degradation["state"] == "BLOCKED_DAY"
    assert degradation["severity"] == "blocked"
    assert degradation["stale_or_blocked_count"] == 2


def test_degradation_stale_data_is_warning() -> None:
    degradation = build_dashboard_degradation(
        _day_view(counts={"total": 2, "blocked": 0, "stale": 1})
    )

    assert degradation["state"] == "STALE_DATA"
    assert degradation["severity"] == "warning"
    assert "1 场比赛数据陈旧" in degradation["message"]


def test_degradation_refreshing_is_info() -> None:
    degradation = build_dashboard_degradation(
        _day_view(
            counts={"total": 1, "blocked": 0, "stale": 0, "lock_eligible": 1},
            freshness={"refreshing": True},
        )
    )

    assert degradation["state"] == "REFRESHING"
    assert degradation["severity"] == "info"


def test_degradation_no_lock_eligible_is_info_not_blocker() -> None:
    degradation = build_dashboard_degradation(
        _day_view(
            environment="staging",
            counts={
                "total": 1,
                "blocked": 0,
                "stale": 0,
                "lock_eligible": 0,
                "analysis_pick": 1,
            }
        )
    )

    assert degradation["state"] == "NO_LOCK_ELIGIBLE"
    assert degradation["severity"] == "info"
    assert degradation["title"] == "当前无正式可锁推荐"
    assert "不是系统故障" in degradation["message"]
    assert "lock_eligible=true" in degradation["message"]


def test_degradation_no_lock_eligible_copy_uses_production_boundary() -> None:
    degradation = build_dashboard_degradation(
        _day_view(
            environment="production",
            counts={
                "total": 1,
                "blocked": 0,
                "stale": 0,
                "lock_eligible": 0,
                "analysis_pick": 1,
            },
        )
    )

    assert degradation["state"] == "NO_LOCK_ELIGIBLE"
    assert degradation["severity"] == "info"
    assert degradation["title"] == "当前无正式可锁推荐"
    assert "RECOMMEND" in degradation["message"]
    assert "可锁审批候选" not in degradation["message"]


def test_degradation_no_analysis_pick_is_info_not_system_failure() -> None:
    degradation = build_dashboard_degradation(
        _day_view(
            counts={
                "total": 1,
                "blocked": 0,
                "stale": 0,
                "lock_eligible": 1,
                "analysis_pick": 0,
            }
        )
    )

    assert degradation["state"] == "NO_ANALYSIS_PICK"
    assert degradation["severity"] == "info"
    assert "不是系统故障" in degradation["message"]


def test_degradation_ok_when_actionable_counts_exist() -> None:
    degradation = build_dashboard_degradation(
        _day_view(
            counts={
                "total": 2,
                "blocked": 0,
                "stale": 0,
                "lock_eligible": 1,
                "analysis_pick": 1,
            }
        )
    )

    assert degradation["state"] == "OK"
    assert degradation["source"] == "w2.dashboard.degradation.v1"


def test_api_unavailable_degradation_skeleton() -> None:
    degradation = build_api_unavailable_degradation(
        "Dashboard request timed out.",
        next_eval_at="2026-07-05T02:30:00Z",
    )

    assert degradation["state"] == "API_UNAVAILABLE"
    assert degradation["severity"] == "blocked"
    assert degradation["message"] == "Dashboard request timed out."
    assert degradation["next_eval_at"] == "2026-07-05T02:30:00Z"


def _day_view(
    *,
    counts: dict[str, object],
    environment: str = "staging",
    freshness: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "environment": environment,
        "counts": {
            "total": 0,
            "lock_eligible": 0,
            "analysis_pick": 0,
            "stale": 0,
            "blocked": 0,
            **counts,
        },
        "freshness": {
            "provider_budget_status": "OK",
            "next_refresh_tick": "2026-07-05T02:30:00Z",
            **(freshness or {}),
        },
        "cards": [],
    }
