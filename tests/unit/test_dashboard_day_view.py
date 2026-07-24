from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from w2.dashboard import day_view
from w2.dashboard.day_view import build_dashboard_day_view
from w2.domain.decision_contract import (
    REQUIRED_DECISION_CONTRACT_FIELDS,
    DecisionContractViolation,
)


def _non_pick_contract(
    *,
    tier: str = "WATCH",
    data_status: str = "PARTIAL",
    **extra: Any,
) -> dict[str, Any]:
    non_pick = {
        "reason_code": "LINEUPS_PENDING",
        "reason_human": "首发未出",
        "action": "等官方首发",
        "next_eval_at": None,
    }
    return {
        "decision_tier": tier,
        "data_status": data_status,
        "lifecycle_status": "DRAFT",
        "outcome_tracked": False,
        "lock_eligible": False,
        "recommendation_id": None,
        "pick": None,
        "non_pick": non_pick,
        "reason_code": non_pick["reason_code"],
        "action": non_pick["action"],
        "next_eval_at": non_pick["next_eval_at"],
        **extra,
    }


def _pick_contract(*, tier: str = "ANALYSIS_PICK") -> dict[str, Any]:
    return {
        "decision_tier": tier,
        "data_status": "READY",
        "lifecycle_status": "DRAFT",
        "outcome_tracked": True,
        "lock_eligible": tier == "RECOMMEND",
        "recommendation_id": "rec-1" if tier == "RECOMMEND" else None,
        "pick": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": "-0.25",
            "odds": "1.95",
        },
        "non_pick": None,
    }


def _payload_with_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": "2026-07-05T00:00:00Z",
        "date": "2026-07-05",
        "selected_football_day": "2026-07-05",
        "all": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2026-07-05T10:00:00Z",
                **deepcopy(contract),
                "decision_contract": deepcopy(contract),
            }
        ],
    }


def test_day_view_projects_valid_decision_contract_card() -> None:
    contract = _non_pick_contract(
        data_status="BLOCKED",
        provider_budget_status="OK",
        probability_source="MARKET_DEVIG",
        model_market_divergence={
            "status": "READY",
            "magnitude": 0.12,
        },
    )
    payload = {
        "generated_at": datetime(2026, 7, 5, 1, 2, tzinfo=UTC),
        "page_updated_at": datetime(2026, 7, 5, 1, 2, tzinfo=UTC),
        "odds_last_confirmed_at": "2026-07-05T01:00:00Z",
        "next_refresh_tick": "2026-07-05T01:15:00Z",
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
                **deepcopy(contract),
                "current_odds": {
                    "ah": {
                        "home_line": "-0.25",
                        "home_price": 1.95,
                        "away_line": "0.25",
                        "away_price": 1.95,
                    },
                    "ou": {"line": "2.5", "over_price": 1.91, "under_price": 1.93},
                },
                "last_known_odds": {
                    "status": "REFERENCE_ONLY",
                    "captured_at": "2026-07-04T10:00:00Z",
                    "executable": False,
                    "markets": {
                        "ah": {
                            "home_line": "-0.25",
                            "home_price": 1.95,
                            "away_line": "0.25",
                            "away_price": 1.95,
                        }
                    },
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
                "pricing_shadow": {
                    "simulation": {
                        "status": "READY",
                        "simulations": 10000,
                    }
                },
                "scoreline_picks": [
                    {
                        "scoreline": "1-0",
                        "home_goals": 1,
                        "away_goals": 0,
                        "probability": 0.12,
                        "probability_label": "12%",
                    }
                ],
                "scoreline_reference": {
                    "source": "formal_simulation",
                    "label": "模拟比分参考",
                },
                "scoreline_readiness": {
                    "status": "READY",
                    "source": "formal_simulation",
                },
                "decision_contract": deepcopy(contract),
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
    assert view["counts"]["total"] == 1
    assert view["counts"]["analysis_pick"] == 0
    assert view["counts"]["recommend"] == 0
    assert view["counts"]["watch"] == 1
    assert view["counts"]["not_ready"] == 0
    assert view["counts"]["skip"] == 0
    assert view["counts"]["ready"] == 0
    assert view["counts"]["partial"] == 0
    assert view["counts"]["stale"] == 0
    assert view["counts"]["blocked"] == 1
    assert view["counts"]["by_decision_tier"]["ANALYSIS_PICK"] == 0
    assert view["counts"]["by_decision_tier"]["WATCH"] == 1
    assert view["counts"]["by_data_status"]["READY"] == 0
    assert view["counts"]["by_data_status"]["BLOCKED"] == 1
    assert view["freshness"]["provider_budget_status"] == "OK"
    assert view["freshness"]["page_updated_at"] == "2026-07-05T01:02:00Z"
    assert view["freshness"]["odds_last_confirmed_at"] == "2026-07-05T01:00:00Z"
    assert view["freshness"]["next_refresh_tick"] == "2026-07-05T01:15:00Z"
    assert view["freshness"]["last_refresh"] == view["freshness"]["page_updated_at"]
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
    assert view["degradation"]["state"] == "BLOCKED_DAY"
    assert view["degradation"]["source"] == "w2.dashboard.degradation.v1"

    contract_card = view["cards"][0]
    assert contract_card["source"] == "decision_contract"
    assert contract_card["decision_tier"] == "WATCH"
    assert contract_card["data_status"] == "BLOCKED"
    assert contract_card["current_odds"] == {}
    assert contract_card["last_known_odds"]["status"] == "REFERENCE_ONLY"
    assert contract_card["last_known_odds"]["executable"] is False
    assert contract_card["market_probabilities"] == {}
    assert contract_card["market_strip"][0]["market"] == "ASIAN_HANDICAP"
    assert contract_card["data_refresh"]["odds_status"] == "READY"
    assert contract_card["scoreline_simulations"] == 10000
    assert contract_card["scoreline_picks"] == []
    assert contract_card["scoreline_reference"] == {}
    assert contract_card["scoreline_readiness"]["status"] == "READY"
    assert contract_card["probability_source"] == "MARKET_DEVIG"
    assert contract_card["model_market_divergence"]["magnitude"] == 0.12
    assert contract_card["pick"] is None



def test_day_view_missing_decision_contract_fails_closed() -> None:
    payload = {
        "generated_at": "2026-07-05T00:00:00Z",
        "date": "2026-07-05",
        "selected_football_day": "2026-07-05",
        "all": [
            {
                "fixture_id": "fixture-without-contract",
                "kickoff_utc": "2026-07-05T10:00:00Z",
                "decision_tier": "WATCH",
                "data_status": "PARTIAL",
                "lifecycle_status": "DRAFT",
            }
        ],
    }

    with pytest.raises(
        DecisionContractViolation,
        match="DECISION_CONTRACT_MISSING:fixture-without-contract",
    ):
        build_dashboard_day_view(payload, environment="staging")


def test_day_view_counts_are_aggregated_from_cards_only() -> None:
    contract = _non_pick_contract()
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
                **deepcopy(contract),
                "decision_contract": deepcopy(contract),
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
    contract = _non_pick_contract()
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
                **deepcopy(contract),
                "decision_contract": deepcopy(contract),
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
    contract = _pick_contract()
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-07-05T00:00:00Z",
            "date": "2026-07-05",
            "selected_football_day": "2026-07-05",
            "refreshing": True,
            "all": [
                {
                    "fixture_id": "fixture-1",
                    **deepcopy(contract),
                    "decision_contract": deepcopy(contract),
                }
            ],
        },
        environment="staging",
    )

    assert view["freshness"]["refreshing"] is True
    assert view["degradation"]["state"] == "REFRESHING"


