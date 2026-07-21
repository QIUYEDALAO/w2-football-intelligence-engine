from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from w2.domain.recommendation_capabilities import RecommendationCapabilityManifest


class RecommendationOutcomeV3(StrEnum):
    NOT_READY = "NOT_READY"
    NO_EDGE = "NO_EDGE"
    ANALYSIS_PICK = "ANALYSIS_PICK"
    FORMAL_RECOMMEND = "FORMAL_RECOMMEND"
    SYSTEM_DEGRADED = "SYSTEM_DEGRADED"


PICK_OUTCOMES = frozenset(
    {RecommendationOutcomeV3.ANALYSIS_PICK, RecommendationOutcomeV3.FORMAL_RECOMMEND}
)


@dataclass(frozen=True, kw_only=True)
class RecommendationDecisionV3:
    fixture_id: str
    competition_id: str
    as_of: str
    outcome: RecommendationOutcomeV3
    reason_code: str
    reason_message: str
    next_action: str
    selected_candidate: dict[str, Any] | None
    evaluated_candidate: dict[str, Any] | None
    statuses: dict[str, str]
    warnings: tuple[str, ...]
    audit_refs: dict[str, str]
    decision_hash: str

    def __post_init__(self) -> None:
        if (self.outcome in PICK_OUTCOMES) != (self.selected_candidate is not None):
            raise ValueError("V3 pick outcomes must carry exactly one selected candidate")
        if self.outcome is RecommendationOutcomeV3.FORMAL_RECOMMEND:
            candidate = self.selected_candidate or {}
            if candidate.get("market") != "ASIAN_HANDICAP":
                raise ValueError("FORMAL_RECOMMEND only supports ASIAN_HANDICAP")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "w2.recommendation_decision.v3",
            "fixture_id": self.fixture_id,
            "competition_id": self.competition_id,
            "as_of": self.as_of,
            "outcome": self.outcome.value,
            "reason": {
                "code": self.reason_code,
                "message": self.reason_message,
            },
            "next_action": self.next_action,
            "selected_candidate": self.selected_candidate,
            "evaluated_candidate": self.evaluated_candidate,
            "statuses": self.statuses,
            "warnings": list(self.warnings),
            "audit_refs": self.audit_refs,
            "decision_hash": self.decision_hash,
        }


def project_decision_v3(
    contract_v2: Mapping[str, Any], *, manifest: RecommendationCapabilityManifest
) -> RecommendationDecisionV3:
    evaluated = _evaluated_candidate(contract_v2)
    candidate = _candidate(contract_v2)
    outcome, reason_code, reason_message = _outcome(contract_v2, candidate, evaluated, manifest)
    if outcome not in PICK_OUTCOMES:
        candidate = None
    statuses = {
        "integrity": _text(contract_v2.get("integrity_status"), "PASS"),
        "data": _text(contract_v2.get("data_status"), "PARTIAL"),
        "quote": _text(contract_v2.get("quote_provenance_status"), "UNKNOWN"),
        "model": _model_status(candidate, evaluated),
        "capability": _capability_status(candidate, manifest),
    }
    core = {
        "fixture_id": _text(contract_v2.get("fixture_id")),
        "competition_id": _text(contract_v2.get("competition_id")),
        "as_of": _text(contract_v2.get("as_of")),
        "outcome": outcome.value,
        "selected_candidate": candidate,
        "evaluated_candidate": evaluated,
        "reason_code": reason_code,
        "model_version": _text(_mapping(evaluated).get("model_version")),
        "calibration_version": _text(_mapping(evaluated).get("calibration_version")),
        "quote_identity": _candidate_quote_identity_for_hash(candidate),
    }
    return RecommendationDecisionV3(
        fixture_id=_text(core["fixture_id"]),
        competition_id=_text(core["competition_id"]),
        as_of=_text(contract_v2.get("as_of")),
        outcome=outcome,
        reason_code=reason_code,
        reason_message=reason_message,
        next_action="MONITOR" if outcome is RecommendationOutcomeV3.ANALYSIS_PICK else "WAIT",
        selected_candidate=candidate,
        evaluated_candidate=evaluated,
        statuses=statuses,
        warnings=tuple(_strings(contract_v2.get("warnings"))),
        audit_refs={"v2_card_hash": _text(contract_v2.get("card_hash"))},
        decision_hash=_hash(core),
    )


