from __future__ import annotations

from datetime import UTC, datetime

from w2.dashboard import day_view
from w2.dashboard.day_view import build_dashboard_day_view


def test_day_view_projects_decision_contract_cards_and_legacy_fallback() -> None:
    payload = {
        "generated_at": datetime(2026, 7, 5, 1, 2, tzinfo=UTC),
        "date": "2026-07-05",
        "selected_football_day": "2026-07-05",
        "timezone": "Asia/Shanghai",
        "window": "today",
        "version": {"api_git_sha": "sha"},
        "recommendations": [{"fixture_id": "ignored-by-counts"}],
        "all": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-05T10:00:00Z",
                "home_team_name": "Home",
                "away_team_name": "Away",
                "decision_tier": "ANALYSIS_PICK",
                "data_status": "READY",
                "lifecycle_status": "DRAFT",
                "outcome_tracked": True,
                "lock_eligible": True,
                "recommendation_id": "rec-1",
                "provider_budget_status": "OK",
                "probability_source": "MARKET_DEVIG",
                "model_market_divergence": {
                    "status": "READY",
                    "magnitude": 0.12,
                },
                "current_odds": {
                    "ah": {
                        "home_line": "-0.25",
                        "home_price": 1.95,
                        "away_line": "0.25",
                        "away_price": 1.95,
                    },
                    "ou": {"line": "2.5", "over_price": 1.91, "under_price": 1.93},
                },
                "market_strip": [
                    {
                        "market": "ASIAN_HANDICAP",
                        "decision": "WATCH",
                        "reason": "跟随市场 · 仅参考",
                    }
                ],
                "data_refresh": {
                    "odds_status": "READY",
                    "lineups_status": "PROVIDER_EMPTY",
                    "xg_status": "INSUFFICIENT_HISTORY",
                },
                "pick": {
                    "market": "ASIAN_HANDICAP",
                    "selection": "HOME_AH",
                    "line": "-0.25",
                    "odds": "1.95",
                    "disclaimer": "分析参考·非稳赢；production 动作需 RECOMMEND",
                },
                "decision_contract": {
                    "decision_tier": "WATCH",
                    "data_status": "BLOCKED",
                },
            },
            {
                "fixture_id": "fixture-2",
                "kickoff_utc": "2026-07-05T12:00:00Z",
                "formal_recommendation": True,
                "recommendation_id": "legacy-rec",
            },
        ],
    }

    view = build_dashboard_day_view(payload, environment="staging")

    assert view["football_day"] == "2026-07-05"
    assert view["checkpoint_key"] == "dashboard:day_view:2026-07-05"
    assert view["would_write_checkpoint"] is False
    assert view["provider_calls"] == 0
    assert view["db_writes"] == 0
    assert view["environment_policy"]["environment"] == "staging"
    assert view["environment_policy"]["policy_version"] == "w2.environment_policy.v1"
    assert view["environment_policy"]["lock_policy"]["name"] == "staging_B"
    assert view["environment_policy"]["lock_policy"]["production_action_allowed"] is False
    assert view["counts"]["total"] == 2
    assert view["counts"]["analysis_pick"] == 0
    assert view["counts"]["recommend"] == 0
    assert view["counts"]["watch"] == 2
    assert view["counts"]["not_ready"] == 0
    assert view["counts"]["skip"] == 0
    assert view["counts"]["ready"] == 0
    assert view["counts"]["partial"] == 1
    assert view["counts"]["stale"] == 0
    assert view["counts"]["blocked"] == 1
    assert view["counts"]["by_decision_tier"]["ANALYSIS_PICK"] == 0
    assert view["counts"]["by_decision_tier"]["WATCH"] == 2
    assert view["counts"]["by_data_status"]["READY"] == 0
    assert view["counts"]["by_data_status"]["BLOCKED"] == 1
    assert view["counts"]["legacy_fallback"] == 1
    assert view["freshness"]["provider_budget_status"] == "OK"
    assert view["freshness"]["data_status_summary"] == view["counts"]["by_data_status"]
    assert view["navigation"]["current_date"] == "2026-07-05"
    assert view["navigation"]["previous_date"] == "2026-07-04"
    assert view["navigation"]["next_date"] == "2026-07-06"
    assert view["navigation"]["today_date"] == "2026-07-05"
    assert view["navigation"]["is_today"] is True
    assert view["navigation"]["has_checkpoint"] is False
    assert view["navigation"]["checkpoint_key"] == "dashboard:day_view:2026-07-05"
    assert view["navigation"]["fallback_mode"] == "read_model"
    assert view["navigation"]["warning"] == (
        "未发现 day_view checkpoint，使用只读 read-model fallback"
    )
    assert view["degradation"]["state"] == "NO_LOCK_ELIGIBLE"
    assert view["degradation"]["source"] == "w2.dashboard.degradation.v1"

    contract_card = view["cards"][0]
    assert contract_card["source"] == "decision_contract"
    assert contract_card["decision_tier"] == "WATCH"
    assert contract_card["data_status"] == "BLOCKED"
    assert contract_card["current_odds"] == {}
    assert contract_card["market_probabilities"] == {}
    assert contract_card["market_strip"][0]["market"] == "ASIAN_HANDICAP"
    assert contract_card["data_refresh"]["odds_status"] == "READY"
    assert contract_card["probability_source"] == "MARKET_DEVIG"
    assert contract_card["model_market_divergence"]["magnitude"] == 0.12
    assert contract_card["pick"] is None

    legacy_card = view["cards"][1]
    assert legacy_card["source"] == "legacy_fallback"
    assert legacy_card["decision_tier"] == "WATCH"
    assert legacy_card["lock_eligible"] is False
    assert legacy_card["outcome_tracked"] is False
    assert legacy_card["recommendation_id"] is None


