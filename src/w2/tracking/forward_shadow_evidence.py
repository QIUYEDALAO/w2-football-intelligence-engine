from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from w2.markets.settlement_probability import effective_settlement_probability

FORWARD_SHADOW_EVIDENCE_SCHEMA = "w2.forward_shadow_evidence.v1"
FORWARD_TARGET_COUNT = 200


def build_forward_shadow_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    model_distribution = _mapping(row.get("model_five_state_distribution"))
    market_distribution = _mapping(row.get("market_five_state_baseline"))
    market_status = str(row.get("market_baseline_status") or "")
    exclusions: list[str] = []
    if market_status != "READY":
        exclusions.append("MARKET_BASELINE_NOT_READY")
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
        "shadow": True,
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
    eligible = [
        row
        for row in captures
        if row["formal_evidence_eligible"] is True and row.get("test_only") is not True
    ]
    conclusion = (
        "PASS_FOR_FORMAL_REVIEW"
        if len(eligible) >= FORWARD_TARGET_COUNT
        else "INSUFFICIENT_EVIDENCE"
    )
    return {
        "schema_version": "w2.forward_shadow_evidence_report.v1",
        "target_count": FORWARD_TARGET_COUNT,
        "real_formal_evidence_count": len(eligible),
        "diagnostic_shadow_count": len(captures) - len(eligible),
        "conclusion": conclusion,
        "status": conclusion,
        "shadow_to_validation_count": 0,
        "shadow_to_official_count": 0,
    }


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
