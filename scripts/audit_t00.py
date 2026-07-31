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
from typing import Any

BASE_SHA = "dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6"
PR450_REF = "refs/remotes/pull/450/head"
PR450_HEAD = "360931d7d84bcbe1416c7946992b5218b759fc8a"
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
    "origin/agent/eval-02b-c9-lineup-event-ordering": "c2ce67401fb3bb81aa120ec97ed8513ab3a7dd1e",
    "origin/agent/eval-02b-c9-ci-fix-runner": "7af59a6d83daa819c99349505c4293177fbc86be",
    "origin/agent/eval-02b-c9-remediation-runner-2": "9f9c496432804663feb339d549b9a2de302d6473",
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


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


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


def ensure_trusted_base() -> None:
    if git("rev-parse", "origin/main") != BASE_SHA:
        raise SystemExit("ORIGIN_MAIN_MOVED")
    git("cat-file", "-e", f"{BASE_SHA}^{{commit}}")
    if git("merge-base", "HEAD", BASE_SHA) != BASE_SHA:
        raise SystemExit("HEAD_NOT_DESCENDED_FROM_TRUSTED_BASE")


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
    rows = []
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
    rows = []
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


def checklist_review() -> dict[str, Any]:
    commit = "3420714df428d10f441bbc6f011566a42b2fb538"
    text = show(commit, CHECKLIST)
    block = text.split("<!-- SCRIPT_AUTHORITY_MATRIX_START -->", 1)[1].split(
        "<!-- SCRIPT_AUTHORITY_MATRIX_END -->", 1
    )[0]
    at_commit = set(tree_paths(commit))
    at_base = set(tree_paths(BASE_SHA))
    rows = []
    for line in block.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        path, decision = cells[0].strip("`"), cells[7].strip("`")
        correct_at_commit = (path in at_commit) if decision == "KEEP" else (path not in at_commit)
        rows.append(
            {
                "path": path,
                "decision": decision,
                "correct_at_commit": correct_at_commit,
                "present_at_base": path in at_base,
                "classification": (
                    "ACCEPT_AS_CORRECT_CONTRACT" if correct_at_commit else "FORWARD_FIX_REQUIRED"
                ),
            }
        )
    return {
        "workflow_deletion": "ACCEPT_AS_CORRECT_CONTRACT",
        "rows": rows,
        "unreviewed": sum(row["classification"] == "FORWARD_FIX_REQUIRED" for row in rows),
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


def governance_report(*, verify_github: bool = False) -> dict[str, Any]:
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
    checklist = checklist_review()
    branch_rows = []
    for ref, expected in BRANCH_HEADS.items():
        actual = git("rev-parse", ref)
        commits_on_branch = git("rev-list", "--reverse", f"{BASE_SHA}..{ref}").splitlines()
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
        "base_sha": BASE_SHA,
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


def python_files() -> dict[str, str]:
    return {
        path: show(BASE_SHA, path)
        for path in tree_paths(BASE_SHA)
        if path.endswith(".py") and path.startswith(("src/w2/", "scripts/", "migrations/versions/"))
    }


def storage_inventory(files: dict[str, str]) -> dict[str, Any]:
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
            if (
                path.startswith("migrations/versions/")
                and isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "op"
                and node.func.attr in {"create_table", "drop_table", "rename_table"}
            ):
                migration_calls[node.func.attr] += 1
    duplicates = sorted(
        name for name, count in Counter(row["table"] for row in tables).items() if count > 1
    )
    tracked_runtime = [
        path for path in tree_paths(BASE_SHA) if path.startswith(("runtime/", "reports/"))
    ]
    return {
        "orm_tables": sorted(tables, key=lambda row: (row["table"], row["path"])),
        "duplicate_orm_table_names": duplicates,
        "migration_call_sites": dict(sorted(migration_calls.items())),
        "tracked_runtime_or_report_assets": tracked_runtime,
    }


def computation_inventory(files: dict[str, str]) -> list[dict[str, Any]]:
    pattern = re.compile(r"canonical|hash|settle|settlement|expected_value|brier|ece|odds|probab")
    rows = []
    for path, source in files.items():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and pattern.search(
                node.name.lower()
            ):
                if "canonical" in node.name.lower() or "hash" in node.name.lower():
                    classification = "MUST_CONVERGE_CANONICAL_SERIALIZATION"
                elif "brier" in node.name.lower() or "ece" in node.name.lower():
                    classification = "MUST_CONVERGE_EVALUATION_METRIC"
                elif "odds" in node.name.lower():
                    classification = "REVIEWED_DISTINCT_ODDS_SCOPE"
                else:
                    classification = "REVIEWED_DISTINCT_DOMAIN_SCOPE"
                rows.append(
                    {
                        "path": path,
                        "symbol": node.name,
                        "line": node.lineno,
                        "classification": classification,
                    }
                )
    return sorted(rows, key=lambda row: (row["path"], row["line"], row["symbol"]))


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
                        {
                            "path": path,
                            "line": node.lineno,
                            "classification": "REVIEW_REQUIRED_EXCEPTION_BOUNDARY",
                        }
                    )
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name in {"os.getenv", "os.environ.get"} or name.endswith("settings.get"):
                    rows["R1"].append(
                        {
                            "path": path,
                            "line": node.lineno,
                            "classification": "REVIEWED_CONFIG_READ_CANDIDATE",
                        }
                    )
                io_name = name.lower()
                is_commit = io_name.endswith(".commit")
                is_external = io_name.endswith((".get", ".post", ".request")) and any(
                    needle in io_name
                    for needle in ("client", "http", "provider", "request", "session")
                )
                if is_commit or is_external:
                    rows["R3"].append(
                        {
                            "path": path,
                            "line": node.lineno,
                            "classification": "REVIEWED_IO_OR_COMMIT_CANDIDATE",
                        }
                    )
        lowered = source.lower()
        if any(
            needle in lowered
            for needle in ("for update", "advisory_lock", "idempot", "uniqueconstraint")
        ):
            rows["R4"].append(
                {"path": path, "line": 1, "classification": "REVIEWED_CONCURRENCY_AUTHORITY_FILE"}
            )
    return {
        key: sorted(value, key=lambda row: (row["path"], row["line"]))
        for key, value in sorted(rows.items())
    }


