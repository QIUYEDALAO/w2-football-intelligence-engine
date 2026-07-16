from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.dashboard import day_view
from w2.dashboard.day_view import build_dashboard_day_view, build_forward_capture_day_view


class _ActiveAndArchivedMatchdayRepository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            _matchday_payload("active", "chinese_super_league"),
            _matchday_payload("archived", "world_cup_2026"),
        ]


def test_internal_forward_capture_preserves_evidence_while_public_l1_omits_it() -> None:
    snapshot = {"estimate_id": "fme-1", "score_matrix": {"0-0": 1.0}}
    payload = {
        "date": "2099-07-01",
        "selected_football_day": "2099-07-01",
        "generated_at": "2099-07-01T00:00:00Z",
        "timezone": "UTC",
        "window": "today",
        "all": [
            {
                "fixture_id": "fixture-1",
                "kickoff_utc": "2099-07-01T10:00:00Z",
                "decision_tier": "WATCH",
                "data_status": "READY",
                "fair_market_estimate_snapshots": [snapshot],
                "fair_market_estimate_ids": ["fme-1"],
                "analysis_gate": {"estimate_id": "fme-1"},
            }
        ],
    }

    public = build_dashboard_day_view(payload, environment="staging")
    internal = build_forward_capture_day_view(payload, environment="staging")

    assert "fair_market_estimate_snapshots" not in public["cards"][0]
    assert internal["cards"][0]["fair_market_estimate_snapshots"] == [snapshot]
    assert internal["cards"][0]["analysis_gate"] == {"estimate_id": "fme-1"}


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

    view = build_dashboard_day_view(
        payload,
        environment="staging",
        active_whitelist_count=13,
    )

    assert view["football_day"] == "2026-07-05"
    assert view["checkpoint_key"] == "dashboard:day_view:2026-07-05"
    assert view["would_write_checkpoint"] is False
    assert view["provider_calls"] == 0
    assert view["db_writes"] == 0
    assert view["environment_policy"]["environment"] == "staging"
    assert view["environment_policy"]["policy_version"] == "w2.environment_policy.v1"
    assert view["environment_policy"]["lock_policy"]["name"] == "staging_B"
    assert view["environment_policy"]["lock_policy"]["production_action_allowed"] is False
    assert view["active_whitelist_count"] == 13
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
    assert contract_card["data_refresh"]["odds_status"] == "READY"
    assert "market_probabilities" not in contract_card
    assert "market_strip" not in contract_card
    assert "model_market_divergence" not in contract_card
    assert "disclaimer" not in contract_card["pick"]

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


def test_day_view_does_not_surface_legacy_scorelines_without_visible_pick() -> None:
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

    assert "pricing_shadow" not in card
    assert card["scoreline_readiness"]["status"] == "READY"
    assert card["scoreline_picks"] == []
    assert "scoreline_reference" not in card


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


def test_day_view_keeps_direction_scoreline_without_full_settlement_distribution() -> None:
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
    card = view["cards"][0]

    assert card["scoreline_picks"][0] == {"scoreline": "3-1"}
    assert all(set(item) == {"scoreline"} for item in card["scoreline_picks"])
    assert "scoreline_reference" not in card
    assert "market_settlement" not in json.dumps(card)


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


