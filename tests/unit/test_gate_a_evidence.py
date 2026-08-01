from __future__ import annotations

from copy import deepcopy

import pytest

from w2.operations.gate_a_evidence import GateAEvidenceError, validate_gate_a_evidence


def valid_evidence() -> dict[str, object]:
    return {
        "schema_version": "w2.gate-a-offline-evidence.v1",
        "serializer_version": "w2.canonical-json.v2",
        "pair_identity": {"production": "pair", "independent": "pair"},
        "bootstrap_seed": {"production": "seed", "independent": "seed"},
        "required_deltas": {
            "provider_calls": 4,
            "business_writes": 3,
            "durable_evidence": 4,
        },
        "lineage": {
            "raw_payload_sha256": "payload",
            "endpoint_capture_sha256": "payload",
        },
        "metrics": {"coverage": 1.0},
    }


def test_gate_a_evidence_accepts_complete_offline_package() -> None:
    validate_gate_a_evidence(valid_evidence())


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (("serializer_version", None), "SERIALIZER_VERSION_MISSING"),
        (("pair_identity.independent", "other"), "INDEPENDENT_PAIR_HASH_MISMATCH"),
        (("bootstrap_seed.independent", "other"), "INDEPENDENT_BOOTSTRAP_SEED_MISMATCH"),
        (("metrics.coverage", float("nan")), "NAN_OR_INFINITY"),
        (("required_deltas.provider_calls", 0), "ANY_REQUIRED_DELTA_ZERO"),
        (("lineage.endpoint_capture_sha256", "other"), "LINEAGE_MISMATCH"),
    ],
)
def test_gate_a_evidence_hard_failures(mutation: tuple[str, object], code: str) -> None:
    payload = deepcopy(valid_evidence())
    path, value = mutation
    if "." in path:
        parent, child = path.split(".")
        target = payload[parent]
        assert isinstance(target, dict)
        target[child] = value
    else:
        payload[path] = value
    with pytest.raises(GateAEvidenceError, match=code):
        validate_gate_a_evidence(payload)
