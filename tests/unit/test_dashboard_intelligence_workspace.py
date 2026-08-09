from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from w2.api import repository as repository_module
from w2.api.schemas import DashboardIntelligenceWorkspaceResponse
from w2.dashboard.workspace import build_dashboard_intelligence_workspace


def _market(snapshot_count: int) -> dict[str, Any]:
    points = [
        {
            "capture_id": f"capture-{index}",
            "captured_at": f"2026-08-09T0{index}:00:00Z",
            "canonical_line": "-0.25",
            "bookmaker_count": 2,
            "prices": {"HOME": 1.95, "AWAY": 1.95},
            "probabilities": {"HOME": 0.5, "AWAY": 0.5},
        }
        for index in range(snapshot_count)
    ]
    return {
        "status": "READY" if snapshot_count else "INSUFFICIENT",
        "snapshot_count": snapshot_count,
        "observation_count": snapshot_count,
        "current": (
            {
                "canonical_line": "-0.25",
                "bookmaker_count": 2,
                "prices": {"HOME": 1.95, "AWAY": 1.95},
                "probabilities": {"HOME": 0.5, "AWAY": 0.5},
                "freshness": {"status": "FRESH"},
            }
            if snapshot_count
            else {}
        ),
        "timeline": {"status": "READY", "points": points},
        "movement": {"status": "STABLE"},
    }


def _risks() -> dict[str, Any]:
    return {
        dimension: {
            "dimension": dimension,
            "status": "OK",
            "reason_codes": [],
            "explanation": "No current evidence",
        }
        for dimension in (
            "EVENT_RISK",
            "DATA_RISK",
            "MODEL_RISK",
            "COLLECTION_RISK",
        )
    }


def _card(fixture_id: str, snapshot_count: int) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "competition_id": "league-103",
        "competition_name": "Test League",
        "kickoff_utc": "2026-08-10T10:00:00Z",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "status": "NS",
        "intelligence_state": "MARKET_STABLE",
        "intelligence_reason_codes": ["MARKET_STABLE_ALL_AVAILABLE_MARKETS"],
        "risk_dimensions": _risks(),
        "data_status": "READY",
        "reason_code": None,
        "missing_fields": [],
        "stale_fields": [],
        "action": None,
        "next_eval_at": None,
        "provider_budget_status": "OK",
        "lineup_requirement": "ADVISORY",
        "decision_tier": "WATCH",
        "analysis_state": "MARKET_STABLE",
        "market_radar": {
            "schema_version": "w2.market-radar.v1",
            "markets": {
                "ASIAN_HANDICAP": _market(snapshot_count),
                "TOTALS": _market(0),
            },
        },
        "model_lab": {
            "schema_version": "w2.model-lab.v1",
            "markets": {
                "ASIAN_HANDICAP": {"status": "COMPARABLE_WITHIN_MARKET_RANGE"},
                "TOTALS": {"status": "MARKET_NOT_READY"},
            },
            "historical_validation": {
                "final_verdict": "NO_EDGE",
                "reexecuted": False,
            },
        },
        "simulation": {
            "status": "READY",
            "simulation": {
                "model_version": "existing-model",
                "calibration_version": "existing-calibration",
                "calibration_status": "AVAILABLE",
                "simulations": 10000,
            },
        },
        "scoreline_simulations": 10000,
        "scoreline_picks": [{"scoreline": "9-9", "probability": 0.99, "sample_count": 9900}],
        "scoreline_reference": {
            "scoreline_projection": {
                "status": "READY",
                "simulations_completed": 10000,
                "top3": [
                    {
                        "scoreline": "1-0",
                        "sample_count": 1500,
                        "unconditional_probability": 0.15,
                        "conditional_probability": 0.3,
                        "probability": 0.99,
                    }
                ],
            }
        },
        "data_refresh": {
            "statistics_status": "AVAILABLE",
            "statistics_captured_at": "2026-08-09T01:00:00Z",
            "lineups_status": "PROVIDER_EMPTY",
            "injuries_status": "AVAILABLE",
        },
        "card_hash": f"hash-{fixture_id}",
        "source": "decision_contract",
        "lock_eligible": True,
        "expected_value": 0.99,
        "market_pick": {"selection": "HOME"},
    }


