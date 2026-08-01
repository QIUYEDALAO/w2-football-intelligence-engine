from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import struct
import subprocess
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
SCHEMA_DOCUMENT: dict[str, Any] = json.loads(SCHEMA.read_text(encoding="utf-8"))
SEMANTIC_CONTRACTS: dict[str, dict[str, Any]] = SCHEMA_DOCUMENT["x-semantic-contracts"]
MANDATORY_CASE_COUNTS = {
    category: len(contract["variants"]) for category, contract in SEMANTIC_CONTRACTS.items()
}


def _decode(node: dict[str, Any]) -> object:
    kind = node["kind"]
    if kind == "null":
        return None
    if kind in {"boolean", "string"}:
        return node["value"]
    if kind == "integer":
        return int(node["value"])
    if kind == "float64":
        return struct.unpack(">d", bytes.fromhex(node["binary64_hex"]))[0]
    if kind == "decimal":
        return Decimal(node["value"])
    if kind == "bytes":
        raw = str(node["value"])
        return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if kind == "date":
        return date.fromisoformat(node["value"])
    if kind in {"datetime", "naive_datetime"}:
        return datetime.fromisoformat(str(node["value"]).replace("Z", "+00:00"))
    if kind == "array":
        return [_decode(item) for item in node["items"]]
    if kind == "object":
        return {item["key"]: _decode(item["value"]) for item in node["entries"]}
    if kind == "unsupported" and node["type"] == "set":
        return set()
    raise ValueError(f"unsupported oracle input kind: {kind}")


def _declared_outcome(oracle: dict[str, Any]) -> dict[str, str]:
    outcome = {"status": oracle.get("status", "")}
    if oracle.get("status") == "error":
        outcome["error_code"] = oracle.get("error_code", "")
    return outcome


def handoff_contract_failures(payload: dict[str, Any]) -> list[str]:
    cases = payload.get("cases", [])
    case_ids = [case.get("case_id") for case in cases]
    failures = ["case_id values must be unique"] if len(case_ids) != len(set(case_ids)) else []
    for category, contract in SEMANTIC_CONTRACTS.items():
        category_cases = [case for case in cases if case.get("category") == category]
        unmatched = list(range(len(contract["variants"])))
        for case in category_cases:
            actual = {
                "request": case.get("request"),
                "expected": _declared_outcome(case.get("oracle", {})),
            }
            match = next(
                (index for index in unmatched if actual == contract["variants"][index]),
                None,
            )
            if match is None:
                failures.append(
                    f"{case.get('case_id')}: request/outcome does not match "
                    f"mandatory semantic contract for {category}"
                )
            else:
                unmatched.remove(match)
        for index in unmatched:
            failures.append(f"mandatory semantic variant missing: {category}[{index}]")
    unknown = sorted({case.get("category") for case in cases} - set(SEMANTIC_CONTRACTS))
    failures.extend(f"unknown mandatory case category: {category}" for category in unknown)
    author = payload.get("oracle_author")
    if author == payload.get("production_implementer"):
        failures.append("production implementer and oracle author must differ")
    if any(record.get("reviewer") == author for record in payload.get("reviewer_records", [])):
        failures.append("oracle author cannot be an independent reviewer")
    return failures


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _imports_production_serializer(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "w2" or alias.name.startswith("w2.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "w2" or module.startswith("w2.") or node.level:
                return True
    return False


def identity_contract_failures(payload: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    try:
        head = payload["production_implementation_head"]
        production_path = payload["production_implementation_path"]
        _git(root, "cat-file", "-e", f"{head}^{{commit}}")
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", head, "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
        ).returncode:
            failures.append("production implementation head is not an ancestor of checkout HEAD")
        blob = subprocess.run(
            ["git", "show", f"{head}:{production_path}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        if _sha256(blob) != payload["production_implementation_sha256"]:
            failures.append("production implementation fingerprint does not match declared head")
        current = (root / production_path).read_bytes()
        if _sha256(current) != payload["production_implementation_sha256"]:
            failures.append("checkout production implementation differs from bound fingerprint")
        implementer = _git(root, "show", "-s", "--format=%ae", head)
        if implementer != payload["production_implementer"]:
            failures.append("production implementer does not match implementation commit author")

        oracle_path = (root / payload["oracle_source_path"]).resolve()
        oracle_path.relative_to(root.resolve())
        if oracle_path == (root / production_path).resolve():
            failures.append("oracle source must differ from production implementation")
        source = oracle_path.read_bytes()
        if _sha256(source) != payload["oracle_source_sha256"]:
            failures.append("oracle source fingerprint does not match checkout source")
        source_text = source.decode("utf-8")
        if _imports_production_serializer(source_text):
            failures.append("oracle source imports production code")
        oracle_commit_author = _git(
            root,
            "log",
            "-1",
            "--format=%ae",
            "--",
            payload["oracle_source_path"],
        )
        if oracle_commit_author != payload["oracle_author"]:
            failures.append("oracle author does not match oracle source commit author")
    except (
        KeyError,
        OSError,
        SyntaxError,
        subprocess.CalledProcessError,
        UnicodeError,
        ValueError,
    ) as exc:
        failures.append(f"oracle identity verification failed: {exc}")
    return failures


def verify_vectors(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(
        SCHEMA_DOCUMENT, format_checker=jsonschema.FormatChecker()
    ).validate(payload)
    failures = handoff_contract_failures(payload)
    failures.extend(identity_contract_failures(payload))
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
