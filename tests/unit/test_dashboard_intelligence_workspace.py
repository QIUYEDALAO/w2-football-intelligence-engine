from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from w2.api import repository as repository_module
from w2.api.schemas import DashboardIntelligenceWorkspaceResponse
from w2.config import get_settings
from w2.dashboard.results import outcome_public_cause
from w2.dashboard.workspace import build_dashboard_intelligence_workspace
from w2.identity.public_team_labels import (
    pending_public_team_labels,
    reviewed_public_team_labels,
)


def test_model_forecast_funnel_reports_not_measurable_without_opportunities() -> None:
    """Captures are not opportunities, so they cannot stand in as a denominator.

    The previous contract multiplied captures by markets and read every missing
    row as "all gates failed, entry not traversed".  With no opportunity writer
    in production that published a 100%-model / 0%-everything funnel describing
    fixtures whose checkpoints had not even come due.  Silence must read as
    silence.
    """

    captures = [
        SimpleNamespace(fixture_id="1"),
        SimpleNamespace(fixture_id="api_football:2"),
    ]

    funnel = repository_module._model_forecast_market_evaluation_funnel(captures, [], set())

    assert funnel["measurement_status"] == "NOT_MEASURABLE"
    assert funnel["opportunity_count"] == 0
    assert funnel["invalid_opportunity_row_count"] == 0
    assert funnel["market_unit_count"] == 0
    assert funnel["gate_rates"] is None
    assert funnel["gate_counts"] == {}
    assert funnel["first_failed_gate_counts"] == {}
    # The captures are still reported -- they are just not the denominator.
    assert funnel["capture_count"] == 2


def test_model_forecast_funnel_flags_official_rows_missing_the_contract() -> None:
    """A row asserting official status must satisfy the contract or be flagged.

    Silently dropping it would report "nothing has happened" about a writer that
    is producing broken records.  Rows that never claimed official status are a
    different case and stay quietly excluded.
    """

    partial = SimpleNamespace(
        evaluation_id="eval-1",
        fixture_id="api_football:1",
        market="ASIAN_HANDICAP",
        denominator_scope="CHECKPOINT_EVALUATION_OPPORTUNITY_V2",
        measurement_semantics="CHECKPOINT_EVALUATION_OPPORTUNITY",
        official_funnel_eligible=True,
        evaluation_policy_version="candidate-eval.v1",
        evaluation_slot_id=None,
        model_forecast_capture_identity_hash="capture-hash-A",
        capture_id="quote-capture-1",
        evaluated_at=None,
        recorded_at=None,
        original_state="NO_EDGE_CURRENT",
        gate_results=None,
        payload={"state": "NO_EDGE_CURRENT"},
    )

    funnel = repository_module._model_forecast_market_evaluation_funnel(
        [SimpleNamespace(fixture_id="1")], [partial], set()
    )

    assert funnel["measurement_status"] == "INVALID"
    assert funnel["opportunity_count"] == 0
    assert funnel["invalid_opportunity_reasons"] == {"SLOT_MISSING": 1}


def _market(snapshot_count: int) -> dict[str, Any]:
    points = [
        {
            "capture_id": f"capture-{index}",
            "checkpoint": f"T{index}",
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
        "observation_count": snapshot_count * 4,
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
        "movement": (
            {
                "status": "STABLE",
                "from_captured_at": points[0]["captured_at"],
                "to_captured_at": points[-1]["captured_at"],
                "line_delta": "0",
                "price_delta": {"HOME": 0.0, "AWAY": 0.0},
                "probability_delta": {"HOME": 0.0, "AWAY": 0.0},
            }
            if snapshot_count > 1
            else {
                "status": "INSUFFICIENT",
                "reason_code": (
                    "INSUFFICIENT_SINGLE_SNAPSHOT"
                    if snapshot_count
                    else "INSUFFICIENT_NO_TIMELINE_EVIDENCE"
                ),
            }
        ),
    }


def _risks() -> dict[str, Any]:
    return {
        dimension: {
            "dimension": dimension,
            "status": "OK",
            "reason_codes": [],
            "explanation": "没有可陈述的源证据",
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
            "market_collection": {
                "latest_snapshot_at": "2026-08-09T01:00:00Z",
                "latest_snapshot_checkpoint": "T24_OPEN_ODDS",
                "target_checkpoint": "T12_ODDS",
                "scheduled_at": "2026-08-09T14:30:00Z",
                "window_end_at": "2026-08-09T15:00:00Z",
                "overdue": False,
                "public_semantics": {"scope": "MATCH", "cause": "NOT_YET_DUE"},
            },
            "lineup_collection": {
                "target_checkpoint": "T60_ODDS_LINEUPS",
                "scheduled_at": "2026-08-10T09:00:00Z",
                "window_end_at": "2026-08-10T09:20:00Z",
                "overdue": False,
                "public_semantics": {"scope": "MATCH", "cause": "NOT_YET_DUE"},
            },
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
        "date_strip": [
            {
                "football_day": (date(2026, 8, 2) + timedelta(days=index)).isoformat(),
                "fixture_count": 3 if index == 7 else 0,
                "competition_count": 1 if index == 7 else 0,
                "finished_fixture_count": 0,
                "upcoming_fixture_count": 3 if index == 7 else 0,
                "persisted_inventory_status": (
                    "PERSISTED_FIXTURES_AVAILABLE" if index == 7 else "EMPTY_PERSISTED_DAY"
                ),
                "persisted_competition_coverage_count": 1 if index == 7 else 0,
                "active_whitelist_count": 13,
                "market_collection_window_status": (
                    "MARKET_EVIDENCE_AVAILABLE" if index == 7 else "EMPTY_PERSISTED_DAY"
                ),
                "market_evidence_fixture_count": 3 if index == 7 else 0,
            }
            for index in range(15)
        ],
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


def _workspace(
    day_view: dict[str, Any],
    *,
    candidate_enabled: bool = False,
    replay: dict[str, Any] | None = None,
    model_forecasts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_dashboard_intelligence_workspace(
        day_view,
        candidate_enabled=candidate_enabled,
        model_forecasts=model_forecasts,
        replay=replay
        or {
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


def test_shadow_candidate_activation_reuses_v4_and_stays_non_production() -> None:
    day_view = _day_view()
    day_view["cards"][0]["market_radar"]["markets"]["ASIAN_HANDICAP"] = _market(2)
    day_view["cards"][0]["market_candidates"] = {
        "ah": {
            "quote_status": "COMPLETE",
            "quote_usage": "EXECUTABLE",
            "quote_identity": {"identity_status": "COMPLETE"},
            "model_status": "READY",
            "blockers": [],
        }
    }
    day_view["cards"][0]["recommendation_decision_v4"] = {
        "outcome": "ANALYSIS_PICK",
        "reason": {"code": "ANALYSIS_ONLY", "message": "当前仅提供影子候选"},
        "selected_candidate": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "exact_line": "-0.25",
            "decimal_odds": "1.95",
            "captured_at": "2026-08-09T01:00:00Z",
        },
        "decision_hash": "a" * 64,
    }

    payload = _workspace(day_view, candidate_enabled=True)
    candidate = payload["matches"][0]["shadow_candidate"]

    assert payload["runtime"]["candidate"] == "SHADOW_ONLY"
    assert payload["matches"][0]["readiness"]["market_aggregate_status"] == "PARTIAL"
    assert candidate == {
        "status": "ACTIVE",
        "mode": "SHADOW_ONLY",
        "authority": "RECOMMENDATION_DECISION_V4",
        "decision_tier": "ANALYSIS_PICK",
        "reason_code": "ANALYSIS_ONLY",
        "reason_message": "当前仅提供影子候选",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME",
        "exact_line": "-0.25",
        "decimal_odds": 1.95,
        "captured_at": "2026-08-09T01:00:00Z",
        "decision_hash": "a" * 64,
        "recommendation_scope": "VALIDATION",
        "outcome_tracked": True,
        "formal_status": "OFF",
        "lock_status": "OFF",
        "production_action_allowed": False,
        "real_money_allowed": False,
    }
    DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "candidate-contract", **payload}
    )


def test_shadow_candidate_fails_closed_when_selected_market_is_not_eligible() -> None:
    day_view = _day_view()
    day_view["cards"][0]["recommendation_decision_v4"] = {
        "outcome": "ANALYSIS_PICK",
        "reason": {"code": "ANALYSIS_ONLY"},
        "selected_candidate": {"market": "ASIAN_HANDICAP", "selection": "HOME"},
        "decision_hash": "a" * 64,
    }
    payload = _workspace(day_view, candidate_enabled=True)

    candidate = payload["matches"][0]["shadow_candidate"]
    assert candidate["status"] == "NOT_READY"
    assert candidate["market"] is None
    assert candidate["outcome_tracked"] is False
    DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "candidate-contract", **payload}
    )


def test_shadow_candidate_uses_exact_quote_age_not_diagnostic_market_age() -> None:
    day_view = _day_view()
    day_view["cards"][0]["market_radar"]["markets"]["ASIAN_HANDICAP"] = _market(2)
    day_view["generated_at"] = "2026-08-09T03:00:00Z"
    day_view["cards"][0]["market_candidates"] = {
        "ah": {
            "quote_status": "STALE",
            "quote_usage": "REFERENCE_ONLY",
            "quote_identity": {"identity_status": "COMPLETE"},
            "model_status": "READY",
            "blockers": [],
        }
    }
    day_view["cards"][0]["recommendation_decision_v4"] = {
        "outcome": "ANALYSIS_PICK",
        "reason": {"code": "ANALYSIS_ONLY"},
        "selected_candidate": {
            "market": "ASIAN_HANDICAP",
            "selection": "HOME",
            "exact_line": "-0.25",
        },
        "decision_hash": "a" * 64,
    }

    payload = _workspace(day_view, candidate_enabled=True)
    match = payload["matches"][0]
    assert match["market_radar"]["markets"]["ASIAN_HANDICAP"]["status"] == "READY"
    assert match["market_radar"]["markets"]["ASIAN_HANDICAP"]["quote_age_seconds"] == 7200
    assert match["shadow_candidate"]["status"] == "NOT_READY"
    assert match["shadow_candidate"]["outcome_tracked"] is False
    DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "candidate-stale", **payload}
    )


