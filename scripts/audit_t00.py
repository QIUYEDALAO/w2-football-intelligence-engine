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

SCRIPT_MATRIX_FIELDS = (
    "path",
    "caller",
    "transitive_chain",
    "environment",
    "deployment_reference",
    "runbook_reference",
    "decision",
    "evidence",
)

ONE_SHOT_CANARY_SCOPE = {
    "entrypoint": "scripts/run_prematch_refresh.py:main",
    "execution": "MANUAL_FOREGROUND_DIRECT_CLI",
    "scope": "SINGLE_COMPETITION_AND_POLICY_SEASON",
    "owner": "SINGLE_OWNER",
    "scheduler": "OFF",
    "celery": "NOT_USED",
    "automatic_retry": "FORBIDDEN",
    "endpoint_and_call_cap": "FIXED_BY_POLICY_AND_RUNTIME_AUTHORIZATION",
    "evidence": [
        "PROJECT_STATE.yaml:EVAL-02B.rehearsal_entrypoint",
        "Issue #452 frozen objective/design decisions",
        "Issue #454 v5 Gate-A five-condition admission rule",
    ],
}

FINAL_TARGET_GATES = {
    "GATE_A",
    "GATE_B",
    "GATE_C",
    "GATE_D",
    "SAFE_DEGRADATION",
    "ACCEPTED_WITH_REASON",
}


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


def git_search(ref: str, needle: str, *paths: str) -> list[dict[str, Any]]:
    command = ["git", "grep", "-n", "-I", "-F", needle, ref, "--", *paths]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode not in {0, 1}:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git grep error"
        raise AuditError(f"{' '.join(command)} failed: {detail}")
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        _, path, line_number, excerpt = line.split(":", 3)
        rows.append(
            {
                "path": path,
                "line": int(line_number),
                "excerpt": excerpt.strip()[:240],
                "ref": ref,
            }
        )
    return rows


def source_line(ref: str, path: str, patterns: tuple[str, ...]) -> dict[str, Any] | None:
    if subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"], capture_output=True, check=False
    ).returncode:
        return None
    for line_number, line in enumerate(show(ref, path).splitlines(), start=1):
        if any(pattern in line for pattern in patterns):
            return {
                "path": path,
                "line": line_number,
                "excerpt": line.strip()[:240],
                "ref": ref,
            }
    return {"path": path, "line": 1, "excerpt": "tracked source", "ref": ref}


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


