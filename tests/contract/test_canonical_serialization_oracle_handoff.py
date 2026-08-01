from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/contracts/w2_canonical_serialization_oracle_vectors_v1.schema.json"
HARNESS = ROOT / "scripts/verify_canonical_serialization_oracle.py"


def test_oracle_input_schema_and_harness_are_ready() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    assert schema["properties"]["oracle_imports_production_serializer"] == {"const": False}
    assert {"success", "error"} == {
        item["properties"]["status"]["const"]
        for item in schema["$defs"]["case"]["properties"]["oracle"]["oneOf"]
    }
    result = subprocess.run(
        [sys.executable, str(HARNESS), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_implementer_tranche_contains_no_oracle_vectors() -> None:
    assert not list((ROOT / "tests").rglob("*golden*canonical*"))
    assert not list((ROOT / "tests").rglob("*oracle*vectors*.json"))
