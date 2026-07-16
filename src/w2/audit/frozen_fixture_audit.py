from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from w2.dashboard.scorelines import (
    _direction_scorelines_from_estimate,
    _market_settlement_distribution,
    _score_matrix_from_estimate,
)
from w2.models.fair_market_estimate import (
    SNAPSHOT_SCHEMA_V2,
    verify_estimate_semantics,
    verify_estimate_snapshot,
)
from w2.tracking.canonical_identity import canonical_capture_candidates
from w2.tracking.canonical_outcomes import project_canonical_outcomes
from w2.tracking.frozen_capture_identity import audit_capture_id, capture_estimate_identity
from w2.tracking.frozen_capture_lookup import FrozenCaptureLookup

FROZEN_AUDIT_SCHEMA_VERSION = "w2.frozen_fixture_audit.v1"
MAX_AUDIT_RESPONSE_BYTES = 512 * 1024
MAX_ESTIMATES = 2
MAX_SCORE_MATRIX_CELLS_PER_ESTIMATE = 169
MAX_GLOBAL_SCORELINES = 10
MAX_DIRECTION_SCORELINES = 10


def build_frozen_fixture_audit(
    lookup: FrozenCaptureLookup,
    *,
    requested_estimate_id: str | None,
) -> dict[str, Any]:
    capture = lookup.capture
    if capture is None:
        return _blocked_projection(lookup, lookup.reason or "CAPTURE_NOT_FOUND")

    snapshots = _snapshots(capture, requested_estimate_id)
    omitted: list[str] = []
    if len(snapshots) > MAX_ESTIMATES:
        snapshots = snapshots[:MAX_ESTIMATES]
        omitted.append("ESTIMATE_LIMIT_APPLIED")

    summaries: list[dict[str, Any]] = []
    invalid_snapshot = False
    corrected_evidence = False
    historical_compatibility = not snapshots
    selected_valid_snapshot: Mapping[str, Any] | None = None
    for snapshot in snapshots:
        integrity_ok = verify_estimate_snapshot(snapshot)
        semantic_ok = integrity_ok and verify_estimate_semantics(snapshot)
        is_v2 = str(snapshot.get("schema_version") or "") == SNAPSHOT_SCHEMA_V2
        corrected = bool(integrity_ok and semantic_ok and is_v2)
        historical = bool(integrity_ok and not is_v2)
        invalid_snapshot = invalid_snapshot or not integrity_ok
        corrected_evidence = corrected_evidence or corrected
        historical_compatibility = historical_compatibility or historical
        if corrected and selected_valid_snapshot is None:
            selected_valid_snapshot = snapshot
        summaries.append(_estimate_summary(snapshot, integrity_ok, semantic_ok, corrected))

    pick = _mapping(capture.get("pick"))
    global_scorelines: list[dict[str, Any]] = []
    direction_scorelines: list[dict[str, Any]] = []
    settlement: dict[str, Any] = {}
    if selected_valid_snapshot is not None:
        matrix = _score_matrix_from_estimate(selected_valid_snapshot) or {}
        global_scorelines = [
            {
                "scoreline": f"{home}-{away}",
                "home_goals": home,
                "away_goals": away,
                "probability": probability,
                "probability_type": "UNCONDITIONAL",
                "estimate_id": selected_valid_snapshot.get("estimate_id"),
            }
            for (home, away), probability in sorted(
                matrix.items(),
                key=lambda item: (-item[1], item[0][0] + item[0][1], item[0]),
            )[:MAX_GLOBAL_SCORELINES]
        ]
        direction_scorelines = _direction_scorelines_from_estimate(
            selected_valid_snapshot,
            pick,
            limit=MAX_DIRECTION_SCORELINES,
        )
        settlement = _market_settlement_distribution(selected_valid_snapshot, pick) or {}

    outcome_projection = project_canonical_outcomes(
        lookup.fixture_records,
        canonical_capture_candidates(lookup.fixture_records),
    )
    source_hash = _capture_hash(capture)
    source_capture_id = audit_capture_id(capture)
    source_estimate_id = capture_estimate_identity(capture).estimate_id
    source_status = "BLOCKED" if invalid_snapshot else lookup.source_status
    projection: dict[str, Any] = {
        "schema_version": FROZEN_AUDIT_SCHEMA_VERSION,
        "fixture_id": lookup.fixture_id,
        "source": "FROZEN_FORWARD_CAPTURE",
        "source_capture_hash": source_hash,
        "source_capture_id": source_capture_id,
        "source_estimate_id": source_estimate_id,
        "source_captured_at": capture.get("captured_at"),
        "source_status": source_status,
        "historical_compatibility": historical_compatibility,
        "corrected_evidence": corrected_evidence,
        "decision": {
            "decision_tier": capture.get("decision_tier"),
            "data_status": capture.get("data_status"),
            "reason_code": capture.get("reason_code"),
            "action": capture.get("action"),
            "outcome_tracked": bool(capture.get("outcome_tracked")),
            "lock_eligible": bool(capture.get("lock_eligible", False)),
            "pick": _pick_summary(pick),
            "non_pick": _pick_summary(_mapping(capture.get("non_pick"))),
        },
        "estimate_summaries": summaries,
        "scoreline_explanation": {
            "global_scorelines": global_scorelines,
            "direction_scorelines": direction_scorelines,
        },
        "settlement_distribution": settlement,
        "market_quote": _bounded_mapping(capture.get("market_quote")),
        "analysis_gate": _bounded_mapping(
            capture.get("analysis_gate") or capture.get("model_market_divergence")
        ),
        "strict_gate": _bounded_mapping(capture.get("strict_gate"))
        if corrected_evidence
        else {},
        "integrity": {
            "status": "BLOCKED"
            if invalid_snapshot
            else "PASS"
            if corrected_evidence
            else "HISTORICAL_COMPATIBILITY",
            "reason": "INVALID_ESTIMATE_SNAPSHOT" if invalid_snapshot else lookup.reason,
            "corruption_count": lookup.corruption_count,
        },
        "canonical_outcome": (
            _outcome_summary(outcome_projection.canonical_outcomes[0])
            if outcome_projection.canonical_outcomes
            else {}
        ),
        "audit_outcome_summary": {
            "raw_outcome_count": outcome_projection.metrics["raw_outcome_row_count"],
            "audit_only_count": outcome_projection.metrics["audit_only_outcome_count"],
            "duplicate_count": outcome_projection.metrics["canonical_duplicate_count"],
            "conflict_count": outcome_projection.metrics["outcome_conflict_count"],
            "identity_unmatched_count": outcome_projection.metrics[
                "identity_aware_unmatched_count"
            ],
            "recommendation_scope": (
                outcome_projection.canonical_outcomes[0].get("recommendation_scope")
                if outcome_projection.canonical_outcomes
                else None
            ),
            "strategy_version": (
                outcome_projection.canonical_outcomes[0].get("strategy_version")
                if outcome_projection.canonical_outcomes
                else None
            ),
        },
        "omitted_sections": omitted,
        "links": {
            "fixture_id": lookup.fixture_id,
            "capture_id": source_capture_id,
            "capture_hash": source_hash,
            "estimate_id": source_estimate_id,
        },
    }
    if _size(projection) <= MAX_AUDIT_RESPONSE_BYTES:
        return projection
    for summary in summaries:
        if summary.get("score_matrix"):
            summary["score_matrix"] = []
    projection["omitted_sections"].append("FULL_SCORE_MATRIX_SIZE_LIMIT")
    if _size(projection) <= MAX_AUDIT_RESPONSE_BYTES:
        return projection
    return _blocked_projection(lookup, "AUDIT_PROJECTION_TOO_LARGE")