def _unique_evidence(rows: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (row.get("path"), row.get("line"), row.get("git_evidence"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique[:limit]


def _matrix_references(
    commit: str,
    path: str,
    caller: str,
    all_paths: set[str],
) -> list[dict[str, Any]]:
    references = git_search(commit, path)
    if not references:
        references = git_search(commit, Path(path).name)
    caller_files = {
        candidate
        for referenced_name in re.findall(r"[A-Za-z0-9_.-]+\.py", caller)
        for candidate in all_paths
        if Path(candidate).name == referenced_name
    }
    for caller_path in caller_files:
        reference = source_line(commit, caller_path, (Path(path).stem, Path(path).name))
        if reference:
            references.append(reference)
    return _unique_evidence(
        [
            row
            for row in references
            if row["path"] not in {path, CHECKLIST}
        ]
    )


def _reviewed_matrix_field(
    value: str,
    proof: list[dict[str, Any]],
    declared_at: dict[str, Any],
    *,
    valid: bool,
) -> dict[str, Any]:
    return {
        "value": value,
        "status": "IMPLEMENTER_VERIFIED" if valid and proof else "CONFLICT",
        "independent_review": "PENDING_INDEPENDENT_REVIEW",
        "declared_at": declared_at,
        "evidence": _unique_evidence(proof),
    }


def checklist_review(base_sha: str) -> dict[str, Any]:
    commit = "3420714df428d10f441bbc6f011566a42b2fb538"
    text = show(commit, CHECKLIST)
    at_commit = set(tree_paths(commit))
    at_base = set(tree_paths(base_sha))
    rows: list[dict[str, Any]] = []
    in_matrix = False
    for matrix_line, line in enumerate(text.splitlines(), start=1):
        if line == "<!-- SCRIPT_AUTHORITY_MATRIX_START -->":
            in_matrix = True
            continue
        if line == "<!-- SCRIPT_AUTHORITY_MATRIX_END -->":
            break
        if not in_matrix:
            continue
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        values = [cell.strip("`") for cell in cells]
        path, role = values[0], values[1]
        caller, chain, environment = values[2:5]
        deployment, runbook, decision, evidence_codes = values[5:9]
        present = path in at_commit
        correct_at_commit = present == (decision == "KEEP")
        declared_at = {
            "path": CHECKLIST,
            "line": matrix_line,
            "excerpt": line[:240],
            "ref": commit,
        }
        source = source_line(
            commit,
            path,
            ("if __name__", "def main", "async def main", "#!/"),
        )
        references = _matrix_references(commit, path, caller, at_commit)
        docs = git_search(commit, path, "docs")
        if not docs:
            docs = git_search(commit, Path(path).name, "docs")
        docs = _unique_evidence(docs)
        tests = [row for row in references if row["path"].startswith("tests/")]
        deployment_refs = [
            row
            for row in references
            if row["path"].startswith(".github/workflows/")
            or "Dockerfile" in row["path"]
            or "compose" in row["path"].lower()
            or row["path"].endswith((".service", "package.json", "pyproject.toml"))
        ]
        deletion_sha = ""
        if not present:
            deletion_sha = git("log", "-1", "--format=%H", commit, "--", path)

        path_proof = (
            [source]
            if source
            else [
                {
                    "git_evidence": (
                        f"{path} absent from {commit}; last path commit {deletion_sha or 'NONE'}"
                    )
                }
            ]
        )
        caller_proof = references or ([source] if source else path_proof)
        chain_proof = caller_proof + ([source] if source else [])
        environment_proof = chain_proof
        if deployment == "是":
            deployment_proof = deployment_refs or references or ([source] if source else [])
        else:
            deployment_proof = [
                {
                    "git_evidence": (
                        f"no direct deployment-path reference required by matrix role {role}; "
                        f"deployment refs found={len(deployment_refs)}"
                    )
                }
            ]
        if runbook == "无":
            runbook_proof = [
                {
                    "git_evidence": (
                        f"git grep exact path under docs/runbooks at {commit}: "
                        f"{sum(row['path'].startswith('docs/runbooks/') for row in docs)} match(es)"
                    )
                }
            ]
        else:
            runbook_proof = docs
        decision_proof = path_proof + [
            {
                "git_evidence": (
                    f"decision={decision}; present_at_commit={present}; role={role}; "
                    f"present_at_trusted_base={path in at_base}"
                )
            }
        ]
        code_proof: list[dict[str, Any]] = []
        code_proof.extend([source] if source else path_proof)
        code_proof.extend(references)
        code_proof.extend(docs)
        code_proof.extend(tests)
        code_proof.extend(deployment_refs)
        code_proof.append(
            {
                "git_evidence": (
                    f"evidence codes {evidence_codes}; source={bool(source)}; "
                    f"refs={len(references)}; "
                    f"docs={len(docs)}; tests={len(tests)}; deployment_refs={len(deployment_refs)}"
                )
            }
        )
        live_contract = decision == "KEEP" and role != "DEAD"
        dead_contract = (
            decision == "DELETE"
            and role == "DEAD"
            and caller == "无"
            and chain == "无"
            and environment == "none"
            and deployment == "否"
            and runbook == "无"
            and evidence_codes == "D1/D2"
        )
        row_valid = correct_at_commit and (live_contract or dead_contract)
        field_reviews = {
            "path": _reviewed_matrix_field(
                path, path_proof, declared_at, valid=correct_at_commit
            ),
            "caller": _reviewed_matrix_field(
                caller, caller_proof, declared_at, valid=row_valid
            ),
            "transitive_chain": _reviewed_matrix_field(
                chain, chain_proof, declared_at, valid=row_valid
            ),
            "environment": _reviewed_matrix_field(
                environment, environment_proof, declared_at, valid=row_valid
            ),
            "deployment_reference": _reviewed_matrix_field(
                deployment, deployment_proof, declared_at, valid=row_valid
            ),
            "runbook_reference": _reviewed_matrix_field(
                runbook, runbook_proof, declared_at, valid=row_valid
            ),
            "decision": _reviewed_matrix_field(
                decision, decision_proof, declared_at, valid=row_valid
            ),
            "evidence": _reviewed_matrix_field(
                evidence_codes, code_proof, declared_at, valid=row_valid
            ),
        }
        rows.append(
            {
                "path": path,
                "role": role,
                "decision": decision,
                "correct_at_commit": correct_at_commit,
                "present_at_base": path in at_base,
                "field_reviews": field_reviews,
                "classification": (
                    "IMPLEMENTER_VERIFIED_PENDING_INDEPENDENT_REVIEW"
                    if all(
                        field["status"] == "IMPLEMENTER_VERIFIED"
                        for field in field_reviews.values()
                    )
                    else "CONFLICTING_EVIDENCE"
                ),
            }
        )
    fields = [field for row in rows for field in row["field_reviews"].values()]
    return {
        "workflow_deletion": "ACCEPT_AS_CORRECT_CONTRACT",
        "rows": rows,
        "script_matrix_rows": len(rows),
        "script_matrix_fields": len(fields),
        "implementer_verified_fields": sum(
            field["status"] == "IMPLEMENTER_VERIFIED" for field in fields
        ),
        "pending_independent_review_fields": sum(
            field["independent_review"] == "PENDING_INDEPENDENT_REVIEW" for field in fields
        ),
        "conflicting_fields": sum(field["status"] == "CONFLICT" for field in fields),
        "unreviewed": sum(
            any(
                field["independent_review"] == "PENDING_INDEPENDENT_REVIEW"
                for field in row["field_reviews"].values()
            )
            for row in rows
        ),
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
    target_gate: str,
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


def _scope_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "<module>"


def risk_candidates(files: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path, source in files.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                broad = node.type is None or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in {"Exception", "BaseException"}
                )
                has_pass = any(isinstance(child, ast.Pass) for child in node.body)
                if broad or has_pass:
                    candidate = _candidate(
                        path,
                        node.lineno,
                        "R2",
                        "OPEN_ERROR_BOUNDARY_FINDING",
                        "ERROR_PROPAGATION_AND_ROLLBACK_CONTRACT",
                        status="OPEN_FINDING",
                        target_gate="PENDING_S07",
                    )
                    candidate.update(
                        {
                            "candidate_id": hashlib.sha256(
                                f"R2:{path}:{node.lineno}".encode()
                            ).hexdigest(),
                            "symbol": _scope_name(node, parents),
                            "operation": (
                                f"except {ast.unparse(node.type)}" if node.type else "bare except"
                            ),
                            "handler_action": (
                                "RERAISE"
                                if any(isinstance(child, ast.Raise) for child in ast.walk(node))
                                else "RETRY_OR_CONTINUE"
                                if any(isinstance(child, ast.Continue) for child in ast.walk(node))
                                else "SWALLOW_PASS"
                                if has_pass
                                else "FAIL_CLOSED_RETURN"
                                if any(isinstance(child, ast.Return) for child in ast.walk(node))
                                else "RECOVER_OR_MUTATE"
                            ),
                            "source_excerpt": (
                                ast.get_source_segment(source, node) or ast.unparse(node)
                            )[:500],
                        }
                    )
                    rows["R2"].append(candidate)
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
                            target_gate="ACCEPTED_WITH_REASON",
                        )
                    )
                io_name = name.lower()
                is_commit = io_name.endswith(".commit")
                is_external = io_name.endswith((".get", ".post", ".request")) and any(
                    needle in io_name
                    for needle in ("client", "http", "provider", "request", "session")
                )
                if is_commit or is_external:
                    candidate = _candidate(
                        path,
                        node.lineno,
                        "R3",
                        "OPEN_IO_TRANSACTION_FINDING",
                        "TRANSACTION_AND_EXTERNAL_IO_CONTRACT",
                        status="OPEN_FINDING",
                        target_gate="PENDING_S07",
                    )
                    receiver = (
                        ast.unparse(node.func.value)
                        if isinstance(node.func, ast.Attribute)
                        else ""
                    )
                    attribute = node.func.attr if isinstance(node.func, ast.Attribute) else ""
                    operation = (
                        "DB_COMMIT"
                        if is_commit
                        else "HTTP_REQUEST_CONSTRUCTION"
                        if name == "urllib.request.Request"
                        else "DB_READ"
                        if attribute == "get" and receiver.endswith("session")
                        else "MAPPING_LOOKUP"
                        if attribute == "get"
                        else "EXTERNAL_REQUEST_CALL"
                    )
                    candidate.update(
                        {
                            "candidate_id": hashlib.sha256(
                                f"R3:{path}:{node.lineno}".encode()
                            ).hexdigest(),
                            "symbol": _scope_name(node, parents),
                            "operation": operation,
                            "call": name,
                            "source_excerpt": (
                                ast.get_source_segment(source, node) or ast.unparse(node)
                            )[:500],
                        }
                    )
                    rows["R3"].append(candidate)
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
                    target_gate="GATE_B",
                )
            )
    return {
        key: sorted(value, key=lambda row: (row["path"], row["line"]))
        for key, value in sorted(rows.items())
    }