def build_recommendation_decision_v3(
    *,
    fixture_identity: Mapping[str, Any],
    exact_quote_candidate: Mapping[str, Any] | None,
    model_evidence: Mapping[str, Any],
    data_readiness: Mapping[str, Any],
    integrity: Mapping[str, Any],
    capability_manifest: RecommendationCapabilityManifest,
    as_of: datetime | str,
) -> RecommendationDecisionV3:
    fixture_id = _text(fixture_identity.get("fixture_id"))
    competition_id = _text(fixture_identity.get("competition_id"))
    as_of_text = _iso(as_of)
    warnings = tuple(_strings(data_readiness.get("warnings")))

    selected_candidate: dict[str, Any] | None = None
    evaluated_candidate = dict(model_evidence) if model_evidence else None
    outcome = RecommendationOutcomeV3.ANALYSIS_PICK
    reason_code = "ANALYSIS_ONLY"
    reason_message = "当前仅提供分析参考"
    next_action = "MONITOR"

    if _text(integrity.get("status"), "PASS") not in {"PASS", "READY"}:
        outcome = RecommendationOutcomeV3.SYSTEM_DEGRADED
        reason_code = "INTEGRITY_CONFLICT"
        reason_message = "数据身份链冲突"
        next_action = "WAIT"
    elif _text(fixture_identity.get("team_identity_status")) != "READY":
        outcome = RecommendationOutcomeV3.NOT_READY
        reason_code = "TEAM_IDENTITY_NOT_READY"
        reason_message = "队伍身份尚未完成审核"
        next_action = "WAIT"
    elif not exact_quote_candidate:
        outcome = RecommendationOutcomeV3.NOT_READY
        reason_code = "CURRENT_QUOTE_MISSING"
        reason_message = "当前可执行报价缺失"
        next_action = "WAIT"
    elif not _model_fields_ready(model_evidence):
        outcome = RecommendationOutcomeV3.NOT_READY
        reason_code = "MODEL_EVIDENCE_NOT_READY"
        reason_message = "模型证据缺少正式 selector 所需字段"
        next_action = "WAIT"
    elif not _quote_binding_matches(model_evidence, exact_quote_candidate):
        outcome = RecommendationOutcomeV3.NOT_READY
        reason_code = "MODEL_QUOTE_IDENTITY_MISMATCH"
        reason_message = "模型证据指向的盘口与当前市场审计报价不一致"
        next_action = "WAIT"
    elif _text(data_readiness.get("quote_freshness_status"), "COMPLETE") != "COMPLETE":
        outcome = RecommendationOutcomeV3.NOT_READY
        reason_code = "CURRENT_QUOTE_STALE"
        reason_message = "当前报价已过期或 freshness 冲突"
        next_action = "WAIT"
    elif not _truthy(_mapping(model_evidence.get("comparison")).get("analysis_direction_allowed")):
        outcome = RecommendationOutcomeV3.NO_EDGE
        reason_code = "NO_ANALYSIS_EDGE"
        reason_message = "同盘口模型与市场比较未形成优势"
        next_action = "WAIT"
    else:
        selected_candidate = {
            key: value
            for key, value in dict(model_evidence).items()
            if key not in {"analysis_markets"}
        }
        selected_candidate["quote_identity"] = _quote_identity_payload(exact_quote_candidate)
        if (
            _text(model_evidence.get("decision")) == "RECOMMEND"
            and _text(model_evidence.get("market")) == "ASIAN_HANDICAP"
            and capability_manifest.capability("formal_ah").feature_enabled
        ):
            outcome = RecommendationOutcomeV3.FORMAL_RECOMMEND
            reason_code = "FORMAL_ADMITTED"
            reason_message = "正式推荐已通过能力门"

    if outcome is not RecommendationOutcomeV3.ANALYSIS_PICK:
        selected_candidate = None
    if outcome is RecommendationOutcomeV3.FORMAL_RECOMMEND:
        raise AssertionError("FORMAL_RECOMMEND_DISABLED_FOR_MATCHDAY_INTAKE_V2")

    statuses = {
        "integrity": _text(integrity.get("status"), "PASS"),
        "data": _text(data_readiness.get("status"), "PARTIAL"),
        "quote": _text(data_readiness.get("quote_status"), "UNKNOWN"),
        "model": "READY" if _model_fields_ready(model_evidence) else "NOT_READY",
        "capability": "ANALYSIS_ONLY",
    }
    core = {
        "fixture_id": fixture_id,
        "competition_id": competition_id,
        "as_of": as_of_text,
        "outcome": outcome.value,
        "reason_code": reason_code,
        "selected_candidate": selected_candidate,
        "evaluated_candidate": evaluated_candidate,
        "quote_identity": _quote_identity_payload(exact_quote_candidate or {})
        if selected_candidate
        else {},
        "model_version": _text(model_evidence.get("model_version")),
        "calibration_version": _text(model_evidence.get("calibration_version")),
    }
    decision = RecommendationDecisionV3(
        fixture_id=fixture_id,
        competition_id=competition_id,
        as_of=as_of_text,
        outcome=outcome,
        reason_code=reason_code,
        reason_message=reason_message,
        next_action=next_action,
        selected_candidate=selected_candidate,
        evaluated_candidate=evaluated_candidate,
        statuses=statuses,
        warnings=warnings,
        audit_refs={
            "quote_identity_hash": _hash(_quote_identity_payload(exact_quote_candidate or {}))
        },
        decision_hash=_hash(core),
    )
    validate_decision_v3_identity(decision)
    return decision


