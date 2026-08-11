from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "w2.dashboard-intelligence-workspace.v1"
PRODUCT = "FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS"
PUBLIC_AUTHORITY = "NEW_INTELLIGENCE_WORKSPACE_ONLY"
SNAPSHOT_STATES = {
    0: "NO_TIMELINE_EVIDENCE",
    1: "ONE_OBSERVATION_NOT_A_TREND",
}
DOMAIN_CONTRACT = {
    "fixtures": ("AVAILABLE", "fixtures_checkpoint", "~15s"),
    "events": ("NOT_AVAILABLE", "not_projected", "~15s"),
    "statistics": ("PARTIAL", "data_refresh.statistics", "~1m"),
    "players": ("NOT_AVAILABLE", "not_projected", "~1m"),
    "lineups": ("PARTIAL_1_OF_13_VERIFIED", "data_refresh.lineups", "~15m"),
    "odds_prematch": ("AVAILABLE_WHEN_OBSERVED", "market_radar.current", "~3h"),
    "odds_live": ("FORBIDDEN_AS_BENCHMARK", "excluded", "~5s"),
    "injuries": ("PARTIAL", "data_refresh.injuries", "~4h"),
    "predictions": ("PARTIAL_NOT_PROJECTED", "not_projected", "~1h"),
    "standings": ("NOT_AVAILABLE", "not_projected", "~1h"),
    "teams_statistics": ("NOT_AVAILABLE", "not_projected", "~12h / ~2 daily"),
    "page_projection": ("AVAILABLE", "dashboard_day_view", "internal"),
}
AFFECTED_DOMAIN_ORDER = ("EVENT", "DATA", "MODEL", "COLLECTION", "MARKET")
PRIMARY_REASON_ORDER = {
    "STALE_MARKET_MEMORY": 0,
    "MARKET_MOVEMENT": 1,
    "MODEL_DIAGNOSTIC": 2,
}
ATTENTION_REASON_ORDER = {
    **PRIMARY_REASON_ORDER,
    "COLLECTION_INCIDENT": 3,
    "DATA_INCOMPLETE": 4,
    "CANDIDATE_INPUT_NOT_READY": 4,
    "LINEUP_PENDING": 5,
}
MODEL_QUALITY_MAX_AGE_SECONDS = 86_400
MARKET_PRICE_ATTENTION_THRESHOLD_RATIO = 0.02
RISK_REASON_LABELS = {
    "DATA_FIELD_STALE": "数据字段已超过新鲜度边界",
    "DATA_IDENTITY_NOT_READY": "比赛或盘口身份尚未完成",
    "DATA_MARKET_TIMELINE_INSUFFICIENT": "让球/大小球时间线证据不足",
    "DATA_REQUIRED_INPUT_MISSING": "必需输入尚未齐全",
    "DATA_STATUS_BLOCKED": "当前数据状态阻塞",
    "MODEL_SIMULATION_NOT_READY": "既有模型模拟尚未就绪",
    "MODEL_LAB_NOT_READY": "模型评估尚未就绪",
    "MODEL_OUTSIDE_MARKET_RANGE": "模型结果超出当前市场观测区间",
    "COLLECTION_ASSESSMENT_NOT_AVAILABLE": "尚无可用采集评估证据",
    "COLLECTION_ASSESSMENT_STALE": "采集评估证据已过期",
}


def build_dashboard_intelligence_workspace(
    day_view: Mapping[str, Any],
    *,
    replay: Mapping[str, Any],
    candidate_enabled: bool = False,
) -> dict[str, Any]:
    """Adapt existing bounded projections into the one final Dashboard read model."""
    cards = _mapping_list(day_view.get("cards"))
    matches = [_match(card, candidate_enabled=candidate_enabled) for card in cards]
    freshness = _mapping(day_view.get("freshness"))
    performance = _mapping(day_view.get("performance"))
    forward = _mapping(performance.get("forward_ledger"))
    for match in matches:
        primary, secondary = _priority_reasons(match)
        match["priority_reason_primary"] = primary
        match["priority_reason_secondary"] = secondary
        match["factual_summary"] = _match_factual_summary(match)
    day_mode, focus_type, focus_fixture_id = _focus_authority(day_view, matches)
    primary_reason_counts = {} if day_mode == "BLOCKED" else _primary_reason_counts(matches)
    global_focus = _global_focus(day_view, matches, day_mode)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": day_view.get("generated_at"),
        "date": _text(day_view.get("date"), day_view.get("football_day")),
        "timezone": _text(day_view.get("timezone"), "Asia/Shanghai"),
        "window": _text(day_view.get("window"), "today"),
        "football_day_timezone": _text(
            day_view.get("football_day_timezone"), day_view.get("timezone"), "Asia/Shanghai"
        ),
        "football_day_cutoff_hour": max(0, _int(day_view.get("football_day_cutoff_hour"))),
        "football_day_start_utc": day_view.get("football_day_start_utc"),
        "football_day_end_utc": day_view.get("football_day_end_utc"),
        "source": "dashboard_day_view+performance_checkpoint+replay_front_door",
        "day_mode": day_mode,
        "default_focus_type": focus_type,
        "default_focus_fixture_id": focus_fixture_id,
        "selected_fixture_id": focus_fixture_id,
        "today_summary": {
            "match_count": len(matches),
            "competition_count": len(
                {match["competition_id"] for match in matches if match["competition_id"]}
            ),
            "priority_match_count": sum(primary_reason_counts.values()),
            "priority_group_count": len(primary_reason_counts),
            "primary_reason_counts": primary_reason_counts,
        },
        "global_focus": global_focus,
        "global_model_quality": _global_model_quality(
            forward,
            day_view.get("generated_at"),
        ),
        "read_contract": {
            "provider_calls": int(day_view.get("provider_calls") or 0),
            "db_writes": int(day_view.get("db_writes") or 0),
            "would_write_checkpoint": day_view.get("would_write_checkpoint") is True,
            "no_call_on_read": True,
        },
        "runtime": {
            "product": PRODUCT,
            "public_dashboard_authority": PUBLIC_AUTHORITY,
            "active_whitelist_count": 13,
            "free_bridge_mode": "SHADOW_ONLY",
            "market_price_attention_threshold_ratio": MARKET_PRICE_ATTENTION_THRESHOLD_RATIO,
            "candidate": "SHADOW_ONLY" if candidate_enabled else "OFF",
            "formal": "OFF",
            "lock": "OFF",
            "production": "OFF",
        },
        "navigation": dict(_mapping(day_view.get("navigation"))),
        "date_strip": _mapping_list(day_view.get("date_strip")),
        "attention": [
            {
                "fixture_id": item["fixture_id"],
                "kickoff_utc": item["kickoff_utc"],
                "intelligence_state": item["intelligence_state"],
                "reason_codes": item["intelligence_reason_codes"],
                "affected_domains": _affected_domains(
                    item["intelligence_state"], item["intelligence_reason_codes"]
                ),
                "factual_summary": item["factual_summary"],
                "readiness_status": item["readiness"]["status"],
                "readiness_context": {
                    key: item["readiness"][key]
                    for key in ("reason_code", "missing_fields", "stale_fields", "action")
                },
                "next_eval_at": item["readiness"]["next_eval_at"],
                "risks": item["risks"],
            }
            for item in matches
        ],
        "matches": matches,
        "validation": _validation(forward, replay),
        "external_intelligence": {
            name: {"status": "NOT_CONNECTED", "affects_match_readiness": False}
            for name in ("weather", "news", "sentiment", "advanced_xg")
        },
        "freshness": {
            "domains": _freshness_domains(cards, freshness),
        },
        "data_operations": _data_operations(day_view, freshness, day_mode),
    }