def _snapshots(
    capture: Mapping[str, Any], requested_estimate_id: str | None
) -> list[Mapping[str, Any]]:
    rows = [
        item
        for item in capture.get("fair_market_estimate_snapshots") or ()
        if isinstance(item, Mapping)
    ]
    if requested_estimate_id:
        rows.sort(key=lambda item: item.get("estimate_id") != requested_estimate_id)
    return rows


def _estimate_summary(
    snapshot: Mapping[str, Any],
    integrity_ok: bool,
    semantic_ok: bool,
    corrected: bool,
) -> dict[str, Any]:
    matrix = _score_matrix_from_estimate(snapshot) if corrected else None
    cells = [
        {"scoreline": f"{home}-{away}", "probability": probability}
        for (home, away), probability in sorted((matrix or {}).items())[
            :MAX_SCORE_MATRIX_CELLS_PER_ESTIMATE
        ]
    ]
    context = _mapping(snapshot.get("model_context"))
    distribution_context = _mapping(snapshot.get("distribution_context"))
    return {
        "schema_version": snapshot.get("schema_version"),
        "estimate_id": snapshot.get("estimate_id"),
        "model_basis_id": snapshot.get("model_basis_id"),
        "market": snapshot.get("market"),
        "status": snapshot.get("status"),
        "fair_line": snapshot.get("fair_line"),
        "probabilities": _bounded_mapping(snapshot.get("probabilities")),
        "home_mu": snapshot.get("home_mu"),
        "away_mu": snapshot.get("away_mu"),
        "artifact_hash": context.get("artifact_hash") or snapshot.get("artifact_hash"),
        "artifact_version": context.get("artifact_version") or snapshot.get("artifact_version"),
        "train_cutoff": context.get("train_cutoff") or snapshot.get("train_cutoff"),
        "feature_as_of": context.get("feature_as_of") or snapshot.get("feature_as_of"),
        "odds_snapshot_hash": _mapping(snapshot.get("input_context")).get(
            "odds_snapshot_hash"
        )
        or snapshot.get("odds_snapshot_hash"),
        "feature_snapshot_hash": _mapping(snapshot.get("input_context")).get(
            "feature_snapshot_hash"
        )
        or snapshot.get("feature_snapshot_hash"),
        "matrix_hash": distribution_context.get("score_matrix_hash"),
        "score_matrix": cells,
        "integrity_status": "PASS" if integrity_ok else "BLOCKED",
        "semantic_status": "PASS" if semantic_ok else "BLOCKED",
        "historical_compatibility": integrity_ok
        and str(snapshot.get("schema_version") or "") != SNAPSHOT_SCHEMA_V2,
        "corrected_evidence": corrected,
    }