def validate_decision_v3_identity(decision: RecommendationDecisionV3 | Mapping[str, Any]) -> str:
    payload = (
        decision.as_dict() if isinstance(decision, RecommendationDecisionV3) else dict(decision)
    )
    reason = _mapping(payload.get("reason"))
    selected = payload.get("selected_candidate")
    evaluated = payload.get("evaluated_candidate")
    selected_mapping = dict(selected) if isinstance(selected, Mapping) else None
    quote_identity = _candidate_quote_identity_for_hash(selected_mapping)
    core = {
        "fixture_id": _text(payload.get("fixture_id")),
        "competition_id": _text(payload.get("competition_id")),
        "as_of": _text(payload.get("as_of")),
        "outcome": _text(payload.get("outcome")),
        "reason_code": _text(reason.get("code") or payload.get("reason_code")),
        "selected_candidate": selected_mapping,
        "evaluated_candidate": dict(evaluated) if isinstance(evaluated, Mapping) else None,
        "quote_identity": quote_identity,
        "model_version": _text(_mapping(evaluated).get("model_version")),
        "calibration_version": _text(_mapping(evaluated).get("calibration_version")),
    }
    expected = _hash(core)
    if payload.get("decision_hash") != expected:
        raise ValueError("DECISION_V3_IDENTITY_CONFLICT")
    return expected


def _outcome(
    contract: Mapping[str, Any],
    candidate: dict[str, Any] | None,
    evaluated: dict[str, Any] | None,
    manifest: RecommendationCapabilityManifest,
) -> tuple[RecommendationOutcomeV3, str, str]:
    integrity = _text(contract.get("integrity_status"), "PASS")
    quote = _text(contract.get("quote_provenance_status"), "UNKNOWN")
    if integrity not in {"PASS", "READY", ""} or quote in {"CONFLICT", "INVALID"}:
        return RecommendationOutcomeV3.SYSTEM_DEGRADED, "INTEGRITY_CONFLICT", "数据身份链冲突"
    evidence = _mapping(evaluated.get("analysis_evidence")) if evaluated else {}
    evidence_status = _text(evidence.get("status"))
    if evidence_status not in {"", "COMPLETE"}:
        return (
            RecommendationOutcomeV3.NOT_READY,
            "ANALYSIS_EVIDENCE_NOT_READY",
            "选定盘口的报价或模型证据尚未就绪",
        )
    if evidence_status == "COMPLETE" and not _truthy(
        _mapping(evidence.get("comparison")).get("analysis_direction_allowed")
    ):
        return RecommendationOutcomeV3.NO_EDGE, "NO_ANALYSIS_EDGE", "同盘口模型与市场比较未形成优势"
    data = _text(contract.get("data_status"), "PARTIAL")
    if data != "READY":
        return RecommendationOutcomeV3.NOT_READY, "DATA_NOT_READY", "数据或可执行盘口尚未就绪"
    tier = _text(contract.get("decision_tier"))
    if tier in {"SKIP", "WATCH", "NOT_READY", ""} or candidate is None:
        return RecommendationOutcomeV3.NO_EDGE, "NO_ANALYSIS_EDGE", "数据完整但没有分析优势"
    if tier == "RECOMMEND" and candidate.get("market") == "ASIAN_HANDICAP":
        if manifest.capability("formal_ah").feature_enabled:
            return (
                RecommendationOutcomeV3.FORMAL_RECOMMEND,
                "FORMAL_ADMITTED",
                "正式推荐已通过能力门",
            )
        return (
            RecommendationOutcomeV3.ANALYSIS_PICK,
            "FORMAL_CAPABILITY_DISABLED",
            "正式推荐能力未开放",
        )
    return RecommendationOutcomeV3.ANALYSIS_PICK, "ANALYSIS_ONLY", "当前仅提供分析参考"


