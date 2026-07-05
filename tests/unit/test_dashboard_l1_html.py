from __future__ import annotations

import pytest

from w2.dashboard import l1_html
from w2.dashboard.l1_html import render_boss_dashboard_l1_html


def test_l1_html_renders_first_screen_counts_and_no_formal_empty_state() -> None:
    html = render_boss_dashboard_l1_html(
        _day_view(
            counts={
                "total": 1,
                "lock_eligible": 0,
                "analysis_pick": 1,
                "recommend": 0,
                "watch": 0,
                "not_ready": 0,
                "skip": 0,
                "ready": 1,
                "partial": 0,
                "stale": 0,
                "blocked": 0,
            },
            cards=[
                _card(
                    "analysis",
                    decision_tier="ANALYSIS_PICK",
                    data_status="READY",
                    pick={"market": "ASIAN_HANDICAP", "selection": "HOME", "line": "-0.25"},
                )
            ],
        )
    )

    assert "<!doctype html>" in html
    assert "W2 今日比赛日" in html
    assert "正式可锁" in html
    assert "分析推荐" in html
    assert "当前无可锁审批候选" in html
    assert "分析参考·非稳赢；production 动作需 RECOMMEND" in html


def test_l1_html_staging_lock_eligible_analysis_pick_is_staging_only_approval() -> None:
    html = render_boss_dashboard_l1_html(
        _day_view(
            environment="staging",
            counts={
                "total": 1,
                "lock_eligible": 1,
                "analysis_pick": 1,
                "recommend": 0,
                "watch": 0,
                "not_ready": 0,
                "skip": 0,
                "ready": 1,
                "partial": 0,
                "stale": 0,
                "blocked": 0,
            },
            cards=[
                _card(
                    "analysis",
                    decision_tier="ANALYSIS_PICK",
                    data_status="READY",
                    lock_eligible=True,
                    pick={"market": "ASIAN_HANDICAP", "selection": "HOME"},
                )
            ],
        )
    )

    lock_section = html.split("可锁审批 / 正式可锁", 1)[1].split("分析推荐", 1)[0]
    header = html.split("可锁审批 / 正式可锁", 1)[0]
    assert "可锁审批" in header
    assert "正式可锁</span>" not in header
    assert "今日有 1 场可锁审批候选" in html
    assert "Home analysis vs Away analysis" in lock_section
    assert "staging-only" in lock_section
    assert "需要审批" in lock_section
    assert "分析参考" in lock_section
    assert "非稳赢" in lock_section
    assert "production 动作需 RECOMMEND" in lock_section


def test_l1_html_production_analysis_pick_not_in_lock_section() -> None:
    html = render_boss_dashboard_l1_html(
        _day_view(
            environment="production",
            counts={
                "total": 1,
                "lock_eligible": 1,
                "analysis_pick": 1,
                "recommend": 0,
                "watch": 0,
                "not_ready": 0,
                "skip": 0,
                "ready": 1,
                "partial": 0,
                "stale": 0,
                "blocked": 0,
            },
            cards=[
                _card(
                    "analysis",
                    decision_tier="ANALYSIS_PICK",
                    data_status="READY",
                    lock_eligible=True,
                )
            ],
        )
    )

    lock_section = html.split("可锁审批 / 正式可锁", 1)[1].split("分析推荐", 1)[0]
    header = html.split("可锁审批 / 正式可锁", 1)[0]
    assert "正式可锁" in header
    assert "Home analysis vs Away analysis" not in lock_section
    assert "Home analysis vs Away analysis" in html.split("分析推荐", 1)[1]


def test_l1_html_empty_lock_notice_uses_environment_copy() -> None:
    staging_html = render_boss_dashboard_l1_html(
        _day_view(
            environment="staging",
            counts={
                "total": 1,
                "lock_eligible": 0,
                "analysis_pick": 0,
                "recommend": 0,
                "watch": 1,
                "not_ready": 0,
                "skip": 0,
                "ready": 0,
                "partial": 1,
                "stale": 0,
                "blocked": 0,
            },
            cards=[_card("watch", decision_tier="WATCH")],
        )
    )
    production_html = render_boss_dashboard_l1_html(
        _day_view(
            environment="production",
            counts={
                "total": 1,
                "lock_eligible": 0,
                "analysis_pick": 0,
                "recommend": 0,
                "watch": 1,
                "not_ready": 0,
                "skip": 0,
                "ready": 0,
                "partial": 1,
                "stale": 0,
                "blocked": 0,
            },
            cards=[_card("watch", decision_tier="WATCH")],
        )
    )

    assert "当前无可锁审批候选" in staging_html
    assert "当前无正式可锁推荐" not in staging_html
    assert "当前无正式可锁推荐" in production_html