def _match(card: Mapping[str, Any], *, candidate_enabled: bool) -> dict[str, Any]:
    radar = _mapping(card.get("market_radar"))
    model_lab = _mapping(card.get("model_lab"))
    markets = {
        name: _market(_mapping(_mapping(radar.get("markets")).get(name)), name)
        for name in ("ASIAN_HANDICAP", "TOTALS")
    }
    primary = next((market for market in markets.values() if market["main_line"]), None)
    simulation = _mapping(card.get("simulation"))
    inner_simulation = _mapping(simulation.get("simulation"))
    source_model_status = _text(simulation.get("status"), "UNAVAILABLE")
    calibration_status = _optional_text(inner_simulation.get("calibration_status"))
    public_model_status = (
        "PRIOR_ONLY" if calibration_status == "BASELINE_PRIOR" else source_model_status
    )
    model_markets = _mapping(model_lab.get("markets"))
    relation = {
        name: _model_relation(_mapping(model_markets.get(name)), name)
        for name in ("ASIAN_HANDICAP", "TOTALS")
    }
    candidates = _mapping(card.get("market_candidates"))
    for name, market in markets.items():
        candidate_key = {"ASIAN_HANDICAP": "ah", "TOTALS": "ou"}[name]
        market["eligibility"] = _market_eligibility(
            market,
            relation[name],
            _mapping(candidates.get(candidate_key)),
        )
    market_aggregate_status = _market_aggregate_status(markets)
    candidate_input_ready = any(
        _text(_mapping(market.get("eligibility")).get("candidate_eligibility_status"))
        == "READY"
        for market in markets.values()
    )
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "competition_id": _optional_text(card.get("competition_id")),
        "competition_name": _optional_text(card.get("competition_name")),
        "kickoff_utc": card.get("kickoff_utc"),
        "home_team_name": _optional_text(card.get("home_team_name")),
        "away_team_name": _optional_text(card.get("away_team_name")),
        "home_team_label": _public_team_label(card, "home"),
        "away_team_label": _public_team_label(card, "away"),
        "status": _optional_text(card.get("status")),
        "intelligence_state": _text(card.get("intelligence_state"), "DATA_INCOMPLETE"),
        "intelligence_reason_codes": _string_list(card.get("intelligence_reason_codes")),
        "risks": _risks(_mapping(card.get("risk_dimensions"))),
        "readiness": {
            "status": _text(card.get("data_status"), "BLOCKED"),
            "reason_code": _optional_text(card.get("reason_code")),
            "reason_codes": _string_list(card.get("intelligence_reason_codes")),
            "missing_fields": _string_list(card.get("missing_fields")),
            "stale_fields": _string_list(card.get("stale_fields")),
            "action": _optional_text(card.get("action")),
            "next_eval_at": card.get("next_eval_at"),
            "provider_budget_status": _optional_text(card.get("provider_budget_status")),
            "lineup_status": _optional_text(
                _mapping(card.get("data_refresh")).get("lineups_status")
            ),
            "lineup_expectation": _optional_text(card.get("lineup_requirement")),
            "market_aggregate_status": market_aggregate_status,
            "market_evidence_status": (
                "AVAILABLE"
                if market_aggregate_status in {"READY", "PARTIAL"}
                else "NOT_READY"
            ),
            "candidate_input_status": (
                "READY" if candidate_input_ready else "NOT_READY"
            ),
        },
        "market_fact": {
            "status": primary["status"] if primary else "INSUFFICIENT",
            "source_status": primary["source_status"] if primary else "INSUFFICIENT",
            "main_line": primary["main_line"] if primary else None,
            "current_odds": primary["prices"] if primary else {},
            "market_probabilities": primary["probabilities"] if primary else {},
            "price_reference": "LAST_AVAILABLE_PREMATCH_SNAPSHOT",
            "canonical_close_status": "NOT_OBTAINABLE_FROM_CURRENT_PROVIDER",
        },
        "w2_analysis": {
            "status": "ANALYSIS_REFERENCE",
            "proof_status": "NOT_PROVEN",
            "decision_tier": _text(card.get("decision_tier"), "NOT_READY"),
            "analysis_state": _text(card.get("analysis_state"), card.get("intelligence_state")),
            "reason_codes": _string_list(card.get("intelligence_reason_codes")),
            "model_view": {
                "status": public_model_status,
                "source_status": source_model_status,
                "model_version": _optional_text(inner_simulation.get("model_version")),
                "calibration_version": _optional_text(inner_simulation.get("calibration_version")),
                "calibration_status": _optional_text(inner_simulation.get("calibration_status")),
                "simulations_completed": _positive_int(
                    card.get("scoreline_simulations"),
                    inner_simulation.get("simulations"),
                ),
            },
            "model_market_relation": relation,
        },
        "shadow_candidate": _shadow_candidate(card, enabled=candidate_enabled),
        "formal_recommendation": {
            "status": "OFF",
            "reason": "PRODUCT_AUTHORITY_DISABLED",
        },
        "market_radar": {
            "schema_version": _text(radar.get("schema_version"), "w2.market-radar.v1"),
            "markets": markets,
        },
        "model_lab": {
            "schema_version": _text(model_lab.get("schema_version"), "w2.model-lab.v1"),
            "w2_model": {
                "status": public_model_status,
                "source_status": source_model_status,
                "model_version": _optional_text(inner_simulation.get("model_version")),
                "calibration_status": _optional_text(inner_simulation.get("calibration_status")),
            },
            "market": {
                name: {
                    "status": item["status"],
                    "source_status": item["source_status"],
                    "main_line": item["main_line"],
                    "bookmaker_count": item["bookmaker_count"],
                    "freshness": item["freshness"],
                }
                for name, item in markets.items()
            },
            "api_football_prediction": {
                "status": "NOT_AVAILABLE",
                "role": "EXTERNAL_MODEL_BENCHMARK",
                "reason_code": "API_FOOTBALL_PREDICTION_NOT_PROJECTED",
            },
            "relation": relation,
            "historical_validation": _historical_validation(
                _mapping(model_lab.get("historical_validation"))
            ),
        },
        "scoreline_reference": _scoreline(card, public_model_status),
        "evidence": {
            "card_hash": _optional_text(card.get("card_hash")),
            "artifact_hash": _optional_text(card.get("artifact_hash")),
            "source": _optional_text(card.get("source")),
            "source_event_at": _optional_text(
                _mapping(card.get("frozen_artifact_provenance")).get("source_event_at")
            ),
            "decision_role": "DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY",
        },
    }