def _day_view() -> dict[str, Any]:
    return {
        "generated_at": "2026-08-09T02:00:00Z",
        "date": "2026-08-09",
        "football_day": "2026-08-09",
        "football_day_timezone": "Asia/Shanghai",
        "football_day_cutoff_hour": 12,
        "football_day_start_utc": "2026-08-09T04:00:00Z",
        "football_day_end_utc": "2026-08-10T04:00:00Z",
        "environment": "staging",
        "timezone": "Asia/Shanghai",
        "window": "today",
        "source": "dashboard_read_model",
        "checkpoint_key": "dashboard:day_view:2026-08-09",
        "provider_calls": 0,
        "db_writes": 0,
        "would_write_checkpoint": False,
        "navigation": {"current_date": "2026-08-09"},
        "freshness": {
            "page_updated_at": "2026-08-09T02:00:00Z",
            "odds_last_confirmed_at": "2026-08-09T01:59:00Z",
            "provider_budget_status": "OK",
        },
        "counts": {"total": 3},
        "degradation": {"state": "HEALTHY"},
        "performance": {
            "forward_ledger": {
                "probability_validation": {
                    "status": "SAMPLE_BUILDING",
                    "sample_count": 12,
                    "model_brier": 0.21,
                    "market_brier": 0.22,
                    "model_minus_market_brier": -0.01,
                    "model_log_loss": 0.61,
                    "market_log_loss": 0.62,
                    "model_minus_market_log_loss": -0.01,
                    "model_ece": 0.04,
                    "market_ece": 0.05,
                    "model_reliability_bins": [],
                    "market_reliability_bins": [],
                },
                "outcomes_canonical": {
                    "settled_sample_count": 7,
                    "hit_count": 4,
                    "miss_count": 2,
                    "push_count": 1,
                    "void_count": 0,
                    "decisive_count": 6,
                    "hit_rate": 4 / 6,
                },
                "performance_cohort": {
                    "validation_count": 12,
                    "eligible_count": 7,
                    "excluded_count": 4,
                    "pending_count": 1,
                    "by_league": [],
                },
                "checkpoint_metadata": {"checkpoint_key": "performance:cohort:all"},
                "clv": {"mean": 9.9},
                "roi": 9.9,
            }
        },
        "cards": [
            _card("fixture-zero", 0),
            _card("fixture-one", 1),
            _card("fixture-two", 2),
        ],
    }


def _workspace(day_view: dict[str, Any]) -> dict[str, Any]:
    return build_dashboard_intelligence_workspace(
        day_view,
        replay={
            "replay_status": "MISSING_OUTCOMES",
            "known_at_summary": {
                "has_day_view": True,
                "generated_at": day_view["generated_at"],
                "source": day_view["source"],
                "checkpoint_key": day_view["checkpoint_key"],
            },
            "reason_summary": [],
            "outcome_tracking_summary": {
                "tracked_count": 0,
                "matched_outcome_count": 0,
                "missing_outcome_count": 0,
                "tracked_fixture_ids": [],
                "matched_fixture_ids": [],
                "missing_outcome_fixture_ids": [],
            },
            "card_hash_checks": [],
            "decision_summary": {
                "total_cards": 3,
                "lock_eligible_count": 3,
                "by_decision_tier": {"WATCH": 3},
                "by_data_status": {"READY": 3},
            },
            "replay_gaps": ["MISSING_OUTCOMES"],
        },
    )


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def test_workspace_is_deterministic_explicit_and_schema_valid() -> None:
    day_view = _day_view()

    first = _workspace(day_view)
    second = _workspace(deepcopy(day_view))

    assert first == second
    assert DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "test-request", **first}
    )
    assert first["read_contract"] == {
        "provider_calls": 0,
        "db_writes": 0,
        "would_write_checkpoint": False,
        "no_call_on_read": True,
    }
    assert first["runtime"]["formal"] == "OFF"
    assert first["football_day_timezone"] == "Asia/Shanghai"
    assert first["football_day_cutoff_hour"] == 12
    assert first["football_day_start_utc"] == "2026-08-09T04:00:00Z"
    assert first["football_day_end_utc"] == "2026-08-10T04:00:00Z"
    assert first["attention"][0] == {
        "fixture_id": "fixture-zero",
        "kickoff_utc": "2026-08-10T10:00:00Z",
        "intelligence_state": "MARKET_STABLE",
        "reason_codes": ["MARKET_STABLE_ALL_AVAILABLE_MARKETS"],
        "affected_domains": ["MARKET"],
        "factual_summary": ("MARKET_STABLE: MARKET_STABLE_ALL_AVAILABLE_MARKETS"),
        "readiness_status": "READY",
        "readiness_context": {
            "reason_code": None,
            "missing_fields": [],
            "stale_fields": [],
            "action": None,
        },
        "next_eval_at": None,
        "risks": _risks(),
    }
    assert first["validation"]["history_replay"]["decision_summary"] == {
        "total_cards": 3,
        "lock_eligible_count": 3,
        "by_decision_tier": {"WATCH": 3},
        "by_data_status": {"READY": 3},
    }
    scoreline = first["matches"][0]["scoreline_reference"]
    assert scoreline["simulations_completed"] == 10_000
    assert scoreline["top3"] == [
        {
            "scoreline": "1-0",
            "unconditional_probability": 0.15,
            "sample_count": 1500,
        }
    ]
    assert first["validation"]["directional"]["market_direction_benchmark"] == (
        "NOT_DEFINED"
    )
    assert {
        item["market_radar"]["markets"]["ASIAN_HANDICAP"]["snapshot_state"]
        for item in first["matches"]
    } == {
        "NO_TIMELINE_EVIDENCE",
        "ONE_OBSERVATION_NOT_A_TREND",
        "DISCRETE_REAL_PATH",
    }