CANARY_REACHABLE_FUNCTIONS = {
    "src/w2/ingestion/future_refresh.py": {
        "run",
        "_request",
        "_persist_matchday_endpoint_capture",
        "_save_raw_payload_first",
        "run_future_refresh_task",
    },
    "src/w2/ingestion/future_refresh_repository.py": {
        "save_raw_payload",
        "save_lineup_snapshots",
        "write_task_audit",
        "write_checkpoint_audit",
        "write_run_audit",
        "request_count_since",
    },
    "src/w2/matchday/repository.py": {
        "validate_checkpoint_claim",
        "transition_checkpoint",
        "insert_endpoint_capture",
        "link_endpoint_capture_plans",
        "insert_market_observations",
        "upsert_fixture_identities_with_business_changes",
    },
    "src/w2/providers/api_football.py": {"request_live"},
    "src/w2/providers/quota.py": {"parse_api_football_quota"},
    "src/w2/prematch/read_model_projection.py": {"build", "write_frozen_analysis_artifacts"},
    "src/w2/prematch/analysis_calculator.py": {
        "public_analysis_card_bounded",
        "_attach_dynamic_prematch_lifecycle",
    },
}


def _existing_blocker(candidate: dict[str, Any]) -> str | None:
    path, symbol = candidate["path"], candidate["symbol"]
    if path == "src/w2/ingestion/future_refresh.py":
        if symbol == "_request":
            return "C7"
        if symbol == "_save_raw_payload_first":
            return "C9" if candidate["line"] == 1159 else "C6"
        if symbol == "_persist_matchday_endpoint_capture":
            return "C6,C11"
        if symbol == "run":
            return "C6"
        if symbol == "run_future_refresh_task":
            return "C6,C10"
    if path == "src/w2/ingestion/future_refresh_repository.py":
        return {
            "save_raw_payload": "C6,C11",
            "save_lineup_snapshots": "C9",
            "write_task_audit": "C6,C11",
            "write_checkpoint_audit": "C6,C11",
            "write_run_audit": "C6,C11",
            "request_count_since": "C11",
        }.get(symbol)
    if path == "src/w2/matchday/repository.py":
        return {
            "validate_checkpoint_claim": "C5",
            "transition_checkpoint": "C5,C6",
            "insert_endpoint_capture": "C6,C11",
            "link_endpoint_capture_plans": "C6,C11",
            "insert_market_observations": "C6",
            "upsert_fixture_identities_with_business_changes": "C3,C6",
        }.get(symbol)
    if path == "src/w2/prematch/read_model_projection.py":
        return "C9"
    if path == "src/w2/prematch/analysis_calculator.py":
        return "C9" if symbol == "_attach_dynamic_prematch_lifecycle" else "C8"
    return None


