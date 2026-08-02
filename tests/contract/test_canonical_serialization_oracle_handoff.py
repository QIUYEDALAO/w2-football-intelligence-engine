from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/contracts/w2_canonical_serialization_oracle_vectors_v2.schema.json"
HARNESS = ROOT / "scripts/verify_canonical_serialization_oracle.py"
VECTORS = ROOT / "oracle/w2_canonical_serialization_oracle_vectors_v2.json"


def test_combined_oracle_vectors_match_production() -> None:
    payload = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert len(payload["cases"]) == 30

    result = subprocess.run(
        [sys.executable, str(HARNESS), str(VECTORS)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_oracle_input_schema_and_harness_are_ready(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    assert {
        "production_implementation_head",
        "production_implementation_path",
        "production_implementation_sha256",
        "production_implementer",
        "adr_id",
        "serializer_version",
        "oracle_author",
        "oracle_source_path",
        "oracle_source_sha256",
        "review_status",
        "reviewer_records",
        "mandatory_case_matrix",
    } <= set(schema["required"])
    assert schema["properties"]["oracle_imports_production_serializer"] == {"const": False}
    assert schema["properties"]["adr_id"] == {"const": "ADR-0019"}
    assert schema["properties"]["serializer_version"] == {"const": "w2.canonical-json.v2"}
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
        SEMANTIC_CONTRACTS,
        handoff_contract_failures,
    )

    cases = [
        {
            "case_id": f"{category}-{index}",
            "category": category,
            "request": copy.deepcopy(variant["request"]),
            "oracle": copy.deepcopy(variant["expected"]),
        }
        for category, contract in SEMANTIC_CONTRACTS.items()
        for index, variant in enumerate(contract["variants"])
    ]
    payload = {
        "production_implementer": "production-implementer",
        "oracle_author": "oracle-author",
        "reviewer_records": [{"reviewer": "independent-reviewer"}],
        "cases": cases,
    }
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["mandatory_case_matrix"]["const"] == list(MANDATORY_CASE_COUNTS)
    assert handoff_contract_failures(payload) == []

    payload["cases"] = cases[:-1] + [cases[0]]
    failures = handoff_contract_failures(payload)
    assert "case_id values must be unique" in failures
    assert any("invalid_pair_hash_rejected" in failure for failure in failures)


def test_oracle_handoff_rejects_category_labels_with_wrong_semantics() -> None:
    from scripts.verify_canonical_serialization_oracle import (
        SEMANTIC_CONTRACTS,
        handoff_contract_failures,
    )

    cases = [
        {
            "case_id": f"{category}-{index}",
            "category": category,
            "request": copy.deepcopy(variant["request"]),
            "oracle": copy.deepcopy(variant["expected"]),
        }
        for category, contract in SEMANTIC_CONTRACTS.items()
        for index, variant in enumerate(contract["variants"])
    ]
    cases[0]["request"] = copy.deepcopy(cases[1]["request"])
    failures = handoff_contract_failures(
        {
            "production_implementer": "production-implementer",
            "oracle_author": "oracle-author",
            "reviewer_records": [{"reviewer": "independent-reviewer"}],
            "cases": cases,
        }
    )
    assert any("request/outcome does not match" in failure for failure in failures)
    assert any("unicode_nfc_key_order[0]" in failure for failure in failures)


def test_legacy_semantic_matrix_freezes_prefix_and_default_hooks() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    contracts = schema["x-semantic-contracts"]

    passthrough = contracts["legacy_v1_reserved_prefix_passthrough"]["variants"]
    assert passthrough[0]["request"]["value"]["entries"] == [
        {
            "key": "$w2_type",
            "value": {"kind": "string", "value": "legacy-caller-value"},
        }
    ]
    assert passthrough[0]["expected"] == {"status": "success"}

    read_model = contracts["legacy_v1_read_model"]["variants"]
    assert [item["value"]["kind"] for item in read_model[0]["request"]["value"]["entries"]] == [
        "string",
        "decimal",
        "date",
        "datetime",
    ]
    read_model_values = {
        item["key"]: item["value"].get("value")
        for item in read_model[0]["request"]["value"]["entries"]
    }
    assert read_model_values == {
        "team": "上海",
        "price": "1.2300",
        "date": "2026-08-01",
        "updated_at": "2026-08-01T12:34:56+08:00",
    }
    assert read_model[1]["request"]["value"]["kind"] == "naive_datetime"
    assert read_model[1]["expected"] == {
        "status": "error",
        "error_code": "NAIVE_DATETIME",
    }

    stage7i = contracts["legacy_v1_stage7i_supervision"]["variants"]
    assert stage7i[1]["request"]["value"] == {
        "kind": "datetime",
        "value": "2026-08-01T12:34:56+08:00",
    }
    assert schema["properties"]["cases"]["minItems"] == 30


def test_naive_datetime_schema_node_reaches_production_rejection() -> None:
    from scripts.verify_canonical_serialization_oracle import SEMANTIC_CONTRACTS, _decode

    from w2.domain.canonical_serialization import (
        CanonicalErrorCode,
        CanonicalSerializationError,
        HashDomain,
        canonical_bytes,
    )

    node = SEMANTIC_CONTRACTS["naive_datetime_rejected"]["variants"][0]["request"]["value"]
    value = _decode(node)
    assert isinstance(value, datetime)
    assert value.tzinfo is None
    with pytest.raises(CanonicalSerializationError) as exc_info:
        canonical_bytes(value, domain=HashDomain.EVAL_02B_PAIR_IDENTITY)
    assert exc_info.value.code is CanonicalErrorCode.NAIVE_DATETIME


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_oracle_identity_binds_git_head_fingerprints_authors_and_imports(
    tmp_path: Path,
) -> None:
    from scripts.verify_canonical_serialization_oracle import identity_contract_failures

    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Production Implementer")
    _git(tmp_path, "config", "user.email", "implementer@example.test")
    production = tmp_path / "src/w2/domain/canonical_serialization.py"
    production.parent.mkdir(parents=True)
    production.write_text("VERSION = 'v2'\n", encoding="utf-8")
    _git(tmp_path, "add", production.relative_to(tmp_path).as_posix())
    _git(tmp_path, "commit", "-m", "production implementation")
    production_head = _git(tmp_path, "rev-parse", "HEAD")

    _git(tmp_path, "config", "user.name", "Independent Oracle")
    _git(tmp_path, "config", "user.email", "oracle@example.test")
    oracle = tmp_path / "oracle/independent.py"
    oracle.parent.mkdir()
    oracle.write_text("import json\n", encoding="utf-8")
    _git(tmp_path, "add", oracle.relative_to(tmp_path).as_posix())
    _git(tmp_path, "commit", "-m", "independent oracle")

    payload = {
        "production_implementation_head": production_head,
        "production_implementation_path": production.relative_to(tmp_path).as_posix(),
        "production_implementation_sha256": hashlib.sha256(production.read_bytes()).hexdigest(),
        "production_implementer": "implementer@example.test",
        "oracle_author": "oracle@example.test",
        "oracle_source_path": oracle.relative_to(tmp_path).as_posix(),
        "oracle_source_sha256": hashlib.sha256(oracle.read_bytes()).hexdigest(),
    }
    assert identity_contract_failures(payload, root=tmp_path) == []

    oracle.write_text(
        "from w2.domain.canonical_serialization import canonical_bytes\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", oracle.relative_to(tmp_path).as_posix())
    _git(tmp_path, "commit", "-m", "forbidden production import")
    payload["oracle_source_sha256"] = hashlib.sha256(oracle.read_bytes()).hexdigest()
    assert "oracle source imports production code" in identity_contract_failures(
        payload, root=tmp_path
    )


def test_implementer_tranche_contains_no_oracle_vectors() -> None:
    assert not list((ROOT / "tests").rglob("*golden*canonical*"))
    assert not list((ROOT / "tests").rglob("*oracle*vectors*.json"))