def test_workspace_allowlist_excludes_legacy_product_authority_fields() -> None:
    payload = _workspace(_day_view())
    keys = _keys(payload)

    assert keys.isdisjoint(
        {
            "roi",
            "clv",
            "expected_value",
            "value_score",
            "opportunity_score",
            "lock_eligible",
            "anonymous_live_odds_benchmark",
            "market_pick",
        }
    )
    assert not any(key.lower().endswith(("_roi", "_clv")) for key in keys)
    assert all(
        item["formal_recommendation"]
        == {"status": "OFF", "reason": "PRODUCT_AUTHORITY_DISABLED"}
        for item in payload["matches"]
    )


@pytest.mark.parametrize("provider_calls,db_writes", [(1, 0), (0, 1)])
def test_workspace_schema_fails_closed_on_read_side_effects(
    provider_calls: int,
    db_writes: int,
) -> None:
    day_view = _day_view()
    day_view["provider_calls"] = provider_calls
    day_view["db_writes"] = db_writes
    payload = _workspace(day_view)

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


@pytest.mark.parametrize("collection", ["attention", "matches"])
def test_workspace_schema_rejects_unknown_intelligence_state(collection: str) -> None:
    payload = _workspace(_day_view())
    payload[collection][0]["intelligence_state"] = "UNKNOWN_STATE"

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_workspace_schema_rejects_missing_risk_axis() -> None:
    payload = _workspace(_day_view())
    del payload["attention"][0]["risks"]["EVENT_RISK"]

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


@pytest.mark.parametrize("axis", ["EXTRA_RISK", "MARKET_RISK", "event_risk"])
def test_workspace_schema_rejects_extra_or_market_risk_axis(axis: str) -> None:
    payload = _workspace(_day_view())
    payload["matches"][0]["risks"][axis] = deepcopy(payload["matches"][0]["risks"]["EVENT_RISK"])

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_workspace_schema_rejects_ready_scoreline_without_10000_samples() -> None:
    payload = _workspace(_day_view())
    payload["matches"][0]["scoreline_reference"]["simulations_completed"] = 9_999

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_public_statistical_readiness_requires_primary_probability_evidence() -> None:
    day_view = _day_view()
    forward = day_view["performance"]["forward_ledger"]
    forward["probability_validation"] = {
        "status": "INSUFFICIENT",
        "sample_count": 0,
        "model_brier": None,
        "model_log_loss": None,
        "model_ece": None,
    }
    forward["outcomes_canonical"] = {
        "hit_count": 4,
        "miss_count": 1,
        "push_count": 0,
        "void_count": 0,
        "decisive_count": 5,
        "hit_rate": 0.8,
    }
    forward["performance_cohort"]["by_league"] = [
        {
            "league": "eliteserien",
            "source_league": "103",
            "competition_id": "103",
            "canonical_competition_id": "eliteserien",
            "competition_name": "Eliteserien",
            "identity_status": "RESOLVED",
            "processed_count": 5,
            "rate_status": "AVAILABLE",
            "model_brier": None,
            "model_log_loss": None,
            "model_ece": None,
            "outcomes": forward["outcomes_canonical"],
        }
    ]

    payload = _workspace(day_view)

    directional = payload["validation"]["directional"]
    assert directional["source_status"] == "AVAILABLE"
    assert directional["status"] == "SAMPLE_BUILDING"
    assert directional["probability_evidence_ready"] is False
    assert directional["direction_accuracy"] == 0.8
    league = payload["validation"]["league_performance"][0]
    assert league["source_statistical_status"] == "AVAILABLE"
    assert league["statistical_status"] == "SAMPLE_BUILDING"
    assert league["probability_evidence_ready"] is False
    assert league["source_league"] == "103"
    assert league["canonical_competition_id"] == "eliteserien"
    assert league["competition_name"] == "Eliteserien"
    assert league["only_record_reason"] == "PROBABILITY_QUALITY_NOT_READY"
    assert league["market_direction_benchmark"] == "NOT_DEFINED"