def test_dayview_omits_full_l2_audit_payloads() -> None:
    matrix = {f"{home}-{away}": 0.001 for home in range(13) for away in range(13)}
    snapshot = {
        "schema_version": "w2.fme_snapshot.v2",
        "estimate_id": "fme-1",
        "model_basis_id": "basis-1",
        "market": "TOTALS",
        "artifact_version": "v1",
        "semantic_status": "VERIFIED",
        "feature_as_of": "2026-07-05T00:00:00Z",
        "score_matrix": matrix,
        "input_context": {"feature_snapshot": {"huge": "x" * 20_000}},
    }
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-07-05T00:00:00Z",
            "date": "2026-07-05",
            "selected_football_day": "2026-07-05",
            "all": [
                {
                    "fixture_id": "fixture-1",
                    "kickoff_utc": "2026-07-05T10:00:00Z",
                    "status": "NS",
                    "decision_tier": "ANALYSIS_PICK",
                    "data_status": "READY",
                    "lifecycle_status": "DRAFT",
                    "pick": {
                        "market": "TOTALS",
                        "selection": "OVER",
                        "line": 2.5,
                        "odds": 1.9,
                        "estimate_id": "fme-1",
                    },
                    "fair_market_estimate_snapshots": [snapshot],
                    "pricing_shadow": {"full": "y" * 20_000},
                    "analysis_gate_v2_shadows": [{"full": "z" * 20_000}],
                    "scoreline_reference": {
                        "probability_type": "UNCONDITIONAL_FILTERED_BY_SETTLEMENT",
                        "top_scorelines": [
                            {"scoreline": "2-1", "probability": 0.1},
                            {"scoreline": "3-1", "probability": 0.08},
                        ],
                    },
                }
            ],
        },
        environment="staging",
    )

    card = view["cards"][0]
    assert "fair_market_estimate_snapshots" not in card
    assert "pricing_shadow" not in card
    assert "analysis_gate_v2_shadows" not in card
    assert "score_matrix" not in json.dumps(card)
    assert card["compact_provenance"]["estimate_id"] == "fme-1"
    assert card["compact_provenance"]["model_basis_id"] == "basis-1"
    assert card["scoreline_picks"] == [
        {"scoreline": "2-1"},
        {"scoreline": "3-1"},
    ]


def test_dayview_payload_size_is_bounded_for_forty_cards() -> None:
    matrix = {f"{home}-{away}": 0.001 for home in range(13) for away in range(13)}
    cards = []
    for index in range(40):
        cards.append(
            {
                "fixture_id": f"fixture-{index}",
                "kickoff_utc": "2026-07-05T10:00:00Z",
                "status": "NS",
                "decision_tier": "NOT_READY",
                "data_status": "BLOCKED",
                "lifecycle_status": "DRAFT",
                "fair_market_estimate_snapshots": [
                    {
                        "schema_version": "w2.fme_snapshot.v2",
                        "estimate_id": f"fme-{index}",
                        "model_basis_id": f"basis-{index}",
                        "score_matrix": matrix,
                    }
                ],
                "pricing_shadow": {"full": "x" * 50_000},
            }
        )
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-07-05T00:00:00Z",
            "date": "2026-07-05",
            "selected_football_day": "2026-07-05",
            "all": cards,
        },
        environment="staging",
    )

    encoded = json.dumps(view, ensure_ascii=False).encode()
    assert len(encoded) <= 1_500_000
    max_card_bytes = max(
        len(json.dumps(card, ensure_ascii=False).encode()) for card in view["cards"]
    )
    assert max_card_bytes <= 20_000


