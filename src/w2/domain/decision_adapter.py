from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from w2.domain.decision_card import DecisionCard, DecisionNonPick, DecisionPick
from w2.domain.decision_policy import (
    DecisionPolicyConfig,
    compute_lock_eligible,
    compute_outcome_tracked,
)
from w2.domain.enums import (
    DataStatus,
    DecisionReasonCode,
    DecisionTier,
    LifecycleStatus,
    ProbabilitySource,
)
from w2.domain.legacy_decision_shim import legacy_decision_view
from w2.models.fair_market_estimate import (
    estimate_snapshot_by_id,
    estimate_snapshots,
    verify_estimate_semantics,
    verify_estimate_snapshot,
)
from w2.models.player_impact import unsupported_player_impact
from w2.readiness.data_gate import (
    DataFreshnessPolicy,
    DataReadinessResult,
    build_data_readiness_from_legacy_payload,
    result_from_mapping,
)
from w2.strategy.analysis_gate_shadow import build_analysis_gate_v2_shadow

ANALYSIS_PICK_DISCLAIMER = DecisionPick.__dataclass_fields__["disclaimer"].default
MIN_ANALYSIS_PICK_CONFIDENCE = 0.55
# AH line-unit divergence. One quarter line is the minimum meaningful handicap step.
MIN_MARKET_ANCHOR_DIVERGENCE_AH_LINE = 0.25
ANALYSIS_MARKETS = ("ASIAN_HANDICAP", "TOTALS")


def build_decision_contract_fields(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
    environment: str,
    as_of: datetime,
    kickoff_utc: datetime,
    competition_id: str | None = None,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    data_readiness = _data_readiness_result(
        card=card,
        market=market,
        recommendation=recommendation,
        readiness=readiness,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
    )
    data_status = data_readiness.data_status
    tier = _decision_tier(
        card=card,
        market=market,
        recommendation=recommendation,
        readiness=readiness,
        data_status=data_status,
    )
    probability_source = _probability_source(card, market, recommendation)
    model_market_divergence = _model_market_divergence(card, market, recommendation)
    analysis_gates = _analysis_gates(
        card=card,
        kickoff_utc=kickoff_utc,
        as_of=as_of,
        environment=environment,
    )
    analysis_gate = _primary_analysis_gate(analysis_gates)
    analysis_gate_v2_shadows = _analysis_gate_v2_shadows(card, analysis_gates)
    analysis_gate_v2_shadow = next(
        (
            item
            for item in analysis_gate_v2_shadows
            if item.get("estimate_id") == analysis_gate.get("estimate_id")
        ),
        {},
    )
    optional_enrichment = _optional_enrichment(card)
    player_impact_estimate = unsupported_player_impact().as_dict()
    tier = _market_anchor_display_tier(
        tier=tier,
        data_status=data_status,
        probability_source=probability_source,
        model_market_divergence=model_market_divergence,
        analysis_gate=analysis_gate,
    )
    lifecycle_status = _lifecycle_status(card)
    recommendation_id = _first_text(
        _get(recommendation, "recommendation_id"),
        _get(recommendation, "id"),
        _get(card, "recommendation_id"),
        _get(market, "recommendation_id"),
    )
    forward_ev_evidence_satisfied = _truthy(_get(card, "forward_ev_evidence_satisfied")) or _truthy(
        _get(recommendation, "forward_ev_evidence_satisfied")
    )
    market_complete = _market_complete(market, recommendation)
    if tier is DecisionTier.RECOMMEND and not _recommend_prerequisites_satisfied(
        data_status=data_status,
        kickoff_utc=kickoff_utc,
        as_of=as_of,
        market_complete=market_complete,
        recommendation_id=recommendation_id,
        forward_ev_evidence_satisfied=forward_ev_evidence_satisfied,
    ):
        tier = DecisionTier.ANALYSIS_PICK if market_complete else DecisionTier.WATCH
    legacy = legacy_decision_view(card, market)
    recommendation_legacy = legacy_decision_view({}, recommendation)
    legacy_formal = legacy.legacy_formal or recommendation_legacy.legacy_formal
    pick_payload = (
        _pick_payload(
            card=card,
            market=market,
            recommendation=recommendation,
            analysis_gate=analysis_gate,
        )
        if tier in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}
        else None
    )
    non_pick_payload = (
        _non_pick_payload(
            card=card,
            market=market,
            recommendation=recommendation,
            readiness=readiness,
            data_readiness=data_readiness,
            kickoff_utc=kickoff_utc,
            as_of=as_of,
            analysis_gate=analysis_gate,
        )
        if tier in {DecisionTier.NOT_READY, DecisionTier.SKIP, DecisionTier.WATCH}
        else None
    )
    core = {
        "fixture_id": fixture_id or str(_get(card, "fixture_id") or ""),
        "competition_id": competition_id or str(_get(card, "competition_id") or ""),
        "kickoff_utc": kickoff_utc,
        "decision_tier": tier.value,
        "data_status": data_status.value,
        "lifecycle_status": lifecycle_status.value,
        "outcome_tracked": compute_outcome_tracked(tier),
        "recommendation_id": recommendation_id,
        "model_version": str(
            _get(card, "model_version")
            or _get(_as_mapping(_get(card, "pricing_shadow")), "model_version")
            or "w2.decision_contract.v2.adapter"
        ),
        "probability_source": probability_source.value,
        "model_market_divergence": model_market_divergence,
        "analysis_gate": analysis_gate,
        "analysis_gates": analysis_gates,
        "analysis_gate_v2_shadow": analysis_gate_v2_shadow,
        "analysis_gate_v2_shadows": analysis_gate_v2_shadows,
        "fair_market_estimates": [dict(item) for item in _fair_market_estimates(card)],
        "fair_market_estimate_ids": _fair_market_estimate_ids(card),
        "fair_market_estimate_snapshots": [
            dict(item) for item in _fair_market_estimate_snapshots(card)
        ],
        "optional_enrichment": optional_enrichment,
        "player_impact_estimate": player_impact_estimate,
        "provenance": {
            "source": str(_get(card, "source") or "legacy_payload"),
            "adapter": "w2.decision_contract.v2.adapter",
            "legacy_formal": legacy_formal,
        },
        "pick": pick_payload,
        "non_pick": non_pick_payload,
        "one_liner": _one_liner(tier, non_pick_payload),
    }
    lock_eligible = compute_lock_eligible(
        core,
        environment,
        DecisionPolicyConfig(
            now_utc=as_of,
            data_integrity_passed=data_status is DataStatus.READY,
            market_complete=market_complete,
            forward_ev_evidence_satisfied=forward_ev_evidence_satisfied,
        ),
    )
    summary = {
        **_serialize_core(core),
        "missing_fields": list(data_readiness.missing_fields),
        "stale_fields": list(data_readiness.stale_fields),
        "data_readiness": data_readiness.as_dict(),
        "provider_budget_status": data_readiness.provider_budget_status,
        "readiness_source": data_readiness.source,
        "environment": environment,
        "lock_eligible": lock_eligible,
        "legacy_formal": legacy_formal,
    }
    summary["card_hash"] = _validated_card_hash(
        core=core,
        environment=environment,
        lock_eligible=lock_eligible,
        kickoff_utc=kickoff_utc,
    )
    return {
        **summary,
        "reason_code": _reason_value(non_pick_payload, data_readiness),
        "action": _action_value(non_pick_payload, data_readiness),
        "next_eval_at": _next_eval_value(non_pick_payload, data_readiness),
        "decision_contract": summary,
    }