def test_baseline_prior_downgrades_public_model_readiness_consistently() -> None:
    day_view = _day_view()
    for card in day_view["cards"]:
        card["simulation"]["status"] = "READY"
        card["simulation"]["simulation"]["calibration_status"] = "BASELINE_PRIOR"

    match = _workspace(day_view)["matches"][0]

    assert match["w2_analysis"]["model_view"]["status"] == "PRIOR_ONLY"
    assert match["w2_analysis"]["model_view"]["source_status"] == "READY"
    assert match["model_lab"]["w2_model"]["status"] == "PRIOR_ONLY"
    assert match["model_lab"]["w2_model"]["source_status"] == "READY"


def test_tournament_performance_is_separate_from_league_performance() -> None:
    day_view = _day_view()
    forward = day_view["performance"]["forward_ledger"]
    row = {
        "league": "world_cup_2026",
        "source_league": "1",
        "source_aliases": ["1", "world_cup_2026"],
        "source_checkpoint_keys": ["performance:cohort:league:1"],
        "scope_group": "world_cup",
        "aggregation_status": "FIXTURE_RECONSTRUCTED",
        "competition_id": "world_cup_2026",
        "canonical_competition_id": "world_cup_2026",
        "competition_name": "World Cup",
        "identity_status": "RESOLVED",
        "processed_count": 1,
        "rate_status": "INSUFFICIENT",
        "model_brier": None,
        "model_log_loss": None,
        "model_ece": None,
        "outcomes": {},
    }
    forward["performance_cohort"]["by_league"] = []
    forward["performance_cohort"]["by_tournament"] = [row]

    validation = _workspace(day_view)["validation"]

    assert validation["league_performance"] == []
    assert validation["tournament_performance"][0]["canonical_competition_id"] == (
        "world_cup_2026"
    )


def test_workspace_schema_rejects_invalid_canonical_aggregation_state() -> None:
    day_view = _day_view()
    forward = day_view["performance"]["forward_ledger"]
    forward["performance_cohort"]["by_league"] = [
        {
            "league": "allsvenskan",
            "source_league": "113",
            "source_aliases": ["113"],
            "source_checkpoint_keys": ["performance:cohort:league:113"],
            "scope_group": "national_leagues",
            "aggregation_status": "FIXTURE_RECONSTRUCTED",
            "competition_id": "allsvenskan",
            "canonical_competition_id": "allsvenskan",
            "competition_name": "Allsvenskan",
            "identity_status": "RESOLVED",
            "processed_count": 1,
            "rate_status": "INSUFFICIENT",
            "model_brier": None,
            "model_log_loss": None,
            "model_ece": None,
            "outcomes": {},
        }
    ]
    payload = _workspace(day_view)
    payload["validation"]["league_performance"][0]["aggregation_status"] = "UNKNOWN"

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_exclusion_distribution_is_projected_without_side_effects() -> None:
    day_view = _day_view()
    forward = day_view["performance"]["forward_ledger"]
    forward["performance_cohort"].update(
        validation_count=56,
        eligible_count=16,
        excluded_count=40,
        pending_count=0,
    )
    forward["validation_excluded_by_reason"] = {
        "MARKET_IDENTITY_NOT_READY": 25,
        "SCORELINE_NOT_READY": 10,
        "RESULT_MISSING": 5,
    }

    records = _workspace(day_view)["validation"]["forward_validation_records"]

    assert records["excluded_count"] == 40
    assert records["excluded_share"] == pytest.approx(40 / 56)
    assert records["excluded_by_reason"] == forward["validation_excluded_by_reason"]


def test_numeric_provider_league_ids_resolve_from_runtime_identity_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = {
        "competition_one": SimpleNamespace(
            profile_payload={"name": "Competition One"},
            provider_mapping={"api_football_league_id": "1"},
        ),
        "competition_103": SimpleNamespace(
            profile_payload={"name": "Competition 103"},
            provider_mapping={"api_football_league_id": "103"},
        ),
    }
    monkeypatch.setattr(
        repository_module.CompetitionRegistry,
        "entries",
        lambda self: entries,
    )

    identities = repository_module._competition_identity_authority()

    assert identities["1"].competition_id == "competition_one"
    assert identities["1"].name == "Competition One"
    assert identities["103"].competition_id == "competition_103"
    assert identities["103"].name == "Competition 103"
    assert "999" not in identities
