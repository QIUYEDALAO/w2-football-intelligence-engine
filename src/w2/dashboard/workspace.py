from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from w2.dashboard.factor_checklist import build_fixture_factor_checklist
from w2.dashboard.results import (
    normalize_match_status,
    outcome_public_cause,
    selected_day_outcome_cause,
    selected_day_record_kind,
)
from w2.domain.recommendation_capabilities import (
    analysis_market_enabled,
    load_recommendation_capability_manifest,
)

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
    "MARKET_MOVEMENT": 0,
    "MODEL_DIAGNOSTIC": 1,
}
ATTENTION_REASON_ORDER = {
    "MARKET_MOVEMENT": 1,
    "MODEL_DIAGNOSTIC": 2,
    "COLLECTION_INCIDENT": 3,
    "DATA_INCOMPLETE": 4,
    "CANDIDATE_INPUT_NOT_READY": 4,
    "LINEUP_PENDING": 5,
}
MODEL_QUALITY_MAX_AGE_SECONDS = 86_400
MARKET_PRICE_ATTENTION_THRESHOLD_RATIO = 0.02
MARKET_DEPTH_ASYMMETRY_REASON = "MARKET_DEPTH_ASYMMETRY"
_EVALUATED_OPPORTUNITY_STATES = frozenset(
    {"EVALUATED_CANDIDATE", "EVALUATED_NO_EDGE", "BLOCKED_BY_GATE"}
)
RISK_REASON_LABELS = {
    "DATA_FIELD_STALE": "数据字段已超过新鲜度边界",
    "DATA_IDENTITY_NOT_READY": "比赛或盘口身份尚未完成",
    "DATA_MARKET_TIMELINE_INSUFFICIENT": "让球/大小球时间线证据不足",
    "DATA_REQUIRED_INPUT_MISSING": "必需输入尚未齐全",
    "DATA_STATUS_BLOCKED": "必需输入尚未全部就绪",
    "MODEL_SIMULATION_NOT_READY": "既有模型模拟尚未就绪",
    "MODEL_LAB_NOT_READY": "模型评估尚未就绪",
    "MODEL_OUTSIDE_MARKET_RANGE": "模型结果超出当前市场观测区间",
    "COLLECTION_ASSESSMENT_NOT_AVAILABLE": "尚无可用采集评估证据",
}
MISSING_FIELD_LABELS = {
    "lineups": "首发",
    "xg": "模型核心输入 xG",
    "ratings": "评级增强输入",
    "team_value": "球队身价增强输入",
    "market": "市场证据",
    "candidate_quote": "精确候选报价",
    "data_readiness": "数据就绪证据",
}


