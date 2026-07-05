from __future__ import annotations

from w2.dashboard import l1_view
from w2.dashboard.l1_view import build_boss_dashboard_l1


def test_l1_counts_are_copied_from_day_view_counts() -> None:
    day_view = _day_view(
        counts={
            "total": 99,
            "lock_eligible": 7,
            "analysis_pick": 6,
            "recommend": 5,
            "watch": 4,
            "not_ready": 3,
            "skip": 2,
            "ready": 1,
            "partial": 8,
            "stale": 9,
            "blocked": 10,
        },
        cards=[_card("watch", decision_tier="WATCH")],
    )

    model = build_boss_dashboard_l1(day_view)

    assert model["counts"] == day_view["counts"]


def test_l1_sorting_uses_lock_then_tier_then_kickoff() -> None:
    model = build_boss_dashboard_l1(
        _day_view(
            cards=[
                _card("not-ready", decision_tier="NOT_READY", kickoff="2026-07-05T01:00:00Z"),
                _card("watch", decision_tier="WATCH", kickoff="2026-07-05T00:30:00Z"),
                _card(
                    "analysis",
                    decision_tier="ANALYSIS_PICK",
                    kickoff="2026-07-05T04:00:00Z",
                ),
                _card(
                    "locked",
                    decision_tier="RECOMMEND",
                    lock_eligible=True,
                    kickoff="2026-07-05T06:00:00Z",
                ),
            ],
        )
    )

    assert [card["fixture_id"] for card in model["cards"]] == [
        "locked",
        "analysis",
        "watch",
        "not-ready",
    ]


def test_l1_analysis_pick_disclaimer_and_production_section_boundary() -> None:
    model = build_boss_dashboard_l1(
        _day_view(
            environment="production",
            counts={
                "total": 2,
                "lock_eligible": 1,
                "analysis_pick": 1,
                "recommend": 1,
                "watch": 0,
                "not_ready": 0,
                "skip": 0,
                "ready": 2,
                "partial": 0,
                "stale": 0,
                "blocked": 0,
            },
            cards=[
                _card(
                    "analysis",
                    decision_tier="ANALYSIS_PICK",
                    lock_eligible=True,
                    pick={"market": "ASIAN_HANDICAP", "selection": "HOME"},
                )
            ],
        )
    )

    analysis_card = model["sections"]["analysis_picks"][0]
    assert analysis_card["disclaimer"] == "分析参考·非稳赢；production 动作需 RECOMMEND"
    assert model["sections"]["lock_eligible_recommendations"] == []