def _factor_checklist_card() -> dict[str, Any]:
    card = _card("fixture-factor-checklist", 2)
    for side in ("home", "away"):
        card[f"{side}_team_label"] = {
            "display_name": "主队" if side == "home" else "客队",
            "state": "CHINESE_LABEL_READY",
            "canonical_team_id": f"w2:{side}",
            "provider_team_id": side,
        }
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        raw = _market(2)
        raw["current"]["bookmaker_count"] = 4
        for point in raw["timeline"]["points"]:
            point["bookmaker_count"] = 4
        card["market_radar"]["markets"][market] = raw
    card["market_candidates"] = {
        key: {
            "quote_status": "STALE",
            "quote_usage": "REFERENCE_ONLY",
            "quote_identity": {"identity_status": "COMPLETE"},
            "model_status": "READY",
            "blockers": ["QUOTE_OLDER_THAN_30_MINUTES"],
        }
        for key in ("ah", "ou")
    }
    card["factor_checklist_inputs"] = {
        "data_readiness": {
            "xg": True,
            "xg_status": "READY",
            "xg_home_match_count": 3,
            "xg_away_match_count": 3,
            "xg_snapshot_count": 2,
            "lineups": False,
            "lineups_status": "NOT_REQUESTED",
        },
        "feature_contributions": [],
        "provider_xg_unavailable_confirmed": False,
    }
    return card


def test_factor_checklist_separates_model_track_from_stale_quote_gate() -> None:
    day_view = _day_view()
    day_view["generated_at"] = "2026-08-09T03:00:00Z"
    day_view["cards"] = [_factor_checklist_card()]

    checklist = _workspace(day_view, candidate_enabled=True)["matches"][0]["factor_checklist"]

    assert checklist["track_model_forecast"] == {
        "state": "READY",
        "blocking_factor_ids": [],
    }
    assert checklist["track_shadow_candidate"]["state"] == "BLOCKED"
    assert checklist["track_shadow_candidate"]["blocking_factor_ids"] == ["MK_QUOTE_AGE"]
    quote_rows = [row for row in checklist["factors"] if row["factor_id"] == "MK_QUOTE_AGE"]
    assert {row["market"] for row in quote_rows} == {"ASIAN_HANDICAP", "TOTALS"}
    assert all(row["next_window_at"] == "2026-08-09T14:30:00Z" for row in quote_rows)
    identity_rows = [row for row in checklist["factors"] if row["factor_id"] == "MK_EXACT_QUOTE"]
    assert all(row["state"] == "READY" for row in identity_rows)
    match = _workspace(day_view, candidate_enabled=True)["matches"][0]
    assert match["readiness"]["market_aggregate_status"] == "NOT_READY"
    assert all(
        market["eligibility"]["candidate_quote_lock_status"] == "NOT_READY"
        for market in match["market_radar"]["markets"].values()
    )
    assert "主盘身份可解析 ≠ 候选报价可锁定" in checklist["market_identity_note_zh"]


def test_factor_checklist_reports_waiting_quote_before_unassessed_decision() -> None:
    day_view = _day_view()
    day_view["generated_at"] = "2026-08-09T03:00:00Z"
    card = _factor_checklist_card()
    for candidate in card["market_candidates"].values():
        candidate.update(
            quote_status="COMPLETE",
            quote_usage="EXECUTABLE",
            blockers=[],
        )
    day_view["cards"] = [card]

    checklist = _workspace(day_view, candidate_enabled=True)["matches"][0][
        "factor_checklist"
    ]

    assert checklist["track_shadow_candidate"]["blocking_factor_ids"] == [
        "MK_QUOTE_AGE"
    ]
    assert "等待中，尚未评估" in checklist["conclusion_zh"]
    assert "最上游待满足：报价时效" in checklist["conclusion_zh"]
    assert "Decision V4" not in checklist["conclusion_zh"]


def test_factor_checklist_reports_no_edge_as_assessed_not_gate_failed() -> None:
    day_view = _day_view()
    day_view["generated_at"] = "2026-08-09T01:20:00Z"
    card = _factor_checklist_card()
    for candidate in card["market_candidates"].values():
        candidate.update(
            quote_status="COMPLETE",
            quote_usage="EXECUTABLE",
            blockers=[],
        )
    card["recommendation_decision_v4"] = {
        "outcome": "NO_EDGE",
        "reason": {
            "code": "CASHFLOW_EDGE_INSUFFICIENT",
            "message": "五态现金流优势不足",
        },
    }
    day_view["cards"] = [card]

    checklist = _workspace(day_view, candidate_enabled=True)["matches"][0][
        "factor_checklist"
    ]

    assert checklist["track_shadow_candidate"]["blocking_factor_ids"] == ["NO_EDGE"]
    assert "Decision V4 已评估" in checklist["conclusion_zh"]
    assert "NO_EDGE（模型与市场一致，无价值差）" in checklist["conclusion_zh"]
    assert "未通过" not in checklist["conclusion_zh"]


def test_factor_checklist_provider_unavailable_requires_explicit_confirmation() -> None:
    day_view = _day_view()
    card = _factor_checklist_card()
    card["factor_checklist_inputs"]["data_readiness"].update(
        {
            "xg": False,
            "xg_status": "PROVIDER_EMPTY_OR_UNAVAILABLE",
            "xg_home_match_count": 0,
            "xg_away_match_count": 0,
        }
    )
    card["factor_checklist_inputs"]["provider_xg_unavailable_confirmed"] = True
    day_view["cards"] = [card]

    checklist = _workspace(day_view)["matches"][0]["factor_checklist"]
    xg = next(row for row in checklist["factors"] if row["factor_id"] == "F9_TRUE_XG")

    assert xg["cause"] == "PROVIDER_NOT_AVAILABLE"
    assert xg["permanence"] == "STRUCTURAL_PERMANENT"
    assert "待采集" not in checklist["conclusion_zh"]


def test_factor_checklist_does_not_promote_generic_provider_empty_to_unsupported() -> None:
    day_view = _day_view()
    card = _factor_checklist_card()
    card["factor_checklist_inputs"]["data_readiness"].update(
        {
            "xg": False,
            "xg_status": "PROVIDER_EMPTY_OR_UNAVAILABLE",
            "xg_home_match_count": 0,
            "xg_away_match_count": 0,
        }
    )
    day_view["cards"] = [card]

    xg = next(
        row
        for row in _workspace(day_view)["matches"][0]["factor_checklist"]["factors"]
        if row["factor_id"] == "F9_TRUE_XG"
    )

    assert xg["cause"] == "NO_MATERIALIZED_HISTORY"
    assert xg["permanence"] == "UNKNOWN"


def test_factor_checklist_reports_xg_shortfall_and_market_depth_per_market() -> None:
    day_view = _day_view()
    card = _factor_checklist_card()
    card["factor_checklist_inputs"]["data_readiness"].update(
        {
            "xg": False,
            "xg_status": "PARTIAL_HISTORY",
            "xg_home_match_count": 3,
            "xg_away_match_count": 1,
        }
    )
    card["market_radar"]["markets"]["ASIAN_HANDICAP"]["current"]["bookmaker_count"] = 1
    card["market_radar"]["markets"]["TOTALS"]["current"]["bookmaker_count"] = 7
    day_view["cards"] = [card]

    checklist = _workspace(day_view)["matches"][0]["factor_checklist"]
    xg = next(row for row in checklist["factors"] if row["factor_id"] == "F9_TRUE_XG")
    depth = {
        row["market"]: row["evidence"]["bookmaker_count"]
        for row in checklist["factors"]
        if row["factor_id"] == "MK_BOOKMAKER_DEPTH"
    }

    assert xg["cause"] == "UNDER_SAMPLED"
    assert xg["evidence"]["shortfall"] == 2
    assert "还差 2 场" in checklist["conclusion_zh"]
    assert depth == {"ASIAN_HANDICAP": 1, "TOTALS": 7}


def test_factor_checklist_roles_are_loaded_from_sc21_authority_matrix() -> None:
    day_view = _day_view()
    day_view["cards"] = [_factor_checklist_card()]
    checklist = _workspace(day_view)["matches"][0]["factor_checklist"]
    matrix = json.loads(
        Path(
            "docs/review_packages/SC21_FACTOR_INPUT_CHAIN/SC21_FACTOR_ROLE_AUTHORITY_MATRIX.json"
        ).read_text()
    )["fixture_factor_roles"]

    for row in checklist["factors"]:
        expected = matrix[row["factor_id"]]
        assert row["role_model_forecast"] == expected["role_model_forecast"]
        assert row["role_shadow_candidate"] == expected["role_shadow_candidate"]


def test_factor_checklist_preserves_source_truth_and_waiting_state() -> None:
    day_view = _day_view()
    card = _factor_checklist_card()
    card["factor_checklist_inputs"]["feature_contributions"] = [
        {
            "id": "F7_STRENGTH_FORM",
            "status": "INSUFFICIENT_DATA",
            "source": "internal_elo_v1",
            "source_group": "ratings",
            "collection_status": "INSUFFICIENT_RATING_HISTORY",
        },
        {
            "id": "F8_SQUAD_VALUE",
            "status": "UNAVAILABLE",
            "source": "team_value_mapping",
            "source_group": "squad_value",
            "collection_status": "MAPPING_MISSING",
        },
    ]
    day_view["cards"] = [card]

    checklist = _workspace(day_view)["matches"][0]["factor_checklist"]
    by_id = {row["factor_id"]: row for row in checklist["factors"] if row.get("market") is None}

    assert by_id["F7_STRENGTH_FORM"]["cause"] == "NOT_MATERIALIZED"
    assert by_id["F7_STRENGTH_FORM"]["permanence"] == "UNKNOWN"
    assert by_id["F8_SQUAD_VALUE"]["cause"] == "SOURCE_NOT_CONFIGURED"
    assert by_id["F8_SQUAD_VALUE"]["permanence"] == "UNKNOWN"
    assert by_id["F10_LMM_V1"]["state"] == "WAITING"
    assert by_id["F10_LMM_V1"]["cause"] == "NOT_YET_DUE"
    assert by_id["F10_LMM_V1"]["next_window_at"] == "2026-08-10T09:00:00Z"
    assert all(
        row["permanence"] != "SELF_RESOLVING"
        for row in checklist["factors"]
        if row["factor_id"] in {"F7_STRENGTH_FORM", "F8_SQUAD_VALUE"}
    )


