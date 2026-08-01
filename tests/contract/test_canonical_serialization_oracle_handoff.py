from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/contracts/w2_canonical_serialization_oracle_vectors_v2.schema.json"
HARNESS = ROOT / "scripts/verify_canonical_serialization_oracle.py"


def test_oracle_input_schema_and_harness_are_ready(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    assert {
        "production_implementation_head",
        "adr_id",
        "serializer_version",
        "oracle_author",
        "review_status",
        "reviewer_records",
        "mandatory_case_matrix",
    } <= set(schema["required"])
    assert schema["properties"]["oracle_imports_production_serializer"] == {"const": False}
    assert schema["properties"]["adr_id"] == {"const": "ADR-0019"}
    assert schema["properties"]["serializer_version"] == {
        "const": "w2.canonical-json.v2"
    }
    assert {"success", "error"} == {
        item["properties"]["status"]["const"]
        for item in schema["$defs"]["case"]["properties"]["oracle"]["oneOf"]
    }
    error_outcome = next(
        item
        for item in schema["$defs"]["case"]["properties"]["oracle"]["oneOf"]
        if item["properties"]["status"]["const"] == "error"
    )
    assert "error_code" in error_outcome["required"]
    assert "error_contains" not in error_outcome["properties"]
    result = subprocess.run(
        [sys.executable, str(HARNESS), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_oracle_handoff_enforces_unique_ids_and_mandatory_matrix() -> None:
    from scripts.verify_canonical_serialization_oracle import (
        MANDATORY_CASE_COUNTS,
        handoff_contract_failures,
    )

    cases = [
        {"case_id": f"{category}-{index}", "category": category}
        for category, count in MANDATORY_CASE_COUNTS.items()
        for index in range(count)
    ]
    payload = {
        "oracle_author": "oracle-author",
        "reviewer_records": [{"reviewer": "independent-reviewer"}],
        "cases": cases,
    }
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["mandatory_case_matrix"]["const"] == list(
        MANDATORY_CASE_COUNTS
    )
    assert handoff_contract_failures(payload) == []

    payload["cases"] = cases[:-1] + [cases[0]]
    failures = handoff_contract_failures(payload)
    assert "case_id values must be unique" in failures
    assert any("invalid_pair_hash_rejected" in failure for failure in failures)


def test_implementer_tranche_contains_no_oracle_vectors() -> None:
    assert not list((ROOT / "tests").rglob("*golden*canonical*"))
    assert not list((ROOT / "tests").rglob("*oracle*vectors*.json"))