def _pick_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "market",
            "selection",
            "line",
            "odds",
            "fair_line",
            "estimate_id",
            "quote_id",
            "strategy_version",
        )
        if value.get(key) is not None
    }


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed = (
        "schema_version",
        "status",
        "reason",
        "market",
        "selection",
        "line",
        "market_line",
        "model_fair_line",
        "magnitude",
        "direction_allowed",
        "estimate_id",
        "quote_id",
        "model_basis_id",
        "policy_version",
        "policy_hash",
        "shadow_only",
        "affects_decision",
        "affects_tier",
    )
    return {key: value.get(key) for key in allowed if value.get(key) is not None}


def _outcome_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "canonical_performance_key",
            "settlement_outcome",
            "recommendation_scope",
            "strategy_version",
            "estimate_id",
            "quote_id",
            "source_capture_hash",
            "final_score",
        )
        if value.get(key) is not None
    }


def _capture_hash(capture: Mapping[str, Any]) -> str:
    return str(
        capture.get("capture_hash")
        or capture.get("evidence_hash")
        or capture.get("card_hash")
        or ""
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _size(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _blocked_projection(lookup: FrozenCaptureLookup, reason: str) -> dict[str, Any]:
    return {
        "schema_version": FROZEN_AUDIT_SCHEMA_VERSION,
        "fixture_id": lookup.fixture_id,
        "source": "FROZEN_FORWARD_CAPTURE",
        "source_capture_hash": lookup.requested_capture_hash,
        "source_capture_id": lookup.requested_capture_id,
        "source_estimate_id": None,
        "source_status": "BLOCKED",
        "historical_compatibility": False,
        "corrected_evidence": False,
        "decision": {},
        "estimate_summaries": [],
        "scoreline_explanation": {"global_scorelines": [], "direction_scorelines": []},
        "settlement_distribution": {},
        "market_quote": {},
        "analysis_gate": {},
        "strict_gate": {},
        "integrity": {"status": "BLOCKED", "reason": reason},
        "canonical_outcome": {},
        "audit_outcome_summary": {},
        "omitted_sections": [],
        "links": {},
    }
