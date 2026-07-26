#!/usr/bin/env python3
"""Fail-closed GitHub gates for the W2 architecture-convergence checklist."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from scripts.classify_ci import (
        CI_JOB_NAMES,
        CiPlan,
        ci_required_passes,
        required_ci_plan,
    )
except ModuleNotFoundError:  # direct `python scripts/check_...py` execution
    from classify_ci import (  # type: ignore[no-redef]
        CI_JOB_NAMES,
        CiPlan,
        ci_required_passes,
        required_ci_plan,
    )

PROTOCOL_ID = "GITHUB_SECONDARY_REVIEW_PROTOCOL_V1"
ACCEPTANCE_MARKER = "W2_EXTERNAL_ACCEPTANCE_V1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_MARKER_RE = re.compile(r"(?m)^W2_TASK_ID:\s*([A-Z0-9-]+)\s*$")
PR_KIND_FIELD_RE = re.compile(r"(?m)^W2_PR_KIND:\s*(PREFLIGHT|IMPLEMENTATION|CLOSURE)\s*$")
TASK_HEADING_RE = re.compile(r"(?m)^####\s+[A-Z]\d+\.\s+([A-Z][A-Z0-9-]+)")
STATUS_RE = re.compile(r"(?m)^Status:\s*([A-Z_]+)\s*$")
FIELD_RE = re.compile(r"(?m)^([A-Z_]+):\s*(\S.*?)\s*$")

CHECKLIST_PATH = (
    "docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
A1_ALLOWED_PATHS = {
    ".github/workflows/architecture-governance.yml",
    "PROJECT_STATE.yaml",
    CHECKLIST_PATH,
    "scripts/check_architecture_governance.py",
    "tests/contract/test_script_authority_inventory.py",
    "tests/unit/test_architecture_governance.py",
}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
CI_JOB_CHECK_NAMES = {
    "governance": "governance-light",
    "python_focused": "python-focused",
    "web": "web",
    "migration": "migration-schema",
    "compose": "compose",
    "staging_parity": "staging-parity",
    "predeploy_e2e": "predeploy-e2e",
    "verify": "verify",
}
VALID_STATUSES = {
    "NOT_STARTED",
    "IN_PROGRESS",
    "IMPLEMENTED_PENDING_ACCEPTANCE",
    "BLOCKED",
    "DONE",
}
MATRIX_SCHEMA_VERSION = "w2.architecture_acceptance_lifecycle.v1"
MATRIX_SCHEMA_PATH = "contracts/governance/architecture_acceptance_lifecycle.v1.schema.json"
MATRIX_DIR = Path("docs/operations/architecture_convergence/acceptance_matrices")
REQUIRED_MATRIX_CASES = {
    "valid",
    "missing",
    "malformed",
    "stale",
    "ambiguous",
    "conflict",
}
REQUIRED_EVIDENCE_LAYERS = {
    "STATIC_AST",
    "RUNTIME_SQL_TRACE",
    "MUTATION_TESTS",
}
REAL_INPUT_EVIDENCE_TYPES = {
    "REAL_DB",
    "REAL_PRODUCER_OUTPUT",
    "CONTENT_ADDRESSED_SANITIZED_ARTIFACT",
}
EVIDENCE_ARTIFACT_KINDS = {
    "REAL_DB": "REAL_DB_EVIDENCE",
    "REAL_PRODUCER_OUTPUT": "REAL_PRODUCER_OUTPUT_EVIDENCE",
    "CONTENT_ADDRESSED_SANITIZED_ARTIFACT": (
        "CONTENT_ADDRESSED_SANITIZED_ARTIFACT_EVIDENCE"
    ),
}
PREFLIGHT_ALLOWED_FILES = {
    "NEXT_ACTION.md",
    "PROJECT_STATE.yaml",
    CHECKLIST_PATH,
    "tests/unit/test_architecture_governance.py",
}
PREFLIGHT_ALLOWED_PREFIXES = (
    f"{MATRIX_DIR.as_posix()}/",
    "docs/operations/architecture_convergence/evidence/",
)
CLOSURE_ALLOWED_FILES = {
    "NEXT_ACTION.md",
    "PROJECT_STATE.yaml",
    CHECKLIST_PATH,
}
# These rows existed in the approved v3 ledger before ARCH-GOVERNANCE-01.
HISTORICAL_DONE_PRS = {
    371,
    374,
    375,
    376,
    377,
    378,
    379,
    380,
    381,
    382,
    383,
    384,
    385,
    387,
}


class GovernanceError(RuntimeError):
    """Raised when GitHub or checklist evidence cannot be trusted."""


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    status: str
    body: str


@dataclass(frozen=True)
class DoneEntry:
    task_id: str
    pr_number: int | None
    merge_sha: str | None


@dataclass
class GateResult:
    errors: list[str] = field(default_factory=list)
    details: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def fail(self, code: str) -> None:
        if code not in self.errors:
            self.errors.append(code)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _repo_file(root: Path, value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    root_resolved = root.resolve()
    candidate = root / path
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return False
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            return False
    return resolved.is_file()


def _safe_repo_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        return None
    return value


def _git_blob(root: Path, commit: str, path: str) -> bytes | None:
    safe_path = _safe_repo_path(path)
    if not SHA_RE.fullmatch(commit) or safe_path is None:
        return None
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        tree = subprocess.run(
            ["git", "ls-tree", "-z", commit, "--", safe_path],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        records = [record for record in tree.split(b"\0") if record]
        if len(records) != 1:
            return None
        metadata, listed_path = records[0].split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        if (
            listed_path.decode("utf-8") != safe_path
            or mode == "120000"
            or object_type != "blob"
        ):
            return None
        return subprocess.run(
            ["git", "cat-file", "-p", object_id],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    except (subprocess.CalledProcessError, UnicodeDecodeError, ValueError):
        return None


def _schema_errors(payload: dict[str, Any], *, root: Path) -> list[str]:
    try:
        schema = json.loads((root / MATRIX_SCHEMA_PATH).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        issues = sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(payload),
            key=str,
        )
    except (OSError, json.JSONDecodeError) as exc:
        return [f"MATRIX_SCHEMA_EXECUTION_ERROR:{type(exc).__name__}"]
    return [f"MATRIX_JSON_SCHEMA_INVALID:{issue.json_path}" for issue in issues]


def _artifact_hash(payload: dict[str, Any], field: str) -> str:
    return _canonical_sha256({key: value for key, value in payload.items() if key != field})


def _symbol_exists(source: bytes, symbol: str) -> bool:
    try:
        nodes: list[ast.stmt] = ast.parse(source.decode("utf-8")).body
    except (SyntaxError, UnicodeDecodeError):
        return False
    parts = symbol.split(".")
    if not parts or any(not part.isidentifier() for part in parts):
        return False
    for index, part in enumerate(parts):
        match = next(
            (
                node
                for node in nodes
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == part
            ),
            None,
        )
        if match is None:
            return False
        if index < len(parts) - 1:
            if not isinstance(match, ast.ClassDef):
                return False
            nodes = match.body
    return True


def validate_acceptance_spec(
    payload: dict[str, Any],
    *,
    root: Path,
    expected_task: str | None = None,
    blob_reader: Callable[[str, str], bytes | None] | None = None,
) -> list[str]:
    """Validate an immutable spec against its frozen baseline commit."""
    errors = _schema_errors(payload, root=root)

    def fail(code: str) -> None:
        if code not in errors:
            errors.append(code)

    task_id = payload.get("task_id")
    if expected_task is not None and task_id != expected_task:
        fail(f"MATRIX_TASK_MISMATCH:{task_id}:{expected_task}")
    baseline = payload.get("frozen_baseline_commit")
    read_blob = blob_reader or (lambda commit, path: _git_blob(root, commit, path))
    if not isinstance(baseline, str) or not SHA_RE.fullmatch(baseline):
        fail("MATRIX_FROZEN_BASELINE_INVALID")
        baseline = ""
    elif read_blob(baseline, CHECKLIST_PATH) is None:
        fail("MATRIX_FROZEN_BASELINE_MISSING")
    if payload.get("spec_sha256") != _artifact_hash(payload, "spec_sha256"):
        fail("MATRIX_SPEC_HASH_MISMATCH")
    scope = payload.get("scope")
    if isinstance(scope, dict) and scope.get("sha256") != _artifact_hash(scope, "sha256"):
        fail("MATRIX_SCOPE_HASH_MISMATCH")

    inventory = payload.get("inventory")
    if isinstance(inventory, dict):
        for group, rows in inventory.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                path = row.get("path")
                blob = read_blob(baseline, path) if isinstance(path, str) else None
                if blob is None:
                    fail(f"MATRIX_INVENTORY_PATH_OR_BASELINE_INVALID:{group}")
                    continue
                if row.get("file_sha256") != hashlib.sha256(blob).hexdigest():
                    fail(f"MATRIX_INVENTORY_HASH_MISMATCH:{group}:{path}")
                symbol = row.get("symbol")
                if isinstance(symbol, str) and not _symbol_exists(blob, symbol):
                    fail(f"MATRIX_INVENTORY_SYMBOL_MISSING:{group}:{symbol}")

    inputs = payload.get("input_contracts")
    input_ids: set[str] = set()
    for shape in inputs if isinstance(inputs, list) else []:
        if not isinstance(shape, dict):
            continue
        shape_id = shape.get("id")
        if isinstance(shape_id, str):
            input_ids.add(shape_id)
        if shape.get("shape_sha256") != _canonical_sha256(shape.get("shape")):
            fail(f"MATRIX_INPUT_SHAPE_HASH_MISMATCH:{shape_id}")
    cases = payload.get("cases")
    case_types = (
        {
            case.get("type")
            for case in cases
            if isinstance(case, dict) and isinstance(case.get("type"), str)
        }
        if isinstance(cases, list)
        else set()
    )
    if case_types != REQUIRED_MATRIX_CASES:
        fail("MATRIX_CASE_SET_INVALID")
    for case in cases if isinstance(cases, list) else []:
        if not isinstance(case, dict):
            continue
        if case.get("source_input_id") not in input_ids:
            fail(f"MATRIX_CASE_INPUT_UNKNOWN:{case.get('type')}")

    primary = payload.get("primary_contract")
    if isinstance(primary, dict):
        path = primary.get("path")
        blob = read_blob(baseline, path) if isinstance(path, str) else None
        if blob is None:
            fail("MATRIX_PRIMARY_CONTRACT_PATH_INVALID")
        elif not _symbol_exists(blob, str(primary.get("test", ""))):
            fail("MATRIX_PRIMARY_CONTRACT_TEST_MISSING")
    return errors


def _evidence_items(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for result in receipt.get("input_results", []):
        items.extend(result.get("evidence", []))
    for layer in receipt.get("layer_results", {}).values():
        items.extend(layer.get("evidence", []))
    for result in receipt.get("case_results", []):
        items.extend(result.get("evidence", []))
    for result in receipt.get("claim_results", []):
        for evidence in result.get("layer_evidence", {}).values():
            items.extend(evidence)
    return [item for item in items if isinstance(item, dict)]


def validate_evidence_artifact(
    payload: dict[str, Any],
    *,
    root: Path,
    expected_type: str,
    expected_head: str,
    blob_reader: Callable[[str, str], bytes | None],
) -> list[str]:
    errors = _schema_errors(payload, root=root)

    def fail(code: str) -> None:
        if code not in errors:
            errors.append(code)

    if payload.get("artifact_kind") != EVIDENCE_ARTIFACT_KINDS.get(expected_type):
        fail("MATRIX_EVIDENCE_ARTIFACT_KIND_INVALID")
    if payload.get("exact_head") != expected_head:
        fail("MATRIX_EVIDENCE_ARTIFACT_HEAD_MISMATCH")
    if payload.get("artifact_sha256") != _artifact_hash(payload, "artifact_sha256"):
        fail("MATRIX_EVIDENCE_ARTIFACT_HASH_MISMATCH")
    generator = payload.get("generator", {})
    generator_path = generator.get("path")
    blob = (
        blob_reader(expected_head, generator_path)
        if isinstance(generator_path, str)
        else None
    )
    if blob is None:
        fail("MATRIX_EVIDENCE_GENERATOR_INVALID")
    else:
        if generator.get("file_sha256") != hashlib.sha256(blob).hexdigest():
            fail("MATRIX_EVIDENCE_GENERATOR_HASH_MISMATCH")
        if not _symbol_exists(blob, str(generator.get("symbol", ""))):
            fail("MATRIX_EVIDENCE_GENERATOR_SYMBOL_MISSING")
    replay = payload.get("replay", {})
    argv = replay.get("argv")
    if (
        not isinstance(argv, list)
        or replay.get("command_sha256") != _canonical_sha256(argv)
    ):
        fail("MATRIX_EVIDENCE_REPLAY_HASH_MISMATCH")
    query = replay.get("query")
    if query is not None and replay.get("query_sha256") != hashlib.sha256(
        str(query).encode("utf-8")
    ).hexdigest():
        fail("MATRIX_EVIDENCE_QUERY_HASH_MISMATCH")
    if expected_type == "REAL_DB" and (
        not isinstance(query, str) or payload.get("db_write_delta") != 0
    ):
        fail("MATRIX_REAL_DB_EVIDENCE_INVALID")
    return errors


def validate_acceptance_receipt(
    payload: dict[str, Any],
    *,
    spec: dict[str, Any],
    root: Path,
    expected_kind: str,
    blob_reader: Callable[[str, str], bytes | None] | None = None,
) -> list[str]:
    """Validate a content-addressed baseline or final receipt."""
    errors = _schema_errors(payload, root=root)

    def fail(code: str) -> None:
        if code not in errors:
            errors.append(code)

    if payload.get("artifact_kind") != expected_kind:
        fail("MATRIX_RECEIPT_KIND_INVALID")
    if payload.get("task_id") != spec.get("task_id"):
        fail("MATRIX_RECEIPT_TASK_MISMATCH")
    if payload.get("spec_sha256") != spec.get("spec_sha256"):
        fail("MATRIX_RECEIPT_SPEC_HASH_MISMATCH")
    if payload.get("receipt_sha256") != _artifact_hash(payload, "receipt_sha256"):
        fail("MATRIX_RECEIPT_HASH_MISMATCH")
    exact_head = payload.get("exact_head")
    read_blob = blob_reader or (lambda commit, path: _git_blob(root, commit, path))
    if not isinstance(exact_head, str) or not SHA_RE.fullmatch(exact_head):
        fail("MATRIX_RECEIPT_HEAD_INVALID")
    if (
        expected_kind == "BASELINE_RECEIPT"
        and exact_head != spec.get("frozen_baseline_commit")
    ):
        fail("MATRIX_BASELINE_HEAD_MISMATCH")
    if expected_kind == "FINAL_EXACT_HEAD_RECEIPT":
        if payload.get("ci_receipt", {}).get("exact_head") != exact_head:
            fail("MATRIX_FINAL_CI_HEAD_MISMATCH")
        if payload.get("external_acceptance", {}).get("accepted_head") != exact_head:
            fail("MATRIX_FINAL_ACCEPTANCE_HEAD_MISMATCH")

    for item in _evidence_items(payload):
        path = item.get("artifact_path")
        item_head = item.get("exact_head")
        blob = (
            read_blob(item_head, path)
            if isinstance(item_head, str) and isinstance(path, str)
            else None
        )
        if blob is None:
            fail(f"MATRIX_EVIDENCE_PATH_OR_HEAD_INVALID:{path}")
            continue
        if item.get("artifact_sha256") != hashlib.sha256(blob).hexdigest():
            fail(f"MATRIX_EVIDENCE_HASH_MISMATCH:{path}")
        if item_head != exact_head:
            fail(f"MATRIX_EVIDENCE_HEAD_MISMATCH:{path}")
        evidence_type = item.get("evidence_type")
        if path.endswith("models.py") and evidence_type != "DECLARED_ORM_SCHEMA":
            fail(f"MATRIX_ORM_EVIDENCE_TYPE_INVALID:{path}")
        if evidence_type in REAL_INPUT_EVIDENCE_TYPES and item.get("role") == "PRIMARY":
            if not path.startswith(
                "docs/operations/architecture_convergence/evidence/"
            ) or not path.endswith(".evidence.json"):
                fail(f"MATRIX_REAL_EVIDENCE_ARTIFACT_PATH_INVALID:{path}")
                continue
            try:
                artifact = json.loads(blob)
            except (json.JSONDecodeError, UnicodeDecodeError):
                fail(f"MATRIX_REAL_EVIDENCE_ARTIFACT_INVALID:{path}")
                continue
            if not isinstance(artifact, dict):
                fail(f"MATRIX_REAL_EVIDENCE_ARTIFACT_INVALID:{path}")
                continue
            for error in validate_evidence_artifact(
                artifact,
                root=root,
                expected_type=evidence_type,
                expected_head=exact_head,
                blob_reader=read_blob,
            ):
                fail(f"{error}:{path}")

    input_specs = {
        row["id"]: row
        for row in spec.get("input_contracts", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    input_results = {
        row["input_id"]: row
        for row in payload.get("input_results", [])
        if isinstance(row, dict) and isinstance(row.get("input_id"), str)
    }
    if set(input_results) != set(input_specs):
        fail("MATRIX_RECEIPT_INPUT_SET_INVALID")
    for input_id, result in input_results.items():
        if result.get("status") != "PASS":
            continue
        evidence_type = result.get("evidence_type")
        primary_types = {
            item.get("evidence_type")
            for item in result.get("evidence", [])
            if item.get("role") == "PRIMARY"
        }
        if (
            evidence_type not in input_specs[input_id].get("accepted_evidence_types", [])
            or evidence_type not in REAL_INPUT_EVIDENCE_TYPES
            or evidence_type not in primary_types
        ):
            fail(f"MATRIX_RECEIPT_INPUT_TYPE_INVALID:{input_id}")

    case_results = {
        row.get("type"): row
        for row in payload.get("case_results", [])
        if isinstance(row, dict)
    }
    case_types = set(case_results)
    if case_types != REQUIRED_MATRIX_CASES:
        fail("MATRIX_RECEIPT_CASE_SET_INVALID")
    spec_cases = {
        row.get("type"): row for row in spec.get("cases", []) if isinstance(row, dict)
    }
    for case_type, result in case_results.items():
        if result.get("status") != "PASS":
            continue
        expected_derivation = (
            "UNCHANGED_REAL_INPUT"
            if case_type == "valid"
            else "CONTROLLED_MUTATION_OF_SANITIZED_REAL_INPUT"
        )
        primary_types = {
            item.get("evidence_type")
            for item in result.get("evidence", [])
            if item.get("role") == "PRIMARY"
        }
        if (
            result.get("derivation") != expected_derivation
            or spec_cases.get(case_type, {}).get("derivation") != expected_derivation
        ):
            fail(f"MATRIX_CASE_DERIVATION_INVALID:{case_type}")
        if case_type == "valid":
            source_input_id = spec_cases.get(case_type, {}).get("source_input_id")
            allowed_real_types = set(
                input_specs.get(source_input_id, {}).get("accepted_evidence_types", [])
            ).intersection(REAL_INPUT_EVIDENCE_TYPES)
            if not primary_types.intersection(allowed_real_types):
                fail("MATRIX_VALID_CASE_REAL_EVIDENCE_MISSING")
        elif (
            "MUTATION_TEST" not in primary_types
            or not primary_types.intersection(REAL_INPUT_EVIDENCE_TYPES)
        ):
            fail(f"MATRIX_MUTATION_CASE_EVIDENCE_MISSING:{case_type}")
    claim_specs = {
        row["name"]: row
        for row in spec.get("claims", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    claim_results = {
        row["name"]: row
        for row in payload.get("claim_results", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    if set(claim_results) != set(claim_specs):
        fail("MATRIX_RECEIPT_CLAIM_SET_INVALID")
    for name, result in claim_results.items():
        applicable = claim_specs[name].get("applicability") == "APPLICABLE"
        if applicable == (result.get("status") == "NOT_APPLICABLE"):
            fail(f"MATRIX_CLAIM_APPLICABILITY_MISMATCH:{name}")
        if result.get("status") == "PASS":
            proof = result.get("layer_evidence", {})
            if set(proof) != REQUIRED_EVIDENCE_LAYERS or any(not proof[layer] for layer in proof):
                fail(f"MATRIX_CLAIM_THREE_LAYER_PROOF_MISSING:{name}")
            else:
                allowed_types = {
                    "STATIC_AST": {"STATIC_AST_SCAN"},
                    "RUNTIME_SQL_TRACE": {"RUNTIME_SQL_TRACE", "REAL_DB"},
                    "MUTATION_TESTS": {"MUTATION_TEST"},
                }
                if any(
                    any(
                        item.get("evidence_type") not in allowed_types[layer]
                        for item in proof[layer]
                    )
                    for layer in REQUIRED_EVIDENCE_LAYERS
                ):
                    fail(f"MATRIX_CLAIM_THREE_LAYER_PROOF_INVALID:{name}")

    layers = payload.get("layer_results", {})
    layer_types = {
        "STATIC_AST": {"STATIC_AST_SCAN"},
        "RUNTIME_SQL_TRACE": {"RUNTIME_SQL_TRACE", "REAL_DB"},
        "MUTATION_TESTS": {"MUTATION_TEST"},
    }
    for layer, result in layers.items():
        if result.get("status") == "PASS" and any(
            item.get("evidence_type") not in layer_types[layer]
            for item in result.get("evidence", [])
        ):
            fail(f"MATRIX_LAYER_EVIDENCE_TYPE_INVALID:{layer}")
    return errors


def _receipt_passes(spec: dict[str, Any], receipt: dict[str, Any]) -> bool:
    if receipt.get("overall_status") != "PASS":
        return False
    inputs = {row.get("id"): row for row in spec.get("input_contracts", [])}
    if any(
        result.get("status") != "PASS"
        or result.get("evidence_type")
        not in inputs.get(result.get("input_id"), {}).get("accepted_evidence_types", [])
        or not result.get("evidence")
        for result in receipt.get("input_results", [])
    ):
        return False
    if receipt.get("artifact_kind") == "FINAL_EXACT_HEAD_RECEIPT":
        exact_head = receipt.get("exact_head")
        if (
            receipt.get("ci_receipt", {}).get("exact_head") != exact_head
            or receipt.get("ci_receipt", {}).get("plan") != "FULL"
            or receipt.get("ci_receipt", {}).get("conclusion") != "success"
            or receipt.get("external_acceptance", {}).get("accepted_head") != exact_head
            or receipt.get("external_acceptance", {}).get("decision") != "PASS"
        ):
            return False
    if any(
        layer.get("status") != "PASS" or not layer.get("evidence")
        for layer in receipt.get("layer_results", {}).values()
    ):
        return False
    if any(
        result.get("status") != "PASS" or not result.get("evidence")
        for result in receipt.get("case_results", [])
    ):
        return False
    claims = {row.get("name"): row for row in spec.get("claims", [])}
    for result in receipt.get("claim_results", []):
        applicable = claims.get(result.get("name"), {}).get("applicability") == "APPLICABLE"
        if applicable and result.get("status") != "PASS":
            return False
        if not applicable and result.get("status") != "NOT_APPLICABLE":
            return False
    return True


def _load_artifact(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def validate_task_acceptance_lifecycle(task_id: str, *, root: Path) -> list[str]:
    spec = _load_artifact(root / MATRIX_DIR / f"{task_id}.spec.json")
    baseline = _load_artifact(root / MATRIX_DIR / f"{task_id}.baseline.json")
    if spec is None or baseline is None:
        return [f"ACCEPTANCE_MATRIX_LIFECYCLE_MISSING:{task_id}"]
    errors = validate_acceptance_spec(spec, root=root, expected_task=task_id)
    errors.extend(
        error
        for error in validate_acceptance_receipt(
            baseline, spec=spec, root=root, expected_kind="BASELINE_RECEIPT"
        )
        if error not in errors
    )
    final_path = root / MATRIX_DIR / f"{task_id}.final.json"
    if final_path.exists():
        final = _load_artifact(final_path)
        if final is None:
            errors.append(f"ACCEPTANCE_FINAL_RECEIPT_INVALID:{task_id}")
        else:
            errors.extend(
                error
                for error in validate_acceptance_receipt(
                    final, spec=spec, root=root, expected_kind="FINAL_EXACT_HEAD_RECEIPT"
                )
                if error not in errors
            )
    return errors


def validate_acceptance_lifecycle_payloads(
    task_id: str,
    *,
    spec: dict[str, Any],
    baseline: dict[str, Any],
    final: dict[str, Any] | None,
    root: Path,
    blob_reader: Callable[[str, str], bytes | None],
) -> list[str]:
    errors = validate_acceptance_spec(
        spec,
        root=root,
        expected_task=task_id,
        blob_reader=blob_reader,
    )
    errors.extend(
        error
        for error in validate_acceptance_receipt(
            baseline,
            spec=spec,
            root=root,
            expected_kind="BASELINE_RECEIPT",
            blob_reader=blob_reader,
        )
        if error not in errors
    )
    if final is not None:
        errors.extend(
            error
            for error in validate_acceptance_receipt(
                final,
                spec=spec,
                root=root,
                expected_kind="FINAL_EXACT_HEAD_RECEIPT",
                blob_reader=blob_reader,
            )
            if error not in errors
        )
    return errors


def task_acceptance_gate(
    task_id: str, pr_kind: str, *, root: Path, exact_head: str | None = None
) -> list[str]:
    errors = validate_task_acceptance_lifecycle(task_id, root=root)
    if errors:
        return errors
    spec = _load_artifact(root / MATRIX_DIR / f"{task_id}.spec.json") or {}
    baseline = _load_artifact(root / MATRIX_DIR / f"{task_id}.baseline.json") or {}
    final = _load_artifact(root / MATRIX_DIR / f"{task_id}.final.json")
    if pr_kind == "IMPLEMENTATION" and (
        not _receipt_passes(spec, baseline)
        or final is None
        or not _receipt_passes(spec, final)
        or exact_head is None
        or final.get("exact_head") != exact_head
    ):
        errors.append(f"MATRIX_IMPLEMENTATION_GATE_BLOCKED:{task_id}")
    if pr_kind == "CLOSURE":
        if (
            final is None
            or not _receipt_passes(spec, final)
        ):
            errors.append(f"MATRIX_FINAL_RECEIPT_BLOCKED:{task_id}")
    return errors


def task_acceptance_payload_gate(
    task_id: str,
    pr_kind: str,
    *,
    spec: dict[str, Any],
    baseline: dict[str, Any],
    final: dict[str, Any] | None,
    root: Path,
    exact_head: str,
    blob_reader: Callable[[str, str], bytes | None],
) -> list[str]:
    errors = validate_acceptance_lifecycle_payloads(
        task_id,
        spec=spec,
        baseline=baseline,
        final=final,
        root=root,
        blob_reader=blob_reader,
    )
    if errors:
        return errors
    if pr_kind == "IMPLEMENTATION" and (
        not _receipt_passes(spec, baseline)
        or final is None
        or not _receipt_passes(spec, final)
        or final.get("exact_head") != exact_head
    ):
        errors.append(f"MATRIX_IMPLEMENTATION_GATE_BLOCKED:{task_id}")
    if pr_kind == "CLOSURE" and (
        final is None
        or not _receipt_passes(spec, final)
    ):
        errors.append(f"MATRIX_FINAL_RECEIPT_BLOCKED:{task_id}")
    return errors


def _task_requires_matrix(tasks: list[TaskRecord], task_id: str) -> bool:
    order = [task.task_id for task in tasks]
    try:
        return order.index(task_id) > order.index("ARCH-GOVERNANCE-03")
    except ValueError:
        return False


class GitHubClient:
    """Small read-only GitHub REST client with fail-closed pagination."""

    def __init__(
        self,
        repository: str,
        credential: str,
        timeout: float = 15.0,
    ) -> None:
        if not repository or "/" not in repository:
            raise GovernanceError("GITHUB_REPOSITORY_INVALID")
        if not credential:
            raise GovernanceError("GITHUB_TOKEN_MISSING")  # token = required credential
        self.repository = repository
        self.credential = credential
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS GitHub API origin
            f"https://api.github.com/{path.lstrip('/')}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.credential}",  # authorization headers
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "w2-architecture-governance",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                if response.status != 200:
                    raise GovernanceError(f"GITHUB_API_STATUS:{response.status}")
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GovernanceError(f"GITHUB_API_ERROR:{type(exc).__name__}") from exc

    def _list(self, path: str) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for page in range(1, 101):
            separator = "&" if "?" in path else "?"
            payload = self._get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(payload, list):
                raise GovernanceError("GITHUB_API_LIST_INVALID")
            if not all(isinstance(item, dict) for item in payload):
                raise GovernanceError("GITHUB_API_LIST_ITEM_INVALID")
            collected.extend(payload)
            if len(payload) < 100:
                return collected
        raise GovernanceError("GITHUB_API_PAGINATION_LIMIT")

    def _object_list(self, path: str, key: str) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for page in range(1, 101):
            separator = "&" if "?" in path else "?"
            payload = self._get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
                raise GovernanceError("GITHUB_API_LIST_INVALID")
            items = payload[key]
            if not all(isinstance(item, dict) for item in items):
                raise GovernanceError("GITHUB_API_LIST_ITEM_INVALID")
            collected.extend(items)
            if len(items) < 100:
                return collected
        raise GovernanceError("GITHUB_API_PAGINATION_LIMIT")

    def get_pull(self, number: int) -> dict[str, Any]:
        payload = self._get(f"/repos/{self.repository}/pulls/{number}")
        if not isinstance(payload, dict):
            raise GovernanceError("GITHUB_PULL_INVALID")
        return payload

    def list_pull_files(self, number: int) -> list[dict[str, Any]]:
        return self._list(f"/repos/{self.repository}/pulls/{number}/files")

    def list_reviews(self, number: int) -> list[dict[str, Any]]:
        return self._list(f"/repos/{self.repository}/pulls/{number}/reviews")

    def list_ci_runs(self, exact_head: str) -> list[dict[str, Any]]:
        if not SHA_RE.fullmatch(exact_head):
            raise GovernanceError("CI_HEAD_INVALID")
        return self._object_list(
            f"/repos/{self.repository}/actions/workflows/ci.yml/runs?head_sha={exact_head}",
            "workflow_runs",
        )

    def list_run_jobs(self, run_id: int) -> list[dict[str, Any]]:
        if run_id <= 0:
            raise GovernanceError("CI_RUN_ID_INVALID")
        return self._object_list(
            f"/repos/{self.repository}/actions/runs/{run_id}/jobs",
            "jobs",
        )

    def get_text_file(self, path: str, ref: str) -> str:
        if not SHA_RE.fullmatch(ref):
            raise GovernanceError("CHECKLIST_REF_INVALID")
        pure = Path(path)
        if not path or pure.is_absolute() or ".." in pure.parts:
            raise GovernanceError("REPOSITORY_PATH_INVALID")
        encoded_path = urllib.parse.quote(path, safe="/")
        payload = self._get(f"/repos/{self.repository}/contents/{encoded_path}?ref={ref}")
        try:
            if payload["encoding"] != "base64":
                raise GovernanceError("CHECKLIST_CONTENT_ENCODING_INVALID")
            encoded = re.sub(r"\s+", "", payload["content"])
            content = base64.b64decode(encoded, validate=True)
            return content.decode("utf-8")
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            raise GovernanceError("CHECKLIST_CONTENT_INVALID") from exc

    def get_json_file(self, path: str, ref: str) -> dict[str, Any]:
        try:
            payload = json.loads(self.get_text_file(path, ref))
        except json.JSONDecodeError as exc:
            raise GovernanceError("REPOSITORY_JSON_INVALID") from exc
        if not isinstance(payload, dict):
            raise GovernanceError("REPOSITORY_JSON_INVALID")
        return payload


def parse_tasks(checklist: str) -> tuple[list[TaskRecord], list[str]]:
    matches = list(TASK_HEADING_RE.finditer(checklist))
    tasks: list[TaskRecord] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(checklist)
        body = checklist[match.start() : end]
        task_id = match.group(1)
        statuses = STATUS_RE.findall(body)
        if task_id in seen:
            errors.append(f"DUPLICATE_TASK:{task_id}")
            continue
        seen.add(task_id)
        if len(statuses) != 1:
            errors.append(f"TASK_STATUS_COUNT:{task_id}:{len(statuses)}")
            continue
        status = statuses[0]
        if status not in VALID_STATUSES:
            errors.append(f"TASK_STATUS_INVALID:{task_id}:{status}")
        tasks.append(TaskRecord(task_id=task_id, status=status, body=body))
    if not tasks:
        errors.append("CHECKLIST_TASKS_MISSING")
    return tasks, errors


def validate_task_sequence(tasks: list[TaskRecord]) -> list[str]:
    errors: list[str] = []
    current_seen = False
    for task in tasks:
        if not current_seen and task.status == "DONE":
            continue
        if not current_seen:
            current_seen = True
            continue
        if task.status != "NOT_STARTED":
            errors.append(f"FUTURE_TASK_STARTED:{task.task_id}:{task.status}")
    return errors


def current_task(tasks: list[TaskRecord]) -> TaskRecord | None:
    return next((task for task in tasks if task.status != "DONE"), None)


def task_field(task: TaskRecord, name: str) -> list[str]:
    pattern = re.compile(rf"(?mi)^{re.escape(name)}:\s*(.+?)\s*$")
    return pattern.findall(task.body)


def parse_done_entries(checklist: str) -> tuple[list[DoneEntry], list[str]]:
    section_match = re.search(r"(?ms)^## 二、.*?(?=^## 三、)", checklist)
    if section_match is None:
        return [], ["DONE_LEDGER_SECTION_MISSING"]
    entries: list[DoneEntry] = []
    errors: list[str] = []
    for line in section_match.group(0).splitlines():
        if not line.startswith("|") or "---" in line or "任务" in line:
            continue
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            errors.append("DONE_LEDGER_ROW_INVALID")
            continue
        task_match = re.match(r"([A-Z0-9-]+)", cells[0])
        pr_match = re.fullmatch(r"#(\d+)", cells[1])
        sha_match = re.fullmatch(r"([0-9a-fA-F]{1,40})", cells[2])
        task_id = task_match.group(1) if task_match else cells[0]
        entries.append(
            DoneEntry(
                task_id=task_id,
                pr_number=int(pr_match.group(1)) if pr_match else None,
                merge_sha=sha_match.group(1).lower() if sha_match else None,
            )
        )
    if not entries:
        errors.append("DONE_LEDGER_EMPTY")
    return entries, errors


def validate_pr_questions(body: str) -> list[str]:
    errors: list[str] = []
    starts: list[tuple[int, int]] = []
    for number in range(1, 9):
        matches = list(re.finditer(rf"(?m)^{number}\.\s+\S", body))
        if len(matches) != 1:
            errors.append(f"PR_QUESTION_{number}_COUNT:{len(matches)}")
        elif matches:
            starts.append((number, matches[0].start()))
    starts.sort(key=lambda item: item[1])
    for index, (number, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(body)
        answer_lines = [
            line.strip().lstrip("-").strip() for line in body[start:end].splitlines()[1:]
        ]
        if not any(answer_lines):
            errors.append(f"PR_QUESTION_{number}_ANSWER_MISSING")
    return errors


def _pull_fields(pull: dict[str, Any]) -> tuple[int, str, str, str, bool]:
    try:
        number = int(pull["number"])
        body = pull["body"]
        head = pull["head"]["sha"]
        base = pull["base"]["ref"]
        draft = pull["draft"]
    except (KeyError, TypeError, ValueError) as exc:
        raise GovernanceError("PULL_FIELDS_MISSING") from exc
    if not isinstance(body, str) or not SHA_RE.fullmatch(head):
        raise GovernanceError("PULL_FIELDS_INVALID")
    if not isinstance(base, str) or not isinstance(draft, bool):
        raise GovernanceError("PULL_FIELDS_INVALID")
    return number, body, head, base, draft


def _event_pull_number(event: dict[str, Any]) -> int:
    event_pull = event.get("pull_request")
    if isinstance(event_pull, dict):
        candidate = event_pull.get("number")
    else:
        issue = event.get("issue")
        candidate = issue.get("number") if isinstance(issue, dict) else None
        if not isinstance(issue, dict) or not isinstance(issue.get("pull_request"), dict):
            raise GovernanceError("EVENT_PULL_REQUEST_MISSING")
    try:
        return int(candidate)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("EVENT_PULL_REQUEST_MISSING") from exc


def _pull_file_paths(files: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for item in files:
        filename = item.get("filename")
        if not isinstance(filename, str):
            raise GovernanceError("PULL_FILE_FIELDS_MISSING")
        paths.append(filename)
        previous = item.get("previous_filename")
        if previous is not None:
            if not isinstance(previous, str):
                raise GovernanceError("PULL_FILE_FIELDS_MISSING")
            paths.append(previous)
    return sorted(set(paths))


def _matrix_artifact_type(path: str) -> str | None:
    for artifact_type in ("spec", "baseline", "final"):
        if path.startswith(f"{MATRIX_DIR.as_posix()}/") and path.endswith(
            f".{artifact_type}.json"
        ):
            return artifact_type
    return None


def validate_matrix_artifact_changes(
    files: list[dict[str, Any]],
    *,
    pr_kind: str,
    task_id: str,
    exact_head: str,
    trusted_base_head: str,
    client: Any,
) -> list[str]:
    errors: list[str] = []

    def fail(code: str) -> None:
        if code not in errors:
            errors.append(code)

    for item in files:
        filename = item.get("filename")
        previous = item.get("previous_filename")
        status = item.get("status")
        paths = [path for path in (filename, previous) if isinstance(path, str)]
        artifact_types = {
            artifact_type
            for path in paths
            if (artifact_type := _matrix_artifact_type(path)) is not None
        }
        if not artifact_types:
            continue
        if status in {"removed", "renamed"} or previous is not None:
            fail(f"MATRIX_ARTIFACT_RENAME_OR_DELETE_FORBIDDEN:{','.join(paths)}")
            continue
        if pr_kind == "IMPLEMENTATION" and artifact_types != {"final"}:
            fail(f"IMPLEMENTATION_MATRIX_ARTIFACT_FORBIDDEN:{','.join(paths)}")
        elif pr_kind == "CLOSURE":
            fail(f"CLOSURE_MATRIX_ARTIFACT_FORBIDDEN:{','.join(paths)}")
        elif pr_kind == "PREFLIGHT" and "final" in artifact_types:
            fail(f"PREFLIGHT_FINAL_ARTIFACT_FORBIDDEN:{','.join(paths)}")
        if pr_kind != "PREFLIGHT" or "spec" not in artifact_types:
            continue
        if not isinstance(filename, str):
            fail("PREFLIGHT_SPEC_PATH_INVALID")
            continue
        try:
            changed_spec = client.get_json_file(filename, exact_head)
        except GovernanceError:
            fail(f"PREFLIGHT_SPEC_INVALID:{filename}")
            continue
        change_control = changed_spec.get("change_control", {})
        change_kind = change_control.get("kind")
        try:
            trusted_spec = client.get_json_file(filename, trusted_base_head)
        except GovernanceError:
            trusted_spec = None
        if status == "added":
            if trusted_spec is not None or change_kind != "INITIAL_FREEZE":
                fail(f"PREFLIGHT_INITIAL_FREEZE_INVALID:{filename}")
        elif not isinstance(trusted_spec, dict):
            fail(f"PREFLIGHT_TRUSTED_SPEC_MISSING:{filename}")
        elif (
            change_kind not in {"REVIEW_MISS", "SCOPE_AMENDMENT"}
            or change_control.get("supersedes_spec_sha256")
            != _artifact_hash(trusted_spec, "spec_sha256")
        ):
            fail(f"PREFLIGHT_SPEC_SUPERSEDES_INVALID:{filename}")
    return errors


def _ci_receipt_matches(plan: CiPlan, jobs: list[dict[str, Any]]) -> bool:
    results: dict[str, str] = {}
    for internal_name, check_name in {
        "classify": "classify",
        **CI_JOB_CHECK_NAMES,
        "ci_required": "CI_REQUIRED",
    }.items():
        matches = [job for job in jobs if job.get("name") == check_name]
        if len(matches) != 1 or not isinstance(matches[0].get("conclusion"), str):
            return False
        results[internal_name] = matches[0]["conclusion"]
    expected = {job: getattr(plan, job) for job in CI_JOB_NAMES}
    return results["ci_required"] == "success" and ci_required_passes(expected, results)


def _find_ci_receipt(client: Any, exact_head: str, plan: CiPlan) -> int | None:
    for run in client.list_ci_runs(exact_head):
        if (
            run.get("head_sha") != exact_head
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("event") not in {"pull_request", "workflow_dispatch"}
        ):
            continue
        run_id = run.get("id")
        if isinstance(run_id, int) and _ci_receipt_matches(plan, client.list_run_jobs(run_id)):
            return run_id
    return None


def _full_ci_plan() -> CiPlan:
    return CiPlan(
        governance=True,
        python_focused=True,
        web=True,
        migration=True,
        compose=True,
        staging_parity=True,
        predeploy_e2e=True,
        verify=True,
        full=True,
    )


def validate_done_matrix_binding(
    task: TaskRecord,
    *,
    spec: dict[str, Any],
    final: dict[str, Any],
    client: Any,
) -> list[str]:
    errors: list[str] = []

    def fail(code: str) -> None:
        if code not in errors:
            errors.append(code)

    exact_head = final.get("exact_head")
    acceptance = final.get("external_acceptance", {})
    ci_receipt = final.get("ci_receipt", {})
    expected_fields = {
        "Accepted head": exact_head,
        "Full CI": str(ci_receipt.get("run_id", "")),
        "Final receipt SHA-256": final.get("receipt_sha256"),
        "Implementation PR": f"#{acceptance.get('implementation_pr_number')}",
    }
    for name, expected in expected_fields.items():
        if task_field(task, name) != [expected]:
            fail(f"MATRIX_DONE_FIELD_MISMATCH:{task.task_id}:{name}")
    try:
        implementation_number = int(acceptance["implementation_pr_number"])
        pull = client.get_pull(implementation_number)
    except (GovernanceError, KeyError, TypeError, ValueError):
        fail(f"MATRIX_IMPLEMENTATION_PR_INVALID:{task.task_id}")
        return errors
    merge_fields = task_field(task, "Merge SHA")
    if (
        pull.get("head", {}).get("sha") != exact_head
        or pull.get("merged_at") is None
        or len(merge_fields) != 1
        or pull.get("merge_commit_sha") != merge_fields[0]
    ):
        fail(f"MATRIX_IMPLEMENTATION_MERGE_BINDING_INVALID:{task.task_id}")
    full_run = _find_ci_receipt(client, str(exact_head), _full_ci_plan())
    if full_run != ci_receipt.get("run_id"):
        fail(f"MATRIX_FINAL_FULL_CI_INVALID:{task.task_id}")
    try:
        reviews = client.list_reviews(implementation_number)
    except GovernanceError:
        fail(f"MATRIX_FINAL_ACCEPTANCE_INVALID:{task.task_id}")
        return errors
    decision, review_errors = validate_external_acceptance(
        reviews, task.task_id, str(exact_head)
    )
    matching_hash = any(
        isinstance(review.get("body"), str)
        and hashlib.sha256(review["body"].encode("utf-8")).hexdigest()
        == acceptance.get("review_sha256")
        for review in reviews
    )
    if decision != "PASS" or review_errors or not matching_hash:
        fail(f"MATRIX_FINAL_ACCEPTANCE_INVALID:{task.task_id}")
    return errors


def _parse_acceptance_review(body: str) -> tuple[dict[str, str] | None, str | None]:
    if ACCEPTANCE_MARKER not in body:
        return None, None
    if body.count(ACCEPTANCE_MARKER) != 1:
        return None, "ACCEPTANCE_MARKER_COUNT"
    fields: dict[str, str] = {}
    for key, value in FIELD_RE.findall(body):
        if key in {"TASK", "EXACT_HEAD", "DECISION", "PROTOCOL"}:
            if key in fields:
                return None, f"ACCEPTANCE_FIELD_DUPLICATE:{key}"
            fields[key] = value.strip()
    required = {"TASK", "EXACT_HEAD", "DECISION", "PROTOCOL"}
    missing = sorted(required - fields.keys())
    if missing:
        return None, f"ACCEPTANCE_FIELDS_MISSING:{','.join(missing)}"
    if not SHA_RE.fullmatch(fields["EXACT_HEAD"]):
        return None, "ACCEPTANCE_SHA_NOT_FULL"
    if fields["DECISION"] not in {"PASS", "FAIL", "REMEDIATION_REQUIRED"}:
        return None, "ACCEPTANCE_DECISION_INVALID"
    if fields["PROTOCOL"] != PROTOCOL_ID:
        return None, "ACCEPTANCE_PROTOCOL_INVALID"
    return fields, None


def validate_external_acceptance(
    reviews: list[dict[str, Any]],
    task_id: str,
    exact_head: str,
) -> tuple[str, list[str]]:
    errors: list[str] = []
    current_decisions: list[str] = []
    for review in reviews:
        state = str(review.get("state", "")).upper()
        if state not in {"COMMENTED", "APPROVED"}:
            continue
        body = review.get("body")
        if not isinstance(body, str):
            continue
        fields, parse_error = _parse_acceptance_review(body)
        if parse_error:
            errors.append(parse_error)
            continue
        if fields is None:
            continue
        if fields["TASK"] != task_id:
            errors.append("ACCEPTANCE_TASK_MISMATCH")
            continue
        review_commit = review.get("commit_id")
        if not isinstance(review_commit, str) or not SHA_RE.fullmatch(review_commit):
            errors.append("ACCEPTANCE_REVIEW_COMMIT_INVALID")
            continue
        if fields["EXACT_HEAD"] != exact_head:
            # A well-formed review for an older exact head is intentionally stale.
            continue
        if review_commit != exact_head:
            errors.append("ACCEPTANCE_REVIEW_COMMIT_MISMATCH")
            continue
        association = str(review.get("author_association", "")).upper()
        if association not in TRUSTED_ASSOCIATIONS:
            errors.append("ACCEPTANCE_REVIEWER_UNTRUSTED")
            continue
        current_decisions.append(fields["DECISION"])
    decisions = set(current_decisions)
    if len(decisions) > 1:
        errors.append("ACCEPTANCE_DECISION_CONFLICT")
        return "CONFLICT", errors
    if decisions & {"FAIL", "REMEDIATION_REQUIRED"}:
        errors.append("ACCEPTANCE_NEGATIVE_DECISION")
        return "INVALID", errors
    if "PASS" in decisions and not errors:
        return "PASS", []
    if errors:
        return "INVALID", errors
    return "MISSING", ["EXTERNAL_ACCEPTANCE_MISSING"]


def check_pre_merge(
    event: dict[str, Any],
    checklist: str,
    client: Any,
    base_checklist: str | None = None,
    matrix_root: Path | None = None,
) -> GateResult:
    result = GateResult()
    try:
        event_number = _event_pull_number(event)
        pull = client.get_pull(event_number)
        number, body, exact_head, base, draft = _pull_fields(pull)
        if number != event_number:
            raise GovernanceError("PULL_NUMBER_MISMATCH")
    except (GovernanceError, KeyError, TypeError, ValueError) as exc:
        result.fail(str(exc))
        result.details["EXTERNAL_ACCEPTANCE"] = "INVALID"
        return result

    result.details["TASK_SCOPE"] = "PASS"
    if base != "main":
        result.fail("PULL_BASE_NOT_MAIN")
    if draft:
        result.fail("PULL_IS_DRAFT")

    task_markers = TASK_MARKER_RE.findall(body)
    if len(task_markers) != 1:
        result.fail(f"TASK_MARKER_COUNT:{len(task_markers)}")
        task_id = ""
    else:
        task_id = task_markers[0]
    pr_kinds = PR_KIND_FIELD_RE.findall(body)
    if len(pr_kinds) != 1:
        result.fail("PR_KIND_MARKER_INVALID")
        pr_kind = ""
    else:
        pr_kind = pr_kinds[0]
    for error in validate_pr_questions(body):
        result.fail(error)

    tasks, task_errors = parse_tasks(checklist)
    for error in task_errors + validate_task_sequence(tasks):
        result.fail(error)
    base_tasks: list[TaskRecord] = []
    if base_checklist is not None:
        base_tasks, base_errors = parse_tasks(base_checklist)
        for error in base_errors + validate_task_sequence(base_tasks):
            result.fail(f"BASE_{error}")
    trusted_tasks = base_tasks or tasks
    matrix_required = _task_requires_matrix(trusted_tasks, task_id)
    if (
        task_id != "ARCH-GOVERNANCE-03"
        and base_tasks
        and any(task.task_id == "ARCH-GOVERNANCE-03" for task in base_tasks)
        and [task.task_id for task in tasks] != [task.task_id for task in base_tasks]
    ):
        result.fail("TRUSTED_TASK_ORDER_CHANGED")
    spec: dict[str, Any] | None = None
    final_receipt: dict[str, Any] | None = None
    if matrix_root is not None and matrix_required:
        try:
            spec = client.get_json_file(
                f"{MATRIX_DIR.as_posix()}/{task_id}.spec.json", exact_head
            )
            baseline_receipt = client.get_json_file(
                f"{MATRIX_DIR.as_posix()}/{task_id}.baseline.json", exact_head
            )
            final_receipt = (
                client.get_json_file(
                    f"{MATRIX_DIR.as_posix()}/{task_id}.final.json", exact_head
                )
                if pr_kind in {"IMPLEMENTATION", "CLOSURE"}
                else None
            )

            def github_blob(commit: str, path: str) -> bytes | None:
                try:
                    return client.get_text_file(path, commit).encode("utf-8")
                except GovernanceError:
                    return None

            for error in task_acceptance_payload_gate(
                task_id,
                pr_kind,
                spec=spec,
                baseline=baseline_receipt,
                final=final_receipt,
                root=matrix_root,
                exact_head=exact_head,
                blob_reader=github_blob,
            ):
                result.fail(error)
        except GovernanceError as exc:
            result.fail(str(exc))
    if task_id != "ARCH-GOVERNANCE-01" and base_checklist is not None:
        base_a1 = next(
            (task for task in base_tasks if task.task_id == "ARCH-GOVERNANCE-01"),
            None,
        )
        if base_a1 is None or base_a1.status != "DONE":
            result.fail("A1_CLOSURE_NOT_COMPLETE_ON_BASE")
    allowed = current_task(tasks)
    if pr_kind == "CLOSURE":
        # A CLOSURE PR closes exactly the task that is the current
        # IMPLEMENTED_PENDING_ACCEPTANCE task on base, carrying its DONE status in
        # head. Validating base — not just the head status the author wrote —
        # prevents closing a future task out of order. The DONE-status check and
        # the post-merge ledger gate still enforce that closure is real.
        closure_task = next((task for task in tasks if task.task_id == task_id), None)
        if closure_task is None:
            result.fail(f"CLOSURE_TASK_MISSING:{task_id}")
        elif closure_task.status != "DONE":
            result.fail(f"CLOSURE_TASK_STATUS_INVALID:{closure_task.status}")
        if base_checklist is not None:
            base_tasks, _ = parse_tasks(base_checklist)
            base_current = current_task(base_tasks)
            if base_current is None or base_current.task_id != task_id:
                actual = base_current.task_id if base_current else "NONE"
                result.fail(f"CLOSURE_TASK_NOT_BASE_CURRENT:{task_id}:{actual}")
            elif base_current.status != "IMPLEMENTED_PENDING_ACCEPTANCE":
                result.fail(f"CLOSURE_BASE_STATUS_INVALID:{task_id}:{base_current.status}")
        if matrix_required and closure_task is not None:
            if spec is None or final_receipt is None:
                result.fail(f"MATRIX_FINAL_RECEIPT_BLOCKED:{task_id}")
            else:
                for error in validate_done_matrix_binding(
                    closure_task,
                    spec=spec,
                    final=final_receipt,
                    client=client,
                ):
                    result.fail(error)
    elif pr_kind == "PREFLIGHT":
        preflight_task = next((task for task in tasks if task.task_id == task_id), None)
        if preflight_task is None:
            result.fail(f"PREFLIGHT_TASK_MISSING:{task_id}")
        elif preflight_task.status != "NOT_STARTED":
            result.fail(f"PREFLIGHT_TASK_STATUS_INVALID:{preflight_task.status}")
        if base_checklist is not None:
            base_current = current_task(base_tasks)
            actual = base_current.task_id if base_current else "NONE"
            if base_current is None or base_current.task_id != task_id:
                result.fail(f"PREFLIGHT_TASK_NOT_BASE_CURRENT:{task_id}:{actual}")
            elif base_current.status != "NOT_STARTED":
                result.fail(
                    f"PREFLIGHT_BASE_STATUS_INVALID:{task_id}:{base_current.status}"
                )
            if [task.task_id for task in tasks] != [
                task.task_id for task in base_tasks
            ]:
                result.fail("PREFLIGHT_TRUSTED_TASK_ORDER_CHANGED")
    elif allowed is None:
        result.fail("CURRENT_TASK_MISSING")
    elif allowed.task_id != task_id:
        result.fail(f"TASK_NOT_CURRENT:{task_id}:{allowed.task_id}")
    elif allowed.status != "IMPLEMENTED_PENDING_ACCEPTANCE":
        result.fail(f"CURRENT_TASK_STATUS_INVALID:{allowed.status}")
    else:
        implementation_values = task_field(allowed, "Implementation SHA")
        if len(implementation_values) != 1:
            result.fail(f"IMPLEMENTATION_SHA_COUNT:{len(implementation_values)}")
        elif implementation_values[0] not in {exact_head, "GITHUB_PR_EXACT_HEAD"}:
            result.fail("IMPLEMENTATION_SHA_NOT_EXACT_HEAD")

    try:
        files = client.list_pull_files(number)
        changed_paths = _pull_file_paths(files)
        filenames = set(changed_paths)
        trusted_base_head = pull.get("base", {}).get("sha")
        if not isinstance(trusted_base_head, str) or not SHA_RE.fullmatch(
            trusted_base_head
        ):
            raise GovernanceError("PULL_BASE_SHA_INVALID")
        if task_id != "ARCH-GOVERNANCE-03" or pr_kind != "IMPLEMENTATION":
            for error in validate_matrix_artifact_changes(
                files,
                pr_kind=pr_kind,
                task_id=task_id,
                exact_head=exact_head,
                trusted_base_head=trusted_base_head,
                client=client,
            ):
                result.fail(error)
        if pr_kind == "PREFLIGHT":
            unexpected = sorted(
                path
                for path in filenames
                if path not in PREFLIGHT_ALLOWED_FILES
                and not path.startswith(PREFLIGHT_ALLOWED_PREFIXES)
            )
            if unexpected:
                result.fail(f"PREFLIGHT_OUT_OF_SCOPE_FILES:{','.join(unexpected)}")
        if pr_kind == "CLOSURE":
            unexpected = sorted(filenames - CLOSURE_ALLOWED_FILES)
            if unexpected:
                result.fail(f"CLOSURE_OUT_OF_SCOPE_FILES:{','.join(unexpected)}")
        if task_id == "ARCH-GOVERNANCE-01":
            unexpected = sorted(filenames - A1_ALLOWED_PATHS)
            if unexpected:
                result.fail(f"A1_OUT_OF_SCOPE_FILES:{','.join(unexpected)}")
        plan = required_ci_plan(changed_paths, pr_kind)
        result.details["CI_REQUIRED_PLAN"] = (
            "FULL"
            if plan.full
            else "LIGHTWEIGHT"
            if not any(getattr(plan, job) for job in CI_JOB_NAMES if job != "governance")
            else "PATH_AWARE"
        )
        receipt = _find_ci_receipt(client, exact_head, plan)
        if receipt is None:
            result.details["CI_REQUIRED_RECEIPT"] = "MISSING"
            result.fail("CI_REQUIRED_RECEIPT_MISSING")
        else:
            result.details["CI_REQUIRED_RECEIPT"] = str(receipt)
            if matrix_required and pr_kind == "IMPLEMENTATION" and (
                final_receipt is None
                or final_receipt.get("ci_receipt", {}).get("run_id") != receipt
            ):
                result.fail("MATRIX_FINAL_CI_RECEIPT_MISMATCH")
    except GovernanceError as exc:
        result.fail(str(exc))

    try:
        reviews = client.list_reviews(number)
        acceptance, acceptance_errors = validate_external_acceptance(reviews, task_id, exact_head)
    except GovernanceError as exc:
        acceptance = "INVALID"
        acceptance_errors = [str(exc)]
    result.details["EXTERNAL_ACCEPTANCE"] = acceptance
    for error in acceptance_errors:
        result.fail(error)
    return result


def check_post_merge(
    checklist: str,
    client: Any,
    matrix_root: Path | None = None,
) -> GateResult:
    result = GateResult()
    tasks, task_errors = parse_tasks(checklist)
    for error in task_errors + validate_task_sequence(tasks):
        result.fail(error)
    if matrix_root is not None:
        matrix_dir = matrix_root / MATRIX_DIR
        for path in sorted(matrix_dir.glob("*.spec.json")):
            task_id = path.name.removesuffix(".spec.json")
            for error in validate_task_acceptance_lifecycle(task_id, root=matrix_root):
                result.fail(error)
    entries, ledger_errors = parse_done_entries(checklist)
    for error in ledger_errors:
        result.fail(error)

    task_counts: dict[str, int] = {}
    pr_counts: dict[int, int] = {}
    actual_shas: dict[int, str] = {}
    pulls_by_number: dict[int, dict[str, Any]] = {}

    def get_pull(number: int) -> dict[str, Any]:
        if number not in pulls_by_number:
            pulls_by_number[number] = client.get_pull(number)
        return pulls_by_number[number]

    for entry in entries:
        task_counts[entry.task_id] = task_counts.get(entry.task_id, 0) + 1
        if entry.pr_number is None:
            result.fail(f"DONE_PR_MISSING:{entry.task_id}")
            continue
        pr_counts[entry.pr_number] = pr_counts.get(entry.pr_number, 0) + 1
        if entry.merge_sha is None:
            result.fail(f"DONE_MERGE_SHA_MISSING:{entry.task_id}")
        try:
            pull = get_pull(entry.pr_number)
        except GovernanceError as exc:
            result.fail(str(exc))
            continue
        actual = pull.get("merge_commit_sha")
        if (
            pull.get("merged_at") is None
            or not isinstance(actual, str)
            or not SHA_RE.fullmatch(actual)
        ):
            result.fail(f"DONE_PR_NOT_MERGED:{entry.task_id}:#{entry.pr_number}")
            continue
        actual_shas[entry.pr_number] = actual
        if entry.merge_sha is None:
            continue
        if len(entry.merge_sha) < 7:
            result.fail(f"DONE_MERGE_SHA_TOO_SHORT:{entry.task_id}")
        if not actual.startswith(entry.merge_sha):
            result.fail(f"DONE_MERGE_SHA_MISMATCH:{entry.task_id}")
        if entry.pr_number not in HISTORICAL_DONE_PRS and len(entry.merge_sha) != 40:
            result.fail(f"NEW_DONE_MERGE_SHA_NOT_FULL:{entry.task_id}")

    for task_id, count in task_counts.items():
        if count != 1:
            result.fail(f"DUPLICATE_DONE_TASK:{task_id}")
    for pr_number, count in pr_counts.items():
        if count != 1:
            result.fail(f"DUPLICATE_DONE_PR:#{pr_number}")

    for entry in entries:
        if entry.merge_sha is None or len(entry.merge_sha) == 40:
            continue
        matches = sum(sha.startswith(entry.merge_sha) for sha in actual_shas.values())
        if matches != 1:
            result.fail(f"DONE_MERGE_SHA_PREFIX_NOT_UNIQUE:{entry.task_id}")

    ledger_by_task = {entry.task_id: entry for entry in entries}
    for task in tasks:
        if task.status == "DONE" and _task_requires_matrix(tasks, task.task_id):
            if matrix_root is None:
                result.fail(f"MATRIX_POST_ROOT_MISSING:{task.task_id}")
            else:
                spec = _load_artifact(
                    matrix_root / MATRIX_DIR / f"{task.task_id}.spec.json"
                )
                final = _load_artifact(
                    matrix_root / MATRIX_DIR / f"{task.task_id}.final.json"
                )
                if (
                    spec is None
                    or final is None
                    or not _receipt_passes(spec, final)
                ):
                    result.fail(f"MATRIX_DONE_FINAL_MISSING_OR_BLOCKED:{task.task_id}")
                else:
                    for error in validate_done_matrix_binding(
                        task,
                        spec=spec,
                        final=final,
                        client=client,
                    ):
                        result.fail(error)
        pr_fields = task_field(task, "PR")
        if len(pr_fields) > 1:
            result.fail(f"TASK_PR_COUNT:{task.task_id}:{len(pr_fields)}")
            continue
        task_pr: int | None = None
        if pr_fields:
            match = re.fullmatch(r"#(\d+)", pr_fields[0])
            if match is None:
                result.fail(f"TASK_PR_INVALID:{task.task_id}")
            else:
                task_pr = int(match.group(1))
        elif task.status == "DONE":
            result.fail(f"DONE_TASK_PR_MISSING:{task.task_id}")

        merge_fields = task_field(task, "Merge SHA")
        if task.status == "DONE":
            if task.task_id not in ledger_by_task:
                result.fail(f"DONE_TASK_LEDGER_MISSING:{task.task_id}")
        elif merge_fields:
            result.fail(f"NON_DONE_TASK_HAS_MERGE_SHA:{task.task_id}")
        if task_pr is None:
            continue
        try:
            pull = get_pull(task_pr)
        except GovernanceError as exc:
            result.fail(str(exc))
            continue
        actual = pull.get("merge_commit_sha")
        merged = (
            pull.get("merged_at") is not None
            and isinstance(actual, str)
            and SHA_RE.fullmatch(actual) is not None
        )
        if not merged:
            if task.status == "DONE":
                result.fail(f"DONE_TASK_PR_NOT_MERGED:{task.task_id}:#{task_pr}")
            continue
        if task.status != "DONE":
            result.fail(f"MERGED_TASK_NOT_CLOSED:{task.task_id}:#{task_pr}")
            continue
        entry = ledger_by_task.get(task.task_id)
        if entry is None:
            result.fail(f"MERGED_TASK_LEDGER_MISSING:{task.task_id}")
        elif entry.pr_number != task_pr:
            result.fail(f"MERGED_TASK_LEDGER_PR_MISMATCH:{task.task_id}")
        if len(merge_fields) != 1:
            result.fail(f"DONE_TASK_MERGE_SHA_COUNT:{task.task_id}:{len(merge_fields)}")
        elif not SHA_RE.fullmatch(merge_fields[0].lower()):
            result.fail(f"DONE_TASK_MERGE_SHA_NOT_FULL:{task.task_id}")
        elif merge_fields[0].lower() != actual:
            result.fail(f"DONE_TASK_MERGE_SHA_MISMATCH:{task.task_id}")
    return result


def check_evidence_artifacts(root: Path, *, replay: bool) -> GateResult:
    result = GateResult()
    evidence_root = root / "docs/operations/architecture_convergence/evidence"
    for path in sorted(evidence_root.rglob("*.evidence.json")):
        payload = _load_artifact(path)
        if payload is None:
            result.fail(f"MATRIX_EVIDENCE_ARTIFACT_INVALID:{path.relative_to(root)}")
            continue
        artifact_kind = payload.get("artifact_kind")
        expected_type = next(
            (
                evidence_type
                for evidence_type, kind in EVIDENCE_ARTIFACT_KINDS.items()
                if kind == artifact_kind
            ),
            "",
        )
        exact_head = str(payload.get("exact_head", ""))
        for error in validate_evidence_artifact(
            payload,
            root=root,
            expected_type=expected_type,
            expected_head=exact_head,
            blob_reader=lambda commit, value: _git_blob(root, commit, value),
        ):
            result.fail(f"{error}:{path.relative_to(root)}")
        if not replay:
            continue
        argv = payload.get("replay", {}).get("argv")
        generator_path = payload.get("generator", {}).get("path")
        if (
            not isinstance(argv, list)
            or argv[:3] != ["uv", "run", "python"]
            or not isinstance(generator_path, str)
            or argv[3:4] != [generator_path]
            or not generator_path.startswith("scripts/")
        ):
            result.fail(f"MATRIX_EVIDENCE_REPLAY_COMMAND_INVALID:{path.relative_to(root)}")
            continue
        try:
            subprocess.run(argv, cwd=root, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError):
            result.fail(f"MATRIX_EVIDENCE_REPLAY_FAILED:{path.relative_to(root)}")
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"EVENT_READ_ERROR:{type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise GovernanceError("EVENT_PAYLOAD_INVALID")
    return payload


def _emit(name: str, result: GateResult) -> int:
    for key, value in sorted(result.details.items()):
        print(f"{key} = {value}")
    for error in result.errors:
        print(f"ERROR = {error}")
    print(f"{name} = {'PASS' if result.passed else 'FAIL'}")
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "gate", choices=("pre-merge", "post-merge", "evidence-artifacts")
    )
    parser.add_argument("--checklist", type=Path, default=Path(CHECKLIST_PATH))
    parser.add_argument("--event-path", type=Path)
    parser.add_argument("--repository", default="")
    parser.add_argument("--checklist-ref")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.gate == "evidence-artifacts":
            return _emit(
                "MATRIX_EVIDENCE_ARTIFACT_GATE",
                check_evidence_artifacts(Path.cwd(), replay=True),
            )
        if not args.live:
            raise GovernanceError("LIVE_GITHUB_API_OPT_IN_REQUIRED")
        client = GitHubClient(
            args.repository,
            os.environ.get("GITHUB_TOKEN", ""),  # token = trusted base workflow only
        )
        base_checklist = args.checklist.read_text(encoding="utf-8")
        if args.gate == "pre-merge":
            if args.event_path is None:
                raise GovernanceError("EVENT_PATH_MISSING")
            event = _load_json(args.event_path)
            checklist_ref = args.checklist_ref
            if not checklist_ref:
                pull = client.get_pull(_event_pull_number(event))
                _, _, checklist_ref, _, _ = _pull_fields(pull)
            checklist = client.get_text_file(CHECKLIST_PATH, checklist_ref)
            result = check_pre_merge(
                event,
                checklist,
                client,
                base_checklist=base_checklist,
                matrix_root=Path.cwd(),
            )
            return _emit("PRE_MERGE_READINESS_GATE", result)
        checklist = (
            client.get_text_file(CHECKLIST_PATH, args.checklist_ref)
            if args.checklist_ref
            else base_checklist
        )
        result = check_post_merge(checklist, client, matrix_root=Path.cwd())
        return _emit("POST_MERGE_CHECKLIST_CONSISTENCY_GATE", result)
    except (OSError, GovernanceError) as exc:
        print(f"ERROR = {exc}")
        gate_name = (
            "PRE_MERGE_READINESS_GATE"
            if args.gate == "pre-merge"
            else "POST_MERGE_CHECKLIST_CONSISTENCY_GATE"
        )
        print(f"{gate_name} = FAIL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
