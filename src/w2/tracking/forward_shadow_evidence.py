from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from w2.markets.settlement_probability import (
    complete_five_state_distribution,
    effective_settlement_probability,
)

FORWARD_SHADOW_EVIDENCE_SCHEMA = "w2.forward_shadow_evidence.v1"
FORWARD_TARGET_COUNT = 200


def build_forward_shadow_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    model_distribution = _mapping(row.get("model_five_state_distribution"))
    market_distribution = _mapping(row.get("market_five_state_baseline"))
    market_status = str(row.get("market_baseline_status") or "")
    exclusions = _capture_exclusions(row, model_distribution, market_distribution)
    payload = {
        "schema_version": FORWARD_SHADOW_EVIDENCE_SCHEMA,
        "fixture_id": row.get("fixture_id"),
        "competition_id": row.get("competition_id"),
        "kickoff_utc": row.get("kickoff_utc"),
        "captured_at": row.get("captured_at"),
        "decision_hash": row.get("decision_hash"),
        "analysis_evidence_hash": row.get("analysis_evidence_hash"),
        "code_sha": row.get("code_sha"),
        "model_version": row.get("model_version"),
        "calibration_version": row.get("calibration_version"),
        "calibration_status": row.get("calibration_status"),
        "factor_registry_sha": row.get("factor_registry_sha"),
        "f5_readiness": row.get("f5_readiness"),
        "f5_fact_hashes": row.get("f5_fact_hashes") or [],
        "f8_readiness": row.get("f8_readiness"),
        "team_value_asof_hashes": row.get("team_value_asof_hashes") or [],
        "market": row.get("market"),
        "selection": row.get("selection"),
        "line": row.get("line"),
        "entry_odds": row.get("entry_odds"),
        "quote_observation_ids": row.get("quote_observation_ids") or [],
        "quote_identity_hash": row.get("quote_identity_hash"),
        "quote_captured_at": row.get("quote_captured_at"),
        "model_five_state_distribution": dict(model_distribution),
        "market_five_state_baseline": dict(market_distribution),
        "market_baseline_status": market_status,
        "market_baseline_hash": row.get("market_baseline_hash"),
        "model_effective_probability": effective_settlement_probability(model_distribution),
        "entry_devig_probability": row.get("entry_devig_probability"),
        "probability_delta": row.get("probability_delta"),
        "expected_value": row.get("expected_value"),
        "uncertainty": row.get("uncertainty"),
        "capability_manifest_sha": row.get("capability_manifest_sha"),
        "shadow": row.get("shadow") is True,
        "not_a_recommendation": True,
        "not_displayed": True,
        "recommendation_scope": "SHADOW",
        "formal_evidence_eligible": not exclusions,
        "exclusion_reasons": exclusions,
        "test_only": row.get("test_only") is True,
    }
    payload["capture_hash"] = _hash(payload)
    return payload