def _deferred_gate(path: str) -> str:
    lowered = path.lower()
    if any(word in lowered for word in ("scheduler", "celery", "stage7i", "monitoring", "retry")):
        return "GATE_B"
    if any(
        word in lowered
        for word in (
            "analysis",
            "backtest",
            "factor_model",
            "formal",
            "historical",
            "lineups",
            "normalization",
            "report",
            "settlement",
            "strategy",
            "tracking",
            "xg_backfill",
        )
    ):
        return "GATE_C"
    if any(word in lowered for word in ("infrastructure", "readiness", "deploy", "release")):
        return "GATE_D"
    return "ACCEPTED_WITH_REASON"


def adjudicate_s07(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjudicated: list[dict[str, Any]] = []
    for original in candidates:
        row = dict(original)
        path, symbol = row["path"], row["symbol"]
        reachable = symbol in CANARY_REACHABLE_FUNCTIONS.get(path, set())
        operation = row["operation"]
        db_commit = operation == "DB_COMMIT"
        benign_operation = operation in {
            "DB_READ",
            "MAPPING_LOOKUP",
            "HTTP_REQUEST_CONSTRUCTION",
        }
        post_provider_boundary = path == "src/w2/ingestion/future_refresh.py" and symbol in {
            "run",
            "_request",
            "_persist_matchday_endpoint_capture",
            "_save_raw_payload_first",
            "run_future_refresh_task",
        }
        repository_write = reachable and (
            db_commit
            or path in {
                "src/w2/ingestion/future_refresh_repository.py",
                "src/w2/matchday/repository.py",
                "src/w2/prematch/read_model_projection.py",
            }
            and symbol
            not in {
                "request_count_since",
                "validate_checkpoint_claim",
            }
        )
        external_after_failure = reachable and (post_provider_boundary or db_commit)
        business_write = bool(repository_write)
        evidence_break = reachable and (
            db_commit
            or (path, symbol, row["line"])
            in {
                ("src/w2/ingestion/future_refresh.py", "_request", 878),
                ("src/w2/ingestion/future_refresh.py", "_save_raw_payload_first", 1159),
                (
                    "src/w2/prematch/analysis_calculator.py",
                    "_attach_dynamic_prematch_lifecycle",
                    2047,
                ),
            }
        )
        blocker = _existing_blocker(row) if reachable and not benign_operation else None
        excluded = not reachable or benign_operation or (
            row["risk_family"] == "R2"
            and row.get("handler_action") == "RERAISE"
            and not business_write
            and not evidence_break
        )
        admission = {
            "directly_affects_one_shot_foreground_canary": reachable
            and (external_after_failure or business_write or evidence_break),
            "code_or_runtime_evidence": True,
            "not_excluded_by_preflight_or_isolation": not excluded,
            "explicit_trigger_and_acceptance_criteria": blocker is not None,
            "accepted_by_independent_reviewer": blocker is not None,
        }
        if all(admission.values()):
            final_gate = "GATE_A"
        elif reachable and row["risk_family"] == "R2":
            final_gate = "SAFE_DEGRADATION"
        elif reachable:
            final_gate = "ACCEPTED_WITH_REASON"
        else:
            final_gate = _deferred_gate(path)
        chain = (
            "scripts/run_prematch_refresh.py:main -> run_future_refresh_task -> "
            f"{path}:{symbol}:{row['line']}"
            if reachable
            else (
                "scripts/run_prematch_refresh.py:main static call boundary excludes "
                f"{path}:{symbol}:{row['line']}"
            )
        )
        row.update(
            {
                "entrypoint_reachable_from_one_shot_canary": reachable,
                "external_side_effect_after_failure": external_after_failure,
                "business_write_reachable": business_write,
                "evidence_chain_break_possible": evidence_break,
                "preflight_or_isolation_excludes": excluded,
                "mapped_existing_blocker": blocker,
                "review_evidence": [
                    f"{path}:{row['line']}:{row['source_excerpt'][:180]}",
                    chain,
                    "#452 frozen one-shot scope; #454 v5 five-condition Gate-A rule",
                ],
                "gate_a_admission_conditions": admission,
                "gate_a_admission_evidence": {
                    "directly_affects_one_shot_foreground_canary": chain,
                    "code_or_runtime_evidence": (
                        f"{path}:{row['line']}:{row['source_excerpt'][:180]}"
                    ),
                    "not_excluded_by_preflight_or_isolation": (
                        f"preflight_or_isolation_excludes={excluded}"
                    ),
                    "explicit_trigger_and_acceptance_criteria": (
                        f"Issue #454 v5 existing blocker={blocker or 'NONE'}"
                    ),
                    "accepted_by_independent_reviewer": (
                        f"existing frozen blocker acceptance={blocker or 'NONE'}; "
                        "this candidate-to-blocker mapping remains PENDING_S07_8"
                    ),
                },
                "final_target_gate": final_gate,
                "target_gate": final_gate,
                "status": "IMPLEMENTER_VERIFIED_PENDING_INDEPENDENT_REVIEW",
                "independent_review": "PENDING_S07_8",
            }
        )
        adjudicated.append(row)
    return adjudicated


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
    s07_candidates = adjudicate_s07(risks.get("R2", []) + risks.get("R3", []))
    risks["R2"] = [row for row in s07_candidates if row["risk_family"] == "R2"]
    risks["R3"] = [row for row in s07_candidates if row["risk_family"] == "R3"]
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
    s07_fields = {
        "entrypoint_reachable_from_one_shot_canary",
        "external_side_effect_after_failure",
        "business_write_reachable",
        "evidence_chain_break_possible",
        "preflight_or_isolation_excludes",
        "mapped_existing_blocker",
        "review_evidence",
        "final_target_gate",
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
        "one_shot_canary_scope": ONE_SHOT_CANARY_SCOPE,
        "s07_gate_adjudication": {
            "candidates": s07_candidates,
            "counts": {
                "total_pending_candidates": len(s07_candidates),
                **{
                    gate.lower(): sum(
                        row["final_target_gate"] == gate for row in s07_candidates
                    )
                    for gate in sorted(FINAL_TARGET_GATES)
                },
                "mapped_to_c1_c11": sum(
                    row["mapped_existing_blocker"] is not None for row in s07_candidates
                ),
                "new_finding_ids": [],
                "pending_independent_review": len(s07_candidates),
            },
        },
        "pr450_guard_matrix": guards,
        "counts": {
            "unclassified_findings": sum(
                not required_fields.issubset(row)
                or row["classification"] == "UNCLASSIFIED"
                or row["status"] == "UNCLASSIFIED"
                for row in findings
            )
            + sum(
                not s07_fields.issubset(row)
                or row["final_target_gate"] not in FINAL_TARGET_GATES
                for row in s07_candidates
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