def test_factor_checklist_exposes_registry_policy_and_ledger_fact() -> None:
    day_view = _day_view()
    card = _factor_checklist_card()
    day_view["cards"] = [card]
    fixture_id = card["fixture_id"]
    ledger = {
        "state": "SETTLED",
        "capture_identity_hash": "a" * 64,
        "captured_at": "2026-08-09T01:00:00Z",
        "model_family": "W2_FOUR_FIELD_XG",
        "model_version": "w2-model-v1",
        "calibration_version": "cal-v1",
        "calibration_status": "AVAILABLE",
        "settled_at": "2026-08-10T01:00:00Z",
        "brier": 0.2,
        "log_loss": 0.4,
        "rps": 0.1,
    }

    checklist = _workspace(
        day_view,
        model_forecasts={fixture_id: ledger},
    )["matches"][0]["factor_checklist"]

    explanations = [
        row
        for row in checklist["factors"]
        if row["factor_id"] in {"F1_MARKET_MOVEMENT", "F2_BOOKMAKER_INTENT"}
    ]
    assert all(row["factor_lifecycle"] == "EXPLANATION_ONLY" for row in explanations)
    assert all(row["numeric_effect_enabled"] is False for row in explanations)
    assert checklist["ledger_fact"] == ledger
    assert checklist["conclusion_zh"].startswith("本场模型预测已结算；")
    assert "当前因子投影仅供对照" in checklist["conclusion_zh"]


def test_factor_checklist_uses_persisted_capture_xg_identity_as_authority() -> None:
    day_view = _day_view()
    card = _factor_checklist_card()
    card["factor_checklist_inputs"]["data_readiness"].update(
        {
            "xg": False,
            "xg_status": "PROVIDER_EMPTY_OR_UNAVAILABLE",
            "xg_home_match_count": 0,
            "xg_away_match_count": 0,
            "xg_snapshot_count": 0,
        }
    )
    day_view["cards"] = [card]
    ledger = {
        "state": "CAPTURED",
        "capture_identity_hash": "a" * 64,
        "captured_at": "2026-08-09T01:00:00Z",
        "model_family": "EXACT_DC_POISSON",
        "model_version": "model-v1",
        "calibration_version": "cal-v1",
        "calibration_status": "AVAILABLE",
        "four_field_xg": {
            "status": "READY",
            "identity_hash": "b" * 64,
            "home_snapshot_identity": "home-snapshot",
            "away_snapshot_identity": "away-snapshot",
            "home_match_count": 5,
            "away_match_count": 4,
        },
    }

    checklist = _workspace(
        day_view,
        model_forecasts={card["fixture_id"]: ledger},
    )["matches"][0]["factor_checklist"]
    xg = next(row for row in checklist["factors"] if row["factor_id"] == "F9_TRUE_XG")

    assert checklist["track_model_forecast"] == {
        "state": "READY",
        "blocking_factor_ids": [],
    }
    assert xg["state"] == "READY"
    assert xg["cause"] is None
    expected_evidence = {
        "as_of": "2026-08-09T01:00:00Z",
        "source": "model_forecast_capture.four_field_xg_identity",
        "sample_count": 4,
        "minimum_required": 3,
        "shortfall": 0,
        "home_sample_count": 5,
        "away_sample_count": 4,
        "home_shortfall": 0,
        "away_shortfall": 0,
        "rolling_snapshot_count": 2,
        "provider_unavailable_confirmed": False,
        "identity_hash": "b" * 64,
        "home_snapshot_identity": "home-snapshot",
        "away_snapshot_identity": "away-snapshot",
    }
    assert {key: xg["evidence"].get(key) for key in expected_evidence} == expected_evidence


def test_data_risk_excludes_enhancement_only_gaps() -> None:
    day_view = _day_view()
    card = _factor_checklist_card()
    card["missing_fields"] = ["ratings", "team_value"]
    card["risk_dimensions"]["DATA_RISK"] = {
        "dimension": "DATA_RISK",
        "status": "INCIDENT",
        "reason_codes": ["DATA_REQUIRED_INPUT_MISSING", "DATA_STATUS_BLOCKED"],
    }
    day_view["cards"] = [card]

    match = _workspace(day_view)["matches"][0]

    assert match["risks"]["DATA_RISK"]["status"] == "OK"
    assert match["factor_checklist"]["enhancement_quality"] == {
        "state": "DEGRADED",
        "missing_factor_ids": [
            "F3_REST_FITNESS",
            "F5_RECENT_AH_COVER",
            "F6_H2H",
            "F7_STRENGTH_FORM",
            "F8_SQUAD_VALUE",
        ],
    }


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
    assert first["runtime"]["market_price_attention_threshold_ratio"] == 0.02
    assert first["selected_fixture_id"] == "fixture-two"
    assert first["today_summary"]["primary_reason_counts"] == {}
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
        "factual_summary": (
            "尚无已落盘让球主盘/大小球主盘市场证据；"
            "无法生成走势或当前模型—市场比较；等待既有调度形成证据。"
        ),
        "readiness_status": "READY",
        "readiness_context": {
            "reason_code": None,
            "missing_fields": [],
            "stale_fields": [],
            "action": None,
        },
        "next_eval_at": None,
        "risks": {
            **_risks(),
            "COLLECTION_RISK": {
                "dimension": "COLLECTION_RISK",
                "status": "OK",
                "reason_codes": [],
                "explanation": "尚未到下一采集窗口，按既有计划正常等待",
                "assessment_status": "ASSESSED_CURRENT",
                "evidence_basis": "COLLECTION_WINDOW_NOT_YET_DUE",
                "source_as_of": "2026-08-09T01:00:00Z",
            },
        },
    }
    assert first["validation"]["history_replay"]["decision_summary"] == {
        "total_cards": 3,
        "lock_eligible_count": 3,
        "by_decision_tier": {"WATCH": 3},
        "by_data_status": {"READY": 3},
    }
    assert first["matches"][0]["outcome"] == {
        "is_finished": False,
        "is_tracked": False,
        "is_recorded": False,
        "public_semantics": {"scope": "MATCH", "cause": "NOT_YET_DUE"},
    }
    assert first["matches"][0]["market_collection"] == {
        "latest_snapshot_at": "2026-08-09T01:00:00Z",
        "latest_snapshot_checkpoint": "T24_OPEN_ODDS",
        "target_checkpoint": "T12_ODDS",
        "scheduled_at": "2026-08-09T14:30:00Z",
        "window_end_at": "2026-08-09T15:00:00Z",
        "overdue": False,
        "public_semantics": {"scope": "MATCH", "cause": "NOT_YET_DUE"},
    }
    assert first["matches"][0]["readiness"]["next_eval_at"] is None
    scoreline = first["matches"][0]["scoreline_reference"]
    assert scoreline["simulations_completed"] == 10_000
    assert scoreline["top3"] == [
        {
            "scoreline": "1-0",
            "unconditional_probability": 0.15,
            "sample_count": 1500,
        }
    ]
    assert first["validation"]["directional"]["market_direction_benchmark"] == ("NOT_DEFINED")
    assert {
        item["market_radar"]["markets"]["ASIAN_HANDICAP"]["snapshot_state"]
        for item in first["matches"]
    } == {
        "NO_TIMELINE_EVIDENCE",
        "ONE_OBSERVATION_NOT_A_TREND",
        "DISCRETE_REAL_PATH",
    }


def test_selected_fixture_is_order_independent_and_information_useful() -> None:
    day_view = _day_view()
    expected = _workspace(day_view)["selected_fixture_id"]
    day_view["cards"].reverse()

    assert expected == "fixture-two"
    assert _workspace(day_view)["selected_fixture_id"] == expected


def test_focus_is_derived_only_from_public_semantics_and_facts() -> None:
    empty = _day_view()
    empty["cards"] = []
    empty["degradation"] = {"state": "EMPTY_DAY"}
    empty["date_strip"][7].update(
        market_collection_window_status="EMPTY_PERSISTED_DAY",
        market_evidence_fixture_count=0,
        fixture_count=0,
        competition_count=0,
        upcoming_fixture_count=0,
        persisted_inventory_status="EMPTY_PERSISTED_DAY",
        persisted_competition_coverage_count=0,
    )
    empty_payload = _workspace(empty)
    assert empty_payload["selected_fixture_id"] is None
    assert empty_payload["global_focus"]["reason_code"] == "NO_FIXTURES_IN_FOOTBALL_DAY"
    assert empty_payload["global_focus"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": None,
    }

    calm = _day_view()
    for card in calm["cards"]:
        card["market_radar"]["markets"]["ASIAN_HANDICAP"] = _market(2)
        card["market_radar"]["markets"]["TOTALS"] = _market(2)
        card["intelligence_state"] = "MARKET_STABLE"
    calm_payload = _workspace(calm)
    assert calm_payload["selected_fixture_id"] is None
    assert calm_payload["global_focus"]["reason_code"] == "NO_PRIORITY_REVIEW_ITEMS"

    blocked = _day_view()
    blocked["degradation"] = {
        "state": "BLOCKED_DAY",
        "reason_code": "COLLECTION_PROVIDER_EMPTY",
    }
    blocked["date_strip"][7]["market_collection_window_status"] = (
        "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY"
    )
    blocked["date_strip"][7]["market_evidence_fixture_count"] = 0
    for card in blocked["cards"]:
        card["intelligence_state"] = "COLLECTION_INCIDENT"
        card["intelligence_reason_codes"] = ["COLLECTION_PROVIDER_EMPTY"]
        card["market_radar"]["markets"]["ASIAN_HANDICAP"] = _market(0)
        card["market_radar"]["markets"]["TOTALS"] = _market(0)
    blocked_payload = _workspace(blocked)
    assert blocked_payload["selected_fixture_id"] is None
    assert blocked_payload["global_focus"]["reason_code"] == "AWAITING_COLLECTION"
    assert blocked_payload["global_focus"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "AWAITING_COLLECTION",
    }
    assert blocked_payload["today_summary"]["priority_match_count"] == 0
    assert blocked_payload["today_summary"]["primary_reason_counts"] == {}
    assert blocked_payload["global_focus"]["affected_fixture_count"] == 3

    mixed = deepcopy(blocked)
    mixed["cards"][0]["market_radar"]["markets"]["ASIAN_HANDICAP"] = _market(1)
    mixed["cards"][0]["market_radar"]["markets"]["TOTALS"] = _market(1)
    mixed_payload = _workspace(mixed)
    assert mixed_payload["global_focus"]["affected_fixture_count"] == 2
    assert mixed_payload["global_focus"]["factual_summary"] == (
        "所选比赛日已有 1 场市场证据；另有 2 场尚未就绪。"
    )


