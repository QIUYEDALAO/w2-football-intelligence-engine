"""Generate golden vectors from the independent oracle only.

Expected bytes, hashes and seeds come exclusively from
``oracle.canonical_serialization_oracle``. The production serializer is never
imported, executed or consulted while producing this file.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oracle.canonical_serialization_oracle import (  # noqa: E402
    OracleError,
    bootstrap_seed,
    canonical_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/contracts/w2_canonical_serialization_oracle_vectors_v2.schema.json"
ORACLE_SOURCE = "oracle/canonical_serialization_oracle.py"
PRODUCTION_PATH = "src/w2/domain/canonical_serialization.py"
PRODUCTION_HEAD = "ff0db4f874b263434290d502b7b787adfcde2964"


def decode(node: dict[str, Any]) -> object:
    kind = node["kind"]
    if kind == "null":
        return None
    if kind == "boolean":
        return node["value"]
    if kind == "integer":
        return int(node["value"])
    if kind == "float64":
        return struct.unpack(">d", bytes.fromhex(node["binary64_hex"]))[0]
    if kind == "decimal":
        return Decimal(node["value"])
    if kind == "string":
        return node["value"]
    if kind == "bytes":
        raw = node["value"]
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if kind == "date":
        return date.fromisoformat(node["value"])
    if kind in {"datetime", "naive_datetime"}:
        return datetime.fromisoformat(node["value"])
    if kind == "array":
        return [decode(item) for item in node["items"]]
    if kind == "object":
        mapping: dict[str, object] = {}
        for entry in node["entries"]:
            mapping[entry["key"]] = decode(entry["value"])
        return mapping
    if kind == "unsupported":
        return set()
    raise ValueError(f"unknown node kind: {kind}")


def run(request: dict[str, Any]) -> dict[str, Any]:
    try:
        if request["operation"] == "eval_02b_bootstrap_seed":
            seed = bootstrap_seed(
                request["contract_version"],
                list(request["validation_pair_identity_hashes"]),
            )
            return {
                "status": "success",
                "seed_payload_utf8_hex": seed.payload.hex(),
                "seed_hash": seed.seed_hash,
                "bootstrap_seed": seed.seed,
            }
        raw = canonical_bytes(
            decode(request["value"]),
            version=request["serializer_version"],
            domain=request["domain"],
        )
        return {
            "status": "success",
            "canonical_utf8_hex": raw.hex(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    except OracleError as exc:
        return {"status": "error", "error_code": exc.code}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256_of(relative: str, *, ref: str | None = None) -> str:
    if ref is None:
        return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    blob = subprocess.check_output(["git", "show", f"{ref}:{relative}"], cwd=ROOT)
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    contracts = schema["x-semantic-contracts"]
    matrix = schema["properties"]["mandatory_case_matrix"]["const"]

    cases: list[dict[str, Any]] = []
    mismatched_expectations: list[str] = []
    for category in matrix:
        for index, variant in enumerate(contracts[category]["variants"]):
            request = variant["request"]
            result = run(request)
            declared = variant["expected"]
            if declared["status"] != result["status"] or (
                declared["status"] == "error"
                and declared.get("error_code") != result.get("error_code")
            ):
                mismatched_expectations.append(f"{category}[{index}]: {result}")
            cases.append(
                {
                    "case_id": f"{category}.{index}".replace("_", "-"),
                    "category": category,
                    "request": request,
                    "oracle": result,
                }
            )

    payload = {
        "schema_version": "w2.canonical-serialization-oracle-vectors.v2",
        "production_implementation_head": PRODUCTION_HEAD,
        "production_implementation_path": PRODUCTION_PATH,
        "production_implementation_sha256": sha256_of(PRODUCTION_PATH, ref=PRODUCTION_HEAD),
        "production_implementer": git("show", "-s", "--format=%ae", PRODUCTION_HEAD),
        "adr_id": "ADR-0019",
        "serializer_version": "w2.canonical-json.v2",
        "oracle_author": git("log", "-1", "--format=%ae", "--", ORACLE_SOURCE),
        "oracle_source_path": ORACLE_SOURCE,
        "oracle_source_sha256": sha256_of(ORACLE_SOURCE),
        "oracle_imports_production_serializer": False,
        "review_status": "PENDING",
        "reviewer_records": [
            {
                "reviewer": "ChatGPT GPT-5.6 Pro",
                "status": "PENDING",
                "recorded_at": datetime.now().astimezone().isoformat(),
            }
        ],
        "mandatory_case_matrix": matrix,
        "cases": cases,
    }

    out = ROOT / "oracle/w2_canonical_serialization_oracle_vectors_v2.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"cases={len(cases)} categories={len(matrix)}")
    if mismatched_expectations:
        print("SCHEMA_EXPECTATION_MISMATCH:")
        for item in mismatched_expectations:
            print(f"  {item}")
        return 1
    print("oracle outcomes match every declared schema expectation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