def _decision_tier(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
    data_status: DataStatus,
) -> DecisionTier:
    if data_status is DataStatus.BLOCKED:
        return DecisionTier.NOT_READY

    for payload in (card, market, recommendation):
        explicit = _get(payload, "decision_tier")
        if explicit is not None:
            tier = DecisionTier(str(explicit))
            if tier in {
                DecisionTier.ANALYSIS_PICK,
                DecisionTier.RECOMMEND,
            } and _pick_strength_insufficient(payload):
                return DecisionTier.WATCH
            return tier

    legacy = legacy_decision_view(card, market)
    recommendation_legacy = legacy_decision_view({}, recommendation)
    if legacy.legacy_formal or recommendation_legacy.legacy_formal:
        return DecisionTier.ANALYSIS_PICK

    decision = _first_upper(
        _get(market, "analysis_decision"),
        _get(market, "decision"),
        _get(card, "analysis_decision"),
        _get(card, "decision"),
        _get(recommendation, "tier"),
    )
    if decision == "NO_EDGE":
        return DecisionTier.WATCH
    if decision in {"ANALYSIS_PICK", "PICK", "FORMAL"}:
        if _pick_strength_insufficient(market) or _pick_strength_insufficient(recommendation):
            return DecisionTier.WATCH
        return DecisionTier.ANALYSIS_PICK
    if (
        legacy.decision_tier is DecisionTier.WATCH
        or recommendation_legacy.decision_tier is DecisionTier.WATCH
    ):
        return DecisionTier.WATCH
    if decision == "WATCH":
        return DecisionTier.WATCH
    if _readiness_blocked(readiness):
        return DecisionTier.NOT_READY
    return DecisionTier.SKIP


def _pick_strength_insufficient(payload: Mapping[str, Any] | None) -> bool:
    confidence = _number(_get(payload, "confidence"))
    if confidence is None:
        return False
    return confidence < MIN_ANALYSIS_PICK_CONFIDENCE


def _recommend_prerequisites_satisfied(
    *,
    data_status: DataStatus,
    kickoff_utc: datetime,
    as_of: datetime,
    market_complete: bool,
    recommendation_id: str | None,
    forward_ev_evidence_satisfied: bool,
) -> bool:
    return (
        data_status is DataStatus.READY
        and kickoff_utc.astimezone(UTC) > as_of.astimezone(UTC)
        and market_complete
        and recommendation_id is not None
        and forward_ev_evidence_satisfied
    )


def _market_anchor_display_tier(
    *,
    tier: DecisionTier,
    data_status: DataStatus,
    probability_source: ProbabilitySource,
    model_market_divergence: Mapping[str, Any],
    analysis_gate: Mapping[str, Any],
) -> DecisionTier:
    if data_status is DataStatus.BLOCKED:
        return DecisionTier.NOT_READY
    if tier in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND} and not (
        analysis_gate
        and analysis_gate.get("estimate_id")
        and analysis_gate.get("decision_source_consistent") is True
    ):
        return DecisionTier.WATCH
    if (
        str(analysis_gate.get("market")) == "ASIAN_HANDICAP"
        and analysis_gate.get("direction_allowed") is not True
    ):
        return DecisionTier.WATCH
    if not _market_anchor_display_enabled():
        return tier
    if analysis_gate:
        if str(analysis_gate.get("status")) != "ELIGIBLE":
            return DecisionTier.WATCH
        if probability_source is not ProbabilitySource.MARKET_DEVIG:
            return DecisionTier.WATCH
        return (
            DecisionTier.RECOMMEND if tier is DecisionTier.RECOMMEND else DecisionTier.ANALYSIS_PICK
        )
    if tier not in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}:
        return tier
    if _market_anchor_blocks_pick(
        probability_source=probability_source,
        model_market_divergence=model_market_divergence,
    ):
        return DecisionTier.WATCH
    return tier


