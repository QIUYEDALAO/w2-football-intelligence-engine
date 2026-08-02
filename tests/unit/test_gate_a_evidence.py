from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import scripts.validate_gate_a_offline_evidence as evidence_cli
from sqlalchemy import create_engine
from tests.unit.test_gate_a_offline import (
    PUBLIC_KEY,
    PUBLIC_KEY_SHA256,
    authorization_payload,
)

from w2.domain.canonical_serialization import (
    HashDomain,
    canonical_sha256,
    eval_02b_bootstrap_seed,
)
from w2.infrastructure.database import Base
from w2.operations.gate_a import GateARuntimeAuthorization
from w2.operations.gate_a_evidence import GateAEvidenceError, validate_gate_a_evidence

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
DIST = {"WIN": 0.4, "HALF_WIN": 0.1, "PUSH": 0.1, "HALF_LOSS": 0.1, "LOSS": 0.3}


def authorization() -> GateARuntimeAuthorization:
    return GateARuntimeAuthorization(
        authorization_id="authorization-1",
        task_key="future-refresh:world_cup_2026:2026:bucket",
        competition_id="world_cup_2026",
        season="2026",
        persistence="db",
        exact_head="a" * 40,
        exact_tree="b" * 40,
        execution_mode="COMPLETE_CLEAN_CHECKOUT",
        runtime_artifact_digest=None,
        complete_checkout_manifest_sha256="c" * 64,
        allowed_endpoints=frozenset({"status", "fixtures", "odds", "lineups"}),
        provider_call_cap=4,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        author="implementer",
        reviewer="independent-reviewer",
        approval_key_id="independent-key",
        approval_public_key_sha256="d" * 64,
        approval_custody_status="INDEPENDENT_SIGNER_CONFIRMED",
    )


