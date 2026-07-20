"""Single compatibility projection from a materialized V3 decision."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def project_canonical_decision(decision: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project only display/compatibility fields; never re-evaluate a decision."""
    payload = dict(decision or {})
    outcome = str(payload.get("outcome") or "NOT_READY")
    candidate = payload.get("selected_candidate")
    selected = dict(candidate) if isinstance(candidate, Mapping) else None
    is_pick = outcome in {"ANALYSIS_PICK", "FORMAL_RECOMMEND"} and selected is not None
    reason = payload.get("reason")
    reason_code = reason.get("code") if isinstance(reason, Mapping) else None
    return {
        "outcome": outcome,
        "pick": selected if is_pick else None,
        "decision_tier": "RECOMMEND"
        if outcome == "FORMAL_RECOMMEND"
        else "ANALYSIS_PICK"
        if is_pick
        else "NOT_READY"
        if outcome == "NOT_READY"
        else "SKIP",
        "outcome_tracked": bool(is_pick),
        "lock_eligible": False,
        "reason_code": reason_code,
        "next_action": payload.get("next_action"),
        "decision_hash": payload.get("decision_hash"),
        "quote_identity": _quote_identity(selected),
    }


def _quote_identity(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(candidate, Mapping):
        return {}
    identity = candidate.get("quote_identity")
    return dict(identity) if isinstance(identity, Mapping) else {}