def test_l1_html_no_fixtures_and_provider_budget_exhausted_degrade() -> None:
    empty_html = render_boss_dashboard_l1_html(
        _day_view(
            cards=[],
            degradation={
                "state": "EMPTY_DAY",
                "title": "今日暂无比赛",
                "message": "当前比赛日没有可展示 fixture。",
                "action": "等待下一次刷新或切换比赛日。",
            },
        )
    )
    exhausted_html = render_boss_dashboard_l1_html(
        _day_view(
            freshness={"provider_budget_status": "EXHAUSTED"},
            degradation={
                "state": "PROVIDER_BUDGET_EXHAUSTED",
                "title": "provider 预算耗尽",
                "message": "当前 provider 预算已耗尽，页面保留现有只读结果。",
                "action": "等待下一 tick 或预算恢复。",
            },
        )
    )

    assert "今日暂无比赛" in empty_html
    assert "当前比赛日没有可展示 fixture。" in empty_html
    assert "provider 预算耗尽，等待下一 tick 或预算恢复" in exhausted_html
    assert "当前 provider 预算已耗尽" in exhausted_html


def test_l1_html_renders_stale_and_refreshing_degradation_copy() -> None:
    stale_html = render_boss_dashboard_l1_html(
        _day_view(
            counts={
                "total": 1,
                "lock_eligible": 1,
                "analysis_pick": 1,
                "recommend": 0,
                "watch": 0,
                "not_ready": 0,
                "skip": 0,
                "ready": 0,
                "partial": 0,
                "stale": 1,
                "blocked": 0,
            },
            cards=[_card("stale", decision_tier="ANALYSIS_PICK", data_status="STALE")],
            degradation={
                "state": "STALE_DATA",
                "title": "存在陈旧数据",
                "message": "当前有 1 场比赛数据陈旧，建议等待刷新后再审批。",
                "action": "等待下一次刷新完成。",
            },
        )
    )
    refreshing_html = render_boss_dashboard_l1_html(
        _day_view(
            degradation={
                "state": "REFRESHING",
                "title": "刷新中",
                "message": "比赛日数据正在刷新，当前页面可能短暂滞后。",
                "action": "刷新完成后自动查看最新结果。",
            }
        )
    )

    assert "存在陈旧数据" in stale_html
    assert "建议等待刷新后再审批" in stale_html
    assert "刷新中" in refreshing_html
    assert "当前页面可能短暂滞后" in refreshing_html


def test_l1_html_keeps_diagnostics_out_of_first_screen() -> None:
    html = render_boss_dashboard_l1_html(
        _day_view(
            cards=[
                {
                    **_card("watch"),
                    "raw_payload": {"provider_request_hash": "hash"},
                    "lambda_home": 1.2,
                    "blocker_codes": ["X"],
                }
            ]
        )
    )

    assert "raw payload" not in html
    assert "provider_request_hash" not in html
    assert "lambda" not in html
    assert "blocker_codes" not in html


def test_l1_html_renders_collapsed_l2_diagnostics() -> None:
    html = render_boss_dashboard_l1_html(
        _day_view(
            cards=[
                {
                    **_card(
                        "watch",
                        decision_tier="WATCH",
                        data_status="PARTIAL",
                        reason_code="LINEUPS_PENDING",
                        action="WAIT_FOR_LINEUPS",
                    ),
                    "lifecycle_status": "PRE_MATCH",
                    "outcome_tracked": False,
                    "provider_budget_status": "OK",
                    "missing_fields": ["lineups"],
                    "stale_fields": ["odds"],
                    "card_hash": "hash-1",
                    "pick": {
                        "market": "ASIAN_HANDICAP",
                        "selection": "HOME",
                        "line": "-0.25",
                        "odds": "1.91",
                    },
                }
            ]
        )
    )

    assert "<details><summary>技术诊断</summary>" in html
    assert "lifecycle_status" in html
    assert "PRE_MATCH" in html
    assert "missing_fields" in html
    assert "lineups" in html
    assert "stale_fields" in html
    assert "odds" in html
    assert "provider_budget_status" in html
    assert "card_hash" in html
    assert "hash-1" in html
    assert "market_snapshot" in html