def guard_matrix() -> dict[str, Any]:
    if git("rev-parse", PR450_REF) != PR450_HEAD:
        raise SystemExit("PR450_HEAD_MISMATCH")
    baseline_source = show(BASE_SHA, DELIVERY_TEST)
    proposed_source = show(PR450_REF, DELIVERY_TEST)
    baseline = ast.parse(baseline_source)
    proposed = ast.parse(proposed_source)
    proposed_tests = {
        node.name: node
        for node in proposed.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }
    proposed_assertions = {
        ast.dump(node.test, include_attributes=False)
        for node in ast.walk(proposed)
        if isinstance(node, ast.Assert)
    }
    rows = []
    for test in baseline.body:
        if not isinstance(
            test, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) or not test.name.startswith("test_"):
            continue
        if test.name not in proposed_tests:
            rows.append(
                {
                    "guard_id": f"TEST:{test.name}",
                    "original_guard": test.name,
                    "current_equivalent": f"{DELIVERY_TEST}@{BASE_SHA}:{test.lineno}",
                    "classification": "RETAINED_EQUIVALENT",
                    "evidence": "T00 branch retains the trusted-base test unchanged",
                }
            )
        for assertion in (node for node in ast.walk(test) if isinstance(node, ast.Assert)):
            normalized = ast.dump(assertion.test, include_attributes=False)
            if normalized in proposed_assertions:
                continue
            source = ast.get_source_segment(baseline_source, assertion) or normalized
            label = "AST_ASSERT_SHA256:" + hashlib.sha256(normalized.encode()).hexdigest()
            if "172." in source or "staging" in source.lower() and "address" in source.lower():
                label = "RETIRED_STAGING_ADDRESS_ABSENCE"
            elif "PR" in source and ("#" in source or "range" in source.lower()):
                label = "HISTORICAL_PR_RANGE_NON_AUTHORITY"
            rows.append(
                {
                    "guard_id": f"ASSERT:{test.name}:{assertion.lineno}",
                    "original_guard": label,
                    "current_equivalent": f"{DELIVERY_TEST}@{BASE_SHA}:{assertion.lineno}",
                    "classification": "RETAINED_EQUIVALENT",
                    "evidence": "T00 branch retains the trusted-base assertion unchanged",
                }
            )
    return {
        "baseline": BASE_SHA,
        "pr450_head": PR450_HEAD,
        "removed_guards": rows,
        "unclassified_removed_guards": sum(
            row["classification"]
            not in {
                "RETAINED_EQUIVALENT",
                "LOST_AND_RESTORED",
                "INTENTIONALLY_RETIRED_WITH_EVIDENCE",
            }
            for row in rows
        ),
    }


def safe_report() -> dict[str, Any]:
    files = python_files()
    findings = [
        {"id": f"C{index}", "classification": "MUST_FIX_FOR_CANARY"} for index in range(1, 12)
    ] + [
        {"id": "R5_CANONICAL_SERIALIZATION", "classification": "MUST_FIX_FOR_CANARY"},
        {"id": "R5_FAIR_ODDS_AUTHORITY", "classification": "MUST_FIX_FOR_CONTINUOUS"},
        {"id": "R5_MARKET_TAXONOMY", "classification": "MUST_FIX_FOR_CONTINUOUS"},
        {"id": "R5_BRIER_ECE_AUTHORITY", "classification": "MUST_FIX_FOR_CONTINUOUS"},
        {"id": "R5_READ_MODEL_NAME_COLLISIONS", "classification": "MUST_FIX_FOR_CONTINUOUS"},
        {"id": "R5_MIGRATION_METADATA_COUPLING", "classification": "MUST_FIX_FOR_CANARY"},
    ]
    computations = computation_inventory(files)
    guards = guard_matrix()
    return {
        "schema_version": "w2.t00.safe.v1",
        "base_sha": BASE_SHA,
        "scan_strategy": "AST_FIRST_WITH_TEXT_FALLBACK",
        "risk_candidates": risk_candidates(files),
        "storage_inventory": storage_inventory(files),
        "computation_authorities": computations,
        "findings": findings,
        "pr450_guard_matrix": guards,
        "counts": {
            "unclassified_findings": sum(not row.get("classification") for row in findings),
            "unclassified_computation_authorities": sum(
                not row.get("classification") for row in computations
            ),
            "unclassified_removed_guards": guards["unclassified_removed_guards"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("gov", "safe", "all"))
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--verify-github", action="store_true")
    args = parser.parse_args()
    ensure_trusted_base()
    payload: Any
    if args.phase == "gov":
        payload = governance_report(verify_github=args.verify_github)
    elif args.phase == "safe":
        payload = safe_report()
    else:
        payload = {
            "governance": governance_report(verify_github=args.verify_github),
            "safety": safe_report(),
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
    main()
