from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.dashboard import day_view
from w2.dashboard.day_view import build_dashboard_day_view


class _ActiveAndArchivedMatchdayRepository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            _matchday_payload("active", "chinese_super_league"),
            _matchday_payload("archived", "world_cup_2026"),
        ]


def _matchday_payload(fixture_id: str, competition_id: str) -> dict[str, Any]:
    return {
        "fixture": {
            "fixture_id": fixture_id,
            "competition_id": competition_id,
            "competition_name": competition_id,
            "kickoff_utc": "2026-07-12T10:00:00Z",
            "status": "NS",
            "home_team_id": "home",
            "away_team_id": "away",
        },
        "card": {},
        "temporal": {},
        "integrity": {},
    }


def test_runtime_matchday_rows_exclude_archived_world_cup(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    service = ReadModelService(repository=cast(Any, _ActiveAndArchivedMatchdayRepository()))

    rows = service._all_matchday_rows()

    assert [row["fixture_id"] for row in rows] == ["active"]


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
                "competition_id": "world_cup_2026",
                "home_team_id": "2",
                "away_team_id": "31",
                "home_team_name": "France",
                "away_team_name": "Morocco",
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
    assert view["counts"]["analysis_pick"] == 1
    assert view["counts"]["recommend"] == 0
    assert view["counts"]["watch"] == 1
    assert view["counts"]["not_ready"] == 0
    assert view["counts"]["skip"] == 0
    assert view["counts"]["ready"] == 0
    assert view["counts"]["partial"] == 1
    assert view["counts"]["stale"] == 0
    assert view["counts"]["blocked"] == 1
    assert view["counts"]["by_decision_tier"]["ANALYSIS_PICK"] == 1
    assert view["counts"]["by_decision_tier"]["WATCH"] == 1
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
    assert view["degradation"]["state"] == "OK"
    assert view["degradation"]["source"] == "w2.dashboard.degradation.v1"
    first_card = view["cards"][0]
    assert first_card["home_team_id"] == "2"
    assert first_card["away_team_id"] == "31"
    assert first_card["home_team_name"] == "France"
    assert first_card["away_team_name"] == "Morocco"
    assert first_card["home_team_name_zh"] == "法国"
    assert first_card["away_team_name_zh"] == "摩洛哥"
    assert first_card["home_team_display_name"] == "法国"
    assert first_card["away_team_display_name"] == "摩洛哥"
    assert first_card["home_team_provider_name"] == "France"
    assert first_card["away_team_provider_name"] == "Morocco"
    assert first_card["home_team_localization_status"] == "MATCHED_BY_ID"
    assert first_card["away_team_localization_status"] == "MATCHED_BY_ID"

    contract_card = view["cards"][0]
    assert contract_card["source"] == "decision_contract"
    assert contract_card["decision_tier"] == "WATCH"
    assert contract_card["data_status"] == "BLOCKED"
    assert contract_card["current_odds"]["ah"]["home_line"] == "-0.25"
    assert contract_card["market_probabilities"]["ah"]["method"] == "POWER"
    assert contract_card["market_probabilities"]["ah"]["probabilities"]["HOME_AH"] == 0.5
    assert contract_card["market_probabilities"]["ou"]["method"] == "POWER"
    assert contract_card["market_probabilities"]["ou"]["probabilities"]["OVER"] == 0.502767
    assert contract_card["market_strip"][0]["market"] == "ASIAN_HANDICAP"
    assert contract_card["data_refresh"]["odds_status"] == "READY"
    assert contract_card["probability_source"] == "MARKET_DEVIG"
    assert contract_card["model_market_divergence"]["magnitude"] == 0.12
    assert contract_card["pick"]["disclaimer"] == (
        "分析参考·非稳赢；production 动作需 RECOMMEND"
    )

    legacy_card = view["cards"][1]
    assert legacy_card["source"] == "legacy_fallback"
    assert legacy_card["decision_tier"] == "ANALYSIS_PICK"
    assert legacy_card["lock_eligible"] is True
    assert legacy_card["recommendation_id"] == "legacy-rec"


def test_day_view_and_repository_use_same_power_devig_market_probability() -> None:
    card = {
        "current_odds": {
            "ah": {
                "home_line": "-0.25",
                "home_price": 1.8,
                "away_line": "0.25",
                "away_price": 2.04,
            }
        }
    }
    day_view_probabilities = day_view._market_probabilities(card)["ah"]["probabilities"]
    repository_probabilities = ReadModelService()._market_probabilities_from_observations(
        [
            {
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "HOME_AH",
                "line": "-0.25",
                "decimal_odds": "1.80",
                "captured_at": "2026-07-08T00:00:00Z",
            },
            {
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "AWAY_AH",
                "line": "-0.25",
                "decimal_odds": "2.04",
                "captured_at": "2026-07-08T00:00:00Z",
            },
        ]
    )["ASIAN_HANDICAP:-0.25"]

    assert day_view_probabilities == repository_probabilities


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


def test_day_view_preserves_shadow_and_scoreline_context_for_boss_view() -> None:
    payload = {
        "generated_at": "2026-07-05T08:00:00Z",
        "date": "2026-07-05",
        "selected_football_day": "2026-07-05",
        "all": [
            {
                "fixture_id": "future",
                "kickoff_utc": "2026-07-05T10:00:00Z",
                "status": "NS",
                "decision_tier": "WATCH",
                "data_status": "PARTIAL",
                "lifecycle_status": "DRAFT",
                "reason_code": "EDGE_INSUFFICIENT",
                "pricing_shadow": {
                    "status": "SIMULATION_READY",
                    "simulation": {
                        "status": "READY",
                        "scoreline_picks": [
                            {"scoreline": "1-1", "probability": 0.12},
                            {"scoreline": "2-1", "probability": 0.10},
                        ],
                    },
                },
                "scoreline_readiness": {
                    "status": "READY",
                    "source": "formal_simulation",
                },
            }
        ],
    }

    view = build_dashboard_day_view(payload, environment="staging")
    card = view["cards"][0]

    assert card["pricing_shadow"]["status"] == "SIMULATION_READY"
    assert card["scoreline_readiness"]["status"] == "READY"
    assert card["scoreline_picks"][0]["scoreline"] == "1-1"
    assert card["scoreline_reference"]["source"] == "formal_simulation"
    assert card["scoreline_reference"]["top_scorelines"][1]["scoreline"] == "2-1"


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


def test_day_view_recomputes_same_source_settlement_after_decision_contract_pick() -> None:
    payload = {
        "generated_at": "2026-07-11T00:00:00Z",
        "date": "2026-07-11",
        "selected_football_day": "2026-07-11",
        "all": [
            {
                "fixture_id": "same-source",
                "kickoff_utc": "2026-07-11T12:00:00Z",
                "status": "NS",
                "decision_contract": {
                    "decision_tier": "ANALYSIS_PICK",
                    "data_status": "PARTIAL",
                    "lifecycle_status": "DRAFT",
                    "outcome_tracked": True,
                    "lock_eligible": False,
                    "pick": {
                        "market": "TOTALS",
                        "selection": "OVER",
                        "line": "3.25",
                        "odds": "1.91",
                        "disclaimer": "分析参考·非稳赢",
                    },
                    "analysis_gate": {"market": "TOTALS"},
                },
                "fair_market_estimates": [
                    {
                        "market": "TOTALS",
                        "status": "READY",
                        "model_family": "R4_1_CALIBRATED",
                        "home_mu": 3.1462969750688647,
                        "away_mu": 1.3672753468077237,
                    }
                ],
                "scoreline_reference": {
                    "source": "fair_market_estimate",
                    "top_scorelines": [{"scoreline": "3-1", "probability": 0.08}],
                    "market_settlement": None,
                },
            }
        ],
    }

    view = build_dashboard_day_view(payload, environment="staging")
    reference = view["cards"][0]["scoreline_reference"]

    assert reference["source"] == "fair_market_estimate"
    assert reference["market_settlement"]["selection"] == "OVER"
    assert reference["market_settlement"]["line"] == 3.25
    assert reference["market_settlement"]["probabilities"]["WIN"] > 0.65


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