def test_schema_rejects_selected_fixture_outside_match_facts() -> None:
    payload = _workspace(_day_view())
    payload["selected_fixture_id"] = "not-in-response"

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_schema_allows_persisted_inventory_before_read_model_projection() -> None:
    payload = _workspace(_day_view())
    payload["date_strip"][7]["fixture_count"] += 1
    payload["date_strip"][7]["upcoming_fixture_count"] += 1
    payload["date_strip"][7]["market_evidence_fixture_count"] += 1

    validated = DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "persisted-inventory-ahead", **payload}
    )

    assert validated.date_strip[7].fixture_count == validated.today_summary.match_count + 1


def test_schema_rejects_projected_match_missing_from_persisted_inventory() -> None:
    payload = _workspace(_day_view())
    payload["date_strip"][7]["fixture_count"] -= 1
    payload["date_strip"][7]["upcoming_fixture_count"] -= 1
    payload["date_strip"][7]["market_evidence_fixture_count"] -= 1

    with pytest.raises(ValueError, match="inventory cannot omit projected matches"):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "persisted-inventory-behind", **payload}
        )


def test_schema_rejects_partial_market_evidence_claimed_as_available() -> None:
    payload = _workspace(_day_view())
    payload["date_strip"][7]["market_evidence_fixture_count"] = 2

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "partial-market-evidence", **payload}
        )


def test_schema_rejects_full_market_evidence_claimed_as_unavailable() -> None:
    payload = _workspace(_day_view())
    payload["date_strip"][7].update(
        market_collection_window_status="MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY",
        public_semantics={"scope": "SELECTED_DAY", "cause": "AWAITING_COLLECTION"},
    )

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "full-market-evidence-hidden", **payload}
        )


def test_schema_rejects_selected_day_count_drift() -> None:
    payload = _workspace(_day_view())
    payload["today_summary"]["match_count"] += 1

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "selected-day-count-drift", **payload}
        )


def test_primary_reason_grouping_counts_each_match_once() -> None:
    day_view = _day_view()
    card = day_view["cards"][2]
    card["intelligence_state"] = "MODEL_DIAGNOSTIC_WARNING"
    card["market_radar"]["markets"]["ASIAN_HANDICAP"]["movement"] = {
        "status": "LINE_MOVEMENT",
        "from_captured_at": "2026-08-09T00:00:00Z",
        "to_captured_at": "2026-08-09T01:00:00Z",
        "line_delta": "-0.25",
        "price_delta": {"HOME": 0.0, "AWAY": 0.0},
        "probability_delta": {"HOME": 0.0, "AWAY": 0.0},
    }

    payload = _workspace(day_view)
    match = next(item for item in payload["matches"] if item["fixture_id"] == "fixture-two")

    assert match["priority_reason_primary"] == "MARKET_MOVEMENT"
    assert match["priority_reason_secondary"] == ["MODEL_DIAGNOSTIC"]
    assert payload["today_summary"]["priority_match_count"] == 1
    assert payload["today_summary"]["primary_reason_counts"] == {"MARKET_MOVEMENT": 1}


def test_price_noise_below_two_percent_does_not_enter_priority() -> None:
    day_view = _day_view()
    card = day_view["cards"][2]
    market = card["market_radar"]["markets"]["ASIAN_HANDICAP"]
    market["current"]["prices"] = {"HOME": 1.80, "AWAY": 1.97}
    market["movement"] = {
        "status": "PRICE_MOVEMENT",
        "from_captured_at": "2026-08-09T00:00:00Z",
        "to_captured_at": "2026-08-09T01:00:00Z",
        "line_delta": "0",
        "price_delta": {"HOME": -0.01, "AWAY": 0.02},
        "probability_delta": {"HOME": 0.0, "AWAY": 0.0},
    }

    payload = _workspace(day_view)
    match = next(item for item in payload["matches"] if item["fixture_id"] == "fixture-two")

    assert match["priority_reason_primary"] is None
    assert payload["today_summary"]["primary_reason_counts"] == {}


def test_price_movement_at_or_above_two_percent_enters_priority() -> None:
    day_view = _day_view()
    card = day_view["cards"][2]
    market = card["market_radar"]["markets"]["ASIAN_HANDICAP"]
    market["current"]["prices"] = {"HOME": 2.00, "AWAY": 1.90}
    market["movement"] = {
        "status": "PRICE_MOVEMENT",
        "from_captured_at": "2026-08-09T00:00:00Z",
        "to_captured_at": "2026-08-09T01:00:00Z",
        "line_delta": "0",
        "price_delta": {"HOME": 0.04, "AWAY": 0.0},
        "probability_delta": {"HOME": 0.0, "AWAY": 0.0},
    }

    payload = _workspace(day_view)
    match = next(item for item in payload["matches"] if item["fixture_id"] == "fixture-two")

    assert match["priority_reason_primary"] == "MARKET_MOVEMENT"


def test_trend_and_cross_sectional_statuses_are_independent() -> None:
    day_view = _day_view()
    day_view["cards"] = [_card("fixture-one", 1)]
    market = _workspace(day_view)["matches"][0]["market_radar"]["markets"]["ASIAN_HANDICAP"]

    assert market["trend_evidence_status"] == "INSUFFICIENT"
    assert market["cross_sectional_comparison_status"] == "AVAILABLE"
    assert market["latest_snapshot_at"] == "2026-08-09T00:00:00Z"


def test_bookmaker_count_change_without_line_or_price_change_remains_stable() -> None:
    day_view = _day_view()
    source = day_view["cards"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]
    source["timeline"]["points"][1]["bookmaker_count"] = 9

    market = _workspace(day_view)["matches"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]

    assert market["movement"]["status"] == "STABLE"
    assert market["trend_evidence_status"] == "AVAILABLE"


def test_ready_scoreline_fails_closed_when_identity_or_model_readiness_is_missing() -> None:
    missing_identity = _day_view()
    missing_identity["cards"][0]["competition_id"] = None
    assert _workspace(missing_identity)["matches"][0]["scoreline_reference"]["status"] == (
        "UNAVAILABLE"
    )

    prior_only = _day_view()
    prior_only["cards"][0]["simulation"]["simulation"]["calibration_status"] = "BASELINE_PRIOR"
    assert _workspace(prior_only)["matches"][0]["scoreline_reference"]["status"] == ("UNAVAILABLE")


def test_lineup_before_expected_window_is_not_a_priority_reason() -> None:
    day_view = _day_view()
    card = _card("too-early", 0)
    card["lineup_requirement"] = "NOT_EXPECTED_YET"
    card["data_refresh"]["lineups_status"] = "PROVIDER_EMPTY"
    day_view["cards"] = [card]

    match = _workspace(day_view)["matches"][0]

    assert match["priority_reason_primary"] is None
    assert "LINEUP_PENDING" not in match["priority_reason_secondary"]


def test_global_model_quality_uses_exact_freshness_boundary_and_fails_closed() -> None:
    day_view = _day_view()
    day_view["performance"]["forward_ledger"]["checkpoint_metadata"] = {
        "checkpoint_key": "performance:cohort:all",
        "checkpoint_generated_at": "2026-08-09T02:00:00Z",
    }
    day_view["generated_at"] = "2026-08-10T02:00:00Z"

    current = _workspace(day_view)["global_model_quality"]
    assert current["status"] == "AVAILABLE"
    assert current["model_log_loss"] == 0.61

    day_view["generated_at"] = "2026-08-10T02:00:01Z"
    stale = _workspace(day_view)["global_model_quality"]
    assert stale["status"] == "STALE"
    assert stale["model_log_loss"] is None

    day_view["generated_at"] = "2026-08-09T02:00:01Z"
    day_view["performance"]["forward_ledger"]["probability_validation"]["market_log_loss"] = None
    incomplete = _workspace(day_view)["global_model_quality"]
    assert incomplete["status"] == "INCOMPLETE"
    assert incomplete["checkpoint_generated_at"] == "2026-08-09T02:00:00Z"
    assert incomplete["model_log_loss"] is None

    del day_view["performance"]["forward_ledger"]["checkpoint_metadata"]
    missing = _workspace(day_view)["global_model_quality"]
    assert missing["status"] == "NOT_AVAILABLE"
    assert missing["checkpoint_generated_at"] is None


