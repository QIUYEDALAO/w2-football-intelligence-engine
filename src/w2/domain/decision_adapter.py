from __future__ import annotations

import math
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
    DecisionRiskCode,
    DecisionTier,
    LifecycleStatus,
    ProbabilitySource,
)
from w2.domain.recommendation_decision_v4 import (
    MODEL_MARKET_DIVERGENCE,
    MODEL_MARKET_DIVERGENCE_EXPLANATION,
)
from w2.lineups.intelligence import lineup_requirement as competition_lineup_requirement
from w2.readiness.data_gate import (
    DataFreshnessPolicy,
    DataReadinessResult,
    build_data_readiness_from_legacy_payload,
    result_from_mapping,
)
from w2.tracking.advisory_blind_spot_policy import (
    validate_advisory_blind_spot_policy,
)

ANALYSIS_PICK_DISCLAIMER = DecisionPick.__dataclass_fields__["disclaimer"].default
MIN_ANALYSIS_PICK_CONFIDENCE = 0.55
MIN_MARKET_ANCHOR_DIVERGENCE = 0.05
_SELECTION_ALIASES = {
    "ASIAN_HANDICAP": {
        "HOME": "HOME",
        "HOME_AH": "HOME",
        "AWAY": "AWAY",
        "AWAY_AH": "AWAY",
    },
    "TOTALS": {
        "OVER": "OVER",
        "OVER_TOTALS": "OVER",
        "UNDER": "UNDER",
        "UNDER_TOTALS": "UNDER",
    },
}


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
    evaluated_candidate = _selected_market_candidate(card, market)
    tier = _decision_tier(
        card=card,
        market=market,
        recommendation=recommendation,
        data_status=data_status,
    )
    probability_source = _probability_source(card, market, recommendation)
    model_market_divergence = _model_market_divergence(evaluated_candidate)
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
    if tier in {
        DecisionTier.ANALYSIS_PICK,
        DecisionTier.RECOMMEND,
    } and not _canonical_pick_evidence_ready(
        evaluated_candidate,
        market=market,
        recommendation=recommendation,
    ):
        tier = DecisionTier.NOT_READY
    lineup_requirement, risk_reason_codes = _lineup_risks(
        card,
        competition_id=competition_id,
    )
    forced_reason: DecisionReasonCode | None = None
    if (
        tier in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}
        and lineup_requirement == "ADVISORY"
        and _get(_as_mapping(evaluated_candidate), "divergence_origin")
        and _first_upper(
            _get(
                _as_mapping(_get(_as_mapping(evaluated_candidate), "divergence_origin")),
                "effective_risk_class",
            )
        )
        in {"MOVED", "MOVED_CONSERVATIVE"}
    ):
        tier = DecisionTier.WATCH
        forced_reason = DecisionReasonCode.MARKET_MOVED_AGAINST_BLIND_SPOT
    if (
        tier in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}
        and lineup_requirement == "ADVISORY"
    ):
        policy = _as_mapping(_get(card, "advisory_blind_spot_policy"))
        if not validate_advisory_blind_spot_policy(policy, as_of=as_of):
            tier = DecisionTier.WATCH
            forced_reason = DecisionReasonCode.ADVISORY_DELTA_POLICY_NOT_READY
        else:
            policy_payload = _as_mapping(policy.get("payload"))
            expected_value = _number(
                _get(
                    _as_mapping(
                        _get(_as_mapping(evaluated_candidate), "analysis_selected_candidate")
                    ),
                    "expected_value",
                )
            )
            threshold = _number(policy_payload.get("effective_threshold"))
            if policy_payload.get("watch_only") is True or (
                expected_value is not None and threshold is not None and expected_value < threshold
            ):
                tier = DecisionTier.WATCH
                forced_reason = DecisionReasonCode.EDGE_INSUFFICIENT
    if tier not in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}:
        recommendation_id = None
    pick_payload = (
        _pick_payload(
            evaluated_candidate=evaluated_candidate,
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
            reason_override=forced_reason,
        )
        if tier
        in {
            DecisionTier.NOT_READY,
            DecisionTier.SKIP,
            DecisionTier.WATCH,
            DecisionTier.MODEL_MARKET_DIVERGENCE,
        }
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
        "model_version": str(_get(card, "model_version") or "w2.decision_contract.v2.adapter"),
        "probability_source": probability_source.value,
        "model_market_divergence": model_market_divergence,
        "provenance": {
            "source": str(_get(card, "source") or "canonical_payload"),
            "adapter": "w2.decision_contract.v2.adapter",
        },
        "pick": pick_payload,
        "non_pick": non_pick_payload,
        "lineup_requirement": lineup_requirement,
        "risk_reason_codes": risk_reason_codes,
        "one_liner": _one_liner(tier, non_pick_payload),
    }
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
        "integrity_status": "PASS",
        "quote_provenance_status": quote_provenance_status,
        "formal_ah_readiness": {
            "schema_version": "w2.formal_ah_readiness.v1",
            "global_gates": {},
            "fixture_gates": [],
            "approval_status": {"passed": False, "reason": "FORMAL_HUMAN_APPROVAL_MISSING"},
            "approved_hashes": {},
            "blockers": ["FORMAL_HUMAN_APPROVAL_MISSING"],
            "admission_ready": False,
            "formal_eligible": False,
            "lock_eligible": False,
        },
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
    summary.update(
        {
            "reason_code": _reason_value(non_pick_payload, data_readiness),
            "action": _action_value(non_pick_payload, data_readiness),
            "next_eval_at": _next_eval_value(non_pick_payload, data_readiness),
        }
    )
    return {
        **summary,
        "decision_contract": dict(summary),
    }