def _candidate(contract: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = contract.get("pick")
    return dict(raw) if isinstance(raw, Mapping) else None


def _evaluated_candidate(contract: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = contract.get("selected_market_candidate")
    if isinstance(raw, Mapping):
        return dict(raw)
    return _candidate(contract)


def _capability_status(
    candidate: Mapping[str, Any] | None, manifest: RecommendationCapabilityManifest
) -> str:
    if candidate is None:
        return "NOT_APPLICABLE"
    return "FORMAL_ENABLED" if manifest.capability("formal_ah").feature_enabled else "ANALYSIS_ONLY"


def _model_status(
    candidate: Mapping[str, Any] | None,
    evaluated: Mapping[str, Any] | None,
) -> str:
    if candidate is not None:
        return "READY"
    evidence = _mapping(evaluated.get("analysis_evidence")) if evaluated else {}
    model = _mapping(evidence.get("model_probability"))
    if _text(model.get("status")) in {"READY", "SIDE_EVIDENCE_AVAILABLE"}:
        return "READY"
    if evaluated is not None and _text(evaluated.get("model_status")) == "READY":
        return "READY"
    return "NOT_SELECTED"


def _quote_identity(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    return {key: candidate.get(key) for key in ("market", "selection", "line", "odds")}


def _candidate_quote_identity_for_hash(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    if candidate is None:
        return {}
    nested = _mapping(candidate.get("quote_identity"))
    if nested:
        return dict(nested)
    return _quote_identity(candidate)


def _hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _text(value: object, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _truthy(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def _iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return _text(value)


def _model_fields_ready(model_evidence: Mapping[str, Any]) -> bool:
    required = (
        "model_probability",
        "market_probability",
        "probability_delta",
        "expected_value",
        "uncertainty",
        "model_version",
        "calibration_version",
        "exact_quote_identity",
    )
    if any(model_evidence.get(key) in (None, "") for key in required):
        return False
    if model_evidence.get("decision_score") in (None, "") and model_evidence.get(
        "signal_strength"
    ) in (None, ""):
        return False
    return True


def _quote_binding_matches(
    model_evidence: Mapping[str, Any], exact_quote_candidate: Mapping[str, Any]
) -> bool:
    model_quote = _mapping(model_evidence.get("exact_quote_identity"))
    exact_quote = _quote_identity_payload(exact_quote_candidate)
    keys = (
        "fixture_id",
        "market",
        "selection",
        "line",
        "provider",
        "bookmaker_id",
        "capture_id",
        "captured_at",
    )
    if any(str(model_quote.get(key) or "") != str(exact_quote.get(key) or "") for key in keys):
        return False
    model_ids = sorted(str(item) for item in _strings(model_quote.get("quote_observation_ids")))
    exact_ids = sorted(str(item) for item in _strings(exact_quote.get("quote_observation_ids")))
    return bool(model_ids) and model_ids == exact_ids


def _quote_identity_payload(quote: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": quote.get("fixture_id"),
        "market": quote.get("market"),
        "selection": quote.get("selection"),
        "line": quote.get("line"),
        "provider": quote.get("provider"),
        "bookmaker_id": quote.get("bookmaker_id"),
        "capture_id": quote.get("capture_id"),
        "quote_observation_ids": list(quote.get("quote_observation_ids") or []),
        "captured_at": quote.get("captured_at"),
    }