def test_postdeploy_real_shape_uses_stale_evidence_and_scopes_raw_blocked_health() -> None:
    day_view = _day_view()
    day_view["degradation"] = {"state": "BLOCKED_DAY", "reason_code": "BLOCKED_DAY"}
    zero_one = _card("zero-one", 0)
    zero_two = _card("zero-two", 0)
    stale = _card("stale-useful", 2)
    for card in (zero_one, zero_two):
        card["intelligence_state"] = "DATA_INCOMPLETE"
        card["intelligence_reason_codes"] = [
            "DATA_IDENTITY_NOT_READY",
            "DATA_MARKET_TIMELINE_INSUFFICIENT",
        ]
        card["data_status"] = "BLOCKED"
        card["market_radar"]["markets"]["TOTALS"] = _market(0)
    stale["intelligence_state"] = "DATA_INCOMPLETE"
    stale["intelligence_reason_codes"] = [
        "DATA_FIELD_STALE",
        "DATA_IDENTITY_NOT_READY",
        "MODEL_SIMULATION_NOT_READY",
    ]
    stale["data_status"] = "BLOCKED"
    stale["market_radar"]["markets"]["ASIAN_HANDICAP"]["current"]["freshness"] = {"status": "STALE"}
    stale["market_radar"]["markets"]["ASIAN_HANDICAP"]["movement"]["status"] = "LINE_MOVEMENT"
    stale["risk_dimensions"]["DATA_RISK"] = {
        "dimension": "DATA_RISK",
        "status": "INCIDENT",
        "reason_codes": [
            "DATA_FIELD_STALE",
            "DATA_IDENTITY_NOT_READY",
            "DATA_REQUIRED_INPUT_MISSING",
        ],
        "explanation": "DATA FIELD STALE",
    }
    day_view["cards"] = [zero_one, stale, zero_two]

    payload = _workspace(day_view)
    focused = next(
        match
        for match in payload["matches"]
        if match["fixture_id"] == payload["selected_fixture_id"]
    )

    assert payload["selected_fixture_id"] == "stale-useful"
    assert payload["data_operations"]["system_health"] == "BLOCKED_DAY"
    assert payload["today_summary"]["primary_reason_counts"] == {"MARKET_MOVEMENT": 1}
    assert focused["priority_reason_primary"] == "MARKET_MOVEMENT"
    assert focused["priority_reason_secondary"] == [
        "CANDIDATE_INPUT_NOT_READY",
    ]
    assert payload["matches"][0]["priority_reason_primary"] is None
    assert payload["matches"][0]["priority_reason_secondary"] == ["DATA_INCOMPLETE"]
    assert focused["factual_summary"] == payload["attention"][1]["factual_summary"]
    assert "已就绪市场可进行模型—市场诊断" in focused["factual_summary"]
    assert focused["risks"]["DATA_RISK"]["explanation"] == (
        "数据字段已超过新鲜度边界；比赛或盘口身份尚未完成；另有 1 项技术原因"
    )
    assert "DATA FIELD STALE" not in focused["risks"]["DATA_RISK"]["explanation"]


def test_all_unusable_matches_fail_closed_to_selected_day_cause() -> None:
    day_view = _day_view()
    day_view["degradation"] = {"state": "BLOCKED_DAY"}
    day_view["date_strip"][7]["market_collection_window_status"] = (
        "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY"
    )
    day_view["date_strip"][7]["market_evidence_fixture_count"] = 0
    for card in day_view["cards"]:
        card["intelligence_state"] = "DATA_INCOMPLETE"
        card["data_status"] = "BLOCKED"
        card["market_radar"]["markets"]["ASIAN_HANDICAP"] = _market(0)
        card["market_radar"]["markets"]["TOTALS"] = _market(0)

    payload = _workspace(day_view)

    assert payload["selected_fixture_id"] is None
    assert payload["global_focus"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "AWAITING_COLLECTION",
    }


def test_schema_rejects_unknown_public_status_field() -> None:
    payload = _workspace(_day_view())
    payload["data_operations"]["public_" + "system_health"] = "DAY_BLOCKED"

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_public_market_readiness_ignores_retired_fixed_age_source_status() -> None:
    day_view = _day_view()
    market = day_view["cards"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]
    market["current"]["freshness"] = {"status": "STALE"}

    payload = _workspace(day_view)
    match = payload["matches"][2]
    radar = match["market_radar"]["markets"]["ASIAN_HANDICAP"]

    assert radar["status"] == "READY"
    assert radar["source_status"] == "READY"
    assert radar["bookmaker_pair_count"] == 4
    assert radar["quote_row_count"] == radar["observation_count"] == 8
    assert match["market_fact"]["status"] == "READY"
    assert match["market_fact"]["source_status"] == "READY"
    assert match["model_lab"]["market"]["ASIAN_HANDICAP"]["status"] == "READY"
    assert match["model_lab"]["market"]["ASIAN_HANDICAP"]["source_status"] == "READY"


def test_market_quote_age_is_recomputed_at_workspace_generation_time() -> None:
    day_view = _day_view()
    day_view["generated_at"] = "2026-08-09T09:00:00Z"
    source = day_view["cards"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]
    source["current"]["freshness"] = {
        "status": "COMPLETE",
        "age_seconds": 0,
        "max_age_seconds": 3600,
    }

    match = _workspace(day_view)["matches"][2]
    market = match["market_radar"]["markets"]["ASIAN_HANDICAP"]

    assert market["latest_snapshot_at"] == "2026-08-09T01:00:00Z"
    assert market["quote_age_seconds"] == 8 * 3600
    assert market["status"] == "READY"
    assert market["eligibility"]["observation_status"] == "AVAILABLE"
    assert market["eligibility"]["cross_sectional_comparison_status"] == "AVAILABLE"


def test_market_quote_age_clock_conflict_is_not_invented() -> None:
    day_view = _day_view()
    day_view["generated_at"] = "2026-08-09T00:30:00Z"
    source = day_view["cards"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]
    source["current"]["freshness"] = {
        "status": "COMPLETE",
        "age_seconds": 0,
        "max_age_seconds": 3600,
    }

    market = _workspace(day_view)["matches"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]

    assert market["status"] == "READY"
    assert market["quote_age_seconds"] is None


def test_retired_market_freshness_payload_is_not_public() -> None:
    day_view = _day_view()
    day_view["cards"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]["current"]["freshness"] = {
        "status": "UNKNOWN"
    }

    market = _workspace(day_view)["matches"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]

    assert market["status"] == "READY"
    assert market["source_status"] == "READY"
    assert "freshness" not in market


def test_workspace_schema_rejects_retired_market_freshness_field() -> None:
    payload = _workspace(_day_view())
    market = payload["matches"][2]["market_radar"]["markets"]["ASIAN_HANDICAP"]
    market["freshness"] = {"status": "STALE"}

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_workspace_schema_rejects_competing_public_market_readiness() -> None:
    payload = _workspace(_day_view())
    payload["matches"][2]["model_lab"]["market"]["ASIAN_HANDICAP"]["status"] = "INSUFFICIENT"

    with pytest.raises(ValueError, match="market readiness must match"):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


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
        item["formal_recommendation"] == {"status": "OFF", "reason": "PRODUCT_AUTHORITY_DISABLED"}
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
    assert validation["tournament_performance"][0]["canonical_competition_id"] == ("world_cup_2026")


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


def test_market_eligibility_preserves_ah_ou_partial_truth_without_cross_contamination() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    card["intelligence_state"] = "DATA_INCOMPLETE"
    card["market_radar"]["markets"]["ASIAN_HANDICAP"] = _market(2)
    card["market_radar"]["markets"]["ASIAN_HANDICAP"]["current"]["bookmaker_count"] = 1
    card["market_radar"]["markets"]["TOTALS"] = _market(2)
    card["market_radar"]["markets"]["TOTALS"]["current"]["bookmaker_count"] = 7
    card["model_lab"]["markets"] = {
        "ASIAN_HANDICAP": {
            "status": "INSUFFICIENT_BOOKMAKER_DEPTH",
            "blockers": ["INSUFFICIENT_BOOKMAKER_DEPTH"],
        },
        "TOTALS": {
            "status": "MODEL_NOT_READY",
            "blockers": ["MODEL_SIMULATION_NOT_READY"],
        },
    }
    card["market_candidates"] = {
        key: {
            "quote_status": "INCOMPLETE",
            "quote_usage": "REFERENCE_ONLY",
            "quote_identity": {"identity_status": "INCOMPLETE"},
            "model_status": "NOT_READY",
            "blockers": ["QUOTE_NOT_EXECUTABLE"],
        }
        for key in ("ah", "ou")
    }

    match = _workspace(day_view)["matches"][0]
    ah = match["market_radar"]["markets"]["ASIAN_HANDICAP"]["eligibility"]
    totals = match["market_radar"]["markets"]["TOTALS"]["eligibility"]

    assert ah["observation_status"] == totals["observation_status"] == "AVAILABLE"
    assert ah["model_diagnostic_status"] == "INSUFFICIENT_BOOKMAKER_DEPTH"
    assert totals["model_diagnostic_status"] == "MODEL_NOT_READY"
    assert ah["candidate_quote_lock_status"] == "NOT_READY"
    assert totals["candidate_quote_lock_status"] == "NOT_READY"
    assert match["readiness"]["market_aggregate_status"] == "NOT_READY"
    assert match["readiness"]["market_evidence_status"] == "AVAILABLE"
    assert match["readiness"]["candidate_input_status"] == "NOT_READY"
    assert match["priority_reason_secondary"] == ["CANDIDATE_INPUT_NOT_READY"]
    assert (
        "可比较模型尚未就绪（需已验证校准），暂不进行模型—市场比较"
        in match["factual_summary"]
    )