def test_l1_staging_lock_eligible_analysis_pick_enters_approval_section() -> None:
    model = build_boss_dashboard_l1(
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

    lock_section = model["sections"]["lock_eligible_recommendations"]
    assert len(lock_section) == model["counts"]["lock_eligible"] == 1
    assert model["headline"] == "今日有 1 场可锁审批候选"
    assert lock_section[0]["fixture_id"] == "analysis"
    assert lock_section[0]["staging_only"] is True
    assert lock_section[0]["action_label"] == "需要审批"
    assert "分析参考" in lock_section[0]["disclaimer"]
    assert "非稳赢" in lock_section[0]["disclaimer"]
    assert "production 动作需 RECOMMEND" in lock_section[0]["disclaimer"]


def test_l1_production_lock_section_is_recommend_only() -> None:
    model = build_boss_dashboard_l1(
        _day_view(
            environment="production",
            counts={
                "total": 2,
                "lock_eligible": 1,
                "analysis_pick": 1,
                "recommend": 1,
                "watch": 0,
                "not_ready": 0,
                "skip": 0,
                "ready": 2,
                "partial": 0,
                "stale": 0,
                "blocked": 0,
            },
            cards=[
                _card(
                    "analysis",
                    decision_tier="ANALYSIS_PICK",
                    lock_eligible=True,
                ),
                _card(
                    "recommend",
                    decision_tier="RECOMMEND",
                    lock_eligible=True,
                ),
            ],
        )
    )

    assert [card["fixture_id"] for card in model["sections"]["lock_eligible_recommendations"]] == [
        "recommend"
    ]
    assert model["headline"] == "今日有 1 场正式可锁推荐"
    assert model["sections"]["lock_eligible_recommendations"][0]["action_label"] == "正式可锁"


def test_l1_empty_lock_headline_uses_environment_copy() -> None:
    staging = build_boss_dashboard_l1(
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
    production = build_boss_dashboard_l1(
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

    assert staging["headline"] == "当前无可锁审批候选"
    assert production["headline"] == "当前无正式可锁推荐"


def test_l1_handles_no_fixtures_and_provider_budget_exhausted() -> None:
    empty = build_boss_dashboard_l1(_day_view(cards=[]))
    exhausted = build_boss_dashboard_l1(
        _day_view(freshness={"provider_budget_status": "EXHAUSTED"})
    )

    assert empty["headline"] == "今日暂无比赛"
    assert exhausted["headline"] == "provider 预算耗尽，等待下一 tick 或预算恢复"


def test_l1_missing_one_liner_uses_reason_action_fallback() -> None:
    model = build_boss_dashboard_l1(
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

    assert model["sections"]["not_ready"][0]["one_liner"] == (
        "缺少人话解释，显示 reason/action：LINEUPS_PENDING / 等官方首发"
    )


def test_l1_does_not_recalculate_day_view_contract_source() -> None:
    model = build_boss_dashboard_l1(
        _day_view(
            cards=[
                _card(
                    "contract-watch",
                    decision_tier="WATCH",
                    source="decision_contract",
                    pick={"market": "ASIAN_HANDICAP", "selection": "HOME"},
                )
            ]
        )
    )

    card = model["cards"][0]
    assert card["decision_tier"] == "WATCH"
    assert card["source"] == "decision_contract"
    assert model["sections"]["watchlist"][0]["fixture_id"] == "contract-watch"


def test_l1_card_contains_l2_diagnostics_from_day_view_card() -> None:
    model = build_boss_dashboard_l1(
        _day_view(
            cards=[
                {
                    **_card(
                        "diagnostic",
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
                    "data_readiness": {
                        "data_status": "PARTIAL",
                        "reason_code": "LINEUPS_PENDING",
                        "action": "WAIT_FOR_LINEUPS",
                        "missing_fields": ["lineups"],
                        "stale_fields": ["odds"],
                    },
                }
            ]
        )
    )

    diagnostics = model["cards"][0]["diagnostics"]
    assert diagnostics["fixture_id"] == "diagnostic"
    assert diagnostics["lifecycle_status"] == "PRE_MATCH"
    assert diagnostics["missing_fields"] == ["lineups"]
    assert diagnostics["stale_fields"] == ["odds"]
    assert diagnostics["data_readiness_summary"]["reason_code"] == "LINEUPS_PENDING"
    assert diagnostics["card_hash"] == "hash-1"


def test_l1_view_module_does_not_call_strategy_decider() -> None:
    assert "decide_match" not in l1_view.__dict__


def _day_view(
    *,
    environment: str = "staging",
    counts: dict[str, object] | None = None,
    freshness: dict[str, object] | None = None,
    cards: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    actual_cards = [_card("fixture-1")] if cards is None else cards
    return {
        "football_day": "2026-07-05",
        "environment": environment,
        "generated_at": "2026-07-05T00:00:00Z",
        "freshness": freshness or {"provider_budget_status": "OK"},
        "counts": counts
        or {
            "total": len(actual_cards),
            "lock_eligible": 0,
            "analysis_pick": 0,
            "recommend": 0,
            "watch": 0,
            "not_ready": 0,
            "skip": 0,
            "ready": 0,
            "partial": 0,
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
    kickoff: str = "2026-07-05T03:00:00Z",
    one_liner: str | None = "等待更多数据。",
    reason_code: str | None = None,
    action: str | None = None,
    source: str = "decision_contract",
    pick: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff,
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
        "source": source,
    }
