#!/usr/bin/env python3
"""Fail-closed GitHub gates for the W2 architecture-convergence checklist."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
PR_KIND_FIELD_RE = re.compile(r"(?m)^W2_PR_KIND:\s*(IMPLEMENTATION|CLOSURE)\s*$")
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
MATRIX_SCHEMA_VERSION = "w2.architecture_acceptance_matrix.v1"
MATRIX_SCHEMA_PATH = "contracts/governance/architecture_acceptance_matrix.v1.schema.json"
MATRIX_DIR = Path("docs/operations/architecture_convergence/acceptance_matrices")
REQUIRED_MATRIX_CASES = {
    "valid",
    "missing",
    "malformed",
    "stale",
    "ambiguous",
    "conflict",
}
REQUIRED_MATRIX_CLAIMS = {
    "DEAD_CODE",
    "ZERO_REACHABILITY",
    "SINGLE_AUTHORITY",
    "ZERO_LEGACY_READ_WRITE",
    "SAFE_DELETION",
}
REQUIRED_EVIDENCE_LAYERS = {
    "static_ast",
    "runtime_sql_trace",
    "mutation_tests",
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
    return not path.is_absolute() and ".." not in path.parts and (root / path).is_file()


def validate_acceptance_matrix(
    payload: dict[str, Any],
    *,
    root: Path,
    expected_task: str | None = None,
) -> list[str]:
    """Validate one frozen, production-shaped architecture acceptance matrix."""
    errors: list[str] = []

    def fail(code: str) -> None:
        if code not in errors:
            errors.append(code)

    task_id = payload.get("task_id")
    if payload.get("schema_version") != MATRIX_SCHEMA_VERSION:
        fail("MATRIX_SCHEMA_VERSION_INVALID")
    if payload.get("schema_path") != MATRIX_SCHEMA_PATH:
        fail("MATRIX_SCHEMA_PATH_INVALID")
    elif not _repo_file(root, payload["schema_path"]):
        fail("MATRIX_SCHEMA_FILE_MISSING")
    if payload.get("task_status") not in VALID_STATUSES:
        fail("MATRIX_TASK_STATUS_INVALID")
    if not isinstance(task_id, str) or not re.fullmatch(r"ARCH-[A-Z0-9-]+", task_id):
        fail("MATRIX_TASK_ID_INVALID")
    elif expected_task is not None and task_id != expected_task:
        fail(f"MATRIX_TASK_MISMATCH:{task_id}:{expected_task}")
    if not isinstance(payload.get("frozen_exact_head"), str) or not SHA_RE.fullmatch(
        payload["frozen_exact_head"]
    ):
        fail("MATRIX_FROZEN_HEAD_INVALID")

    scope = payload.get("frozen_scope")
    if not isinstance(scope, dict):
        fail("MATRIX_SCOPE_INVALID")
    else:
        expected_scope_hash = scope.get("sha256")
        scope_body = {key: value for key, value in scope.items() if key != "sha256"}
        if expected_scope_hash != _canonical_sha256(scope_body):
            fail("MATRIX_SCOPE_HASH_MISMATCH")
        for key in ("summary", "allowed", "forbidden"):
            if not scope.get(key):
                fail(f"MATRIX_SCOPE_{key.upper()}_MISSING")

    inventory = payload.get("inventory")
    if not isinstance(inventory, dict):
        fail("MATRIX_INVENTORY_INVALID")
    else:
        for group in (
            "entry_points",
            "producers",
            "consumers",
            "storage",
            "scripts",
            "config_paths",
        ):
            rows = inventory.get(group)
            if not isinstance(rows, list) or not rows:
                fail(f"MATRIX_INVENTORY_{group.upper()}_MISSING")
                continue
            for row in rows:
                path = row.get("path") if isinstance(row, dict) else None
                if not _repo_file(root, path):
                    fail(f"MATRIX_INVENTORY_PATH_INVALID:{group}")
                frozen_sha = row.get("frozen_source_sha256") if isinstance(row, dict) else None
                if frozen_sha is not None and (
                    not isinstance(frozen_sha, str) or not SHA256_RE.fullmatch(frozen_sha)
                ):
                    fail(f"MATRIX_INVENTORY_SHA_INVALID:{group}")

    shapes = payload.get("input_shapes")
    if not isinstance(shapes, list) or not shapes:
        fail("MATRIX_INPUT_SHAPES_MISSING")
    else:
        for shape in shapes:
            if not isinstance(shape, dict):
                fail("MATRIX_INPUT_SHAPE_INVALID")
                continue
            if shape.get("origin") not in {
                "REAL_PRODUCER_OUTPUT",
                "REAL_DB",
                "TRACKED_REAL_ARTIFACT",
            }:
                fail("MATRIX_INPUT_ORIGIN_INVALID")
            source_path = shape.get("source_path")
            if not _repo_file(root, source_path):
                fail("MATRIX_INPUT_SOURCE_PATH_INVALID")
            source_sha = shape.get("source_sha256")
            if not isinstance(source_sha, str) or not SHA256_RE.fullmatch(source_sha):
                fail(f"MATRIX_INPUT_SOURCE_HASH_INVALID:{shape.get('id', 'UNKNOWN')}")
            if shape.get("shape_sha256") != _canonical_sha256(shape.get("shape")):
                fail(f"MATRIX_INPUT_SHAPE_HASH_MISMATCH:{shape.get('id', 'UNKNOWN')}")

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
            fail("MATRIX_CASE_INVALID")
            continue
        if not case.get("expected_output") or case.get("fail_closed") is not True:
            fail(f"MATRIX_CASE_EXPECTATION_INVALID:{case.get('type', 'UNKNOWN')}")
        if not case.get("forbidden_behaviors"):
            fail(f"MATRIX_CASE_FORBIDDEN_BEHAVIOR_MISSING:{case.get('type', 'UNKNOWN')}")

    alias_rules = payload.get("alias_rules")
    if not isinstance(alias_rules, list) or not alias_rules:
        fail("MATRIX_ALIAS_RULES_MISSING")
    elif any(
        not isinstance(rule, dict)
        or not rule.get("field")
        or not isinstance(rule.get("exact_mapping"), dict)
        for rule in alias_rules
    ):
        fail("MATRIX_ALIAS_RULE_INVALID")

    layers = payload.get("evidence_layers")
    if not isinstance(layers, dict) or set(layers) != REQUIRED_EVIDENCE_LAYERS:
        fail("MATRIX_EVIDENCE_LAYER_SET_INVALID")
        layers = {}
    for name, layer in layers.items():
        if not isinstance(layer, dict) or not layer.get("references"):
            fail(f"MATRIX_EVIDENCE_LAYER_INVALID:{name}")

    claims = payload.get("claims")
    claim_names = (
        {
            claim.get("name")
            for claim in claims
            if isinstance(claim, dict) and isinstance(claim.get("name"), str)
        }
        if isinstance(claims, list)
        else set()
    )
    if claim_names != REQUIRED_MATRIX_CLAIMS:
        fail("MATRIX_CLAIM_SET_INVALID")
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            fail("MATRIX_CLAIM_INVALID")
            continue
        status = claim.get("status")
        if status not in {"PASS", "UNVERIFIABLE", "BLOCKED"}:
            fail(f"MATRIX_CLAIM_STATUS_INVALID:{claim.get('name', 'UNKNOWN')}")
        if status == "PASS":
            proof = claim.get("proof")
            if not isinstance(proof, dict) or set(proof) != REQUIRED_EVIDENCE_LAYERS:
                fail(f"MATRIX_CLAIM_PROOF_INCOMPLETE:{claim.get('name', 'UNKNOWN')}")
            elif any(
                not isinstance(item, dict)
                or item.get("status") != "PASS"
                or item.get("measurement_source") in {None, "", "STATIC_CONSTANT"}
                for item in proof.values()
            ):
                fail(f"MATRIX_CLAIM_PROOF_INVALID:{claim.get('name', 'UNKNOWN')}")

    primary = payload.get("primary_contract_tests")
    if not isinstance(primary, list) or not primary:
        fail("MATRIX_PRIMARY_CONTRACT_TEST_MISSING")
    else:
        for test in primary:
            if (
                not isinstance(test, dict)
                or test.get("input_origin") != "REAL_PRODUCER_OUTPUT"
                or not test.get("producer")
                or not test.get("consumer")
                or test.get("fixture_role") == "PRIMARY_HANDWRITTEN_APPROXIMATION"
            ):
                fail("MATRIX_PRIMARY_CONTRACT_TEST_INVALID")
            path = test.get("path") if isinstance(test, dict) else None
            if not _repo_file(root, path):
                fail("MATRIX_PRIMARY_CONTRACT_TEST_PATH_INVALID")

    external = payload.get("external_evidence")
    if not isinstance(external, dict) or external.get("status") not in {
        "VERIFIED",
        "UNVERIFIABLE",
        "BLOCKED",
    }:
        fail("MATRIX_EXTERNAL_EVIDENCE_INVALID")
    elif (
        external.get("status") in {"UNVERIFIABLE", "BLOCKED"}
        and payload.get("task_status") == "DONE"
    ):
        fail("MATRIX_DONE_WITHOUT_EXTERNAL_EVIDENCE")

    review = payload.get("review_policy")
    if not isinstance(review, dict) or (
        review.get("frozen_before_implementation") is not True
        or review.get("exact_head_change_requires_refreeze") is not True
        or review.get("old_head_first_miss_label") != "REVIEW_MISS"
        or review.get("post_implementation_review")
        != "FROZEN_ASSERTIONS_AND_NEW_DIFF_REGRESSIONS_ONLY"
    ):
        fail("MATRIX_REVIEW_POLICY_INVALID")

    matrix_hash = payload.get("matrix_sha256")
    matrix_body = {key: value for key, value in payload.items() if key != "matrix_sha256"}
    if matrix_hash != _canonical_sha256(matrix_body):
        fail("MATRIX_HASH_MISMATCH")
    return errors


def validate_task_acceptance_matrix(task_id: str, *, root: Path) -> list[str]:
    path = root / MATRIX_DIR / f"{task_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"ACCEPTANCE_MATRIX_MISSING_OR_INVALID:{task_id}"]
    if not isinstance(payload, dict):
        return [f"ACCEPTANCE_MATRIX_MISSING_OR_INVALID:{task_id}"]
    return validate_acceptance_matrix(payload, root=root, expected_task=task_id)


def task_acceptance_gate(task_id: str, pr_kind: str, *, root: Path) -> list[str]:
    errors = validate_task_acceptance_matrix(task_id, root=root)
    if errors:
        return errors
    payload = json.loads((root / MATRIX_DIR / f"{task_id}.json").read_text(encoding="utf-8"))
    if pr_kind == "IMPLEMENTATION" and payload.get("implementation_gate") != "OPEN":
        errors.append(f"MATRIX_IMPLEMENTATION_GATE_BLOCKED:{task_id}")
    if pr_kind == "CLOSURE" and payload.get("external_evidence", {}).get("status") != "VERIFIED":
        errors.append(f"MATRIX_CLOSURE_EVIDENCE_BLOCKED:{task_id}")
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
    if matrix_root is not None and _task_requires_matrix(tasks, task_id):
        for error in task_acceptance_gate(task_id, pr_kind, root=matrix_root):
            result.fail(error)
    if task_id != "ARCH-GOVERNANCE-01" and base_checklist is not None:
        base_tasks, base_errors = parse_tasks(base_checklist)
        for error in base_errors:
            result.fail(f"BASE_{error}")
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
        filenames = {item["filename"] for item in files}
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
        for path in sorted(matrix_dir.glob("*.json")):
            for error in validate_task_acceptance_matrix(path.stem, root=matrix_root):
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
    parser.add_argument("gate", choices=("pre-merge", "post-merge"))
    parser.add_argument("--checklist", type=Path, default=Path(CHECKLIST_PATH))
    parser.add_argument("--event-path", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--checklist-ref")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    try:
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