def _decision_tier(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
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

    return DecisionTier.NOT_READY


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
        statuses[market] = (
            "COMPLETE"
            if freshness == "COMPLETE"
            else ("STALE" if freshness == "STALE" else "INCOMPLETE")
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
    if not _as_mapping(_get(card, "data_readiness")):
        reason_human, action = _reason_text(DecisionReasonCode.COVERAGE_NONE)
        return DataReadinessResult(
            data_status=DataStatus.BLOCKED,
            missing_fields=("data_readiness",),
            stale_fields=(),
            reason_code=DecisionReasonCode.COVERAGE_NONE,
            reason_human=reason_human,
            action=action,
            next_eval_at=None,
            provider_budget_status=None,
            field_statuses=(),
            blocking_fields=("data_readiness",),
        )
    return build_data_readiness_from_legacy_payload(
        card=card,
        market=market,
        recommendation=recommendation,
        analysis_readiness=readiness,
        provider_status=_as_mapping(_get(card, "provider_status")),
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
    evaluated_candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    evaluated = _as_mapping(evaluated_candidate)
    executable_quote = _as_mapping(_as_mapping(evaluated.get("quotes")).get("executable"))
    analysis_evidence = _as_mapping(evaluated.get("analysis_evidence"))
    model_probability = _as_mapping(analysis_evidence.get("model_probability"))
    comparison = _as_mapping(analysis_evidence.get("comparison"))
    pick_market = _first_upper(evaluated.get("market"))
    return {
        "market": pick_market,
        "selection": _canonical_selection(pick_market, evaluated.get("selection")),
        "line": _first_text(executable_quote.get("line")),
        "odds": _first_text(executable_quote.get("decimal_odds")),
        "fair_line": evaluated.get("fair_line"),
        "market_line": evaluated.get("market_line"),
        "value_edge": _number(model_probability.get("expected_value")),
        "key_factors": [str(comparison.get("reason_code") or "MODEL_MARKET_EDGE_READY")],
        "risks": [
            "ANALYSIS_ONLY_FORMAL_DISABLED",
            *[
                str(warning)
                for warning in _string_list(evaluated.get("warnings"))
                if warning == "EV_PLAUSIBILITY_REVIEW"
            ],
        ],
        "invalidation": "EXACT_QUOTE_IDENTITY_OR_MODEL_INPUT_CHANGED",
        "quote_identity": dict(_as_mapping(evaluated.get("quote_identity"))),
        "model_probability": dict(model_probability),
        "market_probability": analysis_evidence.get("market_probability"),
        "probability_delta": comparison.get("probability_delta"),
        "expected_value": model_probability.get("expected_value"),
        "uncertainty": model_probability.get("ev_se"),
        "disclaimer": ANALYSIS_PICK_DISCLAIMER,
    }


def _canonical_pick_evidence_ready(
    candidate: Mapping[str, Any] | None,
    *,
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
) -> bool:
    evaluated = _as_mapping(candidate)
    evidence = _as_mapping(evaluated.get("analysis_evidence"))
    model_probability = _as_mapping(evidence.get("model_probability"))
    comparison = _as_mapping(evidence.get("comparison"))
    quote = _as_mapping(_as_mapping(evaluated.get("quotes")).get("executable"))
    identity = _as_mapping(evaluated.get("quote_identity"))
    evidence_identity = _as_mapping(evidence.get("quote_identity"))
    candidate_market = _first_upper(evaluated.get("market"))
    evidence_market = _first_upper(evidence.get("market"))
    market_market = _first_upper(_get(market, "market"))
    recommendation_market = _first_upper(_get(recommendation, "market"))
    candidate_selection = _canonical_selection(candidate_market, evaluated.get("selection"))
    evidence_selection = _canonical_selection(evidence_market, evidence.get("selection"))
    market_values = {
        value
        for value in (
            candidate_market,
            evidence_market,
            market_market,
            recommendation_market,
        )
        if value is not None
    }
    selection_values: list[str] = []
    for selection_market, raw_selection in (
        (candidate_market, evaluated.get("selection")),
        (evidence_market, evidence.get("selection")),
        (market_market or candidate_market, _get(market, "selection")),
        (market_market or candidate_market, _get(market, "tendency")),
        (recommendation_market or candidate_market, _get(recommendation, "selection")),
        (recommendation_market or candidate_market, _get(recommendation, "tendency")),
    ):
        if raw_selection is None:
            continue
        normalized = _canonical_selection(selection_market, raw_selection)
        if normalized is None:
            return False
        selection_values.append(normalized)
    identity_hash = _first_text(identity.get("quote_identity_hash"))
    decimal_odds = _finite_number(quote.get("decimal_odds"))
    return (
        evaluated.get("schema_version") == "w2.market_candidate.v1"
        and candidate_market in _SELECTION_ALIASES
        and candidate_selection is not None
        and market_values == {candidate_market}
        and evidence_selection == candidate_selection
        and set(selection_values) == {candidate_selection}
        and evaluated.get("quote_status") == "COMPLETE"
        and evaluated.get("quote_usage") == "EXECUTABLE"
        and identity.get("identity_status") == "COMPLETE"
        and identity.get("freshness_status") == "COMPLETE"
        and _first_upper(identity.get("market")) == candidate_market
        and identity_hash is not None
        and evidence_identity.get("identity_status") == "COMPLETE"
        and evidence_identity.get("freshness_status") == "COMPLETE"
        and _first_upper(evidence_identity.get("market")) == candidate_market
        and _first_text(evidence_identity.get("quote_identity_hash")) == identity_hash
        and _valid_market_line(candidate_market, evaluated.get("line"))
        and _same_number(evaluated.get("line"), quote.get("line"))
        and decimal_odds is not None
        and decimal_odds > 1
        and evidence.get("evidence_contract_version") == "w2.analysis-market-evidence.v2"
        and evidence.get("status") == "COMPLETE"
        and evidence.get("quote_usage") == "EXECUTABLE"
        and evidence_market == candidate_market
        and _same_number(evidence.get("line"), evaluated.get("line"))
        and model_probability.get("status") == "READY"
        and _finite_number(model_probability.get("expected_value")) is not None
        and _finite_number(model_probability.get("ev_se")) is not None
        and comparison.get("status") == "READY"
        and _finite_number(comparison.get("probability_delta")) is not None
        and comparison.get("analysis_direction_allowed") is True
    )


def _non_pick_payload(
    *,
    card: Mapping[str, Any],
    market: Mapping[str, Any] | None,
    recommendation: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
    data_readiness: DataReadinessResult,
    kickoff_utc: datetime,
    as_of: datetime,
    reason_override: DecisionReasonCode | None = None,
) -> dict[str, Any]:
    reason_code = (
        reason_override
        or data_readiness.reason_code
        or _reason_code(
            card=card,
            market=market,
            recommendation=recommendation,
            readiness=readiness,
        )
    )
    reason_human, action = (
        (data_readiness.reason_human, data_readiness.action)
        if data_readiness.reason_code is not None and reason_override is None
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
        model_market_divergence = _model_market_divergence(_selected_market_candidate(card, market))
        if _market_anchor_blocks_pick(
            probability_source=probability_source,
            model_market_divergence=model_market_divergence,
        ):
            return DecisionReasonCode.EDGE_INSUFFICIENT
    codes = _blockers(readiness, market=market, recommendation=recommendation)
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
    if reason_code is DecisionReasonCode.MARKET_MOVED_AGAINST_BLIND_SPOT:
        return "盘口移动暴露首发盲区", "等待可观测首发或稳定同线价格"
    if reason_code is DecisionReasonCode.ADVISORY_DELTA_POLICY_NOT_READY:
        return "ADVISORY 风险溢价尚未就绪", "等待写侧策略投影"
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


def _lineup_risks(
    card: Mapping[str, Any],
    *,
    competition_id: str | None,
) -> tuple[str, list[str]]:
    provenance = _as_mapping(_get(card, "lineup_provenance"))
    requirement = _first_upper(provenance.get("requirement"))
    if requirement not in {"STRICT", "ADVISORY"}:
        requirement = competition_lineup_requirement(
            competition_id or str(_get(card, "competition_id") or "")
        )
    risks: set[str] = set()
    if requirement == "ADVISORY":
        risks.add(DecisionRiskCode.LINEUP_UNOBSERVABLE.value)
    rotation_priors = provenance.get("rotation_priors")
    if isinstance(rotation_priors, list) and any(
        isinstance(item, Mapping) and item.get("classification") == "HIGH_ROTATION"
        for item in rotation_priors
    ):
        risks.add(DecisionRiskCode.HIGH_ROTATION_PRIOR.value)
    return requirement, sorted(risks)


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
    market: Mapping[str, Any] | None = None,
    recommendation: Mapping[str, Any] | None = None,
) -> list[str]:
    values: list[str] = []
    for source in (
        _get(readiness, "blockers"),
        _get(market, "blockers"),
        _get(market, "reason_code"),
        _get(recommendation, "reason_code"),
    ):
        values.extend(_string_list(source))
    return values


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
        lineup_requirement=str(core["lineup_requirement"]),
        risk_reason_codes=tuple(
            DecisionRiskCode(str(value)) for value in core["risk_reason_codes"]
        ),
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
    candidate: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    evidence = _as_mapping(candidate.get("analysis_evidence")) if candidate else {}
    if evidence.get("evidence_contract_version") == "w2.analysis-market-evidence.v2":
        comparison = _as_mapping(evidence.get("comparison"))
        return {
            "descriptor": MODEL_MARKET_DIVERGENCE,
            "explanation": MODEL_MARKET_DIVERGENCE_EXPLANATION,
            "source": "analysis_evidence",
            "status": str(comparison.get("status") or evidence.get("status") or "UNKNOWN"),
            "magnitude": _finite_number(comparison.get("probability_delta")),
            "lock_divergence": None,
            "model_fair_line": None,
            "market_line": _optional_text(evidence.get("line")),
            "calibration_status": _optional_text(
                _get(_as_mapping(evidence.get("model_probability")), "calibration_status")
            ),
            "direction_allowed": _truthy(comparison.get("analysis_direction_allowed")),
            "compatibility_only": False,
        }
    return {
        "descriptor": MODEL_MARKET_DIVERGENCE,
        "explanation": MODEL_MARKET_DIVERGENCE_EXPLANATION,
        "source": "analysis_evidence",
        "compatibility_only": False,
        "status": "MISSING",
        "magnitude": None,
        "lock_divergence": None,
        "model_fair_line": None,
        "market_line": None,
        "calibration_status": None,
        "direction_allowed": False,
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
    if tier is DecisionTier.MODEL_MARKET_DIVERGENCE:
        return MODEL_MARKET_DIVERGENCE_EXPLANATION
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


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    number = _number(value)
    return number if number is not None and math.isfinite(number) else None


def _same_number(left: Any, right: Any) -> bool:
    left_number = _finite_number(left)
    right_number = _finite_number(right)
    return left_number is not None and left_number == right_number


def _canonical_selection(market: str | None, value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _SELECTION_ALIASES.get(market or "", {}).get(value)


def _valid_market_line(market: str | None, value: Any) -> bool:
    line = _finite_number(value)
    return bool(
        line is not None
        and abs(line * 4 - round(line * 4)) < 0.001
        and (market != "TOTALS" or line > 0)
    )


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
