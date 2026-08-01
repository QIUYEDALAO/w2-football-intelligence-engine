from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
from datetime import date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.domain.canonical_serialization import (  # noqa: E402
    CanonicalSerializationError,
    HashDomain,
    SerializerVersion,
    canonical_bytes,
    canonical_sha256,
    eval_02b_bootstrap_seed,
)

SCHEMA = ROOT / "docs/contracts/w2_canonical_serialization_oracle_vectors_v2.schema.json"
MANDATORY_CASE_COUNTS = {
    "unicode_nfc": 1,
    "unicode_key_collision": 1,
    "large_decimal_context_independent": 1,
    "float64_min_subnormal": 1,
    "float64_max_finite": 1,
    "float64_adjacent": 2,
    "float64_power_of_ten_boundary": 1,
    "float64_point_one": 1,
    "float64_negative_zero": 1,
    "float64_nan_rejected": 1,
    "float64_infinity_rejected": 2,
    "bytes": 1,
    "aware_datetime": 1,
    "naive_datetime_rejected": 1,
    "unsupported_type_rejected": 1,
    "reserved_tag_rejected": 1,
    "legacy_v1_compatibility": 1,
    "pair_identity": 1,
    "bootstrap_order_independent": 1,
    "invalid_pair_hash_rejected": 1,
}


def _decode(node: dict[str, Any]) -> object:
    kind = node["kind"]
    if kind == "null":
        return None
    if kind in {"boolean", "integer", "string"}:
        return node["value"]
    if kind == "float64":
        return struct.unpack(">d", bytes.fromhex(node["binary64_hex"]))[0]
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


def handoff_contract_failures(payload: dict[str, Any]) -> list[str]:
    cases = payload.get("cases", [])
    case_ids = [case.get("case_id") for case in cases]
    failures = ["case_id values must be unique"] if len(case_ids) != len(set(case_ids)) else []
    categories = [case.get("category") for case in cases]
    for category, minimum in MANDATORY_CASE_COUNTS.items():
        if categories.count(category) < minimum:
            failures.append(f"mandatory case category missing: {category} (minimum {minimum})")
    author = payload.get("oracle_author")
    if any(record.get("reviewer") == author for record in payload.get("reviewer_records", [])):
        failures.append("oracle author cannot be an independent reviewer")
    return failures


def verify_vectors(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        payload
    )
    failures = handoff_contract_failures(payload)
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
                if case["category"] == "bootstrap_order_independent":
                    reversed_seed = eval_02b_bootstrap_seed(
                        list(reversed(request["validation_pair_identity_hashes"])),
                        contract_version=request["contract_version"],
                    )
                    if reversed_seed != seed:
                        failures.append(f"{case['case_id']}: bootstrap order changed seed")
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
            if case["category"] == "large_decimal_context_independent":
                context_outputs: list[bytes] = []
                for precision in (5, 28, 50):
                    with localcontext() as context:
                        context.prec = precision
                        context_outputs.append(
                            canonical_bytes(value, domain=domain, version=version)
                        )
                if any(output != encoded for output in context_outputs):
                    failures.append(f"{case['case_id']}: decimal context changed output")
            if expected["status"] != "success":
                failures.append(f"{case['case_id']}: expected error but production succeeded")
            elif encoded.hex() != expected["canonical_utf8_hex"] or digest != expected["sha256"]:
                failures.append(f"{case['case_id']}: oracle mismatch")
        except Exception as exc:  # noqa: BLE001 - harness compares declared error outcomes.
            actual_code = (
                exc.code.value
                if isinstance(exc, CanonicalSerializationError)
                else "UNSTABLE_HARNESS_ERROR"
            )
            if expected["status"] != "error" or expected["error_code"] != actual_code:
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
