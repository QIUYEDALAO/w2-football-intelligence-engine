from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

GATE_A_EVIDENCE_SCHEMA = "w2.gate-a-offline-evidence.v1"
SERIALIZER_VERSION = "w2.canonical-json.v2"
REQUIRED_DELTAS = {"provider_calls", "business_writes", "durable_evidence"}


class GateAEvidenceError(RuntimeError):
    pass


def validate_gate_a_evidence(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != GATE_A_EVIDENCE_SCHEMA:
        raise GateAEvidenceError("GATE_A_EVIDENCE_SCHEMA_INVALID")
    if payload.get("serializer_version") != SERIALIZER_VERSION:
        raise GateAEvidenceError("SERIALIZER_VERSION_MISSING")
    _matching_hashes(payload, "pair_identity", "INDEPENDENT_PAIR_HASH_MISMATCH")
    _matching_hashes(payload, "bootstrap_seed", "INDEPENDENT_BOOTSTRAP_SEED_MISMATCH")
    if _contains_non_finite(payload):
        raise GateAEvidenceError("NAN_OR_INFINITY")
    deltas = payload.get("required_deltas")
    if not isinstance(deltas, Mapping) or set(deltas) != REQUIRED_DELTAS:
        raise GateAEvidenceError("REQUIRED_DELTAS_INVALID")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in deltas.values()
    ):
        raise GateAEvidenceError("ANY_REQUIRED_DELTA_ZERO")
    lineage = payload.get("lineage")
    if (
        not isinstance(lineage, Mapping)
        or not lineage.get("raw_payload_sha256")
        or lineage.get("raw_payload_sha256") != lineage.get("endpoint_capture_sha256")
    ):
        raise GateAEvidenceError("LINEAGE_MISMATCH")


def _matching_hashes(payload: Mapping[str, Any], key: str, code: str) -> None:
    value = payload.get(key)
    if (
        not isinstance(value, Mapping)
        or not value.get("production")
        or value.get("production") != value.get("independent")
    ):
        raise GateAEvidenceError(code)


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_non_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite(item) for item in value)
    return False
