from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

FORMAL_AH_READINESS_SCHEMA = "w2.formal_ah_readiness.v1"
FORMAL_AH_APPROVAL_SCHEMA = "w2.formal_ah_approval_manifest.v1"


def evaluate_formal_ah_readiness(
    *,
    calibration: Mapping[str, Any],
    f5_historical_ah: Mapping[str, Any],
    f8_identity_value: Mapping[str, Any],
    offline_evidence: Mapping[str, Any],
    forward_shadow: Mapping[str, Any],
    approval_manifest: Mapping[str, Any] | None,
    fixture_evidence: Mapping[str, Any] | None = None,
    capability_enabled: bool = False,
) -> dict[str, Any]:
    actual_hashes = _actual_hashes(
        calibration=calibration,
        f5_historical_ah=f5_historical_ah,
        f8_identity_value=f8_identity_value,
        offline_evidence=offline_evidence,
        forward_shadow=forward_shadow,
    )
    gates = {
        "calibration": _gate(calibration, "PASS_FOR_SHADOW", "FORMAL_CALIBRATION_NOT_VALIDATED"),
        "f5_historical_ah": _gate(f5_historical_ah, "READY", "FORMAL_F5_NOT_READY"),
        "f8_identity_value": _gate(f8_identity_value, "READY", "FORMAL_F8_NOT_READY"),
        "offline_evidence": _gate(
            offline_evidence,
            "PASS_FOR_SHADOW",
            "FORMAL_OFFLINE_EVIDENCE_NOT_READY",
        ),
        "forward_shadow": _gate(
            forward_shadow,
            "PASS_FOR_FORMAL_REVIEW",
            "FORMAL_FORWARD_EVIDENCE_NOT_READY",
        ),
    }
    global_blockers = [gate["reason"] for gate in gates.values() if not gate["passed"]]
    missing_actual_hashes = sorted(key for key, value in actual_hashes.items() if not value)
    if missing_actual_hashes:
        global_blockers.append("FORMAL_ACTUAL_ARTIFACT_HASH_MISSING")
    fixture_gates = _fixture_gates(fixture_evidence)
    fixture_blockers = [gate["reason"] for gate in fixture_gates if not gate["passed"]]
    blockers = [*global_blockers, *fixture_blockers]
    approval = _approval_status(approval_manifest, actual_hashes=actual_hashes)
    if not approval["passed"]:
        blockers.append(approval["reason"])
    human_approved = approval["passed"] is True
    global_evidence_ready = not global_blockers
    fixture_evidence_ready = not fixture_blockers
    if not capability_enabled:
        blockers.append("FORMAL_AH_CAPABILITY_DISABLED")
    admission_ready = global_evidence_ready and fixture_evidence_ready and human_approved
    formal_eligible = admission_ready and capability_enabled
    payload = {
        "schema_version": FORMAL_AH_READINESS_SCHEMA,
        "global_evidence_ready": global_evidence_ready,
        "fixture_evidence_ready": fixture_evidence_ready,
        "human_approved": human_approved,
        "capability_enabled": capability_enabled,
        "global_gates": gates,
        "fixture_gates": fixture_gates,
        "approval_status": approval,
        "approved_hashes": approval.get("accepted_hashes") or {},
        "actual_hashes": actual_hashes,
        "missing_actual_hashes": missing_actual_hashes,
        "blockers": blockers,
        "admission_ready": admission_ready,
        "formal_eligible": formal_eligible,
        "recommendation": None if not admission_ready else "PENDING_FIXTURE_GATE",
        "recommendation_id": None,
        "lock_eligible": False,
    }
    payload["readiness_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return payload


def validate_formal_ah_readiness(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an immutable readiness contract and return a normalized dict."""
    if not isinstance(payload, Mapping):
        raise ValueError("FORMAL_AH_READINESS_INVALID")
    if payload.get("schema_version") != FORMAL_AH_READINESS_SCHEMA:
        raise ValueError("FORMAL_AH_READINESS_SCHEMA_INVALID")
    expected = payload.get("readiness_hash")
    if not isinstance(expected, str) or not expected:
        raise ValueError("FORMAL_AH_READINESS_HASH_MISSING")
    body = dict(payload)
    body.pop("readiness_hash", None)
    actual = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    if actual != expected:
        raise ValueError("FORMAL_AH_READINESS_HASH_MISMATCH")
    actual_hashes = body.get("actual_hashes")
    if not isinstance(actual_hashes, Mapping) or any(
        not isinstance(value, str) or not value for value in actual_hashes.values()
    ):
        raise ValueError("FORMAL_AH_READINESS_ACTUAL_HASH_MISSING")
    accepted_hashes = body.get("approved_hashes")
    if accepted_hashes:
        if not isinstance(accepted_hashes, Mapping):
            raise ValueError("FORMAL_AH_READINESS_APPROVAL_INVALID")
        for key, value in accepted_hashes.items():
            if actual_hashes.get(key) != value:
                raise ValueError("FORMAL_AH_READINESS_APPROVAL_HASH_MISMATCH")
    return dict(payload)


def load_approval_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"approved": False, "accepted_hashes": {}, "manifest_status": "MISSING"}
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _gate(payload: Mapping[str, Any], required: str, reason: str) -> dict[str, Any]:
    status = str(payload.get("status") or payload.get("conclusion") or "")
    return {
        "required_status": required,
        "actual_status": status,
        "passed": status == required,
        "reason": reason,
    }


def _approval_status(
    manifest: Mapping[str, Any] | None,
    *,
    actual_hashes: Mapping[str, str],
) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        return {"passed": False, "reason": "FORMAL_HUMAN_APPROVAL_MISSING", "accepted_hashes": {}}
    if manifest.get("schema_version") != FORMAL_AH_APPROVAL_SCHEMA:
        return {"passed": False, "reason": "FORMAL_APPROVAL_SCHEMA_INVALID", "accepted_hashes": {}}
    hashes = manifest.get("accepted_hashes")
    approved = manifest.get("approved") is True
    if not approved:
        return {
            "passed": False,
            "reason": "FORMAL_HUMAN_APPROVAL_MISSING",
            "accepted_hashes": hashes or {},
        }
    if not str(manifest.get("reviewed_by") or "") or not str(manifest.get("reviewed_at") or ""):
        return {
            "passed": False,
            "reason": "FORMAL_APPROVAL_REVIEWER_MISSING",
            "accepted_hashes": hashes or {},
        }
    if not isinstance(hashes, Mapping) or not hashes:
        return {"passed": False, "reason": "FORMAL_APPROVED_HASH_MISMATCH", "accepted_hashes": {}}
    required = {
        "calibration_artifact",
        "f5_manifest",
        "f8_manifest",
        "offline_evidence_report",
        "forward_shadow_report",
        "code_sha",
        "factor_registry_sha",
    }
    if missing := sorted(required - set(hashes)):
        return {
            "passed": False,
            "reason": "FORMAL_APPROVED_HASH_MISSING",
            "accepted_hashes": dict(hashes),
            "missing_hashes": missing,
        }
    expected_hash = manifest.get("accepted_hash_manifest_sha256")
    if not isinstance(expected_hash, str) or not expected_hash:
        return {
            "passed": False,
            "reason": "FORMAL_APPROVED_HASH_MANIFEST_MISSING",
            "accepted_hashes": dict(hashes),
        }
    actual_hash = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if expected_hash != actual_hash:
        return {
            "passed": False,
            "reason": "FORMAL_APPROVED_HASH_MISMATCH",
            "accepted_hashes": dict(hashes),
        }
    for key in required:
        if actual_hashes.get(key) and hashes.get(key) != actual_hashes[key]:
            return {
                "passed": False,
                "reason": "FORMAL_APPROVED_HASH_MISMATCH",
                "accepted_hashes": dict(hashes),
                "mismatched_hash": key,
            }
    return {"passed": True, "reason": None, "accepted_hashes": dict(hashes)}


def _actual_hashes(
    *,
    calibration: Mapping[str, Any],
    f5_historical_ah: Mapping[str, Any],
    f8_identity_value: Mapping[str, Any],
    offline_evidence: Mapping[str, Any],
    forward_shadow: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "calibration_artifact": _hash_value(calibration, "artifact_hash"),
        "f5_manifest": _hash_value(f5_historical_ah, "manifest_hash", "fact_manifest_hash"),
        "f8_manifest": _hash_value(f8_identity_value, "manifest_hash", "artifact_hash"),
        "offline_evidence_report": _hash_value(offline_evidence, "report_hash", "evidence_hash"),
        "forward_shadow_report": _hash_value(forward_shadow, "report_hash", "evidence_hash"),
        "code_sha": _hash_value(calibration, "code_sha"),
        "factor_registry_sha": _hash_value(calibration, "factor_registry_sha"),
    }


def _hash_value(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _fixture_gates(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return [{"name": "fixture_evidence", "passed": False, "reason": "FIXTURE_EVIDENCE_MISSING"}]
    requirements = (
        ("prematch", "FIXTURE_NOT_PREMATCH"),
        ("executable_ah_quote", "AH_QUOTE_NOT_EXECUTABLE"),
        ("freshness_complete", "AH_QUOTE_FRESHNESS_INCOMPLETE"),
        ("same_pair_identity", "AH_QUOTE_PAIR_IDENTITY_INCOMPLETE"),
        ("simulation_ready", "SIMULATION_NOT_READY"),
        ("approved_calibration_version", "CALIBRATION_VERSION_NOT_APPROVED"),
        ("integrity_asof", "AS_OF_BLOCKED"),
    )
    return [
        {"name": name, "passed": payload.get(name) is True, "reason": reason}
        for name, reason in requirements
    ]