def valid_evidence() -> dict[str, object]:
    identity_input = {
        "canonical_fixture_id": "fixture-1",
        "competition_id": "world_cup_2026",
        "season_id": "2026",
        "provider_id": "api_football",
        "bookmaker_id": "book-1",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME",
        "exact_line": -0.25,
        "pre_evaluation_id": "eval-pre",
        "post_evaluation_id": "eval-post",
    }
    pair_hash = canonical_sha256(identity_input, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
    contract_version = "w2.eval_02b_gate.v1"
    bootstrap = eval_02b_bootstrap_seed([pair_hash], contract_version=contract_version)
    oracle_source = ROOT / "oracle/canonical_serialization_oracle.py"
    lineages: dict[str, object] = {
        "signed_authorization": {
            "source_path": "/independent/authorization.json",
            "source_sha256": "e" * 64,
            "approval_key_id": "independent-key",
            "approval_public_key_sha256": "d" * 64,
            "approval_custody_status": "INDEPENDENT_SIGNER_CONFIRMED",
        },
        "reservation": {
            "lease_epoch": 1,
            "authorization_id": "authorization-1",
            "task_key": "future-refresh:world_cup_2026:2026:bucket",
            "status": "COMPLETED",
            "reserved_at": "2026-08-01T11:59:00Z",
            "finished_at": "2026-08-01T12:01:00Z",
            "provider_call_cap": 4,
            "provider_calls_used": 1,
            "evidence_baseline": {
                name: []
                for name in (
                    "provider_calls",
                    "raw_payload",
                    "endpoint_capture",
                    "lineup_event",
                    "dynamic_evaluation_v2",
                    "five_state_snapshot",
                    "exact_pair",
                    "bootstrap_seed_evidence",
                )
            },
        },
        "task_audit": {
            "task_id": "task-1",
            "task_key": "future-refresh:world_cup_2026:2026:bucket",
            "authorization_id": "authorization-1",
            "lease_epoch": 1,
            "planned_at": "2026-08-01T11:58:00Z",
            "actual_execution_started_at": "2026-08-01T11:59:01Z",
            "finished_at": "2026-08-01T12:00:30Z",
            "status": "COMPLETED",
            "result": {"fixture_count": 1, "request_count": 1},
        },
        "provider_calls": [
            {
                "lease_epoch": 1,
                "ordinal": 1,
                "endpoint": "fixtures",
                "state": "RESPONSE_RECEIVED",
            }
        ],
        "raw_payload_rows": [
            {
                "sha256": "1" * 64,
                "endpoint": "fixtures",
                "captured_at": "2026-08-01T12:00:00Z",
                "inserted_at": "2026-08-01T12:00:00Z",
                "storage_uri": "db://raw_payload/1",
            }
        ],
        "endpoint_capture_rows": [
            {
                "capture_id": "capture-post",
                "endpoint": "odds",
                "request_task_key": "future-refresh:world_cup_2026:2026:bucket",
                "raw_payload_sha256": "1" * 64,
                "provider_captured_at": "2026-08-01T12:00:00Z",
            }
        ],
        "lineup_event_rows": [
            {
                "event_id": "event-1",
                "fixture_id": "fixture-1",
                "captured_at": "2026-08-01T11:59:00Z",
                "source_capture_id": "capture-post",
                "raw_sha256": "1" * 64,
            }
        ],
        "dynamic_evaluation_v2_rows": [
            {
                "evaluation_id": "eval-post",
                "fixture_id": "fixture-1",
                "capture_id": "capture-post",
                "capture_at": "2026-08-01T12:00:00Z",
                "identity_hash": "2" * 64,
                "schema_version": "w2.dynamic_quote_evaluation.v2",
            }
        ],
        "five_state_snapshot_rows": [
            {
                "evaluation_id": "eval-post",
                "distribution": DIST,
                "distribution_sha256": canonical_sha256(
                    DIST, domain=HashDomain.PREMATCH_READ_MODEL_DYNAMIC_EVALUATION
                ),
            }
        ],
        "exact_pair_source_rows": [
            {
                "evaluation_id": "eval-pre",
                "fixture_id": "fixture-1",
                "provider_id": "api_football",
                "bookmaker_id": "book-1",
                "market": "ASIAN_HANDICAP",
                "selection": "HOME",
                "exact_line": -0.25,
                "capture_id": "capture-pre",
                "capture_at": "2026-08-01T11:58:00Z",
                "schema_version": "w2.dynamic_quote_evaluation.v2",
            },
            {
                "evaluation_id": "eval-post",
                "fixture_id": "fixture-1",
                "provider_id": "api_football",
                "bookmaker_id": "book-1",
                "market": "ASIAN_HANDICAP",
                "selection": "HOME",
                "exact_line": -0.25,
                "capture_id": "capture-post",
                "capture_at": "2026-08-01T12:00:00Z",
                "schema_version": "w2.dynamic_quote_evaluation.v2",
            },
        ],
    }
    artifact_counts = {
        name: {"before": 0, "after": 1, "delta": 1}
        for name in (
            "provider_calls",
            "raw_payload",
            "endpoint_capture",
            "lineup_event",
            "dynamic_evaluation_v2",
            "five_state_snapshot",
            "exact_pair",
            "bootstrap_seed_evidence",
        )
    }
    return {
        "schema_version": "w2.gate-a-admission-evidence.v4",
        "serializer_version": "w2.canonical-json.v2",
        "binding": {
            "authorization_id": "authorization-1",
            "task_key": "future-refresh:world_cup_2026:2026:bucket",
            "competition": "world_cup_2026",
            "policy_season": "2026",
            "exact_head": "a" * 40,
            "exact_tree": "b" * 40,
            "execution_mode": "COMPLETE_CLEAN_CHECKOUT",
            "runtime_artifact_digest": None,
            "complete_checkout_manifest_sha256": "c" * 64,
            "serializer_version": "w2.canonical-json.v2",
        },
        "artifact_counts": artifact_counts,
        "lineage": lineages,
        "exact_pair_rows": [
            {
                "identity_input": identity_input,
                "pair_identity_sha256": pair_hash,
                "pre_capture_id": "capture-pre",
                "post_capture_id": "capture-post",
                "pre_capture_at": "2026-08-01T11:58:00Z",
                "post_capture_at": "2026-08-01T12:00:00Z",
                "baseline_distribution": DIST,
                "candidate_distribution": DIST,
            }
        ],
        "bootstrap_seed_evidence": {
            "contract_version": contract_version,
            "validation_pair_identity_hashes": [pair_hash],
            "bootstrap_seed": bootstrap,
        },
        "independent_oracle": {
            "source_path": "oracle/canonical_serialization_oracle.py",
            "source_sha256": hashlib.sha256(oracle_source.read_bytes()).hexdigest(),
            "transport_path": "scripts/invoke_independent_canonical_oracle.py",
        },
    }


def test_gate_a_evidence_accepts_db_produced_package_and_independent_oracle() -> None:
    validate_gate_a_evidence(
        valid_evidence(),
        authorization=authorization(),
        authorization_source_sha256="e" * 64,
    )


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        ("binding.authorization_id", "other", "EVIDENCE_BINDING_MISMATCH"),
        ("binding.complete_checkout_manifest_sha256", "d" * 64, "EVIDENCE_BINDING_MISMATCH"),
        ("exact_pair_rows.0.pair_identity_sha256", "4" * 64, "PAIR_IDENTITY_RECOMPUTE_MISMATCH"),
        (
            "lineage.dynamic_evaluation_v2_rows.0.schema_version",
            "v1",
            "DYNAMIC_EVALUATION_V2_REQUIRED",
        ),
        (
            "lineage.five_state_snapshot_rows.0.distribution.WIN",
            -0.1,
            "FIVE_STATE_PROBABILITY_INVALID",
        ),
        ("exact_pair_rows.0.post_capture_at", "other", "EXACT_PAIR_SOURCE_IDENTITY_MISMATCH"),
        ("artifact_counts.provider_calls.delta", 9, "CALLER_ASSERTED_ARTIFACT_COUNT_REJECTED"),
        (
            "lineage.signed_authorization.source_sha256",
            "0" * 64,
            "AUTHORITY_LINEAGE_MISMATCH",
        ),
        ("lineage.reservation.provider_calls_used", 2, "PROVIDER_CALL_COUNT_MISMATCH"),
        ("lineage.task_audit.result.request_count", 2, "PROVIDER_CALL_COUNT_MISMATCH"),
        ("lineage.provider_calls.0.ordinal", 2, "PROVIDER_CALL_ORDINALS_NOT_CONTIGUOUS"),
        ("lineage.provider_calls.0.lease_epoch", 2, "PROVIDER_CALL_LEASE_MISMATCH"),
        (
            "lineage.provider_calls.0.endpoint",
            "injuries",
            "PROVIDER_ENDPOINT_OUTSIDE_SIGNED_SCOPE",
        ),
    ],
)
def test_gate_a_evidence_hard_failures(path: str, value: object, code: str) -> None:
    payload = deepcopy(valid_evidence())
    target: object = payload
    segments = path.split(".")
    for segment in segments[:-1]:
        target = target[int(segment)] if isinstance(target, list) else target[segment]  # type: ignore[index]
    if isinstance(target, list):
        target[int(segments[-1])] = value
    else:
        target[segments[-1]] = value  # type: ignore[index]
    with pytest.raises(GateAEvidenceError, match=code):
        validate_gate_a_evidence(
            payload,
            authorization=authorization(),
            authorization_source_sha256="e" * 64,
        )


