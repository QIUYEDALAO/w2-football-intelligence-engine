from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import scripts.validate_gate_a_offline_evidence as evidence_cli

from w2.operations.gate_a_evidence import GateAEvidenceError, validate_gate_a_evidence


def valid_evidence() -> dict[str, object]:
    identity_input = {
        "fixture_id": "fixture-1",
        "market": "AH",
        "pre_capture_id": "capture-pre",
        "post_capture_id": "capture-post",
    }
    pair_hash = "cf5b296bab7b43508eaf0dcff8310a6318348f1bab1acedf7ed5633a112edbc9"
    hashes = [pair_hash, "a" * 64]
    contract_version = "w2.eval_02b_gate.v1"
    return {
        "schema_version": "w2.gate-a-offline-evidence.v2",
        "serializer_version": "w2.canonical-json.v2",
        "binding": {
            "authorization_id": "authorization-1",
            "task_key": "future-refresh:world_cup_2026:2026:bucket",
            "competition": "world_cup_2026",
            "policy_season": "2026",
            "exact_head": "a" * 40,
            "exact_tree": "b" * 40,
            "serializer_version": "w2.canonical-json.v2",
        },
        "exact_pair": {
            "identity_input": identity_input,
            "pair_identity_sha256": pair_hash,
        },
        "bootstrap_seed_evidence": {
            "contract_version": contract_version,
            "validation_pair_identity_hashes": hashes,
            "bootstrap_seed": 49142224613414026,
        },
        "required_artifact_deltas": {
            "provider_calls": 4,
            "raw_payload": 4,
            "endpoint_capture": 4,
            "lineup_event": 1,
            "dynamic_evaluation_v2": 1,
            "five_state_snapshot": 1,
            "exact_pair": 1,
            "bootstrap_seed_evidence": 1,
        },
        "lineage": {
            "raw_payload_sha256": "payload",
            "endpoint_capture_sha256": "payload",
        },
        "metrics": {"coverage": 1.0},
    }


def expected_binding() -> dict[str, str]:
    return {
        "authorization_id": "authorization-1",
        "task_key": "future-refresh:world_cup_2026:2026:bucket",
        "competition": "world_cup_2026",
        "policy_season": "2026",
        "exact_head": "a" * 40,
        "exact_tree": "b" * 40,
        "serializer_version": "w2.canonical-json.v2",
    }


def test_gate_a_evidence_accepts_complete_offline_package() -> None:
    validate_gate_a_evidence(valid_evidence(), expected_binding=expected_binding())


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        ("serializer_version", None, "SERIALIZER_VERSION_MISSING"),
        ("binding.exact_tree", "other", "EVIDENCE_CODE_IDENTITY_INVALID"),
        ("binding.authorization_id", "other", "EVIDENCE_BINDING_MISMATCH"),
        ("exact_pair.pair_identity_sha256", "c" * 64, "PAIR_IDENTITY_RECOMPUTE_MISMATCH"),
        ("bootstrap_seed_evidence.bootstrap_seed", 7, "BOOTSTRAP_SEED_RECOMPUTE_MISMATCH"),
        ("metrics.coverage", float("nan"), "NAN_OR_INFINITY"),
        (
            "required_artifact_deltas.provider_calls",
            0,
            "ANY_REQUIRED_ARTIFACT_DELTA_ZERO",
        ),
        (
            "required_artifact_deltas.dynamic_evaluation_v2",
            0,
            "ANY_REQUIRED_ARTIFACT_DELTA_ZERO",
        ),
        (
            "required_artifact_deltas.five_state_snapshot",
            0,
            "ANY_REQUIRED_ARTIFACT_DELTA_ZERO",
        ),
        ("lineage.endpoint_capture_sha256", "other", "LINEAGE_MISMATCH"),
    ],
)
def test_gate_a_evidence_hard_failures(path: str, value: object, code: str) -> None:
    payload = deepcopy(valid_evidence())
    segments = path.split(".")
    target = payload
    for segment in segments[:-1]:
        nested = target[segment]
        assert isinstance(nested, dict)
        target = nested
    target[segments[-1]] = value
    with pytest.raises(GateAEvidenceError, match=code):
        validate_gate_a_evidence(payload, expected_binding=expected_binding())


def test_v1_dynamic_inventory_cannot_satisfy_v2_or_five_state_gate() -> None:
    payload = valid_evidence()
    deltas = payload["required_artifact_deltas"]
    assert isinstance(deltas, dict)
    deltas["dynamic_evaluation_v1"] = deltas.pop("dynamic_evaluation_v2")

    with pytest.raises(GateAEvidenceError, match="REQUIRED_ARTIFACT_DELTAS_INVALID"):
        validate_gate_a_evidence(payload, expected_binding=expected_binding())


def test_gate_a_evidence_cli_positive_and_negative_matrix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    base_args = [
        "validate_gate_a_offline_evidence.py",
        str(evidence_path),
        "--authorization-id",
        "authorization-1",
        "--task-key",
        "future-refresh:world_cup_2026:2026:bucket",
        "--competition",
        "world_cup_2026",
        "--policy-season",
        "2026",
        "--exact-head",
        "a" * 40,
        "--exact-tree",
        "b" * 40,
    ]
    evidence_path.write_text(json.dumps(valid_evidence()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", base_args)
    assert evidence_cli.main() == 0

    rejected = valid_evidence()
    deltas = rejected["required_artifact_deltas"]
    assert isinstance(deltas, dict)
    deltas["bootstrap_seed_evidence"] = 0
    evidence_path.write_text(json.dumps(rejected), encoding="utf-8")
    assert evidence_cli.main() == 1