def test_day_view_module_does_not_call_strategy_decider() -> None:
    assert "decide_match" not in day_view.__dict__


@pytest.mark.parametrize("field", REQUIRED_DECISION_CONTRACT_FIELDS)
def test_day_view_rejects_each_missing_required_contract_field(field: str) -> None:
    payload = _payload_with_contract(_non_pick_contract())
    payload["all"][0]["decision_contract"].pop(field)

    with pytest.raises(
        DecisionContractViolation,
        match=rf"DECISION_CONTRACT_INCOMPLETE:fixture-1:.*{field}",
    ):
        build_dashboard_day_view(payload, environment="staging")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome_tracked", 0),
        ("outcome_tracked", "false"),
        ("lock_eligible", 1),
        ("lock_eligible", "false"),
    ],
)
def test_day_view_rejects_non_bool_contract_flags(field: str, value: object) -> None:
    payload = _payload_with_contract(_non_pick_contract())
    payload["all"][0][field] = value
    payload["all"][0]["decision_contract"][field] = value

    with pytest.raises(
        DecisionContractViolation,
        match=rf"DECISION_CONTRACT_INVALID:fixture-1:{field}",
    ):
        build_dashboard_day_view(payload, environment="staging")


@pytest.mark.parametrize(
    "contract",
    [
        {**_pick_contract(), "pick": None},
        {**_pick_contract(), "non_pick": _non_pick_contract()["non_pick"]},
        {**_non_pick_contract(), "pick": _pick_contract()["pick"]},
        {**_non_pick_contract(), "non_pick": None},
        {**_non_pick_contract(), "lock_eligible": True},
    ],
)
def test_day_view_rejects_pick_non_pick_or_lock_contradictions(
    contract: dict[str, Any],
) -> None:
    payload = _payload_with_contract(contract)

    with pytest.raises(DecisionContractViolation, match="DECISION_CONTRACT_INVALID"):
        build_dashboard_day_view(payload, environment="staging")


def test_day_view_rejects_top_level_decision_field_pollution() -> None:
    payload = _payload_with_contract(_non_pick_contract())
    payload["all"][0]["reason_code"] = "POISONED_TOP_LEVEL_VALUE"

    with pytest.raises(
        DecisionContractViolation,
        match="DECISION_CONTRACT_CONFLICT:fixture-1:reason_code",
    ):
        build_dashboard_day_view(payload, environment="staging")
