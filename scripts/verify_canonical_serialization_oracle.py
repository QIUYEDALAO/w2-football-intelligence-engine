from __future__ import annotations

import argparse
import base64
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import jsonschema

from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_bytes,
    canonical_sha256,
    eval_02b_bootstrap_seed,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/contracts/w2_canonical_serialization_oracle_vectors_v1.schema.json"


def _decode(node: dict[str, Any]) -> object:
    kind = node["kind"]
    if kind == "null":
        return None
    if kind in {"boolean", "integer", "string"}:
        return node["value"]
    if kind == "float":
        return float(node["value"])
    if kind == "decimal":
        return Decimal(node["value"])
    if kind == "bytes":
        raw = str(node["value"])
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if kind == "date":
        return date.fromisoformat(node["value"])
    if kind == "datetime":
        return datetime.fromisoformat(str(node["value"]).replace("Z", "+00:00"))
    if kind == "array":
        return [_decode(item) for item in node["items"]]
    if kind == "object":
        return {item["key"]: _decode(item["value"]) for item in node["entries"]}
    if kind == "unsupported" and node["type"] == "set":
        return set()
    raise ValueError(f"unsupported oracle input kind: {kind}")


def verify_vectors(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        payload
    )
    failures: list[str] = []
    for case in payload["cases"]:
        request = case["request"]
        expected = case["oracle"]
        try:
            domain = HashDomain(request["domain"])
            version = SerializerVersion(request["serializer_version"])
            if request["operation"] == "eval_02b_bootstrap_seed":
                seed_payload = {
                    "contract_version": request["contract_version"],
                    "validation_pair_identity_hashes": sorted(
                        request["validation_pair_identity_hashes"]
                    ),
                }
                encoded = canonical_bytes(seed_payload, domain=domain, version=version)
                digest = canonical_sha256(seed_payload, domain=domain, version=version)
                seed = eval_02b_bootstrap_seed(
                    request["validation_pair_identity_hashes"],
                    contract_version=request["contract_version"],
                )
                if expected["status"] != "success":
                    failures.append(f"{case['case_id']}: expected error but production succeeded")
                elif (
                    encoded.hex() != expected["seed_payload_utf8_hex"]
                    or digest != expected["seed_hash"]
                    or seed != expected["bootstrap_seed"]
                ):
                    failures.append(f"{case['case_id']}: oracle mismatch")
                continue
            value = _decode(request["value"])
            encoded = canonical_bytes(value, domain=domain, version=version)
            digest = canonical_sha256(value, domain=domain, version=version)
            if expected["status"] != "success":
                failures.append(f"{case['case_id']}: expected error but production succeeded")
            elif encoded.hex() != expected["canonical_utf8_hex"] or digest != expected["sha256"]:
                failures.append(f"{case['case_id']}: oracle mismatch")
        except Exception as exc:  # noqa: BLE001 - harness compares declared error outcomes.
            if expected["status"] != "error" or expected["error_contains"] not in str(exc):
                failures.append(f"{case['case_id']}: unexpected error: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vectors", type=Path)
    args = parser.parse_args()
    failures = verify_vectors(args.vectors)
    for failure in failures:
        print(failure)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