def test_l1_html_renders_degradation_diagnostics_source_and_reason() -> None:
    html = render_boss_dashboard_l1_html(
        _day_view(
            degradation={
                "state": "NO_LOCK_ELIGIBLE",
                "title": "当前无可锁审批候选",
                "message": "今天暂时没有 lock_eligible=true 的卡片，这不是系统故障。",
                "action": "继续观察分析推荐和未就绪原因。",
                "reason_code": "NO_LOCK_ELIGIBLE",
                "source": "w2.dashboard.degradation.v1",
            }
        )
    )

    assert "今天暂时没有 lock_eligible=true 的卡片，这不是系统故障。" in html
    assert "degradation_source" in html
    assert "w2.dashboard.degradation.v1" in html
    assert "degradation_reason_code" in html
    assert "NO_LOCK_ELIGIBLE" in html


def test_l1_html_no_lock_degradation_copy_respects_environment() -> None:
    production_html = render_boss_dashboard_l1_html(
        _day_view(
            environment="production",
            degradation={
                "state": "NO_LOCK_ELIGIBLE",
                "title": "当前无正式可锁推荐",
                "message": "今天暂时没有 production 正式可锁推荐，这不是系统故障。",
                "action": "继续观察分析推荐、观察名单和未就绪原因。",
            },
        )
    )
    staging_html = render_boss_dashboard_l1_html(
        _day_view(
            environment="staging",
            degradation={
                "state": "NO_LOCK_ELIGIBLE",
                "title": "当前无可锁审批候选",
                "message": "今天暂时没有 lock_eligible=true 的卡片，这不是系统故障。",
                "action": "继续观察分析推荐和未就绪原因。",
            },
        )
    )

    assert "当前无正式可锁推荐" in production_html
    assert "当前无可锁审批候选" not in production_html
    assert "当前无可锁审批候选" in staging_html


def test_l1_html_forbidden_words_guard() -> None:
    safe_html = render_boss_dashboard_l1_html(
        _day_view(cards=[_card("analysis", decision_tier="ANALYSIS_PICK")])
    )
    assert "必中" not in safe_html
    assert "保证" not in safe_html
    assert "包赢" not in safe_html
    assert "稳赢" not in safe_html.replace("非稳赢", "")

    with pytest.raises(ValueError, match="forbidden term"):
        render_boss_dashboard_l1_html(_day_view(cards=[_card("bad", one_liner="包赢")] ))


def test_l1_html_uses_reason_action_for_missing_one_liner() -> None:
    html = render_boss_dashboard_l1_html(
        _day_view(
            cards=[
                _card(
                    "not-ready",
                    decision_tier="NOT_READY",
                    one_liner=None,
                    reason_code="LINEUPS_PENDING",
                    action="等官方首发",
                )
            ]
        )
    )

    assert "缺少人话解释，显示 reason/action：LINEUPS_PENDING / 等官方首发" in html


def test_l1_html_module_does_not_call_strategy_decider() -> None:
    assert "decide_match" not in l1_html.__dict__


def _day_view(
    *,
    environment: str = "staging",
    counts: dict[str, object] | None = None,
    freshness: dict[str, object] | None = None,
    cards: list[dict[str, object]] | None = None,
    degradation: dict[str, object] | None = None,
) -> dict[str, object]:
    actual_cards = [] if cards == [] else cards or [_card("watch")]
    return {
        "football_day": "2026-07-05",
        "environment": environment,
        "generated_at": "2026-07-05T00:00:00Z",
        "freshness": {
            "last_refresh": "2026-07-05T00:00:00Z",
            "next_refresh_tick": "2026-07-05T00:30:00Z",
            "provider_budget_status": "OK",
            **(freshness or {}),
        },
        "degradation": degradation or {},
        "counts": counts
        or {
            "total": len(actual_cards),
            "lock_eligible": 0,
            "analysis_pick": 0,
            "recommend": 0,
            "watch": len(actual_cards),
            "not_ready": 0,
            "skip": 0,
            "ready": 0,
            "partial": len(actual_cards),
            "stale": 0,
            "blocked": 0,
        },
        "cards": actual_cards,
    }


def _card(
    fixture_id: str,
    *,
    decision_tier: str = "WATCH",
    data_status: str = "PARTIAL",
    lock_eligible: bool = False,
    one_liner: str | None = "等待更多数据。",
    reason_code: str | None = None,
    action: str | None = None,
    pick: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": "2026-07-05T03:00:00Z",
        "home_team_name": f"Home {fixture_id}",
        "away_team_name": f"Away {fixture_id}",
        "decision_tier": decision_tier,
        "data_status": data_status,
        "lock_eligible": lock_eligible,
        "recommendation_id": f"rec-{fixture_id}",
        "one_liner": one_liner,
        "reason_code": reason_code,
        "action": action,
        "next_eval_at": "2026-07-05T02:30:00Z",
        "pick": pick or {},
        "source": "decision_contract",
    }