def build_dashboard_intelligence_workspace(
    day_view: Mapping[str, Any],
    *,
    replay: Mapping[str, Any],
    model_forecasts: Mapping[str, Mapping[str, Any]] | None = None,
    model_forecast_progress: Mapping[str, Any] | None = None,
    candidate_enabled: bool = False,
    recommendation_capabilities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt existing bounded projections into the one final Dashboard read model."""
    active_whitelist_count = max(0, _int(day_view.get("active_whitelist_count")))
    cards = _mapping_list(day_view.get("cards"))
    replay_cards = {
        _text(item.get("fixture_id")): item
        for item in _mapping_list(replay.get("cards"))
        if _text(item.get("fixture_id"))
    }
    outcome_summary = _mapping(replay.get("outcome_tracking_summary"))
    generated_at = day_view.get("generated_at")
    capability_manifest = load_recommendation_capability_manifest()
    enabled_analysis_markets = {
        market
        for market in ("ASIAN_HANDICAP", "TOTALS")
        if analysis_market_enabled(market, manifest=capability_manifest)
    }
    matches = [
        _match(
            card,
            candidate_enabled=candidate_enabled,
            generated_at=generated_at,
            ledger_fact=_mapping((model_forecasts or {}).get(_text(card.get("fixture_id")))),
            enabled_analysis_markets=enabled_analysis_markets,
        )
        for card in cards
    ]
    for card, match in zip(cards, matches, strict=True):
        outcome = _match_outcome(
            card,
            match,
            replay_cards.get(match["fixture_id"], {}),
            outcome_summary,
            generated_at=day_view.get("generated_at"),
        )
        match["outcome"] = outcome
        if outcome["is_recorded"] and normalize_match_status(match.get("status")) != "FINISHED":
            match["status"] = "FT"
    freshness = _mapping(day_view.get("freshness"))
    performance = _mapping(day_view.get("performance"))
    forward = _mapping(performance.get("forward_ledger"))
    for match in matches:
        primary, secondary = _priority_reasons(match)
        match["priority_reason_primary"] = primary
        match["priority_reason_secondary"] = secondary
        match["factual_summary"] = _match_factual_summary(match)
    date_strip = [_date_strip_entry(item) for item in _mapping_list(day_view.get("date_strip"))]
    selected_day_semantics = (
        _mapping(date_strip[len(date_strip) // 2].get("public_semantics"))
        if date_strip
        else {"scope": "SELECTED_DAY", "cause": None}
    )
    selected_day_semantics = _selected_day_semantics(selected_day_semantics, matches)
    if date_strip:
        date_strip[len(date_strip) // 2]["public_semantics"] = selected_day_semantics
    for match in matches:
        match["public_semantics"] = _match_public_semantics(match, selected_day_semantics)
    focus_fixture_id = _selected_focus_fixture_id(matches, selected_day_semantics)
    primary_reason_counts = (
        _primary_reason_counts(matches) if selected_day_semantics.get("cause") is None else {}
    )
    global_focus = _global_focus(
        day_view,
        matches,
        focus_fixture_id,
        selected_day_semantics=selected_day_semantics,
    )
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
        "selected_fixture_id": focus_fixture_id,
        "today_summary": {
            "match_count": len(matches),
            "competition_count": len(
                {match["competition_id"] for match in matches if match["competition_id"]}
            ),
            "priority_match_count": sum(primary_reason_counts.values()),
            "priority_group_count": len(primary_reason_counts),
            "primary_reason_counts": primary_reason_counts,
            "pending_owner_review_team_count": len(
                {
                    label["canonical_team_id"]
                    for match in matches
                    for label in (match["home_team_label"], match["away_team_label"])
                    if label["state"] == "CHINESE_LABEL_PENDING_OWNER_REVIEW"
                    and label["canonical_team_id"]
                }
            ),
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
            "active_whitelist_count": active_whitelist_count,
            "free_bridge_mode": "SHADOW_ONLY",
            "market_price_attention_threshold_ratio": MARKET_PRICE_ATTENTION_THRESHOLD_RATIO,
            "candidate": "SHADOW_ONLY" if candidate_enabled else "OFF",
            "formal": "OFF",
            "lock": "OFF",
            "production": "OFF",
            "recommendation_capabilities": {
                name: {
                    "implementation": _text(_mapping(row).get("implementation")),
                    "feature_enabled": _mapping(row).get("feature_enabled") is True,
                }
                for name, row in _mapping(recommendation_capabilities).items()
                if name
                in {
                    "analysis_ah",
                    "analysis_ou",
                    "shadow_candidate",
                    "formal_ah",
                    "formal_ou",
                    "production_recommendation",
                }
            },
        },
        "navigation": dict(_mapping(day_view.get("navigation"))),
        "date_strip": date_strip,
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
        "validation": {
            **_validation(forward, replay, matches),
            "model_forecast": _model_forecast_progress(model_forecast_progress or {}),
        },
        "external_intelligence": {
            name: {"status": "NOT_CONNECTED", "affects_match_readiness": False}
            for name in ("weather", "news", "sentiment", "advanced_xg")
        },
        "freshness": {
            "domains": _freshness_domains(cards, freshness),
        },
        "data_operations": _data_operations(day_view, freshness),
    }


def _model_forecast_progress(raw: Mapping[str, Any]) -> dict[str, Any]:
    buckets = _mapping(raw.get("lead_time_buckets"))
    data_versions = _mapping(raw.get("data_versions"))
    funnel = _mapping(raw.get("market_evaluation_funnel"))
    official_recommendations = _mapping_list(raw.get("official_recommendations"))
    return {
        "capture_count": max(0, _int(raw.get("capture_count"))),
        "settled_count": max(0, _int(raw.get("settled_count"))),
        "pending_count": max(0, _int(raw.get("pending_count"))),
        "sample_target": max(1, _int(raw.get("sample_target")) or 200),
        "current_flow_candidate_count": max(0, _int(raw.get("current_flow_candidate_count"))),
        "current_flow_settled_count": max(0, _int(raw.get("current_flow_settled_count"))),
        "ever_formed_candidate_count": max(0, _int(raw.get("ever_formed_candidate_count"))),
        "final_candidate_count": max(0, _int(raw.get("final_candidate_count"))),
        "invalidated_candidate_count": max(0, _int(raw.get("invalidated_candidate_count"))),
        "t30_evaluated_candidate_count": max(0, _int(raw.get("t30_evaluated_candidate_count"))),
        "t30_confirmed_candidate_count": max(0, _int(raw.get("t30_confirmed_candidate_count"))),
        "min_xg_matches": max(1, _int(raw.get("min_xg_matches")) or 3),
        "xg_ready_team_count": max(0, _int(raw.get("xg_ready_team_count"))),
        "next_7d_xg_ready_fixture_count": max(0, _int(raw.get("next_7d_xg_ready_fixture_count"))),
        "capture_policy": _text(raw.get("capture_policy"), "FIRST_ELIGIBLE_FREEZE_IMMUTABLE"),
        "market_evaluation_funnel": {
            "scope": _text(funnel.get("scope"), "CHECKPOINT_EVALUATION_OPPORTUNITY_V2"),
            "denominator_unit": _text(
                funnel.get("denominator_unit"),
                "CHECKPOINT_EVALUATION_OPPORTUNITY_SLOT_X_MARKET",
            ),
            "measurement_status": (
                _text(funnel.get("measurement_status"))
                if _text(funnel.get("measurement_status"))
                in {"MEASURABLE", "NOT_MEASURABLE", "INVALID"}
                else "NOT_MEASURABLE"
            ),
            "invalid_opportunity_row_count": max(
                0, _int(funnel.get("invalid_opportunity_row_count"))
            ),
            "invalid_opportunity_reasons": {
                str(key): max(0, _int(value))
                for key, value in _mapping(funnel.get("invalid_opportunity_reasons")).items()
            },
            "opportunity_count": max(0, _int(funnel.get("opportunity_count"))),
            "capture_count": max(0, _int(funnel.get("capture_count"))),
            "fixture_count": max(0, _int(funnel.get("fixture_count"))),
            "market_unit_count": max(0, _int(funnel.get("market_unit_count"))),
            "persisted_market_unit_count": max(0, _int(funnel.get("persisted_market_unit_count"))),
            "recorded_at_count": max(0, _int(funnel.get("recorded_at_count"))),
            "gate_counts": {
                str(key): max(0, _int(value))
                for key, value in _mapping(funnel.get("gate_counts")).items()
            },
            # Preserve None rather than collapsing to {}: the dashboard must be
            # able to say "not measurable" instead of drawing empty bars.
            "gate_rates": (
                {
                    str(key): max(0.0, min(1.0, _number(value) or 0.0))
                    for key, value in _mapping(funnel.get("gate_rates")).items()
                }
                if funnel.get("gate_rates") is not None
                else None
            ),
            "first_failed_gate_counts": {
                str(key): max(0, _int(value))
                for key, value in _mapping(funnel.get("first_failed_gate_counts")).items()
            },
        },
        "official_recommendations": [
            {
                "evaluation_id": _text(row.get("evaluation_id")),
                "fixture_id": _text(row.get("fixture_id")),
                "evaluated_at": _optional_text(row.get("evaluated_at")),
                "kickoff_utc": _optional_text(row.get("kickoff_utc")),
                "market": _text(row.get("market")),
                "selection": _text(row.get("selection")),
                "exact_line": _text(row.get("exact_line")),
                "decimal_odds": _number(row.get("decimal_odds")),
                "home_team_label": _public_team_label(row, "home"),
                "away_team_label": _public_team_label(row, "away"),
                "score": _optional_text(row.get("score")),
                "settlement": _text(row.get("settlement"), "PENDING"),
                "profit_units": _number(row.get("profit_units")),
                "confirmed_checkpoint": _text(
                    row.get("confirmed_checkpoint"), "UNKNOWN_CHECKPOINT"
                ),
                "later_unassessed_checkpoints": _string_list(
                    row.get("later_unassessed_checkpoints")
                ),
                "lifecycle_note_zh": _optional_text(row.get("lifecycle_note_zh")),
            }
            for row in official_recommendations
        ],
        "lead_time_buckets": {
            bucket: {
                "capture_count": max(0, _int(_mapping(buckets.get(bucket)).get("capture_count"))),
                "settled_count": max(0, _int(_mapping(buckets.get(bucket)).get("settled_count"))),
                "pending_count": max(0, _int(_mapping(buckets.get(bucket)).get("pending_count"))),
            }
            for bucket in ("LT_6H", "H6_TO_LT_24H", "D1_TO_D3", "GT_3D")
        },
        "data_versions": {
            version: _model_forecast_data_version_progress(_mapping(progress))
            for version, progress in data_versions.items()
        },
        "public_semantics": {"scope": "CROSS_DAY_CUMULATIVE", "cause": None},
    }


def _model_forecast_data_version_progress(raw: Mapping[str, Any]) -> dict[str, Any]:
    buckets = _mapping(raw.get("lead_time_buckets"))
    return {
        "team_xg_match_count": _int(raw.get("team_xg_match_count")) or None,
        "capture_count": max(0, _int(raw.get("capture_count"))),
        "settled_count": max(0, _int(raw.get("settled_count"))),
        "pending_count": max(0, _int(raw.get("pending_count"))),
        "lead_time_buckets": {
            bucket: {
                "capture_count": max(0, _int(_mapping(buckets.get(bucket)).get("capture_count"))),
                "settled_count": max(0, _int(_mapping(buckets.get(bucket)).get("settled_count"))),
                "pending_count": max(0, _int(_mapping(buckets.get(bucket)).get("pending_count"))),
            }
            for bucket in ("LT_6H", "H6_TO_LT_24H", "D1_TO_D3", "GT_3D")
        },
    }


_EVALUATION_CHECKPOINT_LABELS = {
    "T3_ODDS": "T-3h",
    "T-3h": "T-3h",
    "T60_ODDS_LINEUPS": "T-60m",
    "T45_ODDS": "T-45m",
    "T-30m_VALIDATION_LOCK": "T-30m",
    "T15_ODDS": "T-15m",
}
_OFFICIAL_EVALUATION_SEMANTICS = "CHECKPOINT_EVALUATION_OPPORTUNITY"


def _latest_checkpoint_plans(card: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for plan in _mapping_list(card.get("evaluation_checkpoints")):
        checkpoint = _text(plan.get("checkpoint"))
        if checkpoint not in _EVALUATION_CHECKPOINT_LABELS:
            continue
        previous = latest.get(checkpoint)
        if previous is None or (
            _text(plan.get("scheduled_at")), _text(plan.get("plan_id"))
        ) > (_text(previous.get("scheduled_at")), _text(previous.get("plan_id"))):
            latest[checkpoint] = plan
    return sorted(latest.values(), key=lambda row: _text(row.get("scheduled_at")))


def _percent(value: Any) -> str:
    number = _number(value)
    return "待确认" if number is None else f"{number * 100:+.2f}%"


def _percentage_points(value: Any) -> str:
    number = _number(value)
    return "待确认" if number is None else f"{number * 100:.2f}"


def _no_edge_detail(evaluated: Sequence[tuple[Mapping[str, Any], str, datetime]]) -> str:
    latest: dict[str, tuple[Mapping[str, Any], datetime]] = {}
    for row, state, evaluated_at in evaluated:
        if state not in {"NO_EDGE_CURRENT", "ANALYSIS_COMPLETE"}:
            continue
        market = _text(row.get("market"))
        previous = latest.get(market)
        if previous is None or evaluated_at > previous[1]:
            latest[market] = (row, evaluated_at)
    details = []
    for market in ("ASIAN_HANDICAP", "TOTALS"):
        row = _mapping(latest.get(market, ({}, datetime.min.replace(tzinfo=UTC)))[0])
        if not row:
            continue
        shortfall = _mapping(row.get("shortfall"))
        details.append(
            f"{'让球' if market == 'ASIAN_HANDICAP' else '大小球'}："
            f"EV {_percent(row.get('current_ev'))}；"
            f"delta {_percent(row.get('current_delta'))} / "
            f"需 ≥{_percent(row.get('required_delta')).lstrip('+')}"
            f"（差 {_percentage_points(shortfall.get('delta'))} 个点）；"
            f"EV−SE {_percent(row.get('current_ev_minus_se'))} / 需 >0"
        )
    return "；".join(details) or "已完成评估，Decision V4 未发现达到门槛的价值差。"


def _evaluation_diagnosis(
    card: Mapping[str, Any],
    *,
    official_attempts: Sequence[tuple[Mapping[str, Any], str, datetime]],
    evaluated: Sequence[tuple[Mapping[str, Any], str, datetime]],
    opportunities: Sequence[Mapping[str, Any]],
    factor_checklist: Mapping[str, Any],
    ever_formed_candidate: bool,
    status: str,
) -> dict[str, Any]:
    plans = _latest_checkpoint_plans(card)
    evidence_codes = [
        f"{_text(plan.get('checkpoint'))}:{_text(plan.get('status'))}" for plan in plans
    ]
    enhancements = _mapping(factor_checklist.get("enhancement_quality"))
    non_blocking = [
        _text(item.get("display_name_zh"), _text(item.get("factor_id")))
        for item in _mapping_list(factor_checklist.get("factors"))
        if _text(item.get("factor_id"))
        in set(_string_list(enhancements.get("missing_factor_ids")))
    ]
    base = {
        "next_checkpoint": None,
        "next_checkpoint_at": None,
        "non_blocking_missing_zh": non_blocking,
        "evidence_codes": evidence_codes,
    }
    if plans and all(_text(plan.get("status")) == "PLANNED" for plan in plans):
        next_plan = plans[0]
        return {
            **base,
            "status": "CHECKPOINT_NOT_DUE",
            "primary_blocker_zh": "第一个评估档位尚未到达",
            "missing_detail_zh": "候选轨道尚未启动；尚未发生门禁判定。",
            "next_step_zh": "等待最近一个已注册评估档位。",
            "next_checkpoint": _text(next_plan.get("checkpoint")),
            "next_checkpoint_at": _optional_text(next_plan.get("scheduled_at")),
        }

    xg = next(
        (
            row
            for row in _mapping_list(factor_checklist.get("factors"))
            if _text(row.get("factor_id")) == "F9_TRUE_XG"
        ),
        {},
    )
    if xg and _text(xg.get("state")) != "READY" and not evaluated:
        xg_evidence = _mapping(xg.get("evidence"))
        required = max(1, _int(xg_evidence.get("minimum_required")) or 3)
        return {
            **base,
            "status": "XG_INPUT_MISSING",
            "primary_blocker_zh": "模型核心输入未就绪",
            "missing_detail_zh": (
                f"四字段 xG：主队 {max(0, _int(xg_evidence.get('home_sample_count')))}/{required}，"
                f"客队 {max(0, _int(xg_evidence.get('away_sample_count')))}/{required}。"
            ),
            "next_step_zh": "等待真实历史 xG 达到既有样本门槛。",
        }

    opportunity_by_identity = {
        _text(row.get("opportunity_identity_hash")): row
        for row in opportunities
        if _text(row.get("opportunity_identity_hash"))
    }
    blocked_attempts = [
        item
        for item in official_attempts
        if _text(item[0].get("first_failed_gate"))
        or _text(
            _mapping(opportunity_by_identity.get(_text(item[0].get("opportunity_identity_hash")))).get(
                "state"
            )
        )
        == "BLOCKED_BY_GATE"
    ]
    if blocked_attempts and status not in {"CANDIDATE", "TECHNICAL_INVALIDATED"}:
        row, _state, evaluated_at = max(blocked_attempts, key=lambda item: item[2])
        gate = _text(row.get("first_failed_gate")) or next(
            iter(_string_list(row.get("blockers"))), "UNKNOWN_GATE"
        )
        detail = {
            "MAINLINE_PARSED": "主盘无法解析（MAINLINE_NOT_PARSED）。",
            "PAIR_COMPLETE": "主盘双边报价不完整（PAIR_INCOMPLETE）。",
            "SOURCE_OBSERVATIONS_PRESENT": "缺少原始市场观测（SOURCE_OBSERVATIONS_ABSENT）。",
        }.get(gate)
        if gate in {"BOOKMAKER_DEPTH", "INSUFFICIENT_BOOKMAKER_DEPTH"}:
            detail = f"机构深度 {_int(row.get('bookmaker_count'))} 家 / 需 3 家。"
        elif gate in {"QUOTE_FRESH", "CURRENT_QUOTE_STALE"}:
            captured_at = _datetime(row.get("capture_at"))
            age_seconds = int((evaluated_at - captured_at).total_seconds()) if captured_at else None
            detail = (
                f"报价年龄 {max(0, age_seconds) // 60} 分钟 / 需 ≤30 分钟。"
                if age_seconds is not None
                else "当前报价时效证据缺失。"
            )
        return {
            **base,
            "status": "GATE_BLOCKED",
            "primary_blocker_zh": "候选门禁未通过",
            "missing_detail_zh": detail or f"{gate} 未通过。",
            "next_step_zh": "等待下一官方检查点使用新证据重新评估。",
            "evidence_codes": [*evidence_codes, gate],
        }

    no_edge_evaluated = any(
        state in {"NO_EDGE_CURRENT", "ANALYSIS_COMPLETE"} for _row, state, _at in evaluated
    )
    if status == "CANDIDATE":
        evaluated_times = [at for _row, _state, at in evaluated]
        later_unassessed = [
            row
            for row in opportunities
            if _text(row.get("state")) not in _EVALUATED_OPPORTUNITY_STATES
            and (
                not evaluated_times
                or (
                    _datetime(row.get("scheduled_checkpoint_at"))
                    or datetime.min.replace(tzinfo=UTC)
                )
                > max(evaluated_times)
            )
        ]
        checkpoints = list(
            dict.fromkeys(
                _EVALUATION_CHECKPOINT_LABELS.get(
                    _text(row.get("evaluation_slot_id")), _text(row.get("evaluation_slot_id"))
                )
                for row in sorted(later_unassessed, key=_opportunity_order)
            )
        )
        return {
            **base,
            "status": "CANDIDATE_ACTIVE",
            "primary_blocker_zh": "最终仍为候选",
            "missing_detail_zh": (
                f"此后 {' / '.join(checkpoints)} 未产出评估，不影响最后一次成功确认。"
                if checkpoints
                else "候选轨道已完成评估并保持有效。"
            ),
            "next_step_zh": "等待赛果进入既有结算流程。",
        }
    missed = [row for row in opportunities if _text(row.get("state")) == "MISSED_CHECKPOINT"]
    if missed and (status == "TECHNICAL_INVALIDATED" or not evaluated):
        candidate_times = [
            evaluated_at
            for _row, state, evaluated_at in evaluated
            if state == "ANALYSIS_PICK_ACTIVE"
        ]
        after_candidate = [
            row
            for row in missed
            if not candidate_times
            or (_datetime(row.get("scheduled_checkpoint_at")) or datetime.min.replace(tzinfo=UTC))
            > max(candidate_times)
        ]
        causal = after_candidate or missed
        checkpoints = list(
            dict.fromkeys(
                _EVALUATION_CHECKPOINT_LABELS.get(
                    _text(row.get("evaluation_slot_id")), _text(row.get("evaluation_slot_id"))
                )
                for row in causal
            )
        )
        return {
            **base,
            "status": "CHECKPOINT_MISSED",
            "primary_blocker_zh": "官方检查点错过",
            "missing_detail_zh": f"未完成档位：{' / '.join(checkpoints)}。",
            "next_step_zh": "赛前流程已结束；保留技术失效记录，不回填历史。",
        }

    provider_empty = [plan for plan in plans if _text(plan.get("status")) == "PROVIDER_EMPTY"]
    if provider_empty and (ever_formed_candidate or not no_edge_evaluated):
        plan = provider_empty[-1]
        endpoints = {
            _text(row.get("endpoint")): row
            for row in _mapping_list(plan.get("endpoint_results"))
        }
        if _text(_mapping(endpoints.get("odds")).get("status")) == "CAPTURED" and _text(
            _mapping(endpoints.get("lineups")).get("status")
        ) == "PROVIDER_EMPTY":
            detail = "赔率已采到，阵容为空；多端点档位因此整体为 PROVIDER_EMPTY。"
        else:
            detail = "；".join(
                f"{name}={_text(row.get('status'), 'UNKNOWN')}"
                for name, row in sorted(endpoints.items())
            ) or "Provider 返回空结果。"
        checkpoint = _text(plan.get("checkpoint"))
        return {
            **base,
            "status": "PROVIDER_EMPTY",
            "primary_blocker_zh": "Provider 空结果",
            "missing_detail_zh": (
                f"{_EVALUATION_CHECKPOINT_LABELS.get(checkpoint, checkpoint)}：{detail}"
            ),
            "next_step_zh": "保留端点与评估证据供审计；不回填、不改写已有记录。",
        }

    failed = [plan for plan in plans if _text(plan.get("status")) == "FAILED"]
    if failed or any(_text(row.get("state")) == "EVALUATION_ERROR" for row in opportunities):
        plan = failed[-1] if failed else {}
        checkpoint = _text(plan.get("checkpoint"), "UNKNOWN_CHECKPOINT")
        return {
            **base,
            "status": "EVALUATION_ERROR",
            "primary_blocker_zh": "评估异常",
            "missing_detail_zh": (
                f"{_EVALUATION_CHECKPOINT_LABELS.get(checkpoint, checkpoint)} 执行失败。"
            ),
            "next_step_zh": "检查调度与评估错误证据；不改写既有账本。",
        }

    if no_edge_evaluated:
        return {
            **base,
            "status": "NO_EDGE",
            "primary_blocker_zh": "已完整评估但无价值差",
            "missing_detail_zh": _no_edge_detail(evaluated),
            "next_step_zh": "保留该次完整评估；无需把 NO_EDGE 解释为数据缺失。",
        }
    return {
        **base,
        "status": "UNASSESSED",
        "primary_blocker_zh": "尚无权威评估结论",
        "missing_detail_zh": "当前没有足够的候选轨道证据定位原因。",
        "next_step_zh": "查看已注册档位与只读技术证据。",
    }


def _evaluation_execution(
    card: Mapping[str, Any], factor_checklist: Mapping[str, Any]
) -> dict[str, Any]:
    official_attempts = []
    evaluated = []
    for version in _mapping_list(_mapping(card.get("dynamic_prematch")).get("versions")):
        if (
            version.get("official_funnel_eligible") is not True
            or _text(version.get("measurement_semantics")) != _OFFICIAL_EVALUATION_SEMANTICS
        ):
            continue
        state = _text(version.get("state"))
        evaluated_at = _datetime(version.get("evaluated_at"))
        if evaluated_at is not None:
            official_attempts.append((version, state, evaluated_at))
        if state not in {"NO_EDGE_CURRENT", "ANALYSIS_COMPLETE", "ANALYSIS_PICK_ACTIVE"}:
            continue
        if evaluated_at is None:
            continue
        evaluated.append((version, state, evaluated_at))
    opportunities = _mapping_list(_mapping(card.get("dynamic_prematch")).get("opportunities"))
    evaluated_attempts = {
        (
            _text(version.get("opportunity_identity_hash")),
            _text(version.get("attempt_identity_hash")),
        )
        for version, _state, _evaluated_at in official_attempts
        if _text(version.get("opportunity_identity_hash"))
        and _text(version.get("attempt_identity_hash"))
    }
    final_by_market: dict[str, Mapping[str, Any]] = {}
    for opportunity in opportunities:
        if (
            _text(opportunity.get("state")) not in _EVALUATED_OPPORTUNITY_STATES
            or (
                _text(opportunity.get("opportunity_identity_hash")),
                _text(opportunity.get("latest_attempt_identity_hash")),
            )
            not in evaluated_attempts
        ):
            continue
        market = _text(opportunity.get("market"))
        if not market:
            continue
        previous = final_by_market.get(market)
        order = (
            _text(opportunity.get("scheduled_checkpoint_at")),
            _text(opportunity.get("recorded_at")),
            _text(opportunity.get("opportunity_identity_hash")),
        )
        previous_order = (
            (
                _text(previous.get("scheduled_checkpoint_at")),
                _text(previous.get("recorded_at")),
                _text(previous.get("opportunity_identity_hash")),
            )
            if previous
            else ("", "", "")
        )
        if previous is None or order > previous_order:
            final_by_market[market] = opportunity
    later_unassessed_by_market: dict[str, list[str]] = {}
    for market, final in final_by_market.items():
        final_order = _opportunity_order(final)
        later_unassessed_by_market[market] = list(
            dict.fromkeys(
                _EVALUATION_CHECKPOINT_LABELS.get(
                    _text(row.get("evaluation_slot_id")),
                    _text(row.get("evaluation_slot_id")),
                )
                for row in sorted(opportunities, key=_opportunity_order)
                if _text(row.get("market")) == market
                and (
                    _text(row.get("state")) not in _EVALUATED_OPPORTUNITY_STATES
                    or (
                        _text(row.get("opportunity_identity_hash")),
                        _text(row.get("latest_attempt_identity_hash")),
                    )
                    not in evaluated_attempts
                )
                and _opportunity_order(row) > final_order
            )
        )
    checkpoints: dict[str, set[str]] = {}
    ordered = sorted(evaluated, key=lambda item: _text(item[0].get("evaluated_at")))
    for version, _, _ in ordered:
        slot = _text(
            version.get("evaluation_slot_id"),
            _text(version.get("checkpoint"), "UNKNOWN_CHECKPOINT"),
        )
        label = _EVALUATION_CHECKPOINT_LABELS.get(slot, slot)
        checkpoints.setdefault(label, set()).add(_text(version.get("market")))
    labels = list(checkpoints)
    market_names = sorted({market for markets in checkpoints.values() for market in markets})
    ever_formed_candidate = any(state == "ANALYSIS_PICK_ACTIVE" for _, state, _ in evaluated)
    final_states = {_text(row.get("state")) for row in final_by_market.values()}
    if "EVALUATED_CANDIDATE" in final_states:
        status = "CANDIDATE"
    elif "BLOCKED_BY_GATE" in final_states:
        status = "BLOCKED"
    elif "EVALUATED_NO_EDGE" in final_states:
        status = "NO_EDGE"
    elif ever_formed_candidate:
        status = "CANDIDATE"
    elif evaluated:
        status = "NO_EDGE"
    else:
        status = "UNASSESSED"

    latest_candidates: dict[str, tuple[Mapping[str, Any], datetime]] = {}
    for version, state, evaluated_at in evaluated:
        if state != "ANALYSIS_PICK_ACTIVE":
            continue
        market = _text(version.get("market"))
        previous_candidate_row = latest_candidates.get(market)
        if previous_candidate_row is None or evaluated_at > previous_candidate_row[1]:
            latest_candidates[market] = (version, evaluated_at)
    candidate_rows = [
        {
            "market": market,
            "selection": _optional_text(version.get("selection")),
            "exact_line": _optional_text(version.get("exact_line")),
            "decimal_odds": _number(version.get("decimal_odds")),
            "bookmaker_id": _optional_text(version.get("bookmaker_id")),
            "captured_at": _optional_text(version.get("capture_at")),
            "evaluated_at": _optional_text(version.get("evaluated_at")),
            "checkpoint": _EVALUATION_CHECKPOINT_LABELS.get(
                _text(version.get("evaluation_slot_id"), version.get("checkpoint")),
                _text(version.get("evaluation_slot_id"), version.get("checkpoint")),
            ),
            "final_state": _optional_text(_mapping(final_by_market.get(market)).get("state")),
            "final_active": _text(_mapping(final_by_market.get(market)).get("state"))
            == "EVALUATED_CANDIDATE"
            or (not final_by_market and status == "CANDIDATE"),
            "later_unassessed_checkpoints": later_unassessed_by_market.get(market, []),
        }
        for market, (version, _evaluated_at) in sorted(latest_candidates.items())
    ]
    final_rows = [
        {
            "market": market,
            "checkpoint": _EVALUATION_CHECKPOINT_LABELS.get(
                _text(row.get("evaluation_slot_id")),
                _text(row.get("evaluation_slot_id")),
            ),
            "state": _text(row.get("state")),
            "recorded_at": _optional_text(row.get("recorded_at")),
            "blocker": _optional_text(row.get("blocker")),
        }
        for market, row in sorted(final_by_market.items())
    ]
    lifecycle_notes = [
        (
            "最终确认于 "
            f"{_evaluation_checkpoint_label(row.get('evaluation_slot_id'))}；"
            f"此后 {' / '.join(later_unassessed_by_market.get(market, []))} "
            "未产出评估，不影响该确认"
        )
        for market, row in sorted(final_by_market.items())
        if _text(row.get("state")) == "EVALUATED_CANDIDATE"
        and later_unassessed_by_market.get(market)
    ]
    lifecycle_note = "；".join(dict.fromkeys(lifecycle_notes)) or None
    if status == "UNASSESSED":
        summary = "尚无候选评估记录；当前仍处于等待采集或硬门判定阶段。"
    elif status == "TECHNICAL_INVALIDATED":
        summary = (
            "曾形成候选，但后续官方检查点错过或评估失败，最终未保持有效；"
            "这是技术失效，不代表模型主动撤回。"
        )
    elif status == "NO_CANDIDATE_FORMED":
        summary = "本场未形成候选；期间有检查点错过，但不影响该结论。"
    elif status == "BLOCKED":
        summary = (
            "曾形成候选，最后官方状态已被门禁阻断，不计入正式推荐。"
            if ever_formed_candidate
            else "最后官方状态被门禁阻断，未形成有效候选。"
        )
    else:
        checkpoint_copy = " / ".join(labels)
        market_copy = (
            "两个市场均为 NO_EDGE —— 模型与市场看法一致，无可利用价差。"
            if status == "NO_EDGE"
            and all({"ASIAN_HANDICAP", "TOTALS"} <= markets for markets in checkpoints.values())
            else "最后官方状态仍为候选，计入正式推荐。"
            if status == "CANDIDATE"
            else "已完成市场评估。"
        )
        summary = (
            f"已评估 {len(labels)} 次（{checkpoint_copy}），{market_copy}"
            "模型—市场对比图需已验证校准，暂不绘制。"
        )
        if lifecycle_note:
            summary += lifecycle_note + "。"
    return {
        "status": status,
        "ever_formed_candidate": ever_formed_candidate,
        "final_states": final_rows,
        "latest_candidates": candidate_rows,
        "checkpoint_count": len(labels),
        "market_evaluation_count": len(evaluated),
        "checkpoints": labels,
        "markets": market_names,
        "summary_zh": summary,
        "lifecycle_note_zh": lifecycle_note,
        "diagnosis": _evaluation_diagnosis(
            card,
            official_attempts=official_attempts,
            evaluated=evaluated,
            opportunities=opportunities,
            factor_checklist=factor_checklist,
            ever_formed_candidate=ever_formed_candidate,
            status=status,
        ),
    }


def _opportunity_order(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("scheduled_checkpoint_at")),
        _text(row.get("recorded_at")),
        _text(row.get("opportunity_identity_hash")),
    )


def _evaluation_checkpoint_label(value: Any) -> str:
    checkpoint = _text(value)
    return _EVALUATION_CHECKPOINT_LABELS.get(checkpoint, checkpoint)


def _match(
    card: Mapping[str, Any],
    *,
    candidate_enabled: bool,
    generated_at: Any,
    ledger_fact: Mapping[str, Any],
    enabled_analysis_markets: set[str],
) -> dict[str, Any]:
    fixture_finished = normalize_match_status(card.get("status")) == "FINISHED"
    radar = _mapping(card.get("market_radar"))
    model_lab = _mapping(card.get("model_lab"))
    data_refresh = _mapping(card.get("data_refresh"))
    market_collection = _market_collection(data_refresh)
    lineup_collection = _lineup_collection(data_refresh)
    markets = {
        name: _market(
            _mapping(_mapping(radar.get("markets")).get(name)),
            name,
            generated_at=card.get("kickoff_utc") if fixture_finished else generated_at,
        )
        for name in ("ASIAN_HANDICAP", "TOTALS")
    }
    _mark_market_depth_asymmetry(markets)
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
    market_evidence_ready = any(
        _text(_mapping(market.get("eligibility")).get("observation_status")) == "AVAILABLE"
        for market in markets.values()
    )
    candidate_input_ready = any(
        _text(_mapping(market.get("eligibility")).get("candidate_eligibility_status")) == "READY"
        for market in markets.values()
    )
    home_team_label = _public_team_label(card, "home")
    away_team_label = _public_team_label(card, "away")
    shadow_candidate = _shadow_candidate(
        card,
        markets=markets,
        enabled=candidate_enabled,
        enabled_analysis_markets=enabled_analysis_markets,
    )
    factor_checklist = build_fixture_factor_checklist(
        card,
        markets=markets,
        market_collection=market_collection,
        lineup_collection=lineup_collection,
        home_identity_ready=home_team_label["state"] != "IDENTITY_UNRESOLVED",
        away_identity_ready=away_team_label["state"] != "IDENTITY_UNRESOLVED",
        shadow_candidate=shadow_candidate,
        market_aggregate_status=market_aggregate_status,
        ledger_fact=ledger_fact,
        generated_at=generated_at,
        fixture_finished=fixture_finished,
    )
    evaluation_execution = _evaluation_execution(card, factor_checklist)
    return {
        "fixture_id": _text(card.get("fixture_id")),
        "competition_id": _optional_text(card.get("competition_id")),
        "competition_name": _optional_text(card.get("competition_name")),
        "kickoff_utc": card.get("kickoff_utc"),
        "home_team_name": _optional_text(card.get("home_team_name")),
        "away_team_name": _optional_text(card.get("away_team_name")),
        "home_team_label": home_team_label,
        "away_team_label": away_team_label,
        "status": _optional_text(card.get("status")),
        "market_collection": market_collection,
        "lineup_collection": lineup_collection,
        "intelligence_state": _text(card.get("intelligence_state"), "DATA_INCOMPLETE"),
        "intelligence_reason_codes": _string_list(card.get("intelligence_reason_codes")),
        "risks": _match_risks(
            _mapping(card.get("risk_dimensions")),
            market_collection,
            lineup_collection,
            missing_fields=_string_list(card.get("missing_fields")),
            factor_checklist=factor_checklist,
            fixture_finished=fixture_finished,
            evaluation_execution=evaluation_execution,
        ),
        "readiness": {
            "status": _text(card.get("data_status"), "BLOCKED"),
            "reason_code": _optional_text(card.get("reason_code")),
            "reason_codes": _string_list(card.get("intelligence_reason_codes")),
            "missing_fields": _string_list(card.get("missing_fields")),
            "stale_fields": _string_list(card.get("stale_fields")),
            "action": _optional_text(card.get("action")),
            "next_eval_at": card.get("next_eval_at"),
            "provider_budget_status": _optional_text(card.get("provider_budget_status")),
            "lineup_status": _optional_text(data_refresh.get("lineups_status")),
            "lineup_expectation": _optional_text(card.get("lineup_requirement")),
            "market_aggregate_status": market_aggregate_status,
            "market_evidence_status": "AVAILABLE" if market_evidence_ready else "NOT_READY",
            "candidate_input_status": ("READY" if candidate_input_ready else "NOT_READY"),
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
        "evaluation_execution": evaluation_execution,
        "shadow_candidate": shadow_candidate,
        "factor_checklist": factor_checklist,
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
                    "quote_age_seconds": item["quote_age_seconds"],
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


def _match_outcome(
    card: Mapping[str, Any],
    match: Mapping[str, Any],
    replay_card: Mapping[str, Any],
    outcome_summary: Mapping[str, Any],
    *,
    generated_at: Any,
) -> dict[str, Any]:
    fixture_id = _text(match.get("fixture_id"))
    tracked_ids = set(_string_list(outcome_summary.get("tracked_fixture_ids")))
    recorded_ids = set(_string_list(outcome_summary.get("matched_fixture_ids")))
    is_tracked = (
        card.get("outcome_tracked") is True
        or replay_card.get("outcome_tracked") is True
        or fixture_id in tracked_ids
    )
    is_recorded = (
        _text(replay_card.get("outcome_status")) == "MATCHED" or fixture_id in recorded_ids
    )
    is_finished = normalize_match_status(match.get("status")) == "FINISHED" or is_recorded
    cause = outcome_public_cause(
        status="FINISHED" if is_recorded else match.get("status"),
        kickoff_utc=match.get("kickoff_utc"),
        as_of=generated_at,
        is_tracked=is_tracked,
        is_recorded=is_recorded,
    )
    return {
        "is_finished": is_finished,
        "is_tracked": is_tracked,
        "is_recorded": is_recorded,
        "public_semantics": {"scope": "MATCH", "cause": cause},
    }


def _shadow_candidate(
    card: Mapping[str, Any],
    *,
    markets: Mapping[str, Mapping[str, Any]],
    enabled: bool,
    enabled_analysis_markets: set[str],
) -> dict[str, Any]:
    decision = _mapping(card.get("recommendation_decision_v4"))
    reason = _mapping(decision.get("reason"))
    selected = _mapping(decision.get("selected_candidate"))
    selected_market = _text(selected.get("market"))
    eligibility = _mapping(_mapping(markets.get(selected_market)).get("eligibility"))
    active = (
        enabled
        and selected_market in enabled_analysis_markets
        and _text(decision.get("outcome")) == "ANALYSIS_PICK"
        and bool(selected)
        and _text(eligibility.get("candidate_eligibility_status")) == "READY"
    )
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


def _market_collection(data_refresh: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(data_refresh.get("market_collection"))
    semantics = _mapping(source.get("public_semantics"))
    return {
        "latest_snapshot_at": source.get("latest_snapshot_at"),
        "latest_snapshot_checkpoint": _optional_text(source.get("latest_snapshot_checkpoint")),
        "target_checkpoint": _optional_text(source.get("target_checkpoint")),
        "scheduled_at": source.get("scheduled_at"),
        "window_end_at": source.get("window_end_at"),
        "overdue": bool(source.get("overdue") is True),
        "public_semantics": {
            "scope": "MATCH",
            "cause": semantics.get("cause") if semantics else "UNASSESSED",
        },
    }


def _lineup_collection(data_refresh: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(data_refresh.get("lineup_collection"))
    semantics = _mapping(source.get("public_semantics"))
    return {
        "target_checkpoint": _optional_text(source.get("target_checkpoint")),
        "scheduled_at": source.get("scheduled_at"),
        "window_end_at": source.get("window_end_at"),
        "overdue": bool(source.get("overdue") is True),
        "public_semantics": {
            "scope": "MATCH",
            "cause": semantics.get("cause") if semantics else "UNASSESSED",
        },
    }


def _market(
    raw: Mapping[str, Any],
    name: str,
    *,
    generated_at: Any,
) -> dict[str, Any]:
    current = _mapping(raw.get("current"))
    timeline = _mapping(raw.get("timeline"))
    movement = _mapping(raw.get("movement"))
    count = max(0, _int(raw.get("snapshot_count")))
    source_status = _text(raw.get("status"), "INSUFFICIENT")
    points = [
        {
            "capture_id": _optional_text(point.get("capture_id")),
            "checkpoint": _optional_text(point.get("checkpoint")),
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
    latest_snapshot_at = (
        max(captured_times) if captured_times else _optional_text(current.get("captured_at"))
    )
    public_status = "READY" if current else "INSUFFICIENT"
    trend_evidence_status = (
        "AVAILABLE"
        if len(points) >= 2 and movement_payload["status"] != "INSUFFICIENT"
        else "INSUFFICIENT"
    )
    cross_sectional_status = (
        "AVAILABLE"
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
        "quote_age_seconds": _age_seconds(generated_at, latest_snapshot_at),
        "timeline_points": points,
        "movement": movement_payload,
        "reason_codes": [
            str(value) for value in (movement.get("reason_code"), timeline.get("status")) if value
        ],
        "trend_evidence_status": trend_evidence_status,
        "cross_sectional_comparison_status": cross_sectional_status,
        "latest_snapshot_at": latest_snapshot_at,
    }


def _mark_market_depth_asymmetry(markets: Mapping[str, dict[str, Any]]) -> None:
    handicap = markets["ASIAN_HANDICAP"]
    totals = markets["TOTALS"]
    handicap_depth = {
        point["captured_at"]: point["bookmaker_count"]
        for point in handicap["timeline_points"]
        if point["captured_at"] and point["bookmaker_count"] > 0
    }
    totals_depth = {
        point["captured_at"]: point["bookmaker_count"]
        for point in totals["timeline_points"]
        if point["captured_at"] and point["bookmaker_count"] > 0
    }
    if (
        any(
            handicap_depth[captured_at] * 2 < totals_depth[captured_at]
            for captured_at in handicap_depth.keys() & totals_depth.keys()
        )
        and MARKET_DEPTH_ASYMMETRY_REASON not in handicap["reason_codes"]
    ):
        handicap["reason_codes"].append(MARKET_DEPTH_ASYMMETRY_REASON)


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
    observation_status = "AVAILABLE" if _text(market.get("status")) == "READY" else "INSUFFICIENT"
    blockers = _string_list(candidate.get("blockers"))
    if observation_status != "AVAILABLE":
        blockers.append("MARKET_EVIDENCE_NOT_AVAILABLE")
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
        "candidate_quote_lock_status": "READY" if quote_ready else "NOT_READY",
        "candidate_model_status": "READY" if model_ready else "NOT_READY",
        "candidate_eligibility_status": eligibility,
        "blockers": list(dict.fromkeys(blockers)),
    }


def _market_aggregate_status(markets: Mapping[str, Mapping[str, Any]]) -> str:
    eligibility = [_mapping(market.get("eligibility")) for market in markets.values()]
    if eligibility and all(
        _text(item.get("candidate_eligibility_status")) == "READY" for item in eligibility
    ):
        return "READY"
    if any(_text(item.get("candidate_eligibility_status")) == "READY" for item in eligibility):
        return "PARTIAL"
    return "NOT_READY"


def _public_team_label(card: Mapping[str, Any], side: str) -> dict[str, Any]:
    source = _mapping(card.get(f"{side}_team_label"))
    provider_team_id = _optional_text(source.get("provider_team_id")) or _optional_text(
        card.get(f"{side}_team_id")
    )
    state = _text(source.get("state"), "IDENTITY_UNRESOLVED")
    display_name = _optional_text(source.get("display_name"))
    raw_provider_name = _optional_text(source.get("raw_provider_name")) or _optional_text(
        card.get(f"{side}_team_name")
    )
    if not display_name:
        role = "主队" if side == "home" else "客队"
        suffix = f"：{provider_team_id}" if provider_team_id else ""
        display_name = (
            raw_provider_name or f"{role}（中文译名待映射）"
            if state == "CANONICAL_IDENTITY_READY_LABEL_MISSING"
            else f"{role}（身份待确认{suffix}）"
        )
    cause = {
        "CHINESE_LABEL_PENDING_OWNER_REVIEW": "LABEL_PENDING_OWNER_REVIEW",
        "CANONICAL_IDENTITY_READY_LABEL_MISSING": "LABEL_MISSING",
        "IDENTITY_UNRESOLVED": "IDENTITY_UNRESOLVED",
        "AMBIGUOUS": "AMBIGUOUS",
    }.get(state)
    return {
        "display_name": display_name,
        "state": state,
        "canonical_team_id": _optional_text(source.get("canonical_team_id")),
        "provider_team_id": provider_team_id,
        "public_semantics": {"scope": "MATCH", "cause": cause},
        "technical": {
            "raw_provider_name": raw_provider_name,
        },
    }


def _date_strip_entry(raw: Mapping[str, Any]) -> dict[str, Any]:
    semantics = _mapping(raw.get("public_semantics"))
    if not semantics:
        cause = {
            "PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW": "NOT_YET_DUE",
            "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY": "AWAITING_COLLECTION",
            "MARKET_COLLECTION_PLAN_NOT_PERSISTED": "UNASSESSED",
        }.get(_text(raw.get("market_collection_window_status")))
        semantics = {"scope": "SELECTED_DAY", "cause": cause}
    return {
        "football_day": _text(raw.get("football_day")),
        "fixture_count": max(0, _int(raw.get("fixture_count"))),
        "competition_count": max(0, _int(raw.get("competition_count"))),
        "finished_fixture_count": max(0, _int(raw.get("finished_fixture_count"))),
        "upcoming_fixture_count": max(0, _int(raw.get("upcoming_fixture_count"))),
        "persisted_inventory_status": _text(raw.get("persisted_inventory_status")),
        "persisted_competition_coverage_count": max(
            0, _int(raw.get("persisted_competition_coverage_count"))
        ),
        "active_whitelist_count": max(0, _int(raw.get("active_whitelist_count"))),
        "market_collection_window_status": _text(raw.get("market_collection_window_status")),
        "market_evidence_fixture_count": max(0, _int(raw.get("market_evidence_fixture_count"))),
        "public_semantics": dict(semantics),
    }


def _model_relation(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    return {
        "market": name,
        "status": _text(raw.get("status"), "MARKET_NOT_READY"),
        "canonical_line": _optional_text(raw.get("canonical_line")),
        "bookmaker_count": max(0, _int(raw.get("bookmaker_count"))),
        "market_quote_age_seconds": _optional_nonnegative_int(raw.get("market_quote_age_seconds")),
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
        "simulations_completed": simulations_completed if ready else None,
        "top3": top3 if ready else [],
    }


def _validation(
    forward: Mapping[str, Any],
    replay: Mapping[str, Any],
    matches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
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
    selected_day_record = _selected_day_record_semantics(matches)
    replay_status = _text(replay.get("replay_status"), "NO_REPLAY_INPUTS")
    replay_gaps = _string_list(replay.get("replay_gaps"))
    outcome_summary = _mapping(replay.get("outcome_tracking_summary"))
    record_kind = selected_day_record["record_kind"]
    if record_kind == "EMPTY":
        replay_status = "EMPTY"
        replay_gaps = []
    elif record_kind == "FORWARD_RECORD":
        replay_status = "FORWARD_RECORD"
        replay_gaps = [gap for gap in replay_gaps if gap != "MISSING_OUTCOMES"]
    elif _int(outcome_summary.get("missing_outcome_count")) > 0:
        replay_status = "MISSING_OUTCOMES"
        if "MISSING_OUTCOMES" not in replay_gaps:
            replay_gaps.append("MISSING_OUTCOMES")
    else:
        replay_status = "READY"
        replay_gaps = [gap for gap in replay_gaps if gap != "MISSING_OUTCOMES"]
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
            "public_semantics": {
                "scope": "CROSS_DAY_CUMULATIVE",
                "cause": None if forward else "INSUFFICIENT",
            },
        },
        "history_replay": {
            "status": replay_status,
            "known_at": {
                key: _mapping(replay.get("known_at_summary")).get(key)
                for key in ("has_day_view", "generated_at", "source", "checkpoint_key")
            },
            "decision_summary": dict(_mapping(replay.get("decision_summary"))),
            "reason_summary": _mapping_list(replay.get("reason_summary")),
            "outcome_tracking_summary": dict(_mapping(replay.get("outcome_tracking_summary"))),
            "card_hash_checks": _mapping_list(replay.get("card_hash_checks")),
            "replay_gaps": replay_gaps,
            **selected_day_record,
        },
    }


def _selected_day_record_semantics(
    matches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not matches:
        return {
            "record_kind": "EMPTY",
            "public_semantics": {"scope": "SELECTED_DAY", "cause": None},
        }
    finished = [bool(_mapping(match.get("outcome")).get("is_finished")) for match in matches]
    outcome_causes = [
        _mapping(_mapping(match.get("outcome")).get("public_semantics")).get("cause")
        for match in matches
    ]
    cause = selected_day_outcome_cause(finished, outcome_causes)
    return {
        "record_kind": selected_day_record_kind(finished),
        "public_semantics": {"scope": "SELECTED_DAY", "cause": cause},
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
    system_health = _text(degradation.get("state"), "UNKNOWN")
    return {
        "read_model_source": _text(day_view.get("source")),
        "checkpoint_key": _text(day_view.get("checkpoint_key")),
        "degradation": degradation,
        "counts": safe_counts,
        "system_health": system_health,
        "provider_budget_status": _text(freshness.get("provider_budget_status"), "UNKNOWN"),
    }


def _priority_reasons(match: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    if normalize_match_status(match.get("status")) == "FINISHED":
        return None, []
    reasons: set[str] = set()
    markets = _mapping(_mapping(match.get("market_radar")).get("markets"))
    relation = _mapping(_mapping(match.get("w2_analysis")).get("model_market_relation"))
    diagnosis_status = _text(
        _mapping(_mapping(match.get("evaluation_execution")).get("diagnosis")).get("status")
    )

    if diagnosis_status in {"CHECKPOINT_MISSED", "PROVIDER_EMPTY", "EVALUATION_ERROR"}:
        reasons.add("COLLECTION_INCIDENT")
    if diagnosis_status == "XG_INPUT_MISSING":
        reasons.add("DATA_INCOMPLETE")
    if diagnosis_status == "GATE_BLOCKED":
        reasons.add("CANDIDATE_INPUT_NOT_READY")
    if any(_is_attention_worthy_movement(_mapping(market)) for market in markets.values()):
        reasons.add("MARKET_MOVEMENT")
    if any(
        _text(_mapping(market).get("status")) == "READY"
        and _text(_mapping(relation.get(name)).get("status"))
        not in {"", "MARKET_NOT_READY", "NOT_AVAILABLE"}
        for name, market in markets.items()
    ) and _text(match.get("intelligence_state")) in {
        "MODEL_DIAGNOSTIC_WARNING",
        "MODEL_MARKET_DISAGREEMENT",
        "MARKET_ANOMALY",
    }:
        reasons.add("MODEL_DIAGNOSTIC")

    primary = next(
        (
            reason
            for reason in sorted(
                reasons,
                key=lambda reason: (PRIMARY_REASON_ORDER.get(reason, 99), reason),
            )
            if reason in PRIMARY_REASON_ORDER
        ),
        None,
    )
    secondary = sorted(
        reasons - ({primary} if primary else set()),
        key=lambda reason: (ATTENTION_REASON_ORDER[reason], reason),
    )
    return primary, secondary


def _is_attention_worthy_movement(market: Mapping[str, Any]) -> bool:
    if _text(market.get("status")) != "READY" or _int(market.get("snapshot_count")) < 2:
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
        _relative_price_change(prices.get(side), delta) >= MARKET_PRICE_ATTENTION_THRESHOLD_RATIO
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


def _selected_day_semantics(
    semantics: Mapping[str, Any], matches: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    has_usable_evidence = any(_evidence_rank(match) < 4 for match in matches)
    selected = {"scope": "SELECTED_DAY", "cause": semantics.get("cause")}
    if selected["cause"] is None and matches and not has_usable_evidence:
        selected["cause"] = "INSUFFICIENT"
    return selected


def _match_public_semantics(
    match: Mapping[str, Any], selected_day_semantics: Mapping[str, Any]
) -> dict[str, Any]:
    selected_cause = selected_day_semantics.get("cause")
    if selected_cause is not None:
        return {"scope": "MATCH", "cause": selected_cause}
    readiness = _mapping(match.get("readiness"))
    cause = (
        None if _text(readiness.get("market_evidence_status")) == "AVAILABLE" else "INSUFFICIENT"
    )
    return {"scope": "MATCH", "cause": cause}


def _selected_focus_fixture_id(
    matches: Sequence[Mapping[str, Any]], selected_day_semantics: Mapping[str, Any]
) -> str | None:
    if selected_day_semantics.get("cause") is not None:
        return None
    usable = [match for match in matches if _evidence_rank(match) < 4]
    if not usable:
        return None
    if all(_calm_complete(match) for match in matches):
        return None
    focused = min(usable, key=_focus_rank)
    return _text(focused.get("fixture_id"))


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
    return 2


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
    selected_fixture_id: str | None,
    *,
    selected_day_semantics: Mapping[str, Any],
) -> dict[str, Any] | None:
    if selected_fixture_id is not None:
        return None
    freshness = _mapping(day_view.get("freshness"))
    cause = _optional_text(selected_day_semantics.get("cause"))
    next_evaluations = sorted(
        value
        for match in matches
        if (value := _mapping(match.get("readiness")).get("next_eval_at"))
        and _is_future_timestamp(value, day_view.get("generated_at"))
    )
    affected_matches = [
        match
        for match in matches
        if _text(_mapping(match.get("readiness")).get("market_evidence_status")) == "NOT_READY"
    ]
    common = {
        "affected_fixture_count": len(affected_matches) if cause else 0,
        "affected_competition_count": len(
            {
                match.get("competition_id")
                for match in affected_matches
                if match.get("competition_id")
            }
        )
        if cause
        else 0,
        "source_as_of": freshness.get("page_updated_at") or day_view.get("generated_at"),
        "next_eval_at": next_evaluations[0] if next_evaluations else None,
        "recovery_condition": None,
        "public_semantics": dict(selected_day_semantics),
    }
    if cause:
        ready_count = len(matches) - len(affected_matches)
        return {
            "reason_code": cause,
            "factual_summary": (
                "所选比赛日暂无可用于比赛级分析的持久化市场证据。"
                if ready_count == 0
                else f"所选比赛日已有 {ready_count} 场市场证据；"
                f"另有 {len(affected_matches)} 场尚未就绪。"
            ),
            "recovery_condition": "等待既有调度形成新的持久化证据；本页不会调用 Provider。",
            **{key: value for key, value in common.items() if key != "recovery_condition"},
        }
    if matches:
        return {
            "reason_code": "NO_PRIORITY_REVIEW_ITEMS",
            "factual_summary": "当前没有达到优先复核条件的比赛。",
            **common,
        }
    return {
        "reason_code": "NO_FIXTURES_IN_FOOTBALL_DAY",
        "factual_summary": "本比赛日观察池内没有比赛；不会从其他日期填充。",
        **common,
    }


def _is_future_timestamp(value: Any, generated_at: Any) -> bool:
    try:
        candidate = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        generated = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=UTC)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    return candidate > generated


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
    execution = _mapping(match.get("evaluation_execution"))
    if _text(execution.get("status")) == "UNASSESSED":
        diagnosis = _mapping(execution.get("diagnosis"))
        return "；".join(
            item
            for item in (
                _text(diagnosis.get("primary_blocker_zh")),
                _text(diagnosis.get("missing_detail_zh")),
            )
            if item
        )
    return _text(execution.get("summary_zh"))


def _risks(source: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dimension in ("EVENT_RISK", "DATA_RISK", "MODEL_RISK", "COLLECTION_RISK"):
        risk = dict(_mapping(source.get(dimension)))
        reasons = _string_list(risk.get("reason_codes"))
        if dimension == "MODEL_RISK" and risk.get("assessment_status") == "UNASSESSED":
            risk["explanation"] = "可比较模型尚无已验证校准证据"
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


def _match_risks(
    source: Mapping[str, Any],
    market_collection: Mapping[str, Any],
    lineup_collection: Mapping[str, Any],
    *,
    missing_fields: Sequence[str],
    factor_checklist: Mapping[str, Any],
    fixture_finished: bool = False,
    evaluation_execution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = _risks(source)
    data_risk = result["DATA_RISK"]
    lineup_cause = _optional_text(_mapping(lineup_collection.get("public_semantics")).get("cause"))
    market_cause = _optional_text(_mapping(market_collection.get("public_semantics")).get("cause"))
    diagnosis_status = _text(
        _mapping(_mapping(evaluation_execution).get("diagnosis")).get("status")
    )
    if market_cause == "NOT_YET_DUE" and diagnosis_status == "CHECKPOINT_NOT_DUE":
        data_risk["reason_codes"] = [
            reason
            for reason in _string_list(data_risk.get("reason_codes"))
            if reason != "DATA_MARKET_TIMELINE_INSUFFICIENT"
        ]
    hard_gate_factor_ids = {
        _text(factor.get("factor_id"))
        for factor in _mapping_list(factor_checklist.get("factors"))
        if factor.get("role_model_forecast") == "HARD_GATE"
        and factor.get("state") not in {"READY", "WAITING", "DISABLED"}
    }
    factor_by_field = {"xg": "F9_TRUE_XG", "lineups": "F10_LMM_V1"}
    blocking_fields = [
        field
        for field in missing_fields
        if factor_by_field.get(field) in hard_gate_factor_ids
        and not (field == "lineups" and lineup_cause == "NOT_YET_DUE")
    ]
    if blocking_fields and _text(data_risk.get("status")) != "OK":
        known = [
            MISSING_FIELD_LABELS[field]
            for field in blocking_fields
            if field in MISSING_FIELD_LABELS
        ]
        unknown_count = len(blocking_fields) - len(known)
        missing_copy = "、".join(known)
        if unknown_count:
            missing_copy += ("、" if missing_copy else "") + f"另有 {unknown_count} 项输入"
        data_risk["explanation"] = f"待补齐：{missing_copy}；既有采集或模型投影形成后解除"
    elif fixture_finished and "lineups" in missing_fields:
        data_risk.update(
            {
                "status": "ATTENTION",
                "reason_codes": ["LINEUP_COLLECTION_WINDOW_MISSED"],
                "explanation": "阵容采集窗口已结束且未形成证据；当前不作为模型预测硬门",
                "assessment_status": "ASSESSED_CURRENT",
                "evidence_basis": "LINEUP_COLLECTION_WINDOW_MISSED",
                "source_as_of": lineup_collection.get("window_end_at"),
            }
        )
    elif (
        missing_fields
        and not blocking_fields
        and set(_string_list(data_risk.get("reason_codes")))
        <= {"DATA_REQUIRED_INPUT_MISSING", "DATA_STATUS_BLOCKED"}
    ):
        data_risk.update(
            {
                "status": "OK",
                "reason_codes": [],
                "explanation": "尚无到期的数据输入缺口",
                "assessment_status": "ASSESSED_CURRENT",
                "evidence_basis": "LINEUP_COLLECTION_WINDOW_NOT_YET_DUE",
                "source_as_of": lineup_collection.get("scheduled_at"),
            }
        )
    semantics = _mapping(market_collection.get("public_semantics"))
    cause = _optional_text(semantics.get("cause"))
    source_as_of = market_collection.get("latest_snapshot_at")
    execution_status = _text(_mapping(evaluation_execution).get("status"))
    if fixture_finished and execution_status == "TECHNICAL_INVALIDATED":
        result["COLLECTION_RISK"] = {
            "dimension": "COLLECTION_RISK",
            "status": "INCIDENT",
            "reason_codes": ["OFFICIAL_CHECKPOINT_CONFIRMATION_FAILED"],
            "explanation": "赛前快照可审计，但后续官方检查点错过，候选技术失效",
            "assessment_status": "ASSESSED_INCIDENT",
            "evidence_basis": "DYNAMIC_PREMATCH_OPPORTUNITY_FINAL_STATE",
            "source_as_of": source_as_of,
        }
    elif fixture_finished:
        result["COLLECTION_RISK"] = {
            "dimension": "COLLECTION_RISK",
            "status": "OK",
            "reason_codes": [],
            "explanation": "赛前采集流程已结束；页面保留开球前最后快照供审计",
            "assessment_status": "ASSESSED_CURRENT",
            "evidence_basis": "FINISHED_FIXTURE_PREMATCH_SNAPSHOT",
            "source_as_of": source_as_of,
        }
    elif cause == "NOT_YET_DUE":
        result["COLLECTION_RISK"] = {
            "dimension": "COLLECTION_RISK",
            "status": "OK",
            "reason_codes": [],
            "explanation": "尚未到下一采集窗口，按既有计划正常等待",
            "assessment_status": "ASSESSED_CURRENT",
            "evidence_basis": "COLLECTION_WINDOW_NOT_YET_DUE",
            "source_as_of": source_as_of,
        }
    elif cause == "AWAITING_COLLECTION":
        overdue = bool(market_collection.get("overdue"))
        reason = (
            "COLLECTION_WINDOW_OVERDUE" if overdue else "COLLECTION_WINDOW_OPEN_AWAITING_CAPTURE"
        )
        result["COLLECTION_RISK"] = {
            "dimension": "COLLECTION_RISK",
            "status": "INCIDENT" if overdue else "ATTENTION",
            "reason_codes": [reason],
            "explanation": (
                "采集宽限已结束，计划快照仍未形成"
                if overdue
                else "已到采集时点，仍在计划宽限内等待快照"
            ),
            "assessment_status": "ASSESSED_INCIDENT" if overdue else "ASSESSED_CURRENT",
            "evidence_basis": reason,
            "source_as_of": source_as_of,
        }
    elif cause == "UNASSESSED":
        result["COLLECTION_RISK"] = {
            "dimension": "COLLECTION_RISK",
            "status": "ATTENTION",
            "reason_codes": ["COLLECTION_PLAN_UNASSESSED"],
            "explanation": "尚无可用于判定下一采集窗口的计划证据",
            "assessment_status": "UNASSESSED",
            "evidence_basis": "COLLECTION_PLAN_UNASSESSED",
            "source_as_of": source_as_of,
        }
    elif source_as_of is not None:
        result["COLLECTION_RISK"] = {
            "dimension": "COLLECTION_RISK",
            "status": "OK",
            "reason_codes": [],
            "explanation": "当前采集窗口已有持久化市场快照",
            "assessment_status": "ASSESSED_CURRENT",
            "evidence_basis": "PERSISTED_MARKET_SNAPSHOT",
            "source_as_of": source_as_of,
        }
    return result


def _age_seconds(later: Any, earlier: Any) -> int | None:
    later_at = _datetime(later)
    earlier_at = _datetime(earlier)
    if later_at is None or earlier_at is None or later_at < earlier_at:
        return None
    return int((later_at - earlier_at).total_seconds())


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