def _shadow_candidate(card: Mapping[str, Any], *, enabled: bool) -> dict[str, Any]:
    decision = _mapping(card.get("recommendation_decision_v4"))
    reason = _mapping(decision.get("reason"))
    selected = _mapping(decision.get("selected_candidate"))
    active = enabled and _text(decision.get("outcome")) == "ANALYSIS_PICK" and bool(selected)
    return {
        "status": "ACTIVE" if active else "NOT_READY" if enabled else "OFF",
        "mode": "SHADOW_ONLY",
        "authority": "RECOMMENDATION_DECISION_V4",
        "decision_tier": "ANALYSIS_PICK" if active else _text(decision.get("outcome"), "NOT_READY"),
        "reason_code": _optional_text(reason.get("code")),
        "reason_message": _optional_text(reason.get("message")),
        "market": _optional_text(selected.get("market")) if active else None,
        "selection": _optional_text(selected.get("selection")) if active else None,
        "exact_line": _optional_text(selected.get("exact_line") or selected.get("line"))
        if active
        else None,
        "decimal_odds": _number(selected.get("decimal_odds") or selected.get("odds"))
        if active
        else None,
        "captured_at": selected.get("captured_at") if active else None,
        "decision_hash": _optional_text(decision.get("decision_hash")) if active else None,
        "recommendation_scope": "VALIDATION" if active else "NONE",
        "outcome_tracked": active,
        "formal_status": "OFF",
        "lock_status": "OFF",
        "production_action_allowed": False,
        "real_money_allowed": False,
    }