def test_dayview_does_not_materialize_full_analysis_for_non_pick(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    service = ReadModelService(
        repository=cast(
            Any,
            type(
                "AvailabilityRepository",
                (),
                {
                    "market_availability_for_fixture_ids": lambda _self, ids: {
                        fixture_id: True for fixture_id in ids
                    }
                },
            )(),
        )
    )
    row = {
        "fixture_id": "no-market",
        "kickoff_utc": "2030-07-16T10:00:00Z",
        "competition_id": "chinese_super_league",
        "competition_name": "中超",
        "home_team_id": "1",
        "away_team_id": "2",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "status": "NS",
    }
    monkeypatch.setattr(
        service,
        "version",
        lambda: {"api_git_sha": "sha", "release_id": "sha"},
    )
    monkeypatch.setattr(service, "_dashboard_rows_for_window", lambda **_: [row])
    monkeypatch.setattr(service, "_prime_observations_for_rows", lambda _: None)
    monkeypatch.setattr(
        service,
        "_observations_for_fixture",
        lambda _: [{"canonical_market": "TOTALS"}],
    )
    monkeypatch.setattr(
        "w2.api.repository.build_day_view_capture_index",
        lambda _: type(
            "Index",
            (),
            {"summaries": {}, "ledger_fingerprint": "test", "schema_version": "v1"},
        )(),
    )
    monkeypatch.setattr(
        service,
        "_dashboard_card_from_matchday",
        lambda _: (_ for _ in ()).throw(
            AssertionError("non-pick card must not build full analysis")
        ),
    )
    monkeypatch.setattr(service, "_day_view_performance", lambda *_args, **_kwargs: {})

    view = service._build_dashboard_day_view_payload(
        requested_date=datetime(2030, 7, 16, tzinfo=UTC).date(),
        window="future",
        timezone="Asia/Shanghai",
    )

    assert view["counts"]["total"] == 1
    assert view["counts"]["not_ready"] == 1
    assert view["cards"][0]["reason_code"] == "DECISION_SUMMARY_UNAVAILABLE"


def test_dayview_projects_visible_pick_from_frozen_capture(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    service = ReadModelService(repository=cast(Any, object()))
    row = {
        "fixture_id": "frozen-pick",
        "kickoff_utc": "2030-07-16T10:00:00Z",
        "competition_id": "chinese_super_league",
        "competition_name": "中超",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "status": "NS",
    }
    capture = {
        "fixture_id": "frozen-pick",
        "captured_at": "2030-07-16T08:00:00Z",
        "kickoff_utc": "2030-07-16T10:00:00Z",
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "outcome_tracked": True,
        "pick": {
            "market": "TOTALS",
            "selection": "OVER",
            "line": "2.75",
            "odds": "1.91",
            "fair_line": "3.25",
            "estimate_id": "fme-1",
            "model_basis_id": "basis-1",
        },
        "fair_market_estimate_snapshots": [
            {
                "schema_version": "w2.fme_snapshot.v2",
                "estimate_id": "fme-1",
                "model_basis_id": "basis-1",
                "market": "TOTALS",
                "artifact_version": "r4.1",
                "integrity_status": "PASS",
                "semantic_status": "PASS",
                "feature_as_of": "2030-07-16T07:00:00Z",
            }
        ],
        "scoreline_reference": {
            "source": "fair_market_estimate",
            "top_scorelines": [
                {"scoreline": "2-1", "probability": 0.1},
                {"scoreline": "3-1", "probability": 0.08},
            ],
        },
    }
    monkeypatch.setattr(
        service,
        "version",
        lambda: {"api_git_sha": "sha", "release_id": "sha"},
    )
    monkeypatch.setattr(service, "_dashboard_rows_for_window", lambda **_: [row])
    monkeypatch.setattr(service, "_prime_observations_for_rows", lambda _: None)
    from w2.tracking.day_view_capture_index import _summary_from_capture

    summary = _summary_from_capture({**capture, "capture_hash": "capture-1"})
    assert summary is not None
    monkeypatch.setattr(
        "w2.api.repository.build_day_view_capture_index",
        lambda _: type(
            "Index",
            (),
            {
                "summaries": {"frozen-pick": summary},
                "ledger_fingerprint": "test",
                "schema_version": "v1",
            },
        )(),
    )
    monkeypatch.setattr(service, "_day_view_performance", lambda *_args, **_kwargs: {})

    view = service._build_dashboard_day_view_payload(
        requested_date=datetime(2030, 7, 16, tzinfo=UTC).date(),
        window="future",
        timezone="Asia/Shanghai",
    )

    card = view["cards"][0]
    assert card["decision_tier"] == "ANALYSIS_PICK"
    assert card["pick"] == capture["pick"]
    assert card["compact_provenance"]["estimate_id"] == "fme-1"
    assert card["scoreline_picks"] == [
        {"scoreline": "2-1"},
        {"scoreline": "3-1"},
    ]


def test_future_dayview_is_cursor_paged_and_does_not_prime_all_rows(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import json

    service = ReadModelService(repository=cast(Any, object()))
    rows = [
        {
            "fixture_id": str(index),
            "kickoff_utc": f"2030-07-{16 + index // 24:02d}T{index % 24:02d}:00:00Z",
            "competition_id": "chinese_super_league",
            "home_team_name": "Home",
            "away_team_name": "Away",
            "status": "NS",
        }
        for index in range(500)
    ]
    primed: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(service, "version", lambda: {"api_git_sha": "sha", "release_id": "sha"})
    monkeypatch.setattr(service, "_dashboard_rows_for_window", lambda **_: rows)
    monkeypatch.setattr(service, "_prime_observations_for_rows", lambda page: primed.append(page))
    monkeypatch.setattr(service, "_observations_for_fixture", lambda _: [])
    monkeypatch.setattr(service, "_day_view_performance", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        "w2.api.repository.build_day_view_capture_index",
        lambda _: type(
            "Index",
            (),
            {"summaries": {}, "ledger_fingerprint": "test", "schema_version": "v1"},
        )(),
    )

    first = service._build_dashboard_day_view_payload(
        requested_date=datetime(2030, 7, 16, tzinfo=UTC).date(),
        window="future",
        timezone="UTC",
    )

    assert first["counts"]["total"] == 500
    assert first["page_counts"]["total"] == 20
    assert first["pagination"]["returned_count"] == 20
    assert first["pagination"]["has_more"] is True
    assert primed == []
    assert len(json.dumps(first).encode()) <= 512 * 1024
    assert all(len(json.dumps(card).encode()) <= 24 * 1024 for card in first["cards"])


def test_dayview_preserves_compact_canonical_performance_summary() -> None:
    service = ReadModelService(repository=cast(Any, object()))
    bucket = {
        "settled_sample_count": 2,
        "hit_count": 1,
        "miss_count": 1,
        "push_count": 0,
        "void_count": 0,
        "hit_rate": 0.5,
    }
    compact = service._compact_forward_ledger_summary(
        {
            "schema_version": "w2.forward_ledger_performance.v2",
            "source": "runtime/forward_outcome_ledger",
            "sample_target": 100,
            "fixture_count": 53,
            "double_snapshot_fixture_count": 35,
            "validation_fixture_count": 16,
            "validation_settled_fixture_count": 16,
            "validation_pending_fixture_count": 0,
            "validation_pending_status": {"pending_fixture_count": 0},
            "outcomes_validation": bucket,
            "outcomes_shadow_wide": bucket,
            "outcomes_shadow_strict": {**bucket, "settled_sample_count": 0},
            "outcomes_official": {**bucket, "settled_sample_count": 0},
            "outcomes_raw_audit": {
                "raw_outcome_row_count": 103,
                "canonical_outcome_count": 38,
                "audit_only_outcome_count": 65,
            },
            "performance_integrity": {
                "status": "PASS",
                "canonical_duplicate_count": 0,
                "cross_track_contamination_count": 0,
            },
            "clv_shadow": {"sample_count": 35, "median_decimal": 0.0},
            "by_league": [{"league": "must-not-be-in-l1"}],
            "by_league_market": [{"league": "must-not-be-in-l1"}],
        }
    )

    assert compact["validation_fixture_count"] == 16
    assert compact["outcomes_validation"]["settled_sample_count"] == 2
    assert compact["outcomes_shadow_wide"]["settled_sample_count"] == 2
    assert compact["outcomes_shadow_strict"]["settled_sample_count"] == 0
    assert compact["outcomes_official"]["settled_sample_count"] == 0
    assert compact["performance_integrity"]["status"] == "PASS"
    assert compact["r1_1"] == {
        "valid_pair_count": 35,
        "sample_target": 100,
        "remaining": 65,
        "status": "PENDING",
    }
    assert compact["strict_evidence"]["status"] == "ACCUMULATING"
    assert "by_league" not in compact
    assert "by_league_market" not in compact