def _market_anchor_display_enabled() -> bool:
    return _truthy(os.getenv("W2_MARKET_ANCHOR_DISPLAY_ENABLED"))


def _market_anchor_blocks_pick(
    *,
    probability_source: ProbabilitySource,
    model_market_divergence: Mapping[str, Any],
) -> bool:
    if probability_source is not ProbabilitySource.MARKET_DEVIG:
        return True
    status = str(_get(model_market_divergence, "status") or "").upper()
    if status not in {"READY", "SIGNIFICANT", "ACTIONABLE"}:
        return True
    if _truthy(_get(model_market_divergence, "direction_allowed")) is not True:
        return True
    magnitude = _number(_get(model_market_divergence, "magnitude"))
    threshold = _number(os.getenv("W2_MARKET_ANCHOR_MIN_DIVERGENCE"))
    if threshold is None:
        threshold = MIN_MARKET_ANCHOR_DIVERGENCE_AH_LINE
    return magnitude is None or abs(magnitude) < threshold


def _data_status(
    readiness: Mapping[str, Any] | None,
    card: Mapping[str, Any],
) -> DataStatus:
    blockers = _blockers(readiness, card=card)
    if any("PROVIDER_BUDGET_EXHAUSTED" in blocker or "STALE" in blocker for blocker in blockers):
        return DataStatus.STALE
    status = _first_upper(_get(readiness, "status"), _get(card, "data_status"))
    if status == "READY":
        return DataStatus.READY
    if status == "BLOCKED":
        return DataStatus.BLOCKED
    if status == "STALE":
        return DataStatus.STALE
    return DataStatus.PARTIAL


def _data_readiness_result(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
    as_of: datetime,
    kickoff_utc: datetime,
) -> DataReadinessResult:
    for payload in (
        readiness,
        _as_mapping(_get(readiness, "data_readiness")),
        _as_mapping(_get(card, "data_readiness")),
    ):
        if payload:
            parsed = result_from_mapping(payload)
            if parsed is not None:
                return parsed
    provider_status = _as_mapping(_get(readiness, "provider_status")) or _as_mapping(
        _get(card, "provider_status"),
    )
    return build_data_readiness_from_legacy_payload(
        card=card,
        market=market,
        recommendation=recommendation,
        analysis_readiness=readiness,
        provider_status=provider_status,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        policy=DataFreshnessPolicy(),
    )


def _lifecycle_status(card: Mapping[str, Any]) -> LifecycleStatus:
    raw = _first_upper(_get(card, "lifecycle_status"), _get(card, "lifecycle_state"))
    if raw in {item.value for item in LifecycleStatus}:
        return LifecycleStatus(raw)
    return LifecycleStatus.DRAFT


