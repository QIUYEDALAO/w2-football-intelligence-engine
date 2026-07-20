from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

FORMAL_AH_READINESS_SCHEMA = "w2.formal_ah_readiness.v1"


def evaluate_formal_ah_readiness(
    *,
    calibration: Mapping[str, Any],
    f5_historical_ah: Mapping[str, Any],
    f8_identity_value: Mapping[str, Any],
    offline_evidence: Mapping[str, Any],
    forward_shadow: Mapping[str, Any],
    approval_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
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
    blockers = [gate["reason"] for gate in gates.values() if not gate["passed"]]
    approval = _approval_status(approval_manifest)
    if not approval["passed"]:
        blockers.append(approval["reason"])
    admission_ready = not blockers
    return {
        "schema_version": FORMAL_AH_READINESS_SCHEMA,
        "global_gates": gates,
        "fixture_gates": [],
        "approval_status": approval,
        "approved_hashes": approval.get("accepted_hashes") or {},
        "blockers": blockers,
        "admission_ready": admission_ready,
        "formal_eligible": False if not admission_ready else True,
        "recommendation": None if not admission_ready else "PENDING_FIXTURE_GATE",
        "recommendation_id": None,
        "lock_eligible": False,
    }


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


def _approval_status(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        return {"passed": False, "reason": "FORMAL_HUMAN_APPROVAL_MISSING", "accepted_hashes": {}}
    hashes = manifest.get("accepted_hashes")
    approved = manifest.get("approved") is True
    if not approved:
        return {
            "passed": False,
            "reason": "FORMAL_HUMAN_APPROVAL_MISSING",
            "accepted_hashes": hashes or {},
        }
    if not isinstance(hashes, Mapping) or not hashes:
        return {"passed": False, "reason": "FORMAL_APPROVED_HASH_MISMATCH", "accepted_hashes": {}}
    expected_hash = manifest.get("accepted_hash_manifest_sha256")
    actual_hash = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if expected_hash and expected_hash != actual_hash:
        return {
            "passed": False,
            "reason": "FORMAL_APPROVED_HASH_MISMATCH",
            "accepted_hashes": dict(hashes),
        }
    return {"passed": True, "reason": None, "accepted_hashes": dict(hashes)}