def test_completed_no_edge_evaluations_take_precedence_over_calibration_gap() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    checkpoints = [
        ("T3_ODDS", "2026-08-10T07:04:31Z"),
        ("T60_ODDS_LINEUPS", "2026-08-10T09:02:28Z"),
        ("T45_ODDS", "2026-08-10T09:17:02Z"),
        ("T-30m_VALIDATION_LOCK", "2026-08-10T09:31:31Z"),
        ("T15_ODDS", "2026-08-10T09:46:10Z"),
    ]
    card["dynamic_prematch"] = {
        "versions": [
            {
                "checkpoint": checkpoint,
                "evaluated_at": evaluated_at,
                "market": market,
                "state": "SUPERSEDED" if checkpoint != "T15_ODDS" else "NO_EDGE_CURRENT",
                "original_state": "NO_EDGE_CURRENT",
            }
            for _, evaluated_at in checkpoints
            for market in ("ASIAN_HANDICAP", "TOTALS")
            for checkpoint in ("capture",)
        ]
        + [
            {
                "checkpoint": "capture",
                "evaluated_at": "2026-08-10T04:01:00Z",
                "market": market,
                "state": "SUPERSEDED",
                "original_state": "ANALYSIS_PICK_ACTIVE",
            }
            for market in ("ASIAN_HANDICAP", "TOTALS")
        ]
    }

    match = _workspace(day_view)["matches"][0]

    assert match["evaluation_execution"] == {
        "status": "NO_EDGE",
        "checkpoint_count": 5,
        "market_evaluation_count": 10,
        "checkpoints": ["T-3h", "T-60m", "T-45m", "T-30m", "T-15m"],
        "markets": ["ASIAN_HANDICAP", "TOTALS"],
        "summary_zh": (
            "已评估 5 次（T-3h / T-60m / T-45m / T-30m / T-15m），"
            "两个市场均为 NO_EDGE —— 模型与市场看法一致，无可利用价差。"
            "模型—市场对比图需已验证校准，暂不绘制。"
        ),
    }
    assert match["factual_summary"] == match["evaluation_execution"]["summary_zh"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("market_aggregate_status", "PARTIAL", "market aggregate"),
        ("market_evidence_status", "NOT_READY", "market evidence"),
    ),
)
def test_schema_rejects_cross_panel_market_readiness_contradictions(
    field: str,
    value: str,
    message: str,
) -> None:
    payload = _workspace(_day_view())
    payload["matches"][2]["readiness"][field] = value

    with pytest.raises(ValueError, match=message):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": f"contradictory-{field}", **payload}
        )


def test_data_risk_names_missing_inputs_and_clearance_condition() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    card["missing_fields"] = ["lineups", "xg", "ratings", "team_value"]
    card["risk_dimensions"]["DATA_RISK"] = {
        "dimension": "DATA_RISK",
        "status": "INCIDENT",
        "reason_codes": ["DATA_REQUIRED_INPUT_MISSING", "DATA_STATUS_BLOCKED"],
    }

    explanation = _workspace(day_view)["matches"][0]["risks"]["DATA_RISK"]["explanation"]

    assert explanation == "待补齐：模型核心输入 xG；既有采集或模型投影形成后解除"


def test_data_risk_keeps_lineup_missing_after_collection_is_due() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    card["missing_fields"] = ["lineups", "xg"]
    card["risk_dimensions"]["DATA_RISK"] = {
        "dimension": "DATA_RISK",
        "status": "INCIDENT",
        "reason_codes": ["DATA_REQUIRED_INPUT_MISSING", "DATA_STATUS_BLOCKED"],
    }
    card["data_refresh"]["lineup_collection"]["public_semantics"]["cause"] = "AWAITING_COLLECTION"

    explanation = _workspace(day_view)["matches"][0]["risks"]["DATA_RISK"]["explanation"]

    assert explanation == "待补齐：模型核心输入 xG；既有采集或模型投影形成后解除"


def test_not_yet_due_lineup_alone_is_not_an_abnormal_data_risk() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    card["missing_fields"] = ["lineups"]
    card["risk_dimensions"]["DATA_RISK"] = {
        "dimension": "DATA_RISK",
        "status": "INCIDENT",
        "reason_codes": ["DATA_REQUIRED_INPUT_MISSING", "DATA_STATUS_BLOCKED"],
    }

    risk = _workspace(day_view)["matches"][0]["risks"]["DATA_RISK"]

    assert risk["status"] == "OK"
    assert risk["explanation"] == "尚无到期的数据输入缺口"


def test_schema_rejects_not_yet_due_lineup_as_anomalous_missing_input() -> None:
    payload = _workspace(_day_view())
    match = payload["matches"][0]
    match["readiness"]["missing_fields"] = ["lineups", "xg"]
    match["risks"]["DATA_RISK"]["explanation"] = "待补齐：首发、xG"

    with pytest.raises(
        ValueError, match="not-yet-due lineups cannot be an anomalous missing input"
    ):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "lineup-cross-panel-contradiction", **payload}
        )


@pytest.mark.parametrize(
    ("ah_depth", "ou_depth", "same_snapshot", "expected"),
    (
        (1, 7, True, True),
        (5, 7, True, False),
        (1, 7, False, False),
    ),
)
def test_market_depth_asymmetry_is_a_non_blocking_same_snapshot_technical_signal(
    ah_depth: int,
    ou_depth: int,
    same_snapshot: bool,
    expected: bool,
) -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    for name, depth in (("ASIAN_HANDICAP", ah_depth), ("TOTALS", ou_depth)):
        market = _market(1)
        market["current"]["bookmaker_count"] = depth
        market["timeline"]["points"][0]["bookmaker_count"] = depth
        card["market_radar"]["markets"][name] = market
    if not same_snapshot:
        card["market_radar"]["markets"]["TOTALS"]["timeline"]["points"][0]["captured_at"] = (
            "2026-08-09T02:00:00Z"
        )

    match = _workspace(day_view)["matches"][0]
    handicap = match["market_radar"]["markets"]["ASIAN_HANDICAP"]

    assert ("MARKET_DEPTH_ASYMMETRY" in handicap["reason_codes"]) is expected
    assert match["readiness"]["market_aggregate_status"] == "NOT_READY"


def test_public_team_label_never_silently_uses_raw_english() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    card["home_team_name"] = "Banfield"
    card["home_team_id"] = "476"
    card["away_team_name"] = "Belgrano Cordoba"
    card["away_team_id"] = "478"

    match = _workspace(day_view)["matches"][0]

    assert match["home_team_label"] == {
        "display_name": "主队（身份待确认：476）",
        "state": "IDENTITY_UNRESOLVED",
        "canonical_team_id": None,
        "provider_team_id": "476",
        "public_semantics": {"scope": "MATCH", "cause": "IDENTITY_UNRESOLVED"},
        "technical": {"raw_provider_name": "Banfield"},
    }
    assert match["away_team_label"]["display_name"] == "客队（身份待确认：478）"
    assert "Banfield" not in match["home_team_label"]["display_name"]


def test_known_team_without_chinese_label_keeps_readable_raw_name() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    card["home_team_name"] = "Rosenborg"
    card["home_team_label"] = {
        "display_name": None,
        "state": "CANONICAL_IDENTITY_READY_LABEL_MISSING",
        "canonical_team_id": "w2:team:api_football:331",
        "provider_team_id": "331",
        "raw_provider_name": "Rosenborg",
    }

    label = _workspace(day_view)["matches"][0]["home_team_label"]

    assert label["display_name"] == "Rosenborg"
    assert label["public_semantics"] == {"scope": "MATCH", "cause": "LABEL_MISSING"}


def test_pending_owner_review_team_label_is_visible_and_counted() -> None:
    day_view = _day_view()
    card = day_view["cards"][0]
    card["home_team_label"] = {
        "display_name": "AIK索尔纳",
        "state": "CHINESE_LABEL_PENDING_OWNER_REVIEW",
        "canonical_team_id": "w2:team:api_football:377",
        "provider_team_id": "377",
        "raw_provider_name": "AIK Stockholm",
    }

    payload = _workspace(day_view)
    label = payload["matches"][0]["home_team_label"]

    assert label["display_name"] == "AIK索尔纳"
    assert label["public_semantics"] == {
        "scope": "MATCH",
        "cause": "LABEL_PENDING_OWNER_REVIEW",
    }
    assert payload["today_summary"]["pending_owner_review_team_count"] == 1
    DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "pending-label-contract", **payload}
    )


def test_scope_and_cause_separate_future_day_from_cumulative_validation() -> None:
    day_view = _day_view()
    day_view["date_strip"][7]["market_collection_window_status"] = (
        "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW"
    )

    payload = _workspace(day_view)

    assert payload["date_strip"][7]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "NOT_YET_DUE",
    }
    assert payload["validation"]["history_replay"]["record_kind"] == "FORWARD_RECORD"
    assert payload["validation"]["history_replay"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "NOT_YET_DUE",
    }
    assert payload["validation"]["history_replay"]["status"] == "FORWARD_RECORD"
    assert "MISSING_OUTCOMES" not in payload["validation"]["history_replay"]["replay_gaps"]
    assert payload["validation"]["forward_validation_records"]["public_semantics"] == {
        "scope": "CROSS_DAY_CUMULATIVE",
        "cause": None,
    }


def test_past_due_upcoming_status_awaits_update_instead_of_claiming_not_yet_due() -> None:
    day_view = _day_view()
    day_view["generated_at"] = "2026-08-11T18:00:00Z"

    payload = _workspace(day_view)

    assert all(
        match["outcome"]["public_semantics"] == {"scope": "MATCH", "cause": "AWAITING_COLLECTION"}
        for match in payload["matches"]
    )
    replay = payload["validation"]["history_replay"]
    assert replay["status"] == "FORWARD_RECORD"
    assert replay["record_kind"] == "FORWARD_RECORD"
    assert replay["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "AWAITING_COLLECTION",
    }
    assert "MISSING_OUTCOMES" not in replay["replay_gaps"]
    assert DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "past-due-status", **payload}
    )


