from __future__ import annotations

import os
from collections.abc import Mapping
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
from w2.readiness.data_gate import (
    DataFreshnessPolicy,
    DataReadinessResult,
    build_data_readiness_from_legacy_payload,
    result_from_mapping,
)

ANALYSIS_PICK_DISCLAIMER = DecisionPick.__dataclass_fields__["disclaimer"].default
MIN_ANALYSIS_PICK_CONFIDENCE = 0.55
MIN_MARKET_ANCHOR_DIVERGENCE = 0.05


def _selected_market_candidate(
    card: Mapping[str, Any], market: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Return the market-scoped evidence even when no pick was selected."""
    name = str(_get(market, "market") or _get(card, "primary_market") or "")
    candidates = _as_mapping(_get(card, "market_candidates"))
    key = {"ASIAN_HANDICAP": "ah", "TOTALS": "ou"}.get(name, name)
    candidate = _as_mapping(candidates.get(key))
    return dict(candidate) if candidate else None


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
    tier = _market_anchor_display_tier(
        tier=tier,
        data_status=data_status,
        probability_source=probability_source,
        model_market_divergence=model_market_divergence,
    )
    quote_provenance_status = _quote_provenance_status(
        card=card,
        market=market,
        recommendation=recommendation,
    )
    available_quote_provenance = _available_quote_provenance(card)
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
        tier = DecisionTier.WATCH
    tier = _enforce_non_ready_no_pick(
        tier=tier,
        data_status=data_status,
        quote_provenance_status=quote_provenance_status,
    )
    if tier not in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}:
        recommendation_id = None
    legacy = legacy_decision_view(card, market)
    legacy_formal = legacy.legacy_formal or _truthy(_get(recommendation, "formal_recommendation"))
    pick_payload = (
        _pick_payload(card=card, market=market, recommendation=recommendation)
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
        "provenance": {
            "source": str(_get(card, "source") or "legacy_payload"),
            "adapter": "w2.decision_contract.v2.adapter",
            "legacy_formal": legacy_formal,
        },
        "pick": pick_payload,
        "non_pick": non_pick_payload,
        "one_liner": _one_liner(tier, non_pick_payload),
    }
    evaluated_candidate = _selected_market_candidate(card, market)
    lock_eligible = compute_lock_eligible(
        core,
        environment,
        DecisionPolicyConfig(
            now_utc=as_of,
            data_integrity_passed=data_status is DataStatus.READY,
            market_complete=market_complete and quote_provenance_status == "COMPLETE",
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
        "integrity_status": "PASS",
        "quote_provenance_status": quote_provenance_status,
        # A no-pick has no selected quote by definition.  Preserve that status
        # while separately exposing whether auditable same-line quote evidence
        # exists for the available AH/OU markets.
        "available_quote_provenance": available_quote_provenance,
        "as_of": as_of.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "selected_market_candidate": evaluated_candidate,
        "analysis_evidence": _as_mapping(evaluated_candidate.get("analysis_evidence"))
        if evaluated_candidate
        else {},
        "analysis_evidence_hash": evaluated_candidate.get("evidence_hash")
        if evaluated_candidate
        else None,
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
    if legacy.legacy_formal or _truthy(_get(recommendation, "formal_recommendation")):
        return DecisionTier.ANALYSIS_PICK

    decision = _first_upper(
        _get(market, "analysis_decision"),
        _get(market, "decision"),
        _get(card, "analysis_decision"),
        _get(card, "decision"),
        _get(recommendation, "tier"),
    )
    if decision == "NO_EDGE":
        return DecisionTier.SKIP
    if decision in {"ANALYSIS_PICK", "PICK", "FORMAL"}:
        if _pick_strength_insufficient(market) or _pick_strength_insufficient(recommendation):
            return DecisionTier.WATCH
        return DecisionTier.ANALYSIS_PICK
    if _truthy(_get(card, "candidate")) or _truthy(_get(market, "candidate")):
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


def _enforce_non_ready_no_pick(
    *,
    tier: DecisionTier,
    data_status: DataStatus,
    quote_provenance_status: str,
) -> DecisionTier:
    if data_status is DataStatus.BLOCKED or quote_provenance_status == "INCOMPLETE":
        return DecisionTier.NOT_READY
    if data_status in {DataStatus.STALE, DataStatus.PARTIAL} or quote_provenance_status == "STALE":
        return DecisionTier.WATCH
    if tier in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}:
        if quote_provenance_status != "COMPLETE":
            return DecisionTier.NOT_READY
    return tier


def _quote_provenance_status(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
) -> str:
    audit = _as_mapping(_get(card, "quote_identity_audit"))
    market_name = _first_upper(_get(recommendation, "market"), _get(market, "market"))
    audit_key = {
        "AH": "ah",
        "ASIAN_HANDICAP": "ah",
        "OU": "ou",
        "TOTALS": "ou",
    }.get(market_name or "")
    if audit_key is None:
        return "MISSING"
    identity = _as_mapping(_get(audit, audit_key))
    if not identity:
        return "MISSING"
    if _first_upper(_get(identity, "identity_status")) != "COMPLETE":
        return "INCOMPLETE"
    freshness = _first_upper(_get(identity, "freshness_status"))
    if freshness == "STALE":
        return "STALE"
    if freshness != "COMPLETE":
        return "INCOMPLETE"
    return "COMPLETE"


def _available_quote_provenance(card: Mapping[str, Any]) -> dict[str, str]:
    audit = _as_mapping(_get(card, "quote_identity_audit"))
    statuses: dict[str, str] = {}
    for market, key in (("AH", "ah"), ("OU", "ou")):
        identity = _as_mapping(_get(audit, key))
        if not identity:
            statuses[market] = "MISSING"
            continue
        if _first_upper(_get(identity, "identity_status")) != "COMPLETE":
            statuses[market] = "INCOMPLETE"
            continue
        freshness = _first_upper(_get(identity, "freshness_status"))
        statuses[market] = "COMPLETE" if freshness == "COMPLETE" else (
            "STALE" if freshness == "STALE" else "INCOMPLETE"
        )
    return statuses


def _market_anchor_display_tier(
    *,
    tier: DecisionTier,
    data_status: DataStatus,
    probability_source: ProbabilitySource,
    model_market_divergence: Mapping[str, Any],
) -> DecisionTier:
    if tier not in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}:
        return tier
    if not _market_anchor_display_enabled():
        return tier
    if str(model_market_divergence.get("compatibility_only") or "").lower() != "true":
        return tier
    if data_status is DataStatus.BLOCKED:
        return DecisionTier.NOT_READY
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
        threshold = MIN_MARKET_ANCHOR_DIVERGENCE
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
) -> dict[str, Any]:
    pricing = _as_mapping(_get(card, "pricing_shadow"))
    pick_market = _first_text(_get(recommendation, "market"), _get(market, "market"))
    fair_key, market_key, edge_key = _pricing_keys_for_market(pick_market)
    return {
        "market": pick_market,
        "selection": _first_text(
            _get(recommendation, "selection"),
            _get(market, "tendency"),
            _get(market, "lean"),
        ),
        "line": _first_text(_get(recommendation, "line"), _get(market, "line")),
        "odds": _first_text(_get(recommendation, "odds"), _get(market, "odds")),
        "fair_line": _first_text(_get(pricing, fair_key), _get(market, "fair_line")),
        "market_line": _first_text(_get(pricing, market_key), _get(market, "market_line")),
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
) -> dict[str, Any]:
    reason_code = data_readiness.reason_code or _reason_code(
        card=card,
        market=market,
        recommendation=recommendation,
        readiness=readiness,
    )
    reason_human, action = (
        (data_readiness.reason_human, data_readiness.action)
        if data_readiness.reason_code is not None
        else _reason_text(reason_code)
    )
    return {
        "reason_code": reason_code.value,
        "reason_human": reason_human,
        "action": action,
        "next_eval_at": _format_utc(
            data_readiness.next_eval_at,
        )
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
        compatibility_only = (
            str(model_market_divergence.get("compatibility_only") or "").lower() == "true"
        )
        if compatibility_only and _market_anchor_blocks_pick(
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
    return "覆盖不足", "等待覆盖或跳过"


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
        provenance=_as_mapping(core.get("provenance")),
        environment=environment,
        pick=_decision_pick(_as_mapping(core.get("pick"))),
        non_pick=_decision_non_pick(_as_mapping(core.get("non_pick"))),
        one_liner=str(core["one_liner"]),
    )
    return decision_card.card_hash


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
        return {
            **explicit,
            "compatibility_only": explicit.get("compatibility_only", True),
        }
    candidate = _selected_market_candidate(card, market)
    evidence = _as_mapping(candidate.get("analysis_evidence")) if candidate else {}
    if str(evidence.get("evidence_contract_version") or "").endswith(".v2"):
        comparison = _as_mapping(evidence.get("comparison"))
        return {
            "source": "analysis_evidence",
            "status": str(comparison.get("status") or evidence.get("status") or "UNKNOWN"),
            "magnitude": _number(comparison.get("probability_delta")),
            "lock_divergence": None,
            "model_fair_line": _optional_text(candidate.get("fair_line")) if candidate else None,
            "market_line": _optional_text(candidate.get("market_line")) if candidate else None,
            "calibration_status": _optional_text(
                _get(_as_mapping(evidence.get("model_probability")), "calibration_status")
            ),
            "direction_allowed": _truthy(comparison.get("analysis_direction_allowed")),
            "compatibility_only": False,
        }
    divergence = _as_mapping(_get(card, "market_divergence"))
    pricing = _as_mapping(_get(card, "pricing_shadow"))
    pick_market = _first_text(_get(recommendation, "market"), _get(market, "market"))
    fair_key, market_key, _edge_key = _pricing_keys_for_market(pick_market)
    return {
        "source": "market_divergence" if divergence else "adapter_fallback",
        "compatibility_only": True,
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
    }


def _decision_pick(payload: Mapping[str, Any]) -> DecisionPick | None:
    if not payload:
        return None
    return DecisionPick(
        market=str(payload.get("market") or ""),
        selection=str(payload.get("selection") or ""),
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
