from __future__ import annotations

from collections.abc import Mapping, Sequence
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


def build_dashboard_intelligence_workspace(
    day_view: Mapping[str, Any],
    *,
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    """Adapt existing bounded projections into the one final Dashboard read model."""
    cards = _mapping_list(day_view.get("cards"))
    matches = [_match(card) for card in cards]
    freshness = _mapping(day_view.get("freshness"))
    performance = _mapping(day_view.get("performance"))
    forward = _mapping(performance.get("forward_ledger"))
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
        "selected_fixture_id": matches[0]["fixture_id"] if matches else None,
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
            "candidate": "OFF",
            "formal": "OFF",
            "lock": "OFF",
            "production": "OFF",
        },
        "navigation": dict(_mapping(day_view.get("navigation"))),
        "attention": [
            {
                "fixture_id": item["fixture_id"],
                "kickoff_utc": item["kickoff_utc"],
                "intelligence_state": item["intelligence_state"],
                "reason_codes": item["intelligence_reason_codes"],
                "affected_domains": _affected_domains(
                    item["intelligence_state"], item["intelligence_reason_codes"]
                ),
                "factual_summary": _factual_summary(
                    item["intelligence_state"], item["intelligence_reason_codes"]
                ),
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
        "data_operations": _data_operations(day_view, freshness),
    }


def _match(card: Mapping[str, Any]) -> dict[str, Any]:
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
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "competition_id": _optional_text(card.get("competition_id")),
        "competition_name": _optional_text(card.get("competition_name")),
        "kickoff_utc": card.get("kickoff_utc"),
        "home_team_name": _optional_text(card.get("home_team_name")),
        "away_team_name": _optional_text(card.get("away_team_name")),
        "status": _optional_text(card.get("status")),
        "intelligence_state": _text(card.get("intelligence_state"), "DATA_INCOMPLETE"),
        "intelligence_reason_codes": _string_list(card.get("intelligence_reason_codes")),
        "risks": dict(_mapping(card.get("risk_dimensions"))),
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
        "scoreline_reference": _scoreline(card),
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


def _scoreline(card: Mapping[str, Any]) -> dict[str, Any]:
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
    status = "READY" if top3 else "UNAVAILABLE"
    return {
        "label": "MODEL_SCORELINE_REFERENCE",
        "proof_status": "NOT_PROVEN",
        "status": status,
        "simulations_completed": _positive_int(projection.get("simulations_completed")),
        "top3": top3,
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


def _data_operations(day_view: Mapping[str, Any], freshness: Mapping[str, Any]) -> dict[str, Any]:
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
    return {
        "read_model_source": _text(day_view.get("source")),
        "checkpoint_key": _text(day_view.get("checkpoint_key")),
        "degradation": degradation,
        "counts": safe_counts,
        "system_health": _text(degradation.get("state"), "UNKNOWN"),
        "provider_budget_status": _text(freshness.get("provider_budget_status"), "UNKNOWN"),
    }


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