def test_day_view_counts_are_aggregated_from_cards_only() -> None:
    payload = {
        "generated_at": "2026-07-05T00:00:00Z",
        "date": "2026-07-05",
        "selected_football_day": "2026-07-05",
        "recommendations": [
            {"decision_tier": "RECOMMEND", "lock_eligible": True},
            {"decision_tier": "RECOMMEND", "lock_eligible": True},
        ],
        "upcoming": [{"decision_tier": "WATCH"}],
        "finished": [{"data_status": "BLOCKED"}],
        "all": [
            {
                "fixture_id": "fixture-1",
                "decision_tier": "WATCH",
                "data_status": "PARTIAL",
                "lifecycle_status": "DRAFT",
                "outcome_tracked": False,
                "lock_eligible": False,
                "non_pick": {
                    "reason_code": "LINEUPS_PENDING",
                    "reason_human": "首发未出",
                    "action": "等官方首发",
                    "next_eval_at": None,
                },
            }
        ],
    }

    view = build_dashboard_day_view(payload, environment="staging")

    assert view["counts"]["total"] == 1
    assert view["counts"]["lock_eligible"] == 0
    assert view["counts"]["analysis_pick"] == 0
    assert view["counts"]["recommend"] == 0
    assert view["counts"]["watch"] == 1
    assert view["counts"]["not_ready"] == 0
    assert view["counts"]["skip"] == 0
    assert view["counts"]["ready"] == 0
    assert view["counts"]["partial"] == 1
    assert view["counts"]["stale"] == 0
    assert view["counts"]["blocked"] == 0
    assert view["counts"]["by_decision_tier"]["RECOMMEND"] == 0
    assert view["counts"]["by_decision_tier"]["WATCH"] == 1
    assert view["counts"]["by_data_status"]["BLOCKED"] == 0
    assert view["freshness"]["staleness"]["blocked_cards"] == 0
    assert view["degradation"]["state"] == "NO_LOCK_ELIGIBLE"
    assert view["degradation"]["severity"] == "info"


def test_day_view_excludes_started_or_finished_matches_from_l1() -> None:
    payload = {
        "generated_at": "2026-07-05T08:00:00Z",
        "date": "2026-07-05",
        "selected_football_day": "2026-07-05",
        "all": [
            {
                "fixture_id": "finished",
                "kickoff_utc": "2026-07-05T06:00:00Z",
                "status": "FT",
                "decision_tier": "ANALYSIS_PICK",
                "data_status": "READY",
                "lifecycle_status": "DRAFT",
            },
            {
                "fixture_id": "future",
                "kickoff_utc": "2026-07-05T10:00:00Z",
                "status": "NS",
                "decision_tier": "WATCH",
                "data_status": "PARTIAL",
                "lifecycle_status": "DRAFT",
                "non_pick": {
                    "reason_code": "LINEUPS_PENDING",
                    "reason_human": "首发未出",
                    "action": "等官方首发",
                },
            },
        ],
    }

    view = build_dashboard_day_view(payload, environment="staging")

    assert [card["fixture_id"] for card in view["cards"]] == ["future"]
    assert view["counts"]["total"] == 1
    assert view["counts"]["analysis_pick"] == 0
    assert view["counts"]["watch"] == 1


def test_day_view_production_includes_production_environment_policy() -> None:
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-07-05T00:00:00Z",
            "date": "2026-07-05",
            "selected_football_day": "2026-07-05",
            "all": [],
        },
        environment="production",
    )

    assert view["environment_policy"]["lock_policy"]["name"] == "production_B"
    assert view["environment_policy"]["lock_policy"]["lock_eligible_policy"] == "recommend_only"


def test_day_view_degradation_reflects_refreshing_payload() -> None:
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-07-05T00:00:00Z",
            "date": "2026-07-05",
            "selected_football_day": "2026-07-05",
            "refreshing": True,
            "all": [
                {
                    "fixture_id": "fixture-1",
                    "decision_tier": "ANALYSIS_PICK",
                    "data_status": "READY",
                    "lifecycle_status": "DRAFT",
                    "lock_eligible": True,
                }
            ],
        },
        environment="staging",
    )

    assert view["freshness"]["refreshing"] is True
    assert view["degradation"]["state"] == "REFRESHING"


def test_day_view_module_does_not_call_strategy_decider() -> None:
    assert "decide_match" not in day_view.__dict__
