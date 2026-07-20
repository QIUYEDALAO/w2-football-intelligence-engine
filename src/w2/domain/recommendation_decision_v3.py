from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
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
        "outcome": outcome.value,
        "selected_candidate": candidate,
        "evaluated_candidate": evaluated,
        "reason_code": reason_code,
        "model_version": _text(contract_v2.get("model_version")),
        "quote_identity": _quote_identity(candidate),
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