def _pick_payload(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    analysis_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    pricing = _as_mapping(_get(card, "pricing_shadow"))
    gate_quote = _analysis_gate_quote(card, analysis_gate)
    pick_market = _first_text(
        _get(analysis_gate, "market"),
        _get(recommendation, "market"),
        _get(market, "market"),
    )
    fair_key, market_key, edge_key = _pricing_keys_for_market(pick_market)
    return {
        "market": pick_market,
        "selection": _first_text(
            _get(analysis_gate, "selection"),
            _get(recommendation, "selection"),
            _get(market, "tendency"),
            _get(market, "lean"),
        ),
        "estimate_id": _optional_text(_get(analysis_gate, "estimate_id")),
        "line": _first_text(
            gate_quote.get("line"),
            _get(recommendation, "line"),
            _get(market, "line"),
        ),
        "odds": _first_text(
            gate_quote.get("odds"),
            _get(recommendation, "odds"),
            _get(market, "odds"),
        ),
        "fair_line": _first_text(
            _get(analysis_gate, "fair_line"),
            _get(pricing, fair_key),
            _get(market, "fair_line"),
        ),
        "market_line": _first_text(
            _get(analysis_gate, "market_line"),
            _get(pricing, market_key),
            _get(market, "market_line"),
        ),
        "value_edge": _number(
            _get(recommendation, "risk_adjusted_ev")
            or _get(recommendation, "expected_value")
            or _get(pricing, edge_key)
            or _get(market, "risk_adjusted_ev")
        ),
        "key_factors": _string_list(_get(recommendation, "reasons") or _get(market, "reasons")),
        "risks": _string_list(_get(recommendation, "risks") or _get(market, "risks")),
        "invalidation": _first_text(
            _get(recommendation, "invalidation"),
            _get(market, "invalidation"),
        ),
        "disclaimer": ANALYSIS_PICK_DISCLAIMER,
    }


def _analysis_gate_quote(
    card: Mapping[str, Any],
    analysis_gate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    market = _first_text(_get(analysis_gate, "market"))
    selection = _first_text(_get(analysis_gate, "selection"))
    odds = _as_mapping(card.get("current_odds"))
    if market == "ASIAN_HANDICAP":
        item = _as_mapping(odds.get("ah"))
        if selection == "HOME_AH":
            return {"line": item.get("home_line"), "odds": item.get("home_price")}
        if selection == "AWAY_AH":
            return {"line": item.get("away_line"), "odds": item.get("away_price")}
    if market == "TOTALS":
        item = _as_mapping(odds.get("ou"))
        if selection == "OVER":
            return {"line": item.get("line"), "odds": item.get("over_price")}
        if selection == "UNDER":
            return {"line": item.get("line"), "odds": item.get("under_price")}
    return {}


def _pricing_keys_for_market(market: str | None) -> tuple[str, str, str]:
    if market == "TOTALS":
        return ("fair_ou", "market_ou", "edge_ou")
    return ("fair_ah", "market_ah", "edge_ah")


def _non_pick_payload(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
    data_readiness: DataReadinessResult,
    kickoff_utc: datetime,
    as_of: datetime,
    analysis_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    gate_reason = _gate_reason_code(analysis_gate)
    reason_code = (
        gate_reason
        if gate_reason is not None and data_readiness.data_status is not DataStatus.BLOCKED
        else data_readiness.reason_code
        or _reason_code(
            card=card,
            market=market,
            recommendation=recommendation,
            readiness=readiness,
        )
    )
    reason_human, action = _reason_text(reason_code)
    if gate_reason is None and data_readiness.reason_code is not None:
        reason_human, action = data_readiness.reason_human, data_readiness.action
    return {
        "reason_code": reason_code.value,
        "reason_human": reason_human,
        "action": action,
        "next_eval_at": _first_text(_get(analysis_gate, "next_eval_at"))
        or _format_utc(data_readiness.next_eval_at)
        or _next_eval_at(reason_code, kickoff_utc=kickoff_utc, as_of=as_of),
    }


def _reason_code(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
) -> DecisionReasonCode:
    decision = _first_upper(
        _get(market, "analysis_decision"),
        _get(market, "decision"),
        _get(card, "analysis_decision"),
        _get(card, "decision"),
        _get(recommendation, "tier"),
    )
    if decision == "NO_EDGE":
        return DecisionReasonCode.EDGE_INSUFFICIENT
    if decision in {"ANALYSIS_PICK", "PICK", "FORMAL"} and (
        _pick_strength_insufficient(market) or _pick_strength_insufficient(recommendation)
    ):
        return DecisionReasonCode.EDGE_INSUFFICIENT
    explicit_tier = _first_upper(
        _get(card, "decision_tier"),
        _get(market, "decision_tier"),
        _get(recommendation, "decision_tier"),
    )
    wants_pick = decision in {"ANALYSIS_PICK", "PICK", "FORMAL"} or explicit_tier in {
        "ANALYSIS_PICK",
        "RECOMMEND",
    }
    if wants_pick and _market_anchor_display_enabled():
        probability_source = _probability_source(card, market, recommendation)
        model_market_divergence = _model_market_divergence(card, market, recommendation)
        if _market_anchor_blocks_pick(
            probability_source=probability_source,
            model_market_divergence=model_market_divergence,
        ):
            return DecisionReasonCode.EDGE_INSUFFICIENT
    codes = _blockers(readiness, card=card, market=market, recommendation=recommendation)
    text = " ".join(codes).upper()
    if "FIXTURE_NOT_UPCOMING" in text or "LIVE" in text or "FINISHED" in text:
        return DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED
    if "PROVIDER_BUDGET_EXHAUSTED" in text:
        return DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED
    if "MISSING_LINEUPS" in text or "LINEUPS_PENDING" in text:
        return DecisionReasonCode.LINEUPS_PENDING
    if "MARKET_NOT_READY" in text or "MARKET_UNAVAILABLE" in text or "MISSING_AH_MARKET" in text:
        return DecisionReasonCode.MARKET_UNAVAILABLE
    if "DATA_INSUFFICIENT" in text or "MISSING_XG" in text:
        return DecisionReasonCode.DATA_MISSING_XG
    if (
        "NO_EDGE" in text
        or "EDGE_INSUFFICIENT" in text
        or "AH_EV_BELOW_FORMAL_THRESHOLD" in text
        or "EV_WITHIN_UNCERTAINTY_BAND" in text
    ):
        return DecisionReasonCode.EDGE_INSUFFICIENT
    if "EDGE_BELOW_FORMAL_THRESHOLD" in text:
        return DecisionReasonCode.EDGE_INSUFFICIENT
    if "COVERAGE_NONE" in text or "UNSUPPORTED_COVERAGE" in text:
        return DecisionReasonCode.COVERAGE_NONE
    if "CONTRADICTION" in text or "DIRECTION_INCONSISTENT" in text:
        return DecisionReasonCode.CONTRADICTION_UNEXPLAINED
    return DecisionReasonCode.COVERAGE_NONE


def _reason_text(reason_code: DecisionReasonCode) -> tuple[str, str]:
    if reason_code is DecisionReasonCode.LINEUPS_PENDING:
        return "首发未出", "等官方首发"
    if reason_code is DecisionReasonCode.EDGE_INSUFFICIENT:
        return "盘口价值不足", "盯价格变动"
    if reason_code is DecisionReasonCode.MARKET_UNAVAILABLE:
        return "盘口未就绪", "等盘口开出或刷新"
    if reason_code is DecisionReasonCode.DATA_MISSING_XG:
        return "缺关键 xG / 独立信号不足", "等回填或下一刷新"
    if reason_code is DecisionReasonCode.PROVIDER_BUDGET_EXHAUSTED:
        return "provider 预算耗尽", "等下一 tick 或预算恢复"
    if reason_code is DecisionReasonCode.FIXTURE_LIVE_OR_FINISHED:
        return "比赛已开始或结束", "停止赛前评估"
    if reason_code is DecisionReasonCode.CONTRADICTION_UNEXPLAINED:
        return "信号冲突未解释", "人工复核后再评估"
    if reason_code is DecisionReasonCode.MODEL_FAIR_LINE_UNAVAILABLE:
        return "独立模型公平盘尚不可用", "等待赛前模型输入补齐后重算"
    if reason_code is DecisionReasonCode.NO_EDGE:
        return "模型与市场线差不足 0.25", "保持观察，不降低阈值凑数"
    if reason_code is DecisionReasonCode.FORWARD_EVIDENCE_ACCUMULATING:
        return "方向证据仍在积累", "达到预注册门槛后提交人工复核"
    return "覆盖不足", "等待覆盖或跳过"


def _gate_reason_code(
    analysis_gate: Mapping[str, Any] | None,
) -> DecisionReasonCode | None:
    blockers = {str(value).upper() for value in _string_list(_get(analysis_gate, "blockers"))}
    if "MARKET_UNAVAILABLE" in blockers:
        return DecisionReasonCode.MARKET_UNAVAILABLE
    if "MODEL_FAIR_LINE_UNAVAILABLE" in blockers:
        return DecisionReasonCode.MODEL_FAIR_LINE_UNAVAILABLE
    if "FORWARD_EVIDENCE_ACCUMULATING" in blockers:
        return DecisionReasonCode.FORWARD_EVIDENCE_ACCUMULATING
    if "NO_EDGE" in blockers:
        return DecisionReasonCode.NO_EDGE
    return None


def _next_eval_at(
    reason_code: DecisionReasonCode,
    *,
    kickoff_utc: datetime,
    as_of: datetime,
) -> str:
    if reason_code is DecisionReasonCode.LINEUPS_PENDING:
        target = kickoff_utc - timedelta(minutes=60)
    else:
        target = kickoff_utc - timedelta(minutes=30)
    if target <= as_of:
        target = as_of + timedelta(minutes=30)
    return target.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _reason_value(
    non_pick: Mapping[str, Any] | None,
    data_readiness: DataReadinessResult,
) -> str | None:
    value = _get(non_pick, "reason_code")
    if value is not None:
        return str(value)
    if data_readiness.reason_code is None:
        return None
    return data_readiness.reason_code.value


def _action_value(
    non_pick: Mapping[str, Any] | None,
    data_readiness: DataReadinessResult,
) -> str | None:
    value = _get(non_pick, "action")
    if value is not None:
        return str(value)
    return data_readiness.action or None


def _next_eval_value(
    non_pick: Mapping[str, Any] | None,
    data_readiness: DataReadinessResult,
) -> str | None:
    value = _get(non_pick, "next_eval_at")
    if value is not None:
        return str(value)
    return _format_utc(data_readiness.next_eval_at)


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _blockers(
    readiness: Mapping[str, Any] | None,
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None = None,
    recommendation: Mapping[str, Any] | None = None,
) -> list[str]:
    pricing = _as_mapping(_get(card, "pricing_shadow"))
    values: list[str] = []
    for source in (
        _get(readiness, "blockers"),
        _get(pricing, "formal_blockers"),
        _get(pricing, "canonical_ah_market_blocker"),
        _get(pricing, "ah_mainline_blocker"),
        _get(market, "blockers"),
        _get(market, "reason_code"),
        _get(recommendation, "reason_code"),
        _get(recommendation, "tier"),
    ):
        values.extend(_string_list(source))
    return values


def _readiness_blocked(readiness: Mapping[str, Any] | None) -> bool:
    return str(_get(readiness, "status") or "").upper() in {"BLOCKED", "UNKNOWN"}


def _market_complete(
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
) -> bool:
    for payload in (recommendation, market):
        if payload is not None and all(
            _non_empty(_get(payload, key)) for key in ("market", "line", "odds")
        ):
            return True
    return False


def _serialize_core(core: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(core)
    kickoff = payload.get("kickoff_utc")
    if isinstance(kickoff, datetime):
        payload["kickoff_utc"] = kickoff.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return payload


def _validated_card_hash(
    *,
    core: Mapping[str, Any],
    environment: str,
    lock_eligible: bool,
    kickoff_utc: datetime,
) -> str:
    decision_tier = DecisionTier(str(core["decision_tier"]))
    data_status = DataStatus(str(core["data_status"]))
    if data_status is DataStatus.BLOCKED and decision_tier in {
        DecisionTier.ANALYSIS_PICK,
        DecisionTier.RECOMMEND,
    }:
        raise ValueError("BLOCKED data_status cannot emit pick decision_tier")

    decision_card = DecisionCard(
        fixture_id=str(core["fixture_id"]),
        competition_id=str(core["competition_id"]),
        kickoff_utc=kickoff_utc,
        kickoff_beijing=kickoff_utc.astimezone(timezone(timedelta(hours=8))),
        decision_tier=decision_tier,
        data_status=data_status,
        lifecycle_status=LifecycleStatus(str(core["lifecycle_status"])),
        outcome_tracked=bool(core["outcome_tracked"]),
        lock_eligible=lock_eligible,
        recommendation_id=_optional_text(core.get("recommendation_id")),
        model_version=str(core["model_version"]),
        probability_source=ProbabilitySource(str(core["probability_source"])),
        model_market_divergence=_as_mapping(core.get("model_market_divergence")),
        analysis_gate=_as_mapping(core.get("analysis_gate")),
        analysis_gates=tuple(
            item for item in core.get("analysis_gates", []) if isinstance(item, Mapping)
        ),
        analysis_gate_v2_shadow=_as_mapping(core.get("analysis_gate_v2_shadow")),
        analysis_gate_v2_shadows=tuple(
            item
            for item in core.get("analysis_gate_v2_shadows", [])
            if isinstance(item, Mapping)
        ),
        fair_market_estimates=tuple(
            item for item in core.get("fair_market_estimates", []) if isinstance(item, Mapping)
        ),
        fair_market_estimate_ids=tuple(
            str(item) for item in core.get("fair_market_estimate_ids", []) if item
        ),
        fair_market_estimate_snapshots=tuple(
            item
            for item in core.get("fair_market_estimate_snapshots", [])
            if isinstance(item, Mapping)
        ),
        optional_enrichment=_as_mapping(core.get("optional_enrichment")),
        player_impact_estimate=_as_mapping(core.get("player_impact_estimate")),
        provenance=_as_mapping(core.get("provenance")),
        environment=environment,
        pick=_decision_pick(_as_mapping(core.get("pick"))),
        non_pick=_decision_non_pick(_as_mapping(core.get("non_pick"))),
        one_liner=str(core["one_liner"]),
    )
    return decision_card.card_hash


def _analysis_gates(
    *,
    card: Mapping[str, Any],
    kickoff_utc: datetime,
    as_of: datetime,
    environment: str,
) -> list[dict[str, Any]]:
    estimates = _fair_market_estimate_snapshots(card)
    if not estimates:
        return []
    odds = _as_mapping(_get(card, "current_odds"))
    estimate_set_consistent = _estimate_set_provenance_consistent(estimates)
    gates: list[dict[str, Any]] = []
    for market in ANALYSIS_MARKETS:
        estimate = next(
            (item for item in estimates if str(item.get("market")) == market),
            {},
        )
        market_line = _market_line(odds, market)
        market_ready = _market_odds_ready(odds, market)
        fair_line = _number(estimate.get("fair_line"))
        source_consistent = _estimate_source_consistent(
            estimate=estimate,
            fair_line=fair_line,
            market=market,
            provenance_consistent=(
                estimate_set_consistent
                and _estimate_matches_card_provenance(card=card, estimate=estimate)
            ),
        )
        model_ready = source_consistent
        delta = (
            fair_line - market_line if fair_line is not None and market_line is not None else None
        )
        threshold = MIN_MARKET_ANCHOR_DIVERGENCE_AH_LINE
        direction_allowed = _direction_allowed(card, estimate, market)
        staging_analysis_visible = environment.strip().lower() == "staging"
        blockers: list[str] = []
        advisories: list[str] = []
        if not market_ready:
            blockers.append("MARKET_UNAVAILABLE")
        if not model_ready:
            blockers.append("MODEL_FAIR_LINE_UNAVAILABLE")
        if estimate and not source_consistent:
            blockers.append("DECISION_SOURCE_INCONSISTENT")
        if market_ready and model_ready and delta is not None and abs(delta) < threshold:
            blockers.append("NO_EDGE")
        direction_blocked = not direction_allowed and (
            market == "ASIAN_HANDICAP" or not staging_analysis_visible
        )
        if market_ready and model_ready and delta is not None and abs(delta) >= threshold:
            if direction_blocked:
                blockers.append("FORWARD_EVIDENCE_ACCUMULATING")
            elif not direction_allowed:
                advisories.append("FORWARD_EVIDENCE_ACCUMULATING")
        if not market_ready or not model_ready:
            status = "BLOCKED"
        elif delta is None or abs(delta) < threshold:
            status = "NO_EDGE"
        elif direction_blocked:
            status = "ACCUMULATING"
        else:
            status = "ELIGIBLE"
        if _lineups_pending(card):
            advisories.append("LINEUPS_PENDING")
        gates.append(
            {
                "market": market,
                "estimate_id": estimate.get("estimate_id"),
                "status": status,
                "market_ready": market_ready,
                "model_ready": model_ready,
                "evidence_ready": direction_allowed,
                "direction_allowed": direction_allowed,
                "fair_line": fair_line,
                "market_line": market_line,
                "selection": _selection_for_delta(market, delta),
                "divergence_line_units": round(delta, 6) if delta is not None else None,
                "threshold_line_units": threshold,
                "strength_quarter_lines": round(abs(delta) / threshold, 6)
                if delta is not None
                else None,
                "blockers": blockers,
                "advisories": advisories,
                "next_eval_at": _analysis_next_eval(
                    kickoff_utc=kickoff_utc,
                    as_of=as_of,
                    blockers=blockers,
                ),
                "model_family": estimate.get("model_family"),
                "artifact_hash": estimate.get("artifact_hash"),
                "artifact_version": estimate.get("artifact_version"),
                "train_cutoff": estimate.get("train_cutoff"),
                "feature_as_of": estimate.get("feature_as_of"),
                "decision_source": "FAIR_MARKET_ESTIMATE",
                "decision_source_consistent": source_consistent,
            }
        )
    return gates


def _estimate_source_consistent(
    *,
    estimate: Mapping[str, Any],
    fair_line: float | None,
    market: str,
    provenance_consistent: bool = True,
) -> bool:
    home_mu = _number(estimate.get("home_mu"))
    away_mu = _number(estimate.get("away_mu"))
    return (
        str(estimate.get("market") or "") == market
        and str(estimate.get("status") or "").upper() == "READY"
        and fair_line is not None
        and home_mu is not None
        and home_mu > 0
        and away_mu is not None
        and away_mu > 0
        and bool(str(estimate.get("model_family") or "").strip())
        and provenance_consistent
        and estimate.get("schema_version") == "w2.fme_snapshot.v2"
        and bool(str(estimate.get("estimate_id") or "").strip())
        and bool(str(estimate.get("model_basis_id") or "").strip())
        and verify_estimate_snapshot(estimate)
        and verify_estimate_semantics(estimate)
    )


def _estimate_set_provenance_consistent(
    estimates: Sequence[Mapping[str, Any]],
) -> bool:
    markets = [str(item.get("market") or "") for item in estimates]
    if len(markets) != len(ANALYSIS_MARKETS) or set(markets) != set(ANALYSIS_MARKETS):
        return False
    ready = [
        item
        for item in estimates
        if str(item.get("status") or "").upper() == "READY"
    ]
    for key in (
        "model_family",
        "artifact_hash",
        "artifact_version",
        "train_cutoff",
        "feature_as_of",
        "home_mu",
        "away_mu",
    ):
        if len({_provenance_value(item.get(key)) for item in ready}) > 1:
            return False
    return True


def _estimate_matches_card_provenance(
    *,
    card: Mapping[str, Any],
    estimate: Mapping[str, Any],
) -> bool:
    pricing = _as_mapping(card.get("pricing_shadow"))
    for key in ("model_family", "artifact_hash", "artifact_version", "train_cutoff"):
        expected = _provenance_value(pricing.get(key))
        actual = _provenance_value(estimate.get(key))
        if expected and actual != expected:
            return False
    return True


def _provenance_value(value: Any) -> str:
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value or "").strip()


def _analysis_gates_from_card(card: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = card.get("analysis_gates")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    gate = card.get("analysis_gate")
    return [gate] if isinstance(gate, Mapping) else []


def _primary_analysis_gate(gates: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not gates:
        return {}
    status_rank = {"ELIGIBLE": 0, "ACCUMULATING": 1, "NO_EDGE": 2, "BLOCKED": 3}
    market_rank = {"ASIAN_HANDICAP": 0, "TOTALS": 1}
    return min(
        gates,
        key=lambda item: (
            status_rank.get(str(item.get("status")), 9),
            -float(item.get("strength_quarter_lines") or 0.0),
            market_rank.get(str(item.get("market")), 9),
        ),
    )


def _analysis_gate_v2_shadows(
    card: Mapping[str, Any],
    gates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gate in gates:
        estimate = estimate_snapshot_by_id(card, gate.get("estimate_id"))
        if estimate is None:
            continue
        quote = _analysis_gate_quote(card, gate)
        rows.append(
            build_analysis_gate_v2_shadow(
                estimate=estimate,
                gate=gate,
                odds=quote.get("odds"),
            )
        )
    return rows


def _fair_market_estimates(card: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(estimate_snapshots(card))


def _fair_market_estimate_snapshots(
    card: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    value = card.get("fair_market_estimate_snapshots")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _fair_market_estimate_ids(card: Mapping[str, Any]) -> list[str]:
    value = card.get("fair_market_estimate_ids")
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [
        str(item.get("estimate_id"))
        for item in _fair_market_estimate_snapshots(card)
        if item.get("estimate_id")
    ]


def _market_line(odds: Mapping[str, Any], market: str) -> float | None:
    if market == "ASIAN_HANDICAP":
        return _number(_get(_as_mapping(odds.get("ah")), "home_line"))
    return _number(_get(_as_mapping(odds.get("ou")), "line"))


def _market_odds_ready(odds: Mapping[str, Any], market: str) -> bool:
    if market == "ASIAN_HANDICAP":
        item = _as_mapping(odds.get("ah"))
        return all(
            _non_empty(item.get(key))
            for key in ("home_line", "away_line", "home_price", "away_price")
        )
    item = _as_mapping(odds.get("ou"))
    return all(_non_empty(item.get(key)) for key in ("line", "over_price", "under_price"))


def _direction_allowed(
    card: Mapping[str, Any],
    estimate: Mapping[str, Any],
    market: str,
) -> bool:
    by_market = card.get("direction_allowed_by_market")
    if isinstance(by_market, Mapping) and market in by_market:
        return _truthy(by_market.get(market))
    if estimate.get("direction_allowed") is not None:
        return _truthy(estimate.get("direction_allowed"))
    if market == "ASIAN_HANDICAP":
        divergence = _as_mapping(card.get("model_market_divergence")) or _as_mapping(
            card.get("market_divergence")
        )
        return _truthy(divergence.get("direction_allowed"))
    return False


def _selection_for_delta(market: str, delta: float | None) -> str | None:
    if delta is None or abs(delta) < MIN_MARKET_ANCHOR_DIVERGENCE_AH_LINE:
        return None
    if market == "ASIAN_HANDICAP":
        return "HOME_AH" if delta < 0 else "AWAY_AH"
    return "OVER" if delta > 0 else "UNDER"


def _lineups_pending(card: Mapping[str, Any]) -> bool:
    readiness = _as_mapping(card.get("data_readiness"))
    return not _truthy(readiness.get("lineups"))


def _optional_enrichment(card: Mapping[str, Any]) -> dict[str, Any]:
    readiness = _as_mapping(card.get("data_readiness"))
    available_inputs = _as_mapping(
        _get(_as_mapping(card.get("analysis_readiness")), "available_inputs")
    )
    lineups_available = _truthy(readiness.get("lineups")) or _truthy(
        available_inputs.get("lineups")
    )
    player_value_available = _truthy(readiness.get("team_value"))
    return {
        "lineups": {
            "status": "AVAILABLE_NOT_MODELED" if lineups_available else "PENDING",
            "affects_estimate": False,
            "adjustment": 0.0,
            "source": None,
            "as_of": readiness.get("lineups_captured_at"),
        },
        "player_value": {
            "status": "AVAILABLE_NOT_MODELED" if player_value_available else "NOT_SUPPORTED",
            "affects_estimate": False,
            "source": None,
            "as_of": readiness.get("team_value_captured_at"),
        },
    }


def _analysis_next_eval(
    *,
    kickoff_utc: datetime,
    as_of: datetime,
    blockers: list[str],
) -> str:
    target = kickoff_utc - timedelta(minutes=60 if "LINEUPS_PENDING" in blockers else 30)
    if target <= as_of:
        target = as_of + timedelta(minutes=30)
    return target.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _probability_source(
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
) -> ProbabilitySource:
    explicit = _first_upper(
        _get(card, "probability_source"),
        _get(market, "probability_source"),
        _get(recommendation, "probability_source"),
        _get(_as_mapping(_get(card, "provenance")), "probability_source"),
    )
    if explicit in {item.value for item in ProbabilitySource}:
        return ProbabilitySource(explicit)
    if _as_mapping(_get(card, "current_odds")) or _non_empty(_get(market, "odds")):
        return ProbabilitySource.MARKET_DEVIG
    return ProbabilitySource.MODEL_FALLBACK


def _model_market_divergence(
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    explicit = _as_mapping(_get(card, "model_market_divergence"))
    if explicit:
        return explicit
    divergence = _as_mapping(_get(card, "market_divergence"))
    pricing = _as_mapping(_get(card, "pricing_shadow"))
    pick_market = _first_text(_get(recommendation, "market"), _get(market, "market"))
    fair_key, market_key, _edge_key = _pricing_keys_for_market(pick_market)
    return {
        "source": "market_divergence" if divergence else "adapter_fallback",
        "status": str(_get(divergence, "status") or "UNKNOWN"),
        "magnitude": _number(_get(divergence, "magnitude")),
        "lock_divergence": _number(_get(divergence, "lock_divergence")),
        "model_fair_line": _optional_text(_get(pricing, fair_key)),
        "market_line": _first_text(
            _get(pricing, market_key),
            _get(recommendation, "line"),
            _get(market, "line"),
        ),
        "calibration_status": _optional_text(_get(divergence, "calibration_status")),
        "direction_allowed": _truthy(_get(divergence, "direction_allowed")),
        "model_family": _optional_text(
            _get(divergence, "model_family") or _get(pricing, "model_family")
        ),
        "model_family_fallback_reason": _optional_text(
            _get(divergence, "model_family_fallback_reason")
            or _get(pricing, "model_family_fallback_reason")
        ),
        "artifact_hash": _optional_text(
            _get(divergence, "artifact_hash") or _get(pricing, "artifact_hash")
        ),
        "artifact_version": _optional_text(
            _get(divergence, "artifact_version") or _get(pricing, "artifact_version")
        ),
    }


def _decision_pick(payload: Mapping[str, Any]) -> DecisionPick | None:
    if not payload:
        return None
    return DecisionPick(
        market=str(payload.get("market") or ""),
        selection=str(payload.get("selection") or ""),
        estimate_id=_optional_text(payload.get("estimate_id")),
        line=_optional_text(payload.get("line")),
        odds=_optional_text(payload.get("odds")),
        fair_line=_optional_text(payload.get("fair_line")),
        market_line=_optional_text(payload.get("market_line")),
        value_edge=_number(payload.get("value_edge")),
        key_factors=tuple(_string_list(payload.get("key_factors"))),
        risks=tuple(_string_list(payload.get("risks"))),
        invalidation=_optional_text(payload.get("invalidation")),
        disclaimer=str(payload.get("disclaimer") or ""),
    )


def _decision_non_pick(payload: Mapping[str, Any]) -> DecisionNonPick | None:
    if not payload:
        return None
    return DecisionNonPick(
        reason_code=DecisionReasonCode(str(payload.get("reason_code"))),
        reason_human=str(payload.get("reason_human") or ""),
        action=str(payload.get("action") or ""),
        next_eval_at=_parse_utc(payload.get("next_eval_at")),
    )


def _parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _one_liner(
    tier: DecisionTier,
    non_pick: Mapping[str, Any] | None,
) -> str:
    if tier is DecisionTier.ANALYSIS_PICK:
        return "分析参考·非稳赢；production 动作需 RECOMMEND。"
    if tier is DecisionTier.RECOMMEND:
        return "RECOMMEND requires production evidence and policy gates."
    if non_pick is not None:
        return f"{_get(non_pick, 'reason_human')}；{_get(non_pick, 'action')}。"
    return "等待下一次评估。"


def _get(mapping: Mapping[str, Any] | None, key: str) -> Any:
    if mapping is None:
        return None
    return mapping.get(key)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_upper(*values: Any) -> str | None:
    text = _first_text(*values)
    return text.upper() if text is not None else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _non_empty(value: Any) -> bool:
    return _optional_text(value) is not None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False
