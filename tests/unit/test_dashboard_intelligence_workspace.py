from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

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
        "risk_dimensions": {
            "collection_risk": False,
            "data_risk": False,
            "model_risk": False,
            "market_risk": False,
        },
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
        "scoreline_picks": [
            {"scoreline": "1-0", "probability": 0.15, "sample_count": 1500}
        ],
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