def evaluate_forward_shadow_evidence(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    captures = [build_forward_shadow_evidence(row) for row in rows]
    conflicts = _capture_identity_conflicts(captures)
    exclusion_counts = _exclusion_counts(captures)
    eligible = [
        row
        for row in captures
        if row["formal_evidence_eligible"] is True and row.get("test_only") is not True
        and row["capture_hash"] not in conflicts
    ]
    conclusion = (
        "POLICY_THRESHOLD_UNVALIDATED"
        if len(eligible) >= FORWARD_TARGET_COUNT
        else "INSUFFICIENT_EVIDENCE"
    )
    payload = {
        "schema_version": "w2.forward_shadow_evidence_report.v1",
        "target_count": FORWARD_TARGET_COUNT,
        "real_formal_evidence_count": len(eligible),
        "remaining_count": max(FORWARD_TARGET_COUNT - len(eligible), 0),
        "diagnostic_shadow_count": len(captures) - len(eligible),
        "conclusion": conclusion,
        "status": conclusion,
        "duplicate_or_conflict_count": len(conflicts),
        "exclusion_counts": exclusion_counts,
        "metrics": _forward_metrics(eligible),
        "strata": _strata(eligible),
        "shadow_to_validation_count": sum(
            1 for row in captures if row.get("validation_ready") is True
        ),
        "shadow_to_official_count": sum(
            1 for row in captures if row.get("official_ready") is True
        ),
    }
    payload["report_hash"] = _hash(payload)
    return payload


def _capture_exclusions(
    row: Mapping[str, Any],
    model_distribution: Mapping[str, Any],
    market_distribution: Mapping[str, Any],
) -> list[str]:
    exclusions: list[str] = []
    if row.get("test_only") is True:
        exclusions.append("TEST_ONLY")
    if row.get("shadow") is not True:
        exclusions.append("NOT_SHADOW")
    if row.get("identity_conflict") is True:
        exclusions.append("IDENTITY_CONFLICT")
    if row.get("f5_readiness") != "READY" or not row.get("f5_fact_hashes"):
        exclusions.append("F5_NOT_READY")
    if row.get("f8_readiness") != "READY" or not row.get("team_value_asof_hashes"):
        exclusions.append("F8_NOT_READY")
    if row.get("calibration_status") != "PASS_FOR_SHADOW":
        exclusions.append("CALIBRATION_NOT_PASS_FOR_SHADOW")
    for key in ("model_version", "calibration_version", "factor_registry_sha"):
        if not str(row.get(key) or ""):
            exclusions.append(f"MISSING_{key.upper()}")
    if not str(row.get("quote_identity_hash") or ""):
        exclusions.append("QUOTE_IDENTITY_INCOMPLETE")
    captured = _parse_utc(row.get("quote_captured_at") or row.get("captured_at"))
    kickoff = _parse_utc(row.get("kickoff_utc"))
    if captured is None or kickoff is None or captured >= kickoff:
        exclusions.append("QUOTE_NOT_PREKICKOFF")
    if not str(row.get("selection") or "") or row.get("line") in {None, ""}:
        exclusions.append("LINE_SELECTION_INCOMPLETE")
    if not complete_five_state_distribution(model_distribution):
        exclusions.append("MODEL_FIVE_STATE_INCOMPLETE")
    if row.get("market_baseline_status") != "READY" or not complete_five_state_distribution(
        market_distribution
    ):
        exclusions.append("MARKET_BASELINE_NOT_READY")
    if not str(row.get("result_identity_hash") or "") or not str(
        row.get("settlement_outcome") or ""
    ):
        exclusions.append("RESULT_SETTLEMENT_INCOMPLETE")
    if not str(row.get("clv_identity_hash") or ""):
        exclusions.append("CLV_IDENTITY_INCOMPLETE")
    if not str(row.get("decision_hash") or ""):
        exclusions.append("CAPTURE_IDENTITY_INCOMPLETE")
    return sorted(set(exclusions))


def _capture_identity_conflicts(captures: Sequence[Mapping[str, Any]]) -> set[str]:
    seen: dict[tuple[str, str, str, str], str] = {}
    conflicts: set[str] = set()
    for row in captures:
        key = (
            str(row.get("fixture_id") or ""),
            str(row.get("market") or ""),
            str(row.get("selection") or ""),
            str(row.get("quote_identity_hash") or ""),
        )
        previous = seen.get(key)
        current = str(row.get("capture_hash") or "")
        if previous is not None and previous != current:
            conflicts.update({previous, current})
        seen[key] = current
    return conflicts


def _exclusion_counts(captures: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in captures:
        for reason in row.get("exclusion_reasons") or []:
            key = str(reason)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _forward_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "sample_count": 0,
            "log_loss": None,
            "multiclass_brier": None,
            "classwise_ece": None,
            "mean_ev": None,
            "mean_clv": None,
            "paired_bootstrap": {"replicates": 1000, "seed": 7, "status": "INSUFFICIENT_EVIDENCE"},
        }
    ev = [
        float(row["expected_value"])
        for row in rows
        if isinstance(row.get("expected_value"), int | float)
    ]
    clv = [
        float(row["clv_probability_delta"])
        for row in rows
        if isinstance(row.get("clv_probability_delta"), int | float)
    ]
    return {
        "sample_count": len(rows),
        "log_loss": None,
        "multiclass_brier": None,
        "classwise_ece": None,
        "mean_ev": round(sum(ev) / len(ev), 6) if ev else None,
        "mean_clv": round(sum(clv) / len(clv), 6) if clv else None,
        "paired_bootstrap": {
            "replicates": 1000,
            "seed": 7,
            "status": "POLICY_THRESHOLD_UNVALIDATED",
        },
    }


def _strata(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    strata: dict[str, dict[str, int]] = {"league": {}, "line": {}, "side": {}}
    for row in rows:
        for key, field in (("league", "competition_id"), ("line", "line"), ("side", "selection")):
            value = str(row.get(field) or "UNKNOWN")
            strata[key][value] = strata[key].get(value, 0) + 1
    return strata


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_utc(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
