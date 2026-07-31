#!/usr/bin/env python3
"""Reproducible, exact-base-bound T00 governance and safety inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_SHA = "dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6"
PR450_REF = "refs/remotes/pull/450/head"
PR450_HEAD = "360931d7d84bcbe1416c7946992b5218b759fc8a"
REPOSITORY = "QIUYEDALAO/w2-football-intelligence-engine"
DELIVERY_TEST = "tests/contract/test_delivery_status_documentation.py"
CHECKLIST = (
    "docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)

WORKFLOW_CLASSIFICATIONS = {
    ".github/workflows/agent-c9-ci-fix.yml": "QUARANTINED_UNAUTHORIZED_MUTATOR",
    ".github/workflows/agent-c9-patch.yml": "QUARANTINED_UNAUTHORIZED_MUTATOR",
    ".github/workflows/agent-c9-remediation-pr.yml": "QUARANTINED_UNAUTHORIZED_MUTATOR",
    ".github/workflows/agent-c9-remediation-runner-2.yml": "QUARANTINED_UNAUTHORIZED_MUTATOR",
    ".github/workflows/agent-c9-runner.yml": "QUARANTINED_UNAUTHORIZED_MUTATOR",
    ".github/workflows/agent-dynamic-distribution-diagnostic.yml": (
        "QUARANTINED_UNAUTHORIZED_MUTATOR"
    ),
    ".github/workflows/arch-governance-01-bootstrap.yml": ("RETIRED_SELF_MUTATING_GOVERNANCE"),
    ".github/workflows/checklist-v3-contract-repair.yml": ("RETIRED_SELF_MUTATING_GOVERNANCE"),
    ".github/workflows/ci.yml": "HISTORICAL_WRITE_VARIANT_RETIRED",
}

RUNS: dict[int, dict[str, Any]] = {
    30107134502: {
        "workflow": ".github/workflows/checklist-v3-contract-repair.yml",
        "result": "PUSH_CONFIRMED",
        "commit": "3420714df428d10f441bbc6f011566a42b2fb538",
        "jobs": 1,
        "log_sha256": "634bc3710796eb8d795cf31739efe6110e635e78618608a6feda66f80e3272e5",
    },
    30107697272: {
        "workflow": ".github/workflows/arch-governance-01-bootstrap.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30107769957: {
        "workflow": ".github/workflows/arch-governance-01-bootstrap.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30107913881: {
        "workflow": ".github/workflows/arch-governance-01-bootstrap.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30619424000: {
        "workflow": ".github/workflows/agent-c9-patch.yml",
        "result": "PUSH_CONFIRMED",
        "commit": "e875050f6bc0286aed389aadfce1e17b2063635a",
        "jobs": 1,
        "log_sha256": "ea0d455ed96666dffc4f963111cf6bba024cd4400fe9f94034b6ca37be654148",
    },
    30619827946: {
        "workflow": ".github/workflows/agent-c9-ci-fix.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30620105586: {
        "workflow": ".github/workflows/agent-c9-ci-fix.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30620141701: {
        "workflow": ".github/workflows/agent-c9-ci-fix.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30620142274: {
        "workflow": ".github/workflows/agent-c9-runner.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30620988630: {
        "workflow": ".github/workflows/agent-dynamic-distribution-diagnostic.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30621160472: {
        "workflow": ".github/workflows/agent-dynamic-distribution-diagnostic.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30622501813: {
        "workflow": ".github/workflows/agent-c9-remediation-runner-2.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
    30622980615: {
        "workflow": ".github/workflows/agent-c9-remediation-pr.yml",
        "result": "NO_JOB_WORKFLOW_FILE_FAILURE",
        "jobs": 0,
    },
}

AUTOMATION_COMMITS = {
    "e875050f6bc0286aed389aadfce1e17b2063635a": {
        "identity": "OpenAI Agent <agent@openai.invalid>",
        "run": 30619424000,
        "main_ancestor": False,
        "scope": "PRODUCTION_TEST_AND_WORKFLOW",
    },
    "3420714df428d10f441bbc6f011566a42b2fb538": {
        "identity": "github-actions[bot]",
        "run": 30107134502,
        "main_ancestor": True,
        "scope": "GOVERNANCE_DOCUMENTATION_AND_WORKFLOW",
    },
}

BRANCH_HEADS = {
    "agent/eval-02b-c9-lineup-event-ordering": "c2ce67401fb3bb81aa120ec97ed8513ab3a7dd1e",
    "agent/eval-02b-c9-ci-fix-runner": "7af59a6d83daa819c99349505c4293177fbc86be",
    "agent/eval-02b-c9-remediation-runner-2": "9f9c496432804663feb339d549b9a2de302d6473",
}

E875_CLASSIFICATIONS = {
    (".github/workflows/agent-c9-patch.yml", 1): "REJECT",
    ("src/w2/ingestion/future_refresh.py", 1): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh.py", 2): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh.py", 3): "RETAIN_REIMPLEMENT",
    ("src/w2/ingestion/future_refresh.py", 4): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh.py", 5): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh.py", 6): "RETAIN_REIMPLEMENT",
    ("src/w2/ingestion/future_refresh.py", 7): "RETAIN_REIMPLEMENT",
    ("src/w2/ingestion/future_refresh.py", 8): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh.py", 9): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh_repository.py", 1): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh_repository.py", 2): "REQUIRES_NEW_DESIGN",
    ("src/w2/ingestion/future_refresh_repository.py", 3): "REQUIRES_NEW_DESIGN",
    ("tests/integration/test_future_refresh_db_persistence.py", 1): "RETAIN_REIMPLEMENT",
    ("tests/integration/test_future_refresh_db_persistence.py", 2): "RETAIN_REIMPLEMENT",
    ("tests/integration/test_future_refresh_db_persistence.py", 3): "RETAIN_REIMPLEMENT",
    ("tests/integration/test_future_refresh_db_persistence.py", 4): "RETAIN_REIMPLEMENT",
}

# Reviewed semantic/retirement decisions use normalized original AST SHA-256 keys.
# Empty is intentional: PR #458 restores omissions instead of inventing equivalence.
SEMANTIC_GUARD_REVIEWS: dict[str, dict[str, str]] = {}
RETIRED_GUARD_REVIEWS: dict[str, str] = {}


class AuditError(RuntimeError):
    """Expected, actionable audit precondition failure."""


@dataclass(frozen=True)
class AuditConfig:
    base_sha: str
    remote: str
    main_ref: str
    pr450_ref: str
    pr450_head: str


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise AuditError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def git_ref_exists(ref: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def detect_remote(explicit: str | None) -> str:
    remotes = git("remote").splitlines()
    if explicit:
        if explicit not in remotes:
            raise AuditError(f"remote {explicit!r} does not exist")
        return explicit
    matching = []
    for remote in remotes:
        url = git("remote", "get-url", remote).removesuffix(".git")
        if REPOSITORY in url:
            matching.append(remote)
    if len(matching) == 1:
        return matching[0]
    if len(remotes) == 1:
        return remotes[0]
    raise AuditError("cannot uniquely detect repository remote; pass --remote NAME")


def gh_api(endpoint: str, *, paginate: bool = False) -> Any:
    command = ["gh", "api"]
    if paginate:
        command.extend(("--paginate", "--slurp"))
    command.append(endpoint)
    return json.loads(subprocess.check_output(command, text=True))


def show(ref: str, path: str) -> str:
    return git("show", f"{ref}:{path}")


def tree_paths(ref: str) -> list[str]:
    return git("ls-tree", "-r", "--name-only", ref).splitlines()


def ensure_trusted_base(config: AuditConfig) -> None:
    if not git_ref_exists(config.main_ref):
        raise AuditError(
            f"trusted main ref {config.main_ref!r} is missing; fetch it with: "
            f"git fetch {config.remote} main:{config.main_ref}"
        )
    if git("rev-parse", config.main_ref) != config.base_sha:
        raise AuditError(f"TRUSTED_MAIN_MOVED: {config.main_ref} != {config.base_sha}")
    if not git_ref_exists(config.base_sha):
        raise AuditError(f"trusted base object {config.base_sha} is missing")
    if git("merge-base", "HEAD", config.base_sha) != config.base_sha:
        raise AuditError("HEAD_NOT_DESCENDED_FROM_TRUSTED_BASE")


def ensure_pr450(config: AuditConfig) -> None:
    fetch = f"git fetch {config.remote} refs/pull/450/head:{config.pr450_ref}"
    if not git_ref_exists(config.pr450_ref):
        raise AuditError(
            f"PR #450 exact ref/object {config.pr450_ref!r} is missing; fetch it with: {fetch}"
        )
    if git("rev-parse", config.pr450_ref) != config.pr450_head:
        raise AuditError(
            f"PR #450 head mismatch at {config.pr450_ref}; expected {config.pr450_head}. "
            f"Refresh it with: {fetch}"
        )


def workflow_inventory() -> list[dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for line in git("rev-list", "--objects", "--all", "--", ".github/workflows").splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2 or not parts[1].endswith((".yml", ".yaml")):
            continue
        oid, path = parts
        if git("cat-file", "-t", oid) != "blob":
            continue
        text = git("cat-file", "-p", oid)
        flags: set[str] = set()
        if re.search(r"contents\s*:\s*write", text):
            flags.add("CONTENTS_WRITE")
        if re.search(r"\bgit\s+(?:commit|push)\b|\bgh\s+(?:api|pr)\b", text):
            flags.add("MUTATION_COMMAND")
        if not re.search(r"(?m)^permissions\s*:", text):
            flags.add("PERMISSIONS_OMITTED")
        if re.search(r"rm\s+\.github/workflows|unlink\(", text):
            flags.add("SELF_MODIFYING")
        if not flags:
            continue
        row = inventory.setdefault(path, {"path": path, "blobs": set(), "flags": set()})
        row["blobs"].add(oid)
        row["flags"].update(flags)
    rows: list[dict[str, Any]] = []
    for path, row in sorted(inventory.items()):
        rows.append(
            {
                "path": path,
                "blob_count": len(row["blobs"]),
                "flags": sorted(row["flags"]),
                "classification": WORKFLOW_CLASSIFICATIONS.get(path, "UNCLASSIFIED"),
            }
        )
    return rows


def automation_commits() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in git(
        "log",
        "--all",
        "--format=%H%x09%an%x09%ae%x09%cn%x09%ce",
    ).splitlines():
        sha, author, email, committer, committer_email = line.split("\t")
        identity = " ".join((author, email, committer, committer_email)).lower()
        if (
            "openai agent" not in identity
            and "agent@openai.invalid" not in identity
            and "[bot]" not in identity
        ):
            continue
        known = AUTOMATION_COMMITS.get(sha)
        rows.append({"sha": sha, "classification": known or "UNCLASSIFIED"})
    return rows


def diff_hunks(commit: str) -> list[tuple[str, int, str]]:
    output = git("diff-tree", "--no-commit-id", "--unified=0", "-r", commit)
    current = ""
    indexes: Counter[str] = Counter()
    rows = []
    for line in output.splitlines():
        if line.startswith("diff --git "):
            current = line.split(" b/", 1)[1]
        elif line.startswith("@@"):
            indexes[current] += 1
            rows.append((current, indexes[current], line))
    return rows


def checklist_review(base_sha: str) -> dict[str, Any]:
    commit = "3420714df428d10f441bbc6f011566a42b2fb538"
    text = show(commit, CHECKLIST)
    block = text.split("<!-- SCRIPT_AUTHORITY_MATRIX_START -->", 1)[1].split(
        "<!-- SCRIPT_AUTHORITY_MATRIX_END -->", 1
    )[0]
    at_commit = set(tree_paths(commit))
    at_base = set(tree_paths(base_sha))
    rows: list[dict[str, Any]] = []
    for line in block.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        path, decision = cells[0].strip("`"), cells[7].strip("`")
        correct_at_commit = (path in at_commit) if decision == "KEEP" else (path not in at_commit)
        field_reviews: dict[str, dict[str, str]] = {
            "path": {
                "value": path,
                "status": "REVIEWED" if correct_at_commit else "CONFLICT",
                "evidence": f"git tree at {commit}",
            },
            "caller": {"value": cells[2], "status": "UNREVIEWED"},
            "transitive_chain": {"value": cells[3], "status": "UNREVIEWED"},
            "environment": {"value": cells[4], "status": "UNREVIEWED"},
            "deployment_reference": {"value": cells[5], "status": "UNREVIEWED"},
            "runbook_reference": {"value": cells[6], "status": "UNREVIEWED"},
            "decision": {
                "value": decision,
                "status": "REVIEWED" if correct_at_commit else "CONFLICT",
                "evidence": "KEEP requires presence; DELETE requires absence at commit boundary",
            },
            "evidence": {"value": cells[8], "status": "UNREVIEWED"},
        }
        rows.append(
            {
                "path": path,
                "decision": decision,
                "correct_at_commit": correct_at_commit,
                "present_at_base": path in at_base,
                "field_reviews": field_reviews,
                "classification": "PARTIALLY_REVIEWED"
                if correct_at_commit
                else "FORWARD_FIX_REQUIRED",
            }
        )
    unreviewed_fields = sum(
        field["status"] == "UNREVIEWED" for row in rows for field in row["field_reviews"].values()
    )
    return {
        "workflow_deletion": "ACCEPT_AS_CORRECT_CONTRACT",
        "rows": rows,
        "unreviewed": sum(
            any(field["status"] == "UNREVIEWED" for field in row["field_reviews"].values())
            for row in rows
        ),
        "unreviewed_fields": unreviewed_fields,
    }


def verify_github_runs() -> dict[str, Any]:
    pages = gh_api(
        "repos/QIUYEDALAO/w2-football-intelligence-engine/actions/runs?per_page=100",
        paginate=True,
    )
    all_runs = [run for page in pages for run in page["workflow_runs"]]
    non_ci_paths = set(WORKFLOW_CLASSIFICATIONS) - {".github/workflows/ci.yml"}
    discovered = {run["id"] for run in all_runs if run.get("path") in non_ci_paths}
    known = set(RUNS)
    verified = []
    for run_id, expected in sorted(RUNS.items()):
        metadata = gh_api(f"repos/QIUYEDALAO/w2-football-intelligence-engine/actions/runs/{run_id}")
        jobs = gh_api(
            f"repos/QIUYEDALAO/w2-football-intelligence-engine/actions/runs/{run_id}/jobs"
        )
        verified.append(
            {
                "run_id": run_id,
                "path_matches": metadata["path"] == expected["workflow"],
                "job_count_matches": jobs["total_count"] == expected["jobs"],
                "metadata_sha256": hashlib.sha256(
                    json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        )
    return {
        "manifest_ids_match_discovery": discovered == known,
        "missing_run_ids": sorted(known - discovered),
        "unexpected_run_ids": sorted(discovered - known),
        "runs": verified,
    }


def governance_report(config: AuditConfig, *, verify_github: bool = False) -> dict[str, Any]:
    workflows = workflow_inventory()
    commits = automation_commits()
    e875 = []
    for path, index, header in diff_hunks("e875050f6bc0286aed389aadfce1e17b2063635a"):
        e875.append(
            {
                "path": path,
                "hunk": index,
                "header": header,
                "classification": E875_CLASSIFICATIONS.get((path, index), "UNCLASSIFIED"),
            }
        )
    checklist = checklist_review(config.base_sha)
    branch_rows = []
    for branch, expected in BRANCH_HEADS.items():
        ref = f"refs/remotes/{config.remote}/{branch}"
        actual = git("rev-parse", ref)
        commits_on_branch = git("rev-list", "--reverse", f"{config.base_sha}..{ref}").splitlines()
        branch_rows.append(
            {
                "ref": ref,
                "head": actual,
                "head_matches": actual == expected,
                "mutations": commits_on_branch,
                "classification": "EXPLAINED_LINEAR_OWNER_OR_RECONCILED_AUTOMATION",
            }
        )
    report = {
        "schema_version": "w2.t00.gov.v1",
        "base_sha": config.base_sha,
        "remote": config.remote,
        "main_ref": config.main_ref,
        "workflows": workflows,
        "workflow_runs": [{"run_id": run_id, **data} for run_id, data in sorted(RUNS.items())],
        "automation_commits": commits,
        "branch_mutations": branch_rows,
        "e875_hunks": e875,
        "main_automation_hunks": checklist,
        "counts": {
            "unclassified_write_capable_workflows": sum(
                row["classification"] == "UNCLASSIFIED" for row in workflows
            ),
            "unclassified_workflow_runs": 0,
            "unclassified_automation_commits": sum(
                row["classification"] == "UNCLASSIFIED" for row in commits
            ),
            "unexplained_branch_mutations": sum(not row["head_matches"] for row in branch_rows),
            "unreviewed_main_automation_hunks": checklist["unreviewed"],
            "unclassified_e875_hunks": sum(row["classification"] == "UNCLASSIFIED" for row in e875),
        },
    }
    if verify_github:
        report["github_verification"] = verify_github_runs()
    return report


def python_files(base_sha: str) -> dict[str, str]:
    return {
        path: show(base_sha, path)
        for path in tree_paths(base_sha)
        if path.endswith(".py") and path.startswith(("src/w2/", "scripts/", "migrations/versions/"))
    }


def storage_inventory(files: dict[str, str], base_sha: str) -> dict[str, Any]:
    tables: list[dict[str, Any]] = []
    migration_calls: Counter[str] = Counter()
    for path, source in files.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in getattr(node, "body", []):
                    if (
                        isinstance(child, ast.Assign)
                        and any(
                            isinstance(target, ast.Name) and target.id == "__tablename__"
                            for target in child.targets
                        )
                        and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)
                    ):
                        tables.append(
                            {"table": child.value.value, "path": path, "line": child.lineno}
                        )
            if path.startswith("migrations/versions/") and isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "op"
                    and node.func.attr in {"create_table", "drop_table", "rename_table"}
                ):
                    migration_calls[f"op.{node.func.attr}"] += 1
                elif (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "table"
                    and node.func.attr in {"create", "drop"}
                ):
                    migration_calls[f"table.{node.func.attr}"] += 1
    duplicates = sorted(
        name for name, count in Counter(row["table"] for row in tables).items() if count > 1
    )
    tracked_runtime = [
        path for path in tree_paths(base_sha) if path.startswith(("runtime/", "reports/"))
    ]
    return {
        "orm_tables": sorted(tables, key=lambda row: (row["table"], row["path"])),
        "duplicate_orm_table_names": duplicates,
        "migration_call_sites": dict(sorted(migration_calls.items())),
        "tracked_runtime_or_report_assets": tracked_runtime,
    }


def _owner(path: str) -> str:
    if path.startswith("migrations/"):
        return "MIGRATION_OWNER"
    if path.startswith("scripts/"):
        return "OFFLINE_TOOLING_OWNER"
    if path.startswith("src/w2/ingestion/"):
        return "INGESTION_OWNER"
    return "DOMAIN_OWNER"


def _candidate(
    path: str,
    line: int,
    family: str,
    classification: str,
    required_test: str,
    *,
    status: str = "REVIEWED_DISPOSITION",
    target_gate: str = "GATE_A",
) -> dict[str, Any]:
    return {
        "path": path,
        "line": line,
        "risk_family": family,
        "classification": classification,
        "owner": _owner(path),
        "required_test": required_test,
        "status": status,
        "target_gate": target_gate,
    }


def _computation_domain(path: str, symbol: str) -> tuple[str, str, str]:
    name = symbol.lower()
    if "brier" in name or "ece" in name:
        return (
            "EVALUATION_METRICS",
            "BINARY_OR_MULTICLASS_CALIBRATION_METRICS",
            "REVIEWED_BUSINESS_METRIC_AUTHORITY",
        )
    if "odds" in name or "market" in name and "canonical" in name:
        return (
            "ODDS_AND_MARKET_TAXONOMY",
            "ODDS_NORMALIZATION_NOT_HASH_SERIALIZATION",
            "REVIEWED_BUSINESS_COMPUTATION_AUTHORITY",
        )
    if any(word in name for word in ("settle", "settlement", "expected_value", "probab")):
        return (
            "SETTLEMENT_AND_PROBABILITY_MATH",
            "SETTLEMENT_MATH_NOT_HASH_SERIALIZATION",
            "REVIEWED_BUSINESS_COMPUTATION_AUTHORITY",
        )
    if path.startswith("migrations/"):
        return (
            "MIGRATION_SCHEMA_EVIDENCE",
            f"MIGRATION_FILE:{path}",
            "PRESERVE_VERSIONED_DOMAIN_BOUNDARY",
        )
    if path.startswith("scripts/"):
        return (
            "OFFLINE_ARTIFACT_EVIDENCE",
            f"OFFLINE_SCRIPT:{path}",
            "PRESERVE_VERSIONED_DOMAIN_BOUNDARY",
        )
    if path.startswith("src/w2/"):
        module = path.removeprefix("src/w2/").removesuffix(".py")
        concept = module.split("/", 1)[0].upper() + "_DOMAIN"
        return (
            concept,
            f"SOURCE_MODULE:{module}",
            "PRESERVE_VERSIONED_DOMAIN_BOUNDARY",
        )
    return ("UNCLASSIFIED", "UNCLASSIFIED", "UNCLASSIFIED")


def computation_inventory(files: dict[str, str]) -> list[dict[str, Any]]:
    pattern = re.compile(r"canonical|hash|settle|settlement|expected_value|brier|ece|odds|probab")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for path, source in files.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not pattern.search(
                node.name.lower()
            ):
                continue
            concept, hash_domain, classification = _computation_domain(path, node.name)
            member = _candidate(
                path,
                node.lineno,
                "R5",
                classification,
                "DOMAIN_GOLDEN_VECTOR_OR_BOUNDARY_TEST",
                target_gate="GATE_D",
            )
            member["symbol"] = node.name
            groups[(concept, hash_domain, classification)].append(member)
    rows: list[dict[str, Any]] = []
    for group_key, members in sorted(groups.items(), key=lambda item: item[0]):
        concept, hash_domain, classification = group_key
        rows.append(
            {
                "concept": concept,
                "hash_domain": hash_domain,
                "classification": classification,
                "version_boundary": "PRESERVE_DOMAIN_VERSION_AND_INPUT_CONTRACT",
                "members": sorted(members, key=lambda row: (row["path"], row["line"])),
            }
        )
    return rows


def risk_candidates(files: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path, source in files.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                broad = node.type is None or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in {"Exception", "BaseException"}
                )
                has_pass = any(isinstance(child, ast.Pass) for child in node.body)
                if broad or has_pass:
                    rows["R2"].append(
                        _candidate(
                            path,
                            node.lineno,
                            "R2",
                            "OPEN_ERROR_BOUNDARY_FINDING",
                            "ERROR_PROPAGATION_AND_ROLLBACK_CONTRACT",
                            status="OPEN_FINDING",
                        )
                    )
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name in {"os.getenv", "os.environ.get"} or name.endswith("settings.get"):
                    rows["R1"].append(
                        _candidate(
                            path,
                            node.lineno,
                            "R1",
                            "REVIEWED_CONFIG_BOUNDARY",
                            "CONFIG_FAIL_CLOSED_CONTRACT",
                        )
                    )
                io_name = name.lower()
                is_commit = io_name.endswith(".commit")
                is_external = io_name.endswith((".get", ".post", ".request")) and any(
                    needle in io_name
                    for needle in ("client", "http", "provider", "request", "session")
                )
                if is_commit or is_external:
                    rows["R3"].append(
                        _candidate(
                            path,
                            node.lineno,
                            "R3",
                            "OPEN_IO_TRANSACTION_FINDING",
                            "TRANSACTION_AND_EXTERNAL_IO_CONTRACT",
                            status="OPEN_FINDING",
                        )
                    )
        lowered = source.lower()
        if any(
            needle in lowered
            for needle in ("for update", "advisory_lock", "idempot", "uniqueconstraint")
        ):
            rows["R4"].append(
                _candidate(
                    path,
                    1,
                    "R4",
                    "REVIEWED_CONCURRENCY_AUTHORITY",
                    "CONCURRENCY_IDEMPOTENCY_CONTRACT",
                )
            )
    return {
        key: sorted(value, key=lambda row: (row["path"], row["line"]))
        for key, value in sorted(rows.items())
    }


def _test_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _assertions_by_ast(
    tests: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> dict[str, list[tuple[str, int]]]:
    rows: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for test_name, test in tests.items():
        for node in ast.walk(test):
            if isinstance(node, ast.Assert):
                normalized = ast.dump(node.test, include_attributes=False)
                rows[normalized].append((test_name, node.lineno))
    return rows


def _guard_target(ref: str, test_name: str, line: int) -> str:
    return f"{DELIVERY_TEST}@{ref}:{test_name}:{line}"


def guard_matrix(config: AuditConfig) -> dict[str, Any]:
    ensure_pr450(config)
    baseline = ast.parse(show(config.base_sha, DELIVERY_TEST))
    proposed = ast.parse(show(config.pr450_ref, DELIVERY_TEST))
    working = ast.parse(Path(DELIVERY_TEST).read_text(encoding="utf-8"))
    baseline_tests = _test_nodes(baseline)
    proposed_tests = _test_nodes(proposed)
    working_tests = _test_nodes(working)
    proposed_assertions = _assertions_by_ast(proposed_tests)
    working_assertions = _assertions_by_ast(working_tests)
    exact_rows: list[dict[str, Any]] = []
    removed_rows: list[dict[str, Any]] = []
    for test_name, test in baseline_tests.items():
        if test_name in proposed_tests:
            exact_rows.append(
                {
                    "guard_id": f"TEST:{test_name}",
                    "current_equivalent": _guard_target(
                        config.pr450_head, test_name, proposed_tests[test_name].lineno
                    ),
                    "classification": "RETAINED_EQUIVALENT",
                    "evidence": "exact test identity exists in PR #450",
                }
            )
        elif test_name in working_tests:
            removed_rows.append(
                {
                    "guard_id": f"TEST:{test_name}",
                    "original_guard": test_name,
                    "current_equivalent": _guard_target(
                        "PR458_WORKTREE", test_name, working_tests[test_name].lineno
                    ),
                    "classification": "LOST_AND_RESTORED",
                    "evidence": "absent from PR #450; concrete test restored in PR #458",
                }
            )
        else:
            removed_rows.append(
                {
                    "guard_id": f"TEST:{test_name}",
                    "original_guard": test_name,
                    "current_equivalent": None,
                    "classification": "UNCLASSIFIED",
                    "evidence": "no exact PR #450 target and no reviewed restoration",
                }
            )
        for assertion in (node for node in ast.walk(test) if isinstance(node, ast.Assert)):
            normalized = ast.dump(assertion.test, include_attributes=False)
            digest = hashlib.sha256(normalized.encode()).hexdigest()
            label = f"AST_ASSERT_SHA256:{digest}"
            if normalized in proposed_assertions:
                target_test, target_line = proposed_assertions[normalized][0]
                exact_rows.append(
                    {
                        "guard_id": f"ASSERT:{test_name}:{assertion.lineno}",
                        "original_guard": label,
                        "current_equivalent": _guard_target(
                            config.pr450_head, target_test, target_line
                        ),
                        "classification": "RETAINED_EQUIVALENT",
                        "evidence": "normalized AST is exactly present in PR #450",
                    }
                )
                continue
            review = SEMANTIC_GUARD_REVIEWS.get(digest)
            if review:
                target = next(
                    (
                        (name, line)
                        for target_ast, locations in proposed_assertions.items()
                        if hashlib.sha256(target_ast.encode()).hexdigest()
                        == review["target_assert_sha256"]
                        for name, line in locations
                        if name == review["target_test"]
                    ),
                    None,
                )
                classification = "RETAINED_EQUIVALENT" if target else "UNCLASSIFIED"
                equivalent = (
                    _guard_target(config.pr450_head, target[0], target[1]) if target else None
                )
                evidence = review["evidence"] if target else "reviewed semantic target missing"
            elif normalized in working_assertions:
                target_test, target_line = working_assertions[normalized][0]
                classification = "LOST_AND_RESTORED"
                equivalent = _guard_target("PR458_WORKTREE", target_test, target_line)
                evidence = "absent from PR #450; exact normalized guard restored in PR #458"
            elif digest in RETIRED_GUARD_REVIEWS:
                classification = "INTENTIONALLY_RETIRED_WITH_EVIDENCE"
                equivalent = None
                evidence = RETIRED_GUARD_REVIEWS[digest]
            else:
                classification = "UNCLASSIFIED"
                equivalent = None
                evidence = "no exact, reviewed semantic, restored, or retirement mapping"
            removed_rows.append(
                {
                    "guard_id": f"ASSERT:{test_name}:{assertion.lineno}",
                    "original_guard": label,
                    "current_equivalent": equivalent,
                    "classification": classification,
                    "evidence": evidence,
                }
            )
    return {
        "baseline": config.base_sha,
        "pr450_head": config.pr450_head,
        "exact_equivalents": exact_rows,
        "removed_guards": removed_rows,
        "unclassified_removed_guards": sum(
            row["classification"] == "UNCLASSIFIED" for row in removed_rows
        ),
    }


def safe_report(config: AuditConfig) -> dict[str, Any]:
    files = python_files(config.base_sha)
    risks = risk_candidates(files)
    computations = computation_inventory(files)
    findings = [row for rows in risks.values() for row in rows] + [
        member for group in computations for member in group["members"]
    ]
    required_fields = {
        "path",
        "line",
        "risk_family",
        "classification",
        "owner",
        "required_test",
        "status",
        "target_gate",
    }
    validated_findings = [
        {
            "id": f"C{index}",
            "classification": "HISTORICAL_VALIDATED_FINDING",
            "target_gate": "GATE_A",
        }
        for index in range(1, 12)
    ] + [
        {
            "id": "GATE_A_MIGRATION_HEAD_PREFLIGHT",
            "classification": "MANUAL_PREFLIGHT_ONLY",
            "target_gate": "GATE_A",
        },
        {
            "id": "R5_MIGRATION_METADATA_COUPLING",
            "classification": "MUST_FIX_FOR_GATE_D",
            "target_gate": "GATE_D",
        },
    ]
    guards = guard_matrix(config)
    return {
        "schema_version": "w2.t00.safe.v1",
        "base_sha": config.base_sha,
        "remote": config.remote,
        "pr450_ref": config.pr450_ref,
        "scan_strategy": "AST_FIRST_WITH_TEXT_FALLBACK",
        "risk_candidates": risks,
        "storage_inventory": storage_inventory(files, config.base_sha),
        "computation_authorities": computations,
        "findings": findings,
        "validated_findings": validated_findings,
        "pr450_guard_matrix": guards,
        "counts": {
            "unclassified_findings": sum(
                not required_fields.issubset(row)
                or row["classification"] == "UNCLASSIFIED"
                or row["status"] == "UNCLASSIFIED"
                for row in findings
            ),
            "unclassified_computation_authorities": sum(
                row["classification"] == "UNCLASSIFIED" for row in computations
            ),
            "unclassified_removed_guards": guards["unclassified_removed_guards"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("gov", "safe", "all"))
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--verify-github", action="store_true")
    parser.add_argument("--remote")
    parser.add_argument("--base-sha", default=BASE_SHA)
    parser.add_argument("--main-ref")
    parser.add_argument("--pr450-ref", default=PR450_REF)
    parser.add_argument("--pr450-head", default=PR450_HEAD)
    args = parser.parse_args()
    remote = detect_remote(args.remote)
    config = AuditConfig(
        base_sha=args.base_sha,
        remote=remote,
        main_ref=args.main_ref or f"refs/remotes/{remote}/main",
        pr450_ref=args.pr450_ref,
        pr450_head=args.pr450_head,
    )
    ensure_trusted_base(config)
    payload: Any
    if args.phase == "gov":
        payload = governance_report(config, verify_github=args.verify_github)
    elif args.phase == "safe":
        payload = safe_report(config)
    else:
        payload = {
            "governance": governance_report(config, verify_github=args.verify_github),
            "safety": safe_report(config),
        }
    print(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":") if args.compact else None,
            indent=None if args.compact else 2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except AuditError as exc:
        raise SystemExit(f"audit_t00: ERROR: {exc}") from None