def _market(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    current = _mapping(raw.get("current"))
    timeline = _mapping(raw.get("timeline"))
    movement = _mapping(raw.get("movement"))
    count = max(0, _int(raw.get("snapshot_count")))
    source_status = _text(raw.get("status"), "INSUFFICIENT")
    freshness = dict(_mapping(current.get("freshness")))
    freshness_status = _text(freshness.get("status"), "NOT_AVAILABLE")
    public_status = (
        "INSUFFICIENT"
        if not current
        else "READY"
        if freshness_status in {"COMPLETE", "CURRENT", "FRESH"}
        else "STALE"
        if freshness_status == "STALE"
        else "INSUFFICIENT"
    )
    points = [
        {
            "capture_id": _optional_text(point.get("capture_id")),
            "captured_at": point.get("captured_at"),
            "canonical_line": _optional_text(point.get("canonical_line")),
            "bookmaker_count": max(0, _int(point.get("bookmaker_count"))),
            "prices": dict(_mapping(point.get("prices"))),
            "probabilities": dict(_mapping(point.get("probabilities"))),
        }
        for point in _mapping_list(timeline.get("points"))
    ]
    movement_payload = {
        key: movement.get(key)
        for key in (
            "status",
            "reason_code",
            "from_captured_at",
            "to_captured_at",
            "line_delta",
            "price_delta",
            "probability_delta",
        )
        if key in movement
    }
    if not movement_payload.get("status"):
        movement_payload = {
            "status": "INSUFFICIENT",
            "reason_code": _text(
                timeline.get("status"),
                "INSUFFICIENT_NO_TIMELINE_EVIDENCE",
            ),
        }
    captured_times = [
        _text(point.get("captured_at")) for point in points if point.get("captured_at")
    ]
    latest_snapshot_at = max(captured_times) if captured_times else None
    trend_evidence_status = (
        "AVAILABLE"
        if len(points) >= 2 and movement_payload["status"] != "INSUFFICIENT"
        else "INSUFFICIENT"
    )
    cross_sectional_status = (
        "PAUSED_STALE"
        if public_status == "STALE"
        else "AVAILABLE"
        if public_status == "READY" and max(0, _int(current.get("bookmaker_count"))) > 0
        else "INSUFFICIENT"
    )
    return {
        "market": name,
        "status": public_status,
        "source_status": source_status,
        "snapshot_state": SNAPSHOT_STATES.get(count, "DISCRETE_REAL_PATH"),
        "snapshot_count": count,
        "observation_count": max(0, _int(raw.get("observation_count"))),
        "bookmaker_pair_count": sum(point["bookmaker_count"] for point in points),
        "quote_row_count": max(0, _int(raw.get("observation_count"))),
        "main_line": _optional_text(current.get("canonical_line")),
        "bookmaker_count": max(0, _int(current.get("bookmaker_count"))),
        "prices": dict(_mapping(current.get("prices"))),
        "probabilities": dict(_mapping(current.get("probabilities"))),
        "freshness": freshness,
        "timeline_points": points,
        "movement": movement_payload,
        "reason_codes": [
            str(value) for value in (movement.get("reason_code"), timeline.get("status")) if value
        ],
        "trend_evidence_status": trend_evidence_status,
        "cross_sectional_comparison_status": cross_sectional_status,
        "latest_snapshot_at": latest_snapshot_at,
        "freshness_max_age_seconds": _optional_nonnegative_int(freshness.get("max_age_seconds")),
    }


def _market_eligibility(
    market: Mapping[str, Any],
    relation: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    quote_identity = _mapping(candidate.get("quote_identity"))
    quote_ready = (
        _text(candidate.get("quote_status")) == "COMPLETE"
        and _text(candidate.get("quote_usage")) == "EXECUTABLE"
        and _text(quote_identity.get("identity_status")) == "COMPLETE"
    )
    model_ready = _text(candidate.get("model_status")) == "READY"
    observation_status = (
        "AVAILABLE"
        if _text(market.get("status")) == "READY"
        else "STALE"
        if _text(market.get("status")) == "STALE"
        else "INSUFFICIENT"
    )
    blockers = _string_list(candidate.get("blockers"))
    if observation_status != "AVAILABLE":
        blockers.append("MARKET_EVIDENCE_NOT_CURRENT")
    if not quote_ready:
        blockers.append("EXECUTABLE_CANDIDATE_QUOTE_NOT_READY")
    if not model_ready:
        blockers.append("CANDIDATE_MODEL_NOT_READY")
    blockers.extend(_string_list(relation.get("blockers")))
    eligibility = (
        "READY"
        if observation_status == "AVAILABLE" and quote_ready and model_ready
        else "NOT_READY"
    )
    return {
        "observation_status": observation_status,
        "trend_evidence_status": _text(market.get("trend_evidence_status"), "INSUFFICIENT"),
        "cross_sectional_comparison_status": _text(
            market.get("cross_sectional_comparison_status"), "INSUFFICIENT"
        ),
        "model_diagnostic_status": _text(relation.get("status"), "MARKET_NOT_READY"),
        "candidate_quote_identity_status": "READY" if quote_ready else "NOT_READY",
        "candidate_model_status": "READY" if model_ready else "NOT_READY",
        "candidate_eligibility_status": eligibility,
        "blockers": list(dict.fromkeys(blockers)),
    }


def _market_aggregate_status(markets: Mapping[str, Mapping[str, Any]]) -> str:
    eligibility = [
        _mapping(market.get("eligibility")) for market in markets.values()
    ]
    if eligibility and all(
        _text(item.get("candidate_eligibility_status")) == "READY" for item in eligibility
    ):
        return "READY"
    if any(_text(item.get("observation_status")) == "AVAILABLE" for item in eligibility):
        return "PARTIAL"
    return "NOT_READY"


def _public_team_label(card: Mapping[str, Any], side: str) -> dict[str, Any]:
    source = _mapping(card.get(f"{side}_team_label"))
    provider_team_id = _optional_text(source.get("provider_team_id")) or _optional_text(
        card.get(f"{side}_team_id")
    )
    state = _text(source.get("state"), "IDENTITY_UNRESOLVED")
    display_name = _optional_text(source.get("display_name"))
    if not display_name:
        role = "主队" if side == "home" else "客队"
        suffix = f"：{provider_team_id}" if provider_team_id else ""
        display_name = (
            f"{role}（中文译名待映射）"
            if state == "CANONICAL_IDENTITY_READY_LABEL_MISSING"
            else f"{role}（身份待确认{suffix}）"
        )
    return {
        "display_name": display_name,
        "state": state,
        "canonical_team_id": _optional_text(source.get("canonical_team_id")),
        "provider_team_id": provider_team_id,
        "technical": {
            "raw_provider_name": _optional_text(source.get("raw_provider_name"))
            or _optional_text(card.get(f"{side}_team_name")),
        },
    }


def _model_relation(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    return {
        "market": name,
        "status": _text(raw.get("status"), "MARKET_NOT_READY"),
        "canonical_line": _optional_text(raw.get("canonical_line")),
        "bookmaker_count": max(0, _int(raw.get("bookmaker_count"))),
        "freshness_status": _optional_text(raw.get("freshness_status")),
        "diagnostics": _mapping_list(raw.get("diagnostics")),
        "blockers": _string_list(raw.get("blockers")),
    }


def _scoreline(card: Mapping[str, Any], public_model_status: str) -> dict[str, Any]:
    reference = _mapping(card.get("scoreline_reference"))
    projection = _mapping(reference.get("scoreline_projection"))
    rows = _mapping_list(projection.get("top3"))
    top3 = [
        {
            "scoreline": _text(row.get("scoreline")),
            "unconditional_probability": _number(row.get("unconditional_probability")),
            "sample_count": _optional_int(row.get("sample_count")),
        }
        for row in rows[:3]
        if _text(row.get("scoreline"))
    ]
    simulations_completed = _positive_int(projection.get("simulations_completed"))
    identity_ready = bool(_optional_text(card.get("competition_id")))
    ready = (
        bool(top3)
        and public_model_status == "READY"
        and identity_ready
        and simulations_completed == 10_000
    )
    return {
        "label": "MODEL_SCORELINE_REFERENCE",
        "proof_status": "NOT_PROVEN",
        "status": "READY" if ready else "UNAVAILABLE",
        "simulations_completed": simulations_completed,
        "top3": top3 if ready else [],
    }


def _validation(forward: Mapping[str, Any], replay: Mapping[str, Any]) -> dict[str, Any]:
    probability = _mapping(forward.get("probability_validation"))
    outcomes = _mapping(forward.get("outcomes_canonical"))
    cohort = _mapping(forward.get("performance_cohort"))
    leagues = _mapping_list(cohort.get("by_league"))
    tournaments = _mapping_list(cohort.get("by_tournament"))
    probability_ready = _probability_evidence_ready(probability)
    source_directional_status = _directional_status(outcomes)
    validation_count = max(0, _int(cohort.get("validation_count")))
    excluded_count = max(0, _int(cohort.get("excluded_count")))
    excluded_by_reason = dict(
        _mapping(
            forward.get("validation_excluded_by_reason")
            or forward.get("canonical_excluded_by_reason")
        )
    )
    return {
        "probability": {
            "status": _text(probability.get("status"), "INSUFFICIENT"),
            "sample_count": max(0, _int(probability.get("sample_count"))),
            "model_brier": _number(probability.get("model_brier")),
            "market_brier": _number(probability.get("market_brier")),
            "model_minus_market_brier": _number(probability.get("model_minus_market_brier")),
            "model_log_loss": _number(probability.get("model_log_loss")),
            "market_log_loss": _number(probability.get("market_log_loss")),
            "model_minus_market_log_loss": _number(probability.get("model_minus_market_log_loss")),
            "model_calibration_error": _number(probability.get("model_ece")),
            "market_calibration_error": _number(probability.get("market_ece")),
            "model_reliability_bins": _mapping_list(probability.get("model_reliability_bins")),
            "market_reliability_bins": _mapping_list(probability.get("market_reliability_bins")),
            "checkpoint_metadata": dict(_mapping(forward.get("checkpoint_metadata"))),
        },
        "directional": {
            "status": (
                source_directional_status
                if probability_ready
                else "SAMPLE_BUILDING"
                if outcomes
                else "INSUFFICIENT"
            ),
            "source_status": source_directional_status,
            "probability_evidence_ready": probability_ready,
            "validation_n": validation_count,
            "decisive_n": max(0, _int(outcomes.get("decisive_count"))),
            "correct": max(0, _int(outcomes.get("hit_count"))),
            "wrong": max(0, _int(outcomes.get("miss_count"))),
            "push": max(0, _int(outcomes.get("push_count"))),
            "void": max(0, _int(outcomes.get("void_count"))),
            "direction_accuracy": _number(outcomes.get("hit_rate")),
            "effective_n": max(0, _int(outcomes.get("decisive_count"))),
            "market_direction_benchmark": "NOT_DEFINED",
            "only_record_reason": (
                None
                if probability_ready and source_directional_status == "AVAILABLE"
                else "PROBABILITY_QUALITY_NOT_READY"
                if source_directional_status == "AVAILABLE"
                else "SAMPLE_INSUFFICIENT"
            ),
        },
        "league_performance": [_league(row) for row in leagues],
        "tournament_performance": [_league(row) for row in tournaments],
        "forward_validation_records": {
            "status": "AVAILABLE" if forward else "INSUFFICIENT",
            "validation_count": validation_count,
            "eligible_count": max(0, _int(cohort.get("eligible_count"))),
            "excluded_count": excluded_count,
            "excluded_share": excluded_count / validation_count if validation_count else 0.0,
            "excluded_by_reason": excluded_by_reason,
            "pending_count": max(0, _int(cohort.get("pending_count"))),
            "outcomes": {
                key: outcomes.get(key)
                for key in (
                    "settled_sample_count",
                    "hit_count",
                    "miss_count",
                    "push_count",
                    "void_count",
                    "decisive_count",
                    "hit_rate",
                )
                if key in outcomes
            },
            "checkpoint_metadata": dict(_mapping(forward.get("checkpoint_metadata"))),
        },
        "history_replay": {
            "status": _text(replay.get("replay_status"), "NO_REPLAY_INPUTS"),
            "known_at": {
                key: _mapping(replay.get("known_at_summary")).get(key)
                for key in ("has_day_view", "generated_at", "source", "checkpoint_key")
            },
            "decision_summary": dict(_mapping(replay.get("decision_summary"))),
            "reason_summary": _mapping_list(replay.get("reason_summary")),
            "outcome_tracking_summary": dict(_mapping(replay.get("outcome_tracking_summary"))),
            "card_hash_checks": _mapping_list(replay.get("card_hash_checks")),
            "replay_gaps": _string_list(replay.get("replay_gaps")),
        },
    }


def _league(row: Mapping[str, Any]) -> dict[str, Any]:
    outcomes = _mapping(row.get("outcomes"))
    decisive = max(0, _int(outcomes.get("decisive_count")))
    validation_n = max(0, _int(row.get("processed_count")))
    source_status = _statistical_status(_text(row.get("rate_status")), validation_n)
    probability_ready = source_status == "AVAILABLE" and all(
        _number(row.get(field)) is not None
        for field in ("model_brier", "model_log_loss", "model_ece")
    )
    aggregation_status = _text(row.get("aggregation_status"), "SOURCE_CHECKPOINT")
    only_record_reason = (
        None
        if probability_ready
        else "AGGREGATION_CONFLICT"
        if aggregation_status == "CONFLICT"
        else "PROBABILITY_QUALITY_NOT_READY"
        if source_status == "AVAILABLE"
        else "SAMPLE_INSUFFICIENT"
    )
    return {
        "league": _text(row.get("league"), row.get("competition_id")),
        "source_league": _text(row.get("source_league"), row.get("league")),
        "source_aliases": _string_list(row.get("source_aliases")),
        "source_checkpoint_keys": _string_list(row.get("source_checkpoint_keys")),
        "scope_group": _text(row.get("scope_group"), "UNRESOLVED"),
        "aggregation_status": aggregation_status,
        "competition_id": _text(row.get("competition_id"), row.get("league")),
        "canonical_competition_id": _optional_text(row.get("canonical_competition_id")),
        "competition_name": _optional_text(row.get("competition_name")),
        "identity_status": (
            "RESOLVED"
            if _text(row.get("identity_status")) == "RESOLVED"
            and _optional_text(row.get("competition_name"))
            else "UNRESOLVED"
        ),
        "validation_n": validation_n,
        "decisive_n": decisive,
        "correct": max(0, _int(outcomes.get("hit_count"))),
        "wrong": max(0, _int(outcomes.get("miss_count"))),
        "push": max(0, _int(outcomes.get("push_count"))),
        "void": max(0, _int(outcomes.get("void_count"))),
        "direction_accuracy": _number(outcomes.get("hit_rate")),
        "brier": _number(row.get("model_brier")),
        "log_loss": _number(row.get("model_log_loss")),
        "calibration": _number(row.get("model_ece")),
        "statistical_status": (
            source_status
            if probability_ready
            else "SAMPLE_BUILDING"
            if validation_n
            else "INSUFFICIENT"
        ),
        "source_statistical_status": source_status,
        "probability_evidence_ready": probability_ready,
        "only_record_reason": only_record_reason,
        "market_direction_benchmark": "NOT_DEFINED",
    }


def _freshness_domains(
    cards: Sequence[Mapping[str, Any]], freshness: Mapping[str, Any]
) -> dict[str, Any]:
    page_as_of = freshness.get("page_updated_at")
    odds_as_of = freshness.get("odds_last_confirmed_at")
    projected = {
        "fixtures": ("AVAILABLE", page_as_of),
        "statistics": _card_domain(cards, "statistics"),
        "lineups": _card_domain(cards, "lineups"),
        "odds_prematch": ("AVAILABLE" if odds_as_of else "NOT_AVAILABLE", odds_as_of),
        "injuries": _card_domain(cards, "injuries"),
        "page_projection": ("AVAILABLE", page_as_of),
    }
    return {
        name: {
            "domain": name.upper(),
            "availability": availability,
            "status": projected.get(name, ("NOT_AVAILABLE", None))[0],
            "source": source,
            "source_as_of": projected.get(name, ("NOT_AVAILABLE", None))[1],
            "provider_refresh_authority": authority,
            "readiness_semantics": (
                "SOURCE_VALUE_ONLY"
                if projected.get(name, (None, None))[1]
                else "SOURCE_AS_OF_NOT_PROJECTED"
            ),
            "no_call_on_read": True,
        }
        for name, (availability, source, authority) in DOMAIN_CONTRACT.items()
    }


def _card_domain(cards: Sequence[Mapping[str, Any]], name: str) -> tuple[str, Any]:
    statuses: list[str] = []
    captured: list[str] = []
    for card in cards:
        refresh = _mapping(card.get("data_refresh"))
        status = _optional_text(refresh.get(f"{name}_status"))
        captured_at = _optional_text(refresh.get(f"{name}_captured_at"))
        if status:
            statuses.append(status)
        if captured_at:
            captured.append(captured_at)
    return (sorted(set(statuses))[0] if statuses else "NOT_AVAILABLE", max(captured, default=None))


def _data_operations(
    day_view: Mapping[str, Any], freshness: Mapping[str, Any], day_mode: str
) -> dict[str, Any]:
    counts = _mapping(day_view.get("counts"))
    safe_counts = {
        key: counts.get(key)
        for key in (
            "total",
            "monitored_fixtures",
            "market_complete_fixtures",
            "fresh_quotes",
            "market_stable_fixtures",
            "market_movement_fixtures",
            "model_diagnostic_warnings",
            "data_incidents",
            "collection_incidents",
            "by_data_status",
            "by_intelligence_state",
        )
        if key in counts
    }
    degradation = dict(_mapping(day_view.get("degradation")))
    system_health = _text(degradation.get("state"), "UNKNOWN")
    public_system_health = (
        "DAY_BLOCKED"
        if day_mode == "BLOCKED"
        else "HEALTHY"
        if system_health in {"HEALTHY", "EMPTY_DAY"}
        else "PARTIAL_DEGRADATION"
    )
    return {
        "read_model_source": _text(day_view.get("source")),
        "checkpoint_key": _text(day_view.get("checkpoint_key")),
        "degradation": degradation,
        "counts": safe_counts,
        "system_health": system_health,
        "public_system_health": public_system_health,
        "provider_budget_status": _text(freshness.get("provider_budget_status"), "UNKNOWN"),
    }


def _priority_reasons(match: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    reasons: set[str] = set()
    state = _text(match.get("intelligence_state"))
    markets = _mapping(_mapping(match.get("market_radar")).get("markets"))
    relation = _mapping(_mapping(match.get("w2_analysis")).get("model_market_relation"))

    if state == "COLLECTION_INCIDENT":
        reasons.add("COLLECTION_INCIDENT")
    if state == "DATA_INCOMPLETE":
        readiness = _mapping(match.get("readiness"))
        reasons.add(
            "CANDIDATE_INPUT_NOT_READY"
            if _text(readiness.get("market_aggregate_status")) == "PARTIAL"
            else "DATA_INCOMPLETE"
        )
    stale = any(_text(_mapping(market).get("status")) == "STALE" for market in markets.values())
    if stale:
        reasons.add("STALE_MARKET_MEMORY")
    if any(_is_attention_worthy_movement(_mapping(market)) for market in markets.values()):
        reasons.add("MARKET_MOVEMENT")
    if any(
        _text(_mapping(market).get("status")) == "READY"
        and _text(_mapping(relation.get(name)).get("status"))
        not in {"", "MARKET_NOT_READY", "NOT_AVAILABLE"}
        for name, market in markets.items()
    ) and state in {
        "MODEL_DIAGNOSTIC_WARNING",
        "MODEL_MARKET_DISAGREEMENT",
        "MARKET_ANOMALY",
    }:
        reasons.add("MODEL_DIAGNOSTIC")
    readiness = _mapping(match.get("readiness"))
    if _text(readiness.get("lineup_expectation")) == "EXPECTED_NEAR_KICKOFF" and _text(
        readiness.get("lineup_status")
    ) in {"", "NOT_AVAILABLE", "PROVIDER_EMPTY", "PENDING"}:
        reasons.add("LINEUP_PENDING")

    primary = next(
        (
            reason
            for reason in sorted(
                reasons,
                key=lambda reason: (PRIMARY_REASON_ORDER.get(reason, 99), reason),
            )
            if reason in PRIMARY_REASON_ORDER and not (reason == "MARKET_MOVEMENT" and stale)
        ),
        "STALE_MARKET_MEMORY" if stale else None,
    )
    secondary = sorted(
        reasons - ({primary} if primary else set()),
        key=lambda reason: (ATTENTION_REASON_ORDER[reason], reason),
    )
    return primary, secondary


def _is_attention_worthy_movement(market: Mapping[str, Any]) -> bool:
    if (
        _text(market.get("status")) not in {"READY", "STALE"}
        or _int(market.get("snapshot_count")) < 2
    ):
        return False
    movement = _mapping(market.get("movement"))
    status = _text(movement.get("status"))
    if status in {"LINE_MOVEMENT", "LINE_AND_PRICE_MOVEMENT"}:
        return True
    if status != "PRICE_MOVEMENT":
        return False
    prices = _mapping(market.get("prices"))
    deltas = _mapping(movement.get("price_delta"))
    return any(
        _relative_price_change(prices.get(side), delta)
        >= MARKET_PRICE_ATTENTION_THRESHOLD_RATIO
        for side, delta in deltas.items()
    )


def _relative_price_change(current: Any, delta: Any) -> float:
    raw_current = _mapping(current).get("median") if isinstance(current, Mapping) else current
    current_value = _number(raw_current)
    delta_value = _number(delta)
    if current_value is None or delta_value is None:
        return 0.0
    previous_value = current_value - delta_value
    return abs(delta_value) / abs(previous_value) if previous_value else 0.0


def _primary_reason_counts(matches: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in matches:
        reason = _optional_text(match.get("priority_reason_primary"))
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (PRIMARY_REASON_ORDER[item[0]], item[0])))


def _focus_authority(
    day_view: Mapping[str, Any], matches: Sequence[Mapping[str, Any]]
) -> tuple[str, str, str | None]:
    degradation_state = _text(_mapping(day_view.get("degradation")).get("state"))
    blocking_degradation = degradation_state in {
        "BLOCKED",
        "BLOCKED_DAY",
        "COLLECTION_INCIDENT",
        "PROVIDER_EMPTY",
    }
    if not matches:
        if blocking_degradation and degradation_state != "EMPTY_DAY":
            return "BLOCKED", "GLOBAL_INCIDENT", None
        return "EMPTY", "EMPTY_STATE", None
    usable = [match for match in matches if _evidence_rank(match) < 4]
    if not usable:
        return "BLOCKED", "GLOBAL_INCIDENT", None
    if all(_calm_complete(match) for match in matches):
        return "CALM", "DAY_SUMMARY", None
    focused = min(usable, key=_focus_rank)
    return "NORMAL", "MATCH", _text(focused.get("fixture_id"))


def _focus_rank(match: Mapping[str, Any]) -> tuple[int, int, int, str, str]:
    reason = _text(match.get("priority_reason_primary"))
    markets = _mapping(_mapping(match.get("market_radar")).get("markets"))
    timeline_depth = max(
        (_int(_mapping(market).get("snapshot_count")) for market in markets.values()),
        default=0,
    )
    return (
        _evidence_rank(match),
        PRIMARY_REASON_ORDER.get(reason, len(PRIMARY_REASON_ORDER)),
        -timeline_depth,
        _text(match.get("kickoff_utc"), "9999-12-31T23:59:59Z"),
        _text(match.get("fixture_id")),
    )


def _evidence_rank(match: Mapping[str, Any]) -> int:
    markets = _mapping(_mapping(match.get("market_radar")).get("markets"))
    statuses = [_text(_mapping(market).get("status")) for market in markets.values()]
    depth = max(
        (_int(_mapping(market).get("snapshot_count")) for market in markets.values()),
        default=0,
    )
    if "READY" in statuses:
        return 0 if depth >= 2 else 1
    if "STALE" in statuses:
        return 2 if depth >= 2 else 3
    return 4


def _calm_complete(match: Mapping[str, Any]) -> bool:
    markets = _mapping(_mapping(match.get("market_radar")).get("markets"))
    return (
        _text(match.get("intelligence_state")) == "MARKET_STABLE"
        and bool(markets)
        and all(_text(_mapping(market).get("status")) == "READY" for market in markets.values())
    )


def _global_focus(
    day_view: Mapping[str, Any],
    matches: Sequence[Mapping[str, Any]],
    day_mode: str,
) -> dict[str, Any] | None:
    if day_mode == "NORMAL":
        return None
    degradation = _mapping(day_view.get("degradation"))
    freshness = _mapping(day_view.get("freshness"))
    competition_count = len(
        {match.get("competition_id") for match in matches if match.get("competition_id")}
    )
    next_evaluations = sorted(
        value
        for match in matches
        if (value := _mapping(match.get("readiness")).get("next_eval_at"))
    )
    common = {
        "affected_fixture_count": len(matches) if day_mode == "BLOCKED" else 0,
        "affected_competition_count": competition_count if day_mode == "BLOCKED" else 0,
        "source_as_of": freshness.get("page_updated_at") or day_view.get("generated_at"),
        "next_eval_at": next_evaluations[0] if next_evaluations else None,
        "recovery_condition": None,
    }
    if day_mode == "BLOCKED":
        return {
            "status": "INCIDENT",
            "reason_code": _text(
                degradation.get("reason_code"),
                degradation.get("state"),
                "COLLECTION_INCIDENT",
            ),
            "factual_summary": "当日持久化采集证据不足，无法形成比赛级默认焦点。",
            "recovery_condition": "等待既有调度形成新的持久化证据；本页不会调用 Provider。",
            **{key: value for key, value in common.items() if key != "recovery_condition"},
        }
    if day_mode == "CALM":
        return {
            "status": "CALM",
            "reason_code": "NO_PRIORITY_REVIEW_ITEMS",
            "factual_summary": "当前没有达到优先复核条件的比赛。",
            **common,
        }
    return {
        "status": "EMPTY",
        "reason_code": "NO_FIXTURES_IN_FOOTBALL_DAY",
        "factual_summary": "本比赛日观察池内没有比赛；不会从其他日期填充。",
        **common,
    }


def _global_model_quality(forward: Mapping[str, Any], generated_at: Any) -> dict[str, Any]:
    probability = _mapping(forward.get("probability_validation"))
    metadata = _mapping(forward.get("checkpoint_metadata"))
    checkpoint_generated_at = next(
        (
            metadata.get(key)
            for key in ("checkpoint_generated_at", "generated_at", "as_of", "created_at")
            if metadata.get(key)
        ),
        None,
    )
    metrics = {
        "model_log_loss": _number(probability.get("model_log_loss")),
        "market_log_loss": _number(probability.get("market_log_loss")),
        "model_brier": _number(probability.get("model_brier")),
        "market_brier": _number(probability.get("market_brier")),
        "model_calibration_error": _number(probability.get("model_ece")),
    }
    complete = all(value is not None for value in metrics.values())
    age_seconds = _age_seconds(generated_at, checkpoint_generated_at)
    status = (
        "NOT_AVAILABLE"
        if checkpoint_generated_at is None
        else "STALE"
        if age_seconds is None or age_seconds > MODEL_QUALITY_MAX_AGE_SECONDS
        else "INCOMPLETE"
        if not complete
        else "AVAILABLE"
    )
    return {
        "status": status,
        "checkpoint_key": _optional_text(metadata.get("checkpoint_key")),
        "checkpoint_generated_at": checkpoint_generated_at,
        "freshness_max_age_seconds": MODEL_QUALITY_MAX_AGE_SECONDS,
        **(metrics if status == "AVAILABLE" else dict.fromkeys(metrics)),
        "sample_count": (
            max(0, _int(probability.get("sample_count"))) if status == "AVAILABLE" else 0
        ),
    }


def _match_factual_summary(match: Mapping[str, Any]) -> str:
    markets = list(_mapping(_mapping(match.get("market_radar")).get("markets")).values())
    statuses = {_text(_mapping(market).get("status")) for market in markets}
    depth = max(
        (_int(_mapping(market).get("snapshot_count")) for market in markets),
        default=0,
    )
    if "STALE" in statuses:
        return (
            "已落盘 AH/OU 历史市场证据已过期；当前走势与模型—市场比较暂停；等待既有调度形成新快照。"
        )
    if statuses <= {"INSUFFICIENT"} or depth == 0:
        return "尚无已落盘 AH/OU 市场证据；无法生成走势或当前模型—市场比较；等待既有调度形成证据。"
    aggregate = _text(_mapping(match.get("readiness")).get("market_aggregate_status"))
    if aggregate == "PARTIAL":
        ready_markets = [
            _text(_mapping(market).get("market"))
            for market in markets
            if _text(_mapping(market).get("status")) == "READY"
        ]
        return (
            f"已有当前 {'/'.join(ready_markets) or 'AH/OU'} 持久化市场证据；"
            "市场事实可以查看，但精确候选报价或模型输入尚未全部就绪，暂不形成影子候选。"
        )
    if depth < 2:
        return (
            "已有当前 AH/OU 市场证据，但时间线不足两点；仅展示当前横截面，"
            "不判断走势；等待既有调度形成下一快照。"
        )
    return (
        "已有当前 AH/OU 持久化时间线；可展示已证实走势并进行模型—市场诊断；"
        "状态随既有调度形成的新证据更新。"
    )


def _risks(source: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dimension in ("EVENT_RISK", "DATA_RISK", "MODEL_RISK", "COLLECTION_RISK"):
        risk = dict(_mapping(source.get(dimension)))
        reasons = _string_list(risk.get("reason_codes"))
        if dimension == "MODEL_RISK" and risk.get("assessment_status") == "UNASSESSED":
            risk["explanation"] = "尚无可用模型评估证据"
            result[dimension] = risk
            continue
        translated = [
            RISK_REASON_LABELS[reason] for reason in reasons if reason in RISK_REASON_LABELS
        ]
        if translated:
            shown = translated[:2]
            explanation = "；".join(shown)
            if len(reasons) > len(shown):
                explanation += f"；另有 {len(reasons) - len(shown)} 项技术原因"
        else:
            source_explanation = _text(risk.get("explanation"))
            explanation = (
                source_explanation
                if source_explanation
                and any("\u4e00" <= char <= "\u9fff" for char in source_explanation)
                else "没有可陈述的源证据"
            )
        risk["explanation"] = explanation
        result[dimension] = risk
    return result


def _age_seconds(later: Any, earlier: Any) -> int | None:
    later_at = _datetime(later)
    earlier_at = _datetime(earlier)
    if later_at is None or earlier_at is None:
        return None
    return max(0, int((later_at - earlier_at).total_seconds()))


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _historical_validation(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in (
            "protocol",
            "final_verdict",
            "v_continuation_gate",
            "ou_close_best_predictive_lift",
            "ah_close_best_predictive_lift",
            "ou_pre_best_frozen_selections",
            "historical_incremental_edge",
            "h_result_access",
            "reexecuted",
        )
        if key in source
    }


def _affected_domains(state: Any, reason_codes: Any) -> list[str]:
    evidence = [_text(state), *_string_list(reason_codes)]
    return [domain for domain in AFFECTED_DOMAIN_ORDER if any(domain in item for item in evidence)]


def _factual_summary(state: Any, reason_codes: Any) -> str:
    reasons = _string_list(reason_codes)
    return f"{_text(state)}: {', '.join(reasons)}"


def _directional_status(outcomes: Mapping[str, Any]) -> str:
    decisive = max(0, _int(outcomes.get("decisive_count")))
    if outcomes.get("hit_rate") is not None:
        return "AVAILABLE"
    return "SAMPLE_BUILDING" if decisive else "INSUFFICIENT"


def _probability_evidence_ready(probability: Mapping[str, Any]) -> bool:
    return _text(probability.get("status")) == "AVAILABLE" and all(
        _number(probability.get(field)) is not None
        for field in ("model_brier", "model_log_loss", "model_ece")
    )


def _statistical_status(rate_status: str, validation_n: int) -> str:
    if rate_status == "AVAILABLE":
        return "AVAILABLE"
    return "SAMPLE_BUILDING" if validation_n else "INSUFFICIENT"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [str(item) for item in value if item is not None]


def _text(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    number = _int(value)
    return number if number >= 0 and value is not None else None


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _positive_int(*values: Any) -> int | None:
    for value in values:
        number = _int(value)
        if number > 0:
            return number
    return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