@pytest.mark.parametrize(
    ("status", "kickoff", "as_of", "tracked", "recorded", "cause"),
    [
        (
            "UPCOMING",
            "2026-08-09T14:30:00Z",
            "2026-08-09T17:29:59Z",
            False,
            False,
            "NOT_YET_DUE",
        ),
        (
            "UPCOMING",
            "2026-08-09T14:30:00Z",
            "2026-08-09T17:30:00Z",
            False,
            False,
            "AWAITING_COLLECTION",
        ),
        (
            "POSTPONED",
            "2026-08-09T14:30:00Z",
            "2026-08-09T17:30:00Z",
            False,
            False,
            "UNASSESSED",
        ),
        (None, "2026-08-09T14:30:00Z", "2026-08-09T17:30:00Z", False, False, "UNASSESSED"),
        ("UPCOMING", None, "2026-08-09T17:30:00Z", False, False, "UNASSESSED"),
        ("FT", "2026-08-09T14:30:00Z", "2026-08-09T17:30:00Z", False, False, "UNASSESSED"),
        (
            "FT",
            "2026-08-09T14:30:00Z",
            "2026-08-09T17:30:00Z",
            True,
            False,
            "AWAITING_COLLECTION",
        ),
        ("FT", "2026-08-09T14:30:00Z", "2026-08-09T17:30:00Z", True, True, None),
    ],
)
def test_match_outcome_cause_uses_one_temporal_authority(
    status: str | None,
    kickoff: str | None,
    as_of: str,
    tracked: bool,
    recorded: bool,
    cause: str | None,
) -> None:
    assert (
        outcome_public_cause(
            status=status,
            kickoff_utc=kickoff,
            as_of=as_of,
            is_tracked=tracked,
            is_recorded=recorded,
        )
        == cause
    )


def test_schema_rejects_not_yet_due_after_result_collection_delay() -> None:
    day_view = _day_view()
    day_view["generated_at"] = "2026-08-11T18:00:00Z"
    payload = _workspace(day_view)
    payload["matches"][0]["outcome"]["public_semantics"]["cause"] = "NOT_YET_DUE"

    with pytest.raises(ValueError, match="status and time"):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "past-due-conflict", **payload}
        )


def test_finished_match_missing_outcome_is_awaiting_collection() -> None:
    day_view = _day_view()
    for card in day_view["cards"]:
        card["status"] = "FT"
        card["outcome_tracked"] = True

    replay = {
        "replay_status": "MISSING_OUTCOMES",
        "cards": [
            {
                "fixture_id": card["fixture_id"],
                "outcome_tracked": True,
                "outcome_status": "MISSING_OUTCOME",
            }
            for card in day_view["cards"]
        ],
        "known_at_summary": {},
        "reason_summary": [],
        "outcome_tracking_summary": {
            "tracked_fixture_ids": [card["fixture_id"] for card in day_view["cards"]],
            "matched_fixture_ids": [],
            "missing_outcome_fixture_ids": [card["fixture_id"] for card in day_view["cards"]],
            "missing_outcome_count": 3,
        },
        "card_hash_checks": [],
        "decision_summary": {
            "total_cards": 3,
            "lock_eligible_count": 0,
            "by_decision_tier": {},
            "by_data_status": {},
        },
        "replay_gaps": ["MISSING_OUTCOMES"],
    }
    payload = _workspace(day_view, replay=replay)

    assert payload["validation"]["history_replay"]["record_kind"] == "REPLAY"
    assert payload["validation"]["history_replay"]["public_semantics"] == {
        "scope": "SELECTED_DAY",
        "cause": "AWAITING_COLLECTION",
    }
    assert all(
        match["outcome"]["public_semantics"]["cause"] == "AWAITING_COLLECTION"
        for match in payload["matches"]
    )


@pytest.mark.parametrize(
    (
        "status",
        "tracked",
        "outcome_status",
        "replay_status",
        "replay_gaps",
        "expected",
    ),
    [
        (
            "NS",
            False,
            "OUTCOME_NOT_PRODUCED",
            "OUTCOMES_NOT_PRODUCED",
            [],
            (False, False, False, "NOT_YET_DUE"),
        ),
        (
            "NS",
            True,
            "OUTCOME_NOT_PRODUCED",
            "OUTCOMES_NOT_PRODUCED",
            [],
            (False, True, False, "NOT_YET_DUE"),
        ),
        (
            "FT",
            True,
            "MATCHED",
            "READY",
            [],
            (True, True, True, None),
        ),
        (
            "NS",
            True,
            "MATCHED",
            "READY",
            [],
            (True, True, True, None),
        ),
        (
            "FT",
            True,
            "MISSING_OUTCOME",
            "MISSING_OUTCOMES",
            ["MISSING_OUTCOMES"],
            (True, True, False, "AWAITING_COLLECTION"),
        ),
        (
            "FT",
            False,
            "NOT_TRACKED",
            "OUTCOMES_NOT_PRODUCED",
            [],
            (True, False, False, "UNASSESSED"),
        ),
    ],
)
def test_match_outcome_truth_table_is_derived_from_persisted_facts(
    status: str,
    tracked: bool,
    outcome_status: str,
    replay_status: str,
    replay_gaps: list[str],
    expected: tuple[bool, bool, bool, str | None],
) -> None:
    day_view = _day_view()
    card = day_view["cards"][2]
    card["status"] = status
    card["outcome_tracked"] = tracked
    day_view["cards"] = [card]
    day_view["date_strip"][7].update(
        fixture_count=1,
        competition_count=1,
        finished_fixture_count=1 if status == "FT" else 0,
        upcoming_fixture_count=0 if status == "FT" else 1,
        persisted_competition_coverage_count=1,
        market_evidence_fixture_count=1,
    )
    fixture_id = card["fixture_id"]
    recorded = outcome_status == "MATCHED"
    missing = outcome_status == "MISSING_OUTCOME"
    replay = {
        "replay_status": replay_status,
        "cards": [
            {
                "fixture_id": fixture_id,
                "outcome_tracked": tracked,
                "outcome_status": outcome_status,
            }
        ],
        "known_at_summary": {},
        "reason_summary": [],
        "outcome_tracking_summary": {
            "tracked_count": 1 if tracked else 0,
            "matched_outcome_count": 1 if recorded else 0,
            "missing_outcome_count": 1 if missing else 0,
            "tracked_fixture_ids": [fixture_id] if tracked else [],
            "matched_fixture_ids": [fixture_id] if recorded else [],
            "missing_outcome_fixture_ids": [fixture_id] if missing else [],
        },
        "card_hash_checks": [],
        "decision_summary": {
            "total_cards": 1,
            "lock_eligible_count": 0,
            "by_decision_tier": {},
            "by_data_status": {},
        },
        "replay_gaps": replay_gaps,
    }

    payload = _workspace(day_view, replay=replay)
    outcome = payload["matches"][0]["outcome"]

    assert (
        outcome["is_finished"],
        outcome["is_tracked"],
        outcome["is_recorded"],
        outcome["public_semantics"]["cause"],
    ) == expected
    assert outcome["public_semantics"]["scope"] == "MATCH"
    assert DashboardIntelligenceWorkspaceResponse.model_validate(
        {"request_id": "outcome-truth-table", **payload}
    )


def test_empty_selected_day_cannot_inherit_raw_replay_gaps() -> None:
    day_view = _day_view()
    day_view["cards"] = []

    payload = _workspace(day_view)

    assert payload["validation"]["history_replay"]["status"] == "EMPTY"
    assert payload["validation"]["history_replay"]["replay_gaps"] == []


@pytest.mark.parametrize(
    ("record_kind", "status", "cause", "replay_gaps"),
    [
        ("EMPTY", "MISSING_OUTCOMES", None, ["MISSING_OUTCOMES"]),
        ("FORWARD_RECORD", "MISSING_OUTCOMES", "NOT_YET_DUE", []),
        ("FORWARD_RECORD", "FORWARD_RECORD", "NOT_YET_DUE", ["MISSING_OUTCOMES"]),
        ("FORWARD_RECORD", "READY", "NOT_YET_DUE", []),
        ("REPLAY", "FORWARD_RECORD", None, []),
        ("REPLAY", "READY", "NOT_YET_DUE", []),
        ("REPLAY", "MISSING_OUTCOMES", None, ["MISSING_OUTCOMES"]),
        ("REPLAY", "MISSING_OUTCOMES", "AWAITING_COLLECTION", []),
        ("MIXED_RECORD", "OUTCOMES_NOT_PRODUCED", None, []),
        ("MIXED_RECORD", "FORWARD_RECORD", None, []),
        ("MIXED_RECORD", "READY", "AWAITING_COLLECTION", ["MISSING_OUTCOMES"]),
    ],
)
def test_schema_rejects_replay_state_that_conflicts_with_public_semantics(
    record_kind: str,
    status: str,
    cause: str | None,
    replay_gaps: list[str],
) -> None:
    payload = _workspace(_day_view())
    replay = payload["validation"]["history_replay"]
    replay.update(
        record_kind=record_kind,
        status=status,
        replay_gaps=replay_gaps,
        public_semantics={"scope": "SELECTED_DAY", "cause": cause},
    )

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_schema_rejects_outcome_fact_and_status_conflicts() -> None:
    payload = _workspace(_day_view())
    outcome = payload["matches"][0]["outcome"]
    outcome.update(
        is_finished=True,
        public_semantics={"scope": "MATCH", "cause": "UNASSESSED"},
    )

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "status-conflict", **payload}
        )


def test_schema_rejects_recorded_outcome_for_unfinished_match() -> None:
    payload = _workspace(_day_view())
    payload["matches"][0]["outcome"]["is_recorded"] = True

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "unfinished-recorded", **payload}
        )


def test_schema_rejects_day_record_kind_that_conflicts_with_match_outcomes() -> None:
    payload = _workspace(_day_view())
    payload["validation"]["history_replay"].update(
        record_kind="REPLAY",
        status="READY",
        replay_gaps=[],
        public_semantics={"scope": "SELECTED_DAY", "cause": None},
    )

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "record-kind-conflict", **payload}
        )


