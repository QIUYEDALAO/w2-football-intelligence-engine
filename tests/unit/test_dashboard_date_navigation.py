from __future__ import annotations

from w2.dashboard.date_navigation import build_date_navigation


def test_date_navigation_builds_previous_today_next() -> None:
    navigation = build_date_navigation(
        "2026-07-05",
        as_of="2026-07-05T01:00:00Z",
        has_checkpoint=True,
        checkpoint_key="dashboard:day_view:2026-07-05",
    )

    assert navigation["current_date"] == "2026-07-05"
    assert navigation["previous_date"] == "2026-07-04"
    assert navigation["next_date"] == "2026-07-06"
    assert navigation["today_date"] == "2026-07-05"
    assert navigation["is_today"] is True
    assert navigation["can_go_previous"] is True
    assert navigation["can_go_next"] is True
    assert navigation["has_checkpoint"] is True
    assert navigation["fallback_mode"] == "checkpoint"
    assert navigation["warning"] is None


def test_date_navigation_future_day_warns() -> None:
    navigation = build_date_navigation("2026-07-06", as_of="2026-07-05T01:00:00Z")

    assert navigation["is_today"] is False
    assert navigation["fallback_mode"] == "future_day"
    assert navigation["warning"] == "未来日期可能没有完整数据"


def test_date_navigation_read_model_fallback_when_checkpoint_absent() -> None:
    navigation = build_date_navigation("2026-07-04", as_of="2026-07-05T01:00:00Z")

    assert navigation["has_checkpoint"] is False
    assert navigation["fallback_mode"] == "read_model"
    assert navigation["warning"] == "未发现 day_view checkpoint，使用只读 read-model fallback"


def test_date_navigation_respects_min_max_bounds() -> None:
    navigation = build_date_navigation(
        "2026-07-05",
        as_of="2026-07-05T01:00:00Z",
        min_date="2026-07-05",
        max_date="2026-07-05",
    )

    assert navigation["can_go_previous"] is False
    assert navigation["can_go_next"] is False
    assert navigation["source"] == "w2.dashboard.date_navigation.v1"
