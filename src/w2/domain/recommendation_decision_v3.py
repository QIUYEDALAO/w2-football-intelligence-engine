"""Read-only validation for historical RecommendationDecisionV3 evidence.

V3 is retired as a decision writer.  Current decisions are created only by
RecommendationDecisionV4; this module remains solely so persisted V3 evidence can be
verified without being reinterpreted as current product authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def validate_decision_v3_identity(decision: Mapping[str, Any]) -> str:
    payload = dict(decision)
    reason = _mapping(payload.get("reason"))
    selected = payload.get("selected_candidate")
    evaluated = payload.get("evaluated_candidate")
    selected_mapping = dict(selected) if isinstance(selected, Mapping) else None
    core = {
        "fixture_id": _text(payload.get("fixture_id")),
        "competition_id": _text(payload.get("competition_id")),
        "as_of": _text(payload.get("as_of")),
        "outcome": _text(payload.get("outcome")),
        "reason_code": _text(reason.get("code") or payload.get("reason_code")),
        "selected_candidate": selected_mapping,
        "evaluated_candidate": dict(evaluated) if isinstance(evaluated, Mapping) else None,
        "quote_identity": _candidate_quote_identity_for_hash(selected_mapping),
        "model_version": _text(_mapping(evaluated).get("model_version")),
        "calibration_version": _text(_mapping(evaluated).get("calibration_version")),
    }
    expected = _hash(core)
    if payload.get("decision_hash") != expected:
        raise ValueError("DECISION_V3_IDENTITY_CONFLICT")
    if payload.get("decision_envelope_hash") != _decision_envelope_hash(payload):
        raise ValueError("DECISION_V3_ENVELOPE_CONFLICT")
    return expected


def validate_decision_v3_card_parity(
    decision: Mapping[str, Any],
    *,
    card_hash: object,
    decision_contract_card_hash: object,
) -> None:
    audit_refs = _mapping(decision.get("audit_refs"))
    v3_card_hash = _text(audit_refs.get("v2_card_hash"))
    if _text(card_hash) != _text(decision_contract_card_hash) or _text(card_hash) != v3_card_hash:
        raise ValueError("DECISION_V3_CARD_HASH_PARITY_CONFLICT")


def _candidate_quote_identity_for_hash(
    candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if candidate is None:
        return {}
    nested = _mapping(candidate.get("quote_identity"))
    if nested:
        return dict(nested)
    return {key: candidate.get(key) for key in ("market", "selection", "line", "odds")}


def _decision_envelope_hash(payload: Mapping[str, Any]) -> str:
    reason = _mapping(payload.get("reason"))
    selected = payload.get("selected_candidate")
    evaluated = payload.get("evaluated_candidate")
    return _hash(
        {
            "schema_version": _text(
                payload.get("schema_version"), "w2.recommendation_decision.v3"
            ),
            "fixture_id": _text(payload.get("fixture_id")),
            "competition_id": _text(payload.get("competition_id")),
            "as_of": _text(payload.get("as_of")),
            "outcome": _text(payload.get("outcome")),
            "reason": {
                "code": _text(reason.get("code") or payload.get("reason_code")),
                "message": _text(reason.get("message")),
            },
            "next_action": _text(payload.get("next_action")),
            "selected_candidate": dict(selected) if isinstance(selected, Mapping) else None,
            "evaluated_candidate": dict(evaluated) if isinstance(evaluated, Mapping) else None,
            "statuses": dict(_mapping(payload.get("statuses"))),
            "warnings": _strings(payload.get("warnings")),
            "audit_refs": dict(_mapping(payload.get("audit_refs"))),
            "decision_hash": _text(payload.get("decision_hash")),
        }
    )


def _hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _text(value: object, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