def test_schema_rejects_day_cause_that_conflicts_with_match_outcomes() -> None:
    day_view = _day_view()
    for card in day_view["cards"]:
        card["status"] = "FT"
        card["outcome_tracked"] = True
    fixture_ids = [card["fixture_id"] for card in day_view["cards"]]
    replay = {
        "replay_status": "READY",
        "cards": [
            {
                "fixture_id": fixture_id,
                "outcome_tracked": True,
                "outcome_status": "MATCHED",
            }
            for fixture_id in fixture_ids
        ],
        "known_at_summary": {},
        "reason_summary": [],
        "outcome_tracking_summary": {
            "tracked_count": len(fixture_ids),
            "matched_outcome_count": len(fixture_ids),
            "missing_outcome_count": 0,
            "tracked_fixture_ids": fixture_ids,
            "matched_fixture_ids": fixture_ids,
            "missing_outcome_fixture_ids": [],
        },
        "card_hash_checks": [],
        "decision_summary": {
            "total_cards": 3,
            "lock_eligible_count": 0,
            "by_decision_tier": {},
            "by_data_status": {},
        },
        "replay_gaps": [],
    }
    payload = _workspace(day_view, replay=replay)
    payload["validation"]["history_replay"].update(
        status="MISSING_OUTCOMES",
        replay_gaps=["MISSING_OUTCOMES"],
        public_semantics={"scope": "SELECTED_DAY", "cause": "AWAITING_COLLECTION"},
    )

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "record-cause-conflict", **payload}
        )


def test_schema_rejects_untyped_or_misspelled_outcome_summary_fields() -> None:
    payload = _workspace(_day_view())
    summary = payload["validation"]["history_replay"]["outcome_tracking_summary"]
    summary["tracked_fixture_count"] = summary.pop("tracked_count")

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "outcome-summary-typo", **payload}
        )


def test_schema_rejects_multi_day_workspace_window() -> None:
    payload = _workspace(_day_view())
    payload["window"] = "future"

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "multi-day-window", **payload}
        )


@pytest.mark.parametrize("field,value", [("scope", "WRONG_SCOPE"), ("cause", "WRONG_CAUSE")])
def test_schema_rejects_unknown_public_semantics(field: str, value: str) -> None:
    payload = _workspace(_day_view())
    payload["matches"][0]["home_team_label"]["public_semantics"][field] = value

    with pytest.raises(ValueError):
        DashboardIntelligenceWorkspaceResponse.model_validate(
            {"request_id": "test-request", **payload}
        )


def test_canonical_identity_and_approved_public_label_are_the_only_ready_path() -> None:
    fixture = SimpleNamespace(
        provider="api_football",
        competition_id="allsvenskan",
        season="2026",
        team_identity_status="PROVIDER_PRIMARY_READY",
        home_provider_team_id="370",
        home_w2_team_id="w2:team:api_football:370",
        payload={"home_team_name": "Sirius"},
    )
    canonical = {
        fixture.home_w2_team_id: SimpleNamespace(
            display_name="Sirius",
            payload={"public_zh_name": "天狼星"},
        )
    }
    ready = repository_module._public_team_label_from_identity(
        fixture=fixture,
        side="home",
        canonical=canonical,
        reviewed_labels={fixture.home_w2_team_id: "天狼星"},
    )
    label_missing = repository_module._public_team_label_from_identity(
        fixture=fixture,
        side="home",
        canonical=canonical,
        reviewed_labels={},
    )

    assert ready["state"] == "CHINESE_LABEL_READY"
    assert ready["display_name"] == "天狼星"
    assert ready["raw_provider_name"] == "Sirius"
    assert label_missing["state"] == "CANONICAL_IDENTITY_READY_LABEL_MISSING"
    assert label_missing["display_name"] is None


def test_pending_owner_review_label_is_visible_but_not_approved() -> None:
    fixture = SimpleNamespace(
        provider="api_football",
        competition_id="allsvenskan",
        season="2026",
        team_identity_status="PROVIDER_PRIMARY_READY",
        home_provider_team_id="377",
        home_w2_team_id="w2:team:api_football:377",
        payload={"home_team_name": "AIK Stockholm"},
    )
    pending = repository_module._public_team_label_from_identity(
        fixture=fixture,
        side="home",
        canonical={fixture.home_w2_team_id: SimpleNamespace()},
        reviewed_labels={},
        pending_labels={fixture.home_w2_team_id: "AIK索尔纳"},
    )

    assert pending == {
        "display_name": "AIK索尔纳",
        "state": "CHINESE_LABEL_PENDING_OWNER_REVIEW",
        "canonical_team_id": fixture.home_w2_team_id,
        "provider_team_id": "377",
        "raw_provider_name": "AIK Stockholm",
    }


def test_approved_public_label_authority_reuses_existing_product_labels() -> None:
    labels = reviewed_public_team_labels()
    fixture = SimpleNamespace(
        provider="api_football",
        competition_id="allsvenskan",
        season="2026",
        team_identity_status="PROVIDER_PRIMARY_READY",
        home_provider_team_id="370",
        home_w2_team_id="w2:team:api_football:370",
        payload={"home_team_name": "Sirius"},
    )
    canonical = {fixture.home_w2_team_id: SimpleNamespace(display_name="Sirius", payload={})}
    ready = repository_module._public_team_label_from_identity(
        fixture=fixture,
        side="home",
        canonical=canonical,
        reviewed_labels=labels,
    )

    assert ready["state"] == "CHINESE_LABEL_READY"
    assert ready["display_name"] == "天狼星"


def test_r18_eliteserien_candidates_are_owner_approved() -> None:
    labels = reviewed_public_team_labels()
    pending = pending_public_team_labels()

    assert pending == {}
    assert {
        team_id: labels[team_id]
        for team_id in (
            "w2:team:api_football:2149",
            "w2:team:api_football:319",
            "w2:team:api_football:325",
            "w2:team:api_football:326",
            "w2:team:api_football:329",
            "w2:team:api_football:332",
            "w2:team:api_football:333",
            "w2:team:api_football:757",
        )
    } == {
        "w2:team:api_football:2149": "费德列斯达",
        "w2:team:api_football:319": "布兰",
        "w2:team:api_football:325": "特罗姆瑟",
        "w2:team:api_football:326": "瓦勒伦加",
        "w2:team:api_football:329": "莫尔德",
        "w2:team:api_football:332": "桑纳菲尤尔",
        "w2:team:api_football:333": "萨尔普斯堡08",
        "w2:team:api_football:757": "阿勒桑",
    }


def test_r16_allsvenskan_candidates_remain_owner_approved() -> None:
    labels = reviewed_public_team_labels()
    pending = pending_public_team_labels()

    assert pending == {}
    assert {
        team_id: labels[team_id]
        for team_id in (
            "w2:team:api_football:2170",
            "w2:team:api_football:377",
        )
    } == {
        "w2:team:api_football:2170": "哥德堡盖斯",
        "w2:team:api_football:377": "AIK索尔纳",
    }


def test_owner_authorized_current_schedule_labels_are_all_approved() -> None:
    labels = reviewed_public_team_labels()

    expected = {
        "435": "河床",
        "437": "罗萨里奥中央",
        "445": "飓风队",
        "458": "阿根廷青年人",
        "474": "萨米恩托",
        "478": "科尔多瓦学院",
        "2432": "巴拉卡斯中央",
        "438": "萨斯菲尔德",
        "442": "国防与司法",
        "446": "拉努斯",
        "453": "阿根廷独立",
        "455": "图库曼竞技",
        "2424": "里奥夸尔托学生队",
        "193": "兹沃勒",
        "194": "阿贾克斯",
        "198": "海牙",
        "202": "格罗宁根",
        "209": "费耶诺德",
        "210": "海伦芬",
        "410": "前进之鹰",
        "415": "特温特",
        "533": "比利亚雷亚尔",
        "539": "莱万特",
        "540": "西班牙人",
        "4665": "桑坦德竞技",
        "544": "拉科鲁尼亚",
        "797": "埃尔切",
        "1595": "西雅图海湾人",
        "1597": "达拉斯FC",
        "1599": "费城联合",
        "1603": "温哥华白帽",
        "1604": "纽约城",
        "1607": "芝加哥火焰",
        "1617": "波特兰伐木者",
        "16489": "奥斯汀FC",
        "214": "马里迪莫",
        "215": "莫雷伦斯",
        "217": "布拉加",
        "230": "埃斯托里尔",
        "240": "阿罗卡",
        "242": "法马利康",
        "762": "吉尔维森特",
        "211": "本菲卡",
        "4716": "卡萨皮亚",
    }

    assert pending_public_team_labels() == {}
    assert {team_id: labels[f"w2:team:api_football:{team_id}"] for team_id in expected} == expected


def test_owner_authorized_public_label_review_closes_observed_gaps() -> None:
    labels = reviewed_public_team_labels()

    assert {
        team_id: labels[f"w2:team:api_football:{team_id}"]
        for team_id in (
            "124",
            "130",
            "2143",
            "225",
            "227",
            "331",
            "440",
            "441",
            "449",
            "794",
            "1065",
        )
    } == {
        "124": "弗鲁米嫩塞",
        "130": "格雷米奥",
        "2143": "KFUM奥斯陆",
        "225": "国民队",
        "227": "圣克拉拉",
        "331": "罗森博格",
        "440": "贝尔格拉诺",
        "441": "圣菲联合",
        "449": "班菲尔德",
        "794": "布拉干蒂诺红牛",
        "1065": "科尔多瓦中央",
    }


def test_sc19_public_label_authority_uses_runtime_config_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "identity" / "public_team_labels.zh-CN.v1.json"
    target.parent.mkdir()
    target.write_bytes(Path("config/identity/public_team_labels.zh-CN.v1.json").read_bytes())
    monkeypatch.setenv("W2_READINESS_CONFIG_PATH", str(tmp_path))
    get_settings.cache_clear()
    reviewed_public_team_labels.cache_clear()
    pending_public_team_labels.cache_clear()
    try:
        assert reviewed_public_team_labels()["w2:team:api_football:370"] == "天狼星"
    finally:
        reviewed_public_team_labels.cache_clear()
        pending_public_team_labels.cache_clear()
        get_settings.cache_clear()