def test_any_derived_zero_delta_fails() -> None:
    payload = valid_evidence()
    lineage = payload["lineage"]
    assert isinstance(lineage, dict)
    lineage["five_state_snapshot_rows"] = []
    counts = payload["artifact_counts"]
    assert isinstance(counts, dict)
    counts["five_state_snapshot"] = {"before": 0, "after": 0, "delta": 0}
    with pytest.raises(GateAEvidenceError, match="ANY_REQUIRED_ARTIFACT_DELTA_ZERO"):
        validate_gate_a_evidence(
            payload,
            authorization=authorization(),
            authorization_source_sha256="e" * 64,
        )


def test_gate_a_evidence_cli_recomputes_from_db_before_atomic_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "evidence.json"
    compare_path = tmp_path / "existing.json"
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text("{}", encoding="utf-8")
    payload = valid_evidence()
    lineage = payload["lineage"]
    assert isinstance(lineage, dict)
    signed = lineage["signed_authorization"]
    assert isinstance(signed, dict)
    signed["source_sha256"] = hashlib.sha256(b"{}").hexdigest()
    compare_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(
        evidence_cli.GateARuntimeAuthorization, "load", lambda _path, **_kwargs: authorization()
    )
    monkeypatch.setattr(evidence_cli, "create_engine", lambda: object())
    monkeypatch.setattr(evidence_cli, "produce_gate_a_evidence", lambda **_kwargs: payload)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_gate_a_offline_evidence.py",
            "--authorization-file",
            str(authorization_path),
            "--output",
            str(output_path),
            "--compare-evidence",
            str(compare_path),
        ],
    )
    assert evidence_cli.main() == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload


def test_caller_evidence_is_canonical_compare_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    authorization_path = tmp_path / "authorization.json"
    compare_path = tmp_path / "fabricated.json"
    output_path = tmp_path / "evidence.json"
    authorization_path.write_text("{}", encoding="utf-8")
    authoritative = valid_evidence()
    signed = authoritative["lineage"]["signed_authorization"]  # type: ignore[index]
    signed["source_sha256"] = hashlib.sha256(b"{}").hexdigest()  # type: ignore[index]
    fabricated = deepcopy(authoritative)
    fabricated["artifact_counts"]["provider_calls"]["delta"] = 99  # type: ignore[index]
    compare_path.write_text(json.dumps(fabricated), encoding="utf-8")
    monkeypatch.setattr(
        evidence_cli.GateARuntimeAuthorization, "load", lambda _path, **_kwargs: authorization()
    )
    monkeypatch.setattr(evidence_cli, "create_engine", lambda: object())
    monkeypatch.setattr(
        evidence_cli, "produce_gate_a_evidence", lambda **_kwargs: authoritative
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_gate_a_offline_evidence.py",
            "--authorization-file",
            str(authorization_path),
            "--compare-evidence",
            str(compare_path),
            "--output",
            str(output_path),
        ],
    )
    assert evidence_cli.main() == 1
    assert not output_path.exists()


def test_fabricated_evidence_cannot_replace_empty_db_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    authorization_path = tmp_path / "authorization.json"
    fabricated_path = tmp_path / "fabricated.json"
    output_path = tmp_path / "admitted.json"
    authorization_path.write_text("{}", encoding="utf-8")
    fabricated_path.write_text(json.dumps(valid_evidence()), encoding="utf-8")
    monkeypatch.setattr(
        evidence_cli.GateARuntimeAuthorization, "load", lambda _path, **_kwargs: authorization()
    )
    monkeypatch.setattr(evidence_cli, "create_engine", lambda: object())

    def reject_empty_db(**_kwargs: object) -> dict[str, object]:
        raise GateAEvidenceError("GATE_A_RESERVATION_NOT_COMPLETED")

    monkeypatch.setattr(evidence_cli, "produce_gate_a_evidence", reject_empty_db)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_gate_a_offline_evidence.py",
            "--authorization-file",
            str(authorization_path),
            "--compare-evidence",
            str(fabricated_path),
            "--output",
            str(output_path),
        ],
    )
    assert evidence_cli.main() == 1
    assert not output_path.exists()


def test_valid_signed_authorization_cannot_admit_self_consistent_fabrication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    authorization_path = tmp_path / "authorization.json"
    trust_path = tmp_path / "trust.json"
    fabricated_path = tmp_path / "fabricated.json"
    output_path = tmp_path / "admitted.json"
    signed = authorization_payload(
        authorization_id="authorization-1",
        task_key="future-refresh:world_cup_2026:2026:bucket",
    )
    authorization_path.write_text(json.dumps(signed), encoding="utf-8")
    trust_path.write_text(
        json.dumps(
            {
                "schema_version": "w2.gate-a-authorization-trust.v1",
                "trusted_ed25519_keys": {
                    "test-independent-key": {
                        "public_key_base64": PUBLIC_KEY,
                        "public_key_sha256": PUBLIC_KEY_SHA256,
                        "custody_status": "INDEPENDENT_SIGNER_CONFIRMED",
                        "authorization_enabled": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    authorization = GateARuntimeAuthorization.load(
        authorization_path, trust_store_path=trust_path
    )
    fabricated = valid_evidence()
    lineage = fabricated["lineage"]
    assert isinstance(lineage, dict)
    signed_lineage = lineage["signed_authorization"]
    assert isinstance(signed_lineage, dict)
    signed_lineage["source_sha256"] = hashlib.sha256(authorization_path.read_bytes()).hexdigest()
    signed_lineage["approval_key_id"] = "test-independent-key"
    signed_lineage["approval_public_key_sha256"] = PUBLIC_KEY_SHA256
    validate_gate_a_evidence(
        fabricated,
        authorization=authorization,
        authorization_source_sha256=signed_lineage["source_sha256"],
    )
    fabricated_path.write_text(json.dumps(fabricated), encoding="utf-8")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    original_load = GateARuntimeAuthorization.load.__func__

    def load_test_authorization(
        cls: type[GateARuntimeAuthorization], path: Path, **_kwargs: object
    ) -> GateARuntimeAuthorization:
        return original_load(cls, path, trust_store_path=trust_path)

    monkeypatch.setattr(
        evidence_cli.GateARuntimeAuthorization,
        "load",
        classmethod(load_test_authorization),
    )
    monkeypatch.setattr(evidence_cli, "create_engine", lambda: engine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_gate_a_offline_evidence.py",
            "--authorization-file",
            str(authorization_path),
            "--compare-evidence",
            str(fabricated_path),
            "--output",
            str(output_path),
        ],
    )
    assert evidence_cli.main() == 1
    assert not output_path.exists()
