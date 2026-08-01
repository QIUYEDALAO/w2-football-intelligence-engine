from __future__ import annotations

import hmac
import math
import re
from collections.abc import Mapping
from typing import Any

from w2.domain.canonical_serialization import (
    HashDomain,
    canonical_sha256,
    eval_02b_bootstrap_seed,
)

GATE_A_EVIDENCE_SCHEMA = "w2.gate-a-offline-evidence.v2"
SERIALIZER_VERSION = "w2.canonical-json.v2"
REQUIRED_ARTIFACT_DELTAS = {
    "provider_calls",
    "raw_payload",
    "endpoint_capture",
    "lineup_event",
    "dynamic_evaluation_v2",
    "five_state_snapshot",
    "exact_pair",
    "bootstrap_seed_evidence",
}
REQUIRED_BINDING_FIELDS = {
    "authorization_id",
    "task_key",
    "competition",
    "policy_season",
    "exact_head",
    "exact_tree",
    "serializer_version",
}


class GateAEvidenceError(RuntimeError):
    pass


def validate_gate_a_evidence(
    payload: Mapping[str, Any],
    *,
    expected_binding: Mapping[str, str],
) -> None:
    if payload.get("schema_version") != GATE_A_EVIDENCE_SCHEMA:
        raise GateAEvidenceError("GATE_A_EVIDENCE_SCHEMA_INVALID")
    if payload.get("serializer_version") != SERIALIZER_VERSION:
        raise GateAEvidenceError("SERIALIZER_VERSION_MISSING")
    if _contains_non_finite(payload):
        raise GateAEvidenceError("NAN_OR_INFINITY")
    _validate_binding(payload.get("binding"), expected=expected_binding)
    pair_hash = _recompute_pair_hash(payload.get("exact_pair"))
    _recompute_bootstrap_seed(payload.get("bootstrap_seed_evidence"), pair_hash=pair_hash)
    _validate_required_deltas(payload.get("required_artifact_deltas"))
    lineage = payload.get("lineage")
    if (
        not isinstance(lineage, Mapping)
        or not lineage.get("raw_payload_sha256")
        or lineage.get("raw_payload_sha256") != lineage.get("endpoint_capture_sha256")
    ):
        raise GateAEvidenceError("LINEAGE_MISMATCH")


def _validate_binding(value: Any, *, expected: Mapping[str, str]) -> None:
    if not isinstance(value, Mapping) or set(value) != REQUIRED_BINDING_FIELDS:
        raise GateAEvidenceError("EVIDENCE_BINDING_INVALID")
    if value.get("serializer_version") != SERIALIZER_VERSION:
        raise GateAEvidenceError("EVIDENCE_BINDING_INVALID")
    if any(not isinstance(value.get(field), str) or not value[field] for field in value):
        raise GateAEvidenceError("EVIDENCE_BINDING_INVALID")
    if any(
        re.fullmatch(r"[0-9a-f]{40}", str(value[field])) is None
        for field in ("exact_head", "exact_tree")
    ):
        raise GateAEvidenceError("EVIDENCE_CODE_IDENTITY_INVALID")
    if set(expected) != REQUIRED_BINDING_FIELDS or any(
        not hmac.compare_digest(str(value[field]), expected[field])
        for field in REQUIRED_BINDING_FIELDS
    ):
        raise GateAEvidenceError("EVIDENCE_BINDING_MISMATCH")


def _recompute_pair_hash(value: Any) -> str:
    if not isinstance(value, Mapping) or set(value) != {
        "identity_input",
        "pair_identity_sha256",
    }:
        raise GateAEvidenceError("EXACT_PAIR_EVIDENCE_INVALID")
    claimed = value["pair_identity_sha256"]
    if not isinstance(claimed, str) or re.fullmatch(r"[0-9a-f]{64}", claimed) is None:
        raise GateAEvidenceError("EXACT_PAIR_EVIDENCE_INVALID")
    actual = canonical_sha256(
        value["identity_input"],
        domain=HashDomain.EVAL_02B_PAIR_IDENTITY,
    )
    if not hmac.compare_digest(actual, claimed):
        raise GateAEvidenceError("PAIR_IDENTITY_RECOMPUTE_MISMATCH")
    return actual


def _recompute_bootstrap_seed(value: Any, *, pair_hash: str) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "contract_version",
        "validation_pair_identity_hashes",
        "bootstrap_seed",
    }:
        raise GateAEvidenceError("BOOTSTRAP_SEED_EVIDENCE_INVALID")
    hashes = value["validation_pair_identity_hashes"]
    contract_version = value["contract_version"]
    claimed = value["bootstrap_seed"]
    if (
        not isinstance(hashes, list)
        or not all(isinstance(item, str) for item in hashes)
        or pair_hash not in hashes
        or not isinstance(contract_version, str)
        or not isinstance(claimed, int)
        or isinstance(claimed, bool)
    ):
        raise GateAEvidenceError("BOOTSTRAP_SEED_EVIDENCE_INVALID")
    actual = eval_02b_bootstrap_seed(hashes, contract_version=contract_version)
    if actual != claimed:
        raise GateAEvidenceError("BOOTSTRAP_SEED_RECOMPUTE_MISMATCH")


def _validate_required_deltas(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != REQUIRED_ARTIFACT_DELTAS:
        raise GateAEvidenceError("REQUIRED_ARTIFACT_DELTAS_INVALID")
    if any(
        not isinstance(delta, int) or isinstance(delta, bool) or delta <= 0
        for delta in value.values()
    ):
        raise GateAEvidenceError("ANY_REQUIRED_ARTIFACT_DELTA_ZERO")


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_non_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite(item) for item in value)
    return False
