#!/usr/bin/env python3
"""Reproducible, exact-base-bound T00 governance and safety inventory."""

from __future__ import annotations

import argparse
import ast
import builtins
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
INCLUDED_PRODUCTION_ROOTS = ("apps/", "migrations/", "scripts/", "src/w2/")
EXCLUDED_PYTHON_ROOTS = {
    "tests/": "TEST_ONLY_NOT_PART_OF_PRODUCTION_DENOMINATOR",
}

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
SCRIPT_MATRIX_CARRY_FORWARD_FIELDS = {
    "role": "CARRY_TO_PR450_DOCUMENTATION_REPAIR",
}
SCRIPT_MATRIX_COLUMN_ORDER = (
    "path",
    "role",
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

PROPOSED_TARGET_GATES = {
    "PROPOSED_GATE_A",
    "PROPOSED_GATE_B",
    "PROPOSED_GATE_C",
    "PROPOSED_GATE_D",
    "PROPOSED_SAFE_DEGRADATION",
    "PROPOSED_ACCEPTED_WITH_REASON",
}

# Every mapping is bound to one exact AST candidate coordinate. The scanner
# converts these coordinates to candidate IDs and never falls back by function.
EXACT_BLOCKER_SPECS = (
    ("R2", "src/w2/ingestion/future_refresh.py", 806, "C6"),
    ("R2", "src/w2/ingestion/future_refresh.py", 824, "C6"),
    ("R2", "src/w2/ingestion/future_refresh.py", 878, "C7"),
    ("R2", "src/w2/ingestion/future_refresh.py", 1061, "C6,C11"),
    ("R2", "src/w2/ingestion/future_refresh.py", 1159, "C9"),
    ("R2", "src/w2/ingestion/future_refresh.py", 1181, "C6"),
    ("R2", "src/w2/ingestion/future_refresh.py", 2098, "C6"),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 194, "C6,C11"),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 292, "C9"),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 295, "C9"),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 2434, "C6,C11"),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 2575, "C6,C11"),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 2614, "C6,C11"),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 2648, "C11"),
    ("R2", "src/w2/prematch/analysis_calculator.py", 1942, "C8"),
    ("R2", "src/w2/prematch/analysis_calculator.py", 2047, "C9"),
    ("R2", "src/w2/prematch/read_model_projection.py", 351, "C9"),
    ("R2", "src/w2/prematch/read_model_projection.py", 961, "C9"),
    ("R2", "src/w2/providers/ledger.py", 98, "C11-A"),
    ("R2", "src/w2/providers/ledger.py", 100, "C11-A"),
    ("R2", "src/w2/providers/ledger.py", 142, "C11-A"),
    ("R3", "src/w2/ingestion/future_refresh_repository.py", 186, "C6,C11"),
    ("R3", "src/w2/ingestion/future_refresh_repository.py", 290, "C9"),
    ("R3", "src/w2/ingestion/future_refresh_repository.py", 2433, "C6,C11"),
    ("R3", "src/w2/ingestion/future_refresh_repository.py", 2573, "C6,C11"),
    ("R3", "src/w2/ingestion/future_refresh_repository.py", 2613, "C6,C11"),
    ("R3", "src/w2/matchday/repository.py", 192, "C5,C6"),
    ("R3", "src/w2/matchday/repository.py", 321, "C5"),
    ("R3", "src/w2/matchday/repository.py", 387, "C6,C11"),
    ("R3", "src/w2/matchday/repository.py", 415, "C6,C11"),
    ("R3", "src/w2/matchday/repository.py", 453, "C6"),
    ("R3", "src/w2/matchday/repository.py", 514, "C3,C6"),
    ("R3", "src/w2/prematch/read_model_projection.py", 960, "C9"),
    ("R3", "src/w2/providers/ledger.py", 97, "C11-A"),
    ("R3", "src/w2/providers/ledger.py", 141, "C11-A"),
)
INDEPENDENT_BLOCKER_SCOPES = {
    "C10": "FOREGROUND_ISOLATION_COMPOSE_RESTART_NO",
}

# These are the 30 exact candidates that carried the prior Wave-1 Gate-A
# templates. They remain proposals; the five other blocker mappings do not.
PROPOSED_TEST_CONTRACT_SPECS = {
    (family, path, line)
    for family, path, line, _ in EXACT_BLOCKER_SPECS
} - {
    ("R2", "src/w2/ingestion/future_refresh.py", 1061),
    ("R2", "src/w2/ingestion/future_refresh_repository.py", 2648),
    ("R2", "src/w2/prematch/analysis_calculator.py", 1942),
    ("R2", "src/w2/providers/ledger.py", 100),
    ("R2", "src/w2/providers/ledger.py", 142),
}

NETWORK_CALLS = {
    "urllib.request.urlopen": "NETWORK_TRANSPORT",
    "requests.request": "NETWORK_TRANSPORT",
    "httpx.request": "NETWORK_TRANSPORT",
    "aiohttp.request": "NETWORK_TRANSPORT",
    "socket.create_connection": "NETWORK_TRANSPORT",
}
NETWORK_METHODS = {"request", "send", "get", "post", "put", "patch", "delete"}
REDIS_KV_METHODS = {
    "append": "REDIS_KV_WRITE",
    "decr": "REDIS_KV_COUNTER_WRITE",
    "decrby": "REDIS_KV_COUNTER_WRITE",
    "delete": "REDIS_KV_DELETE",
    "eval": "REDIS_KV_SCRIPT_WRITE",
    "expire": "REDIS_KV_EXPIRY_WRITE",
    "expireat": "REDIS_KV_EXPIRY_WRITE",
    "hdel": "REDIS_KV_DELETE",
    "hmset": "REDIS_KV_WRITE",
    "hset": "REDIS_KV_WRITE",
    "incr": "REDIS_KV_COUNTER_WRITE",
    "incrby": "REDIS_KV_COUNTER_WRITE",
    "lpush": "REDIS_KV_WRITE",
    "pexpire": "REDIS_KV_EXPIRY_WRITE",
    "pexpireat": "REDIS_KV_EXPIRY_WRITE",
    "psetex": "REDIS_KV_WRITE",
    "rpush": "REDIS_KV_WRITE",
    "sadd": "REDIS_KV_WRITE",
    "set": "REDIS_KV_WRITE",
    "setex": "REDIS_KV_WRITE",
    "setnx": "REDIS_KV_WRITE",
    "xadd": "REDIS_KV_STREAM_WRITE",
    "xdel": "REDIS_KV_DELETE",
    "zadd": "REDIS_KV_WRITE",
    "zrem": "REDIS_KV_DELETE",
}
LOCK_DURABILITY_CALLS = {
    "fcntl.flock": "FILE_LOCK_OPERATION",
    "os.fdatasync": "FILE_DURABILITY_SYNC",
    "os.fsync": "FILE_DURABILITY_SYNC",
}
PROCESS_EXECUTION_CALLS = {
    "subprocess.Popen": "PROCESS_EXECUTION",
    "subprocess.check_call": "PROCESS_EXECUTION",
    "subprocess.check_output": "PROCESS_EXECUTION",
    "subprocess.run": "PROCESS_EXECUTION",
}
FILE_CALLS = {
    "os.remove": "FILE_DELETE",
    "os.rename": "FILE_RENAME",
    "os.replace": "FILE_REPLACE",
    "os.unlink": "FILE_DELETE",
    "shutil.copy2": "FILE_COPY",
    "shutil.copytree": "FILE_TREE_COPY",
    "shutil.rmtree": "FILE_TREE_DELETE",
}
DB_METHODS = {
    "add": "DB_WRITE_STAGE",
    "add_all": "DB_WRITE_STAGE",
    "bulk_insert_mappings": "DB_WRITE_STAGE",
    "bulk_save_objects": "DB_WRITE_STAGE",
    "commit": "DB_COMMIT",
    "delete": "DB_WRITE_STAGE",
    "execute": "DB_EXECUTE",
    "flush": "DB_FLUSH",
    "merge": "DB_WRITE_STAGE",
    "rollback": "DB_ROLLBACK",
}
FILE_METHODS = {
    "exists": "FILE_READ",
    "is_dir": "FILE_READ",
    "is_file": "FILE_READ",
    "read": "FILE_READ",
    "read_bytes": "FILE_READ",
    "read_text": "FILE_READ",
    "stat": "FILE_READ",
    "write": "FILE_WRITE",
    "writelines": "FILE_WRITE",
    "write_bytes": "FILE_WRITE",
    "write_text": "FILE_WRITE",
    "replace": "FILE_REPLACE",
    "rename": "FILE_RENAME",
    "unlink": "FILE_DELETE",
}
EXTERNAL_WRITE_METHODS = {
    "put_object": "OBJECT_STORE_WRITE",
    "upload_file": "OBJECT_STORE_WRITE",
    "upload_fileobj": "OBJECT_STORE_WRITE",
    "delete_object": "OBJECT_STORE_DELETE",
    "publish": "MESSAGE_PUBLISH",
    "send_message": "MESSAGE_SEND",
}
IO_RECEIVER_MARKERS = (
    "bucket",
    "cache",
    "client",
    "conn",
    "connection",
    "database",
    "db",
    "engine",
    "file",
    "handle",
    "http",
    "kv",
    "provider",
    "queue",
    "redis",
    "session",
    "socket",
    "stream",
    "transport",
)
CALL_DISPOSITIONS = (
    "INTERNAL_PROJECT_CALL",
    "KNOWN_PURE_OR_LOCAL_TRANSFORM",
    "RECOGNIZED_SIDE_EFFECT_PRIMITIVE",
    "UNRESOLVED_EXTERNAL_CALL",
    "UNRESOLVED_DYNAMIC_CALL",
)
KNOWN_PURE_CALLS = {
    **{
        f"builtins.{name}": "reviewed deterministic builtin or local-container transform"
        for name in (
            "abs",
            "all",
            "any",
            "bool",
            "bytes",
            "dict",
            "enumerate",
            "filter",
            "float",
            "frozenset",
            "int",
            "isinstance",
            "issubclass",
            "len",
            "list",
            "map",
            "max",
            "min",
            "range",
            "repr",
            "reversed",
            "round",
            "set",
            "slice",
            "sorted",
            "str",
            "sum",
            "tuple",
            "type",
            "zip",
        )
    },
    "copy.copy": "reviewed in-memory object copy",
    "copy.deepcopy": "reviewed in-memory object copy",
    "dataclasses.asdict": "reviewed in-memory dataclass transform",
    "hashlib.sha256": "reviewed in-memory digest constructor",
    "json.dumps": "reviewed in-memory JSON encoding",
    "json.loads": "reviewed in-memory JSON decoding",
    "re.compile": "reviewed in-memory regular-expression compilation",
    "re.escape": "reviewed in-memory regular-expression escaping",
    "re.fullmatch": "reviewed in-memory regular-expression match",
    "re.match": "reviewed in-memory regular-expression match",
    "re.search": "reviewed in-memory regular-expression search",
    "re.sub": "reviewed in-memory regular-expression substitution",
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
        "status": (
            "EVIDENCE_ATTACHED_PENDING_INDEPENDENT_REVIEW"
            if valid and proof
            else "CONFLICT"
        ),
        "independent_review": "PENDING_INDEPENDENT_REVIEW",
        "independently_verified": False,
        "declared_at": declared_at,
        "evidence": _unique_evidence(proof),
    }


FIELD_REVIEW_RULES = {
    "path": (
        "G10_7_PATH_EXACT_OBJECT",
        "compare declared path presence with the exact 3420714d tree and decision",
        "exact git tree/source object",
    ),
    "caller": (
        "G10_7_CALLER_EXACT_REFERENCE",
        "require an exact repository reference outside the declared source and checklist",
        "exact git grep reference",
    ),
    "transitive_chain": (
        "G10_7_CHAIN_SEMANTIC_EXCEPTION",
        "retain every declared transitive chain as an exception until independently traced",
        "attached call/reference evidence",
    ),
    "environment": (
        "G10_7_ENVIRONMENT_SEMANTIC_EXCEPTION",
        "retain every environment declaration as an exception until independently resolved",
        "attached source/reference evidence",
    ),
    "deployment_reference": (
        "G10_7_DEPLOYMENT_EXACT_REFERENCE",
        "prove positive deployment declarations only with an exact deployment-file reference",
        "workflow/Dockerfile/compose/service/package/pyproject reference",
    ),
    "runbook_reference": (
        "G10_7_RUNBOOK_EXACT_REFERENCE_OR_ABSENCE",
        "prove a named runbook by exact docs/runbooks reference or 'none' by exact "
        "zero-match evidence",
        "exact docs/runbooks git grep",
    ),
    "decision": (
        "G10_7_DECISION_TREE_CONTRACT",
        "compare KEEP/DELETE and role contract with exact path presence at 3420714d",
        "exact git tree plus declared matrix row",
    ),
    "evidence": (
        "G10_7_EVIDENCE_CODE_SEMANTIC_EXCEPTION",
        "retain evidence-code meaning as an exception until independently interpreted",
        "attached source/reference/test/deployment evidence",
    ),
}


def _field_rule_proves(
    field_type: str, row: dict[str, Any], field: dict[str, Any]
) -> bool:
    if field["status"] != "EVIDENCE_ATTACHED_PENDING_INDEPENDENT_REVIEW":
        return False
    evidence = field["evidence"]
    if field_type == "path":
        return bool(evidence) and row["correct_at_commit"]
    if field_type == "caller":
        return any(
            item.get("path") not in {None, row["path"], CHECKLIST}
            and bool(item.get("excerpt"))
            for item in evidence
        )
    if field_type in {"transitive_chain", "environment", "evidence"}:
        return False
    if field_type == "deployment_reference":
        if field["value"] != "是":
            return False
        return any(
            item.get("path", "").startswith(".github/workflows/")
            or "Dockerfile" in item.get("path", "")
            or "compose" in item.get("path", "").lower()
            or item.get("path", "").endswith(
                (".service", "package.json", "pyproject.toml")
            )
            for item in evidence
        )
    if field_type == "runbook_reference":
        if field["value"] == "无":
            return any(
                "git grep exact path under docs/runbooks" in item.get("git_evidence", "")
                and "0 match(es)" in item.get("git_evidence", "")
                for item in evidence
            )
        return any(item.get("path", "").startswith("docs/runbooks/") for item in evidence)
    if field_type == "decision":
        return row["correct_at_commit"] and any(
            item.get("git_evidence", "").startswith("decision=") for item in evidence
        )
    raise AuditError(f"UNASSIGNED_FIELD_REVIEW_RULE: {field_type}")


def grouped_field_review_bundle(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    assigned: list[str] = []
    for field_type in SCRIPT_MATRIX_FIELDS:
        rule_id, algorithm, evidence_source = FIELD_REVIEW_RULES[field_type]
        population: list[tuple[dict[str, Any], dict[str, Any]]] = [
            (row, row["field_reviews"][field_type]) for row in rows
        ]
        covered = [
            field["field_id"]
            for row, field in population
            if _field_rule_proves(field_type, row, field)
        ]
        exceptions = [
            field["field_id"]
            for row, field in population
            if not _field_rule_proves(field_type, row, field)
        ]
        assigned.extend(field["field_id"] for _, field in population)
        groups.append(
            {
                "field_rule_id": rule_id,
                "field_type": field_type,
                "verification_algorithm": algorithm,
                "population_count": len(population),
                "evidence_source": evidence_source,
                "covered_field_ids": covered,
                "exception_field_ids": exceptions,
                "independent_review_status": "PENDING_INDEPENDENT_REVIEW",
                "accepted_by_independent_reviewer": False,
            }
        )
    all_fields = [
        field["field_id"]
        for row in rows
        for field in row["field_reviews"].values()
    ]
    assignment_counts = Counter(assigned)
    unassigned = sorted(set(all_fields) - set(assigned))
    duplicates = sorted(field_id for field_id, count in assignment_counts.items() if count != 1)
    if unassigned or duplicates:
        raise AuditError("G10_7_FIELD_RULE_ACCOUNTING_FAILED")
    exception_count = sum(len(group["exception_field_ids"]) for group in groups)
    return {
        "rule_groups": groups,
        "counts": {
            "field_review_total": len(all_fields),
            "field_review_rule_groups": len(groups),
            "field_review_rule_covered": len(all_fields) - exception_count,
            "field_review_exceptions": exception_count,
            "unassigned_fields": len(unassigned),
            "duplicate_field_assignments": len(duplicates),
            "independently_verified_fields": 0,
        },
    }


def validate_script_matrix_columns(column_types: tuple[str, ...], cell_count: int) -> None:
    accounted = set(SCRIPT_MATRIX_FIELDS) | set(SCRIPT_MATRIX_CARRY_FORWARD_FIELDS)
    if (
        column_types != SCRIPT_MATRIX_COLUMN_ORDER
        or len(column_types) != len(accounted)
        or set(column_types) != accounted
        or cell_count != len(column_types)
    ):
        raise AuditError("UNASSIGNED_SCRIPT_MATRIX_COLUMN")


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
        validate_script_matrix_columns(SCRIPT_MATRIX_COLUMN_ORDER, len(values))
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
        for field_type, field in field_reviews.items():
            field.update(
                {
                    "field_id": hashlib.sha256(
                        f"3420714d:{path}:{matrix_line}:{field_type}".encode()
                    ).hexdigest(),
                    "field_type": field_type,
                }
            )
        rows.append(
            {
                "path": path,
                "role": role,
                "carry_forward_fields": {
                    "role": {
                        "field_id": hashlib.sha256(
                            f"3420714d:{path}:{matrix_line}:role".encode()
                        ).hexdigest(),
                        "field_type": "role",
                        "value": role,
                        "disposition": SCRIPT_MATRIX_CARRY_FORWARD_FIELDS["role"],
                        "independent_review_status": "NOT_REQUESTED_IN_PR458",
                        "accepted_by_independent_reviewer": False,
                        "independently_verified": False,
                    }
                },
                "decision": decision,
                "correct_at_commit": correct_at_commit,
                "present_at_base": path in at_base,
                "field_reviews": field_reviews,
                "classification": (
                    "EVIDENCE_ATTACHED_PENDING_INDEPENDENT_REVIEW"
                    if all(
                        field["status"]
                        == "EVIDENCE_ATTACHED_PENDING_INDEPENDENT_REVIEW"
                        for field in field_reviews.values()
                    )
                    else "CONFLICTING_EVIDENCE"
                ),
            }
        )
    fields = [field for row in rows for field in row["field_reviews"].values()]
    carried_fields = [
        field for row in rows for field in row["carry_forward_fields"].values()
    ]
    cell_universe = len(rows) * len(SCRIPT_MATRIX_COLUMN_ORDER)
    unassigned_fields = cell_universe - len(fields) - len(carried_fields)
    if unassigned_fields:
        raise AuditError("SCRIPT_MATRIX_CELL_ACCOUNTING_FAILED")
    review_bundle = grouped_field_review_bundle(rows)
    return {
        "workflow_deletion": "ACCEPT_AS_CORRECT_CONTRACT",
        "rows": rows,
        "grouped_field_review_bundle": review_bundle,
        "script_matrix_rows": len(rows),
        "script_matrix_columns": len(SCRIPT_MATRIX_COLUMN_ORDER),
        "script_matrix_cell_universe": cell_universe,
        "currently_accounted_fields": len(fields),
        "role_fields_carried_to_pr450": len(carried_fields),
        "unassigned_fields": unassigned_fields,
        "script_matrix_fields": len(fields),
        "evidence_attached_pending_independent_review_fields": sum(
            field["status"] == "EVIDENCE_ATTACHED_PENDING_INDEPENDENT_REVIEW"
            for field in fields
        ),
        "independently_verified_fields": sum(field["independently_verified"] for field in fields),
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


def _python_root(path: str) -> str:
    parts = Path(path).parts
    if len(parts) == 1:
        return "./"
    if parts[0] == "src" and len(parts) > 2:
        return f"src/{parts[1]}/"
    return f"{parts[0]}/"


def production_python_scope(base_sha: str) -> dict[str, Any]:
    python_paths = [path for path in tree_paths(base_sha) if path.endswith(".py")]
    discovered_roots = sorted({_python_root(path) for path in python_paths})
    classified_roots = set(INCLUDED_PRODUCTION_ROOTS) | set(EXCLUDED_PYTHON_ROOTS)
    unclassified_roots = sorted(set(discovered_roots) - classified_roots)
    if unclassified_roots:
        raise AuditError(
            "UNCLASSIFIED_PYTHON_ROOTS: "
            f"{','.join(unclassified_roots)}; add each root to INCLUDED_PRODUCTION_ROOTS "
            "or EXCLUDED_PYTHON_ROOTS with an explicit reviewed reason"
        )
    return {
        "included_production_roots": list(INCLUDED_PRODUCTION_ROOTS),
        "excluded_python_roots": [
            {"root": root, "reason": reason}
            for root, reason in sorted(EXCLUDED_PYTHON_ROOTS.items())
        ],
        "discovered_python_roots": discovered_roots,
        "unclassified_python_roots": unclassified_roots,
    }


def python_files(base_sha: str) -> dict[str, str]:
    production_python_scope(base_sha)
    return {
        path: show(base_sha, path)
        for path in tree_paths(base_sha)
        if path.endswith(".py") and path.startswith(INCLUDED_PRODUCTION_ROOTS)
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


def _control_nodes(node: ast.AST) -> list[ast.AST]:
    """Return handler control-flow nodes without descending into nested scopes."""
    rows: list[ast.AST] = []

    def visit(current: ast.AST) -> None:
        if current is not node and isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            return
        rows.append(current)
        for child in ast.iter_child_nodes(current):
            visit(child)

    visit(node)
    return rows


def _statement_terminates(node: ast.stmt) -> bool:
    if isinstance(node, (ast.Raise, ast.Return, ast.Continue, ast.Break)):
        return True
    if isinstance(node, ast.If):
        return bool(node.orelse) and _block_terminates(node.body) and _block_terminates(node.orelse)
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return _block_terminates(node.body)
    if isinstance(node, ast.Try):
        if _block_terminates(node.finalbody):
            return True
        return bool(node.handlers) and _block_terminates(node.body) and all(
            _block_terminates(handler.body) for handler in node.handlers
        )
    return False


def _block_terminates(body: list[ast.stmt]) -> bool:
    return any(_statement_terminates(statement) for statement in body)


def _handler_action(node: ast.ExceptHandler) -> tuple[str, list[str]]:
    control_nodes = _control_nodes(node)
    calls = [ast.unparse(child.func) for child in control_nodes if isinstance(child, ast.Call)]
    lowered = [call.lower() for call in calls]
    direct_raises = sum(isinstance(child, ast.Raise) for child in control_nodes)
    all_paths_terminate = _block_terminates(node.body)
    if direct_raises:
        return (
            "RAISE_TERMINAL" if all_paths_terminate else "CONDITIONAL_RAISE_WITH_FALLTHROUGH",
            calls,
        )
    if any("rollback" in call for call in lowered):
        return "ROLLBACK_THEN_CONTINUE", calls
    if any(isinstance(child, ast.Continue) for child in ast.walk(node)):
        return "CONTINUE", calls
    if any(isinstance(child, ast.Return) for child in ast.walk(node)):
        return "RETURN", calls
    if any(isinstance(child, ast.Pass) for child in node.body):
        return "PASS", calls
    if any(
        marker in call
        for call in lowered
        for marker in ("log", "diagnostic", "warning", "notes.append", "errors.append")
    ):
        return "DIAGNOSTIC_THEN_CONTINUE", calls
    if any(
        marker in call
        for call in lowered
        for marker in ("recover", "restore", "fallback", "reset")
    ):
        return "RECOVERY_CALL_THEN_CONTINUE", calls
    if node.body and all(isinstance(child, ast.Expr) for child in node.body) and calls:
        return "CALL_ONLY_THEN_CONTINUE", calls
    return "STATE_UPDATE_THEN_CONTINUE", calls


def _candidate_id(family: str, path: str, line: int, discriminator: str = "") -> str:
    return hashlib.sha256(f"{family}:{path}:{line}:{discriminator}".encode()).hexdigest()


def _io_call(node: ast.Call, name: str) -> tuple[str, str] | None:
    lowered = name.lower()
    attribute = node.func.attr.lower() if isinstance(node.func, ast.Attribute) else ""
    receiver_names = {
        child.id.lower()
        for child in ast.walk(node.func.value)
        if isinstance(child, ast.Name)
    } | {
        child.attr.lower()
        for child in ast.walk(node.func.value)
        if isinstance(child, ast.Attribute)
    } if isinstance(node.func, ast.Attribute) else set()

    def receiver_matches(markers: tuple[str, ...]) -> bool:
        return any(
            identifier == marker
            or identifier.startswith(f"{marker}_")
            or identifier.endswith(f"_{marker}")
            for identifier in receiver_names
            for marker in markers
        )

    if name in NETWORK_CALLS:
        return NETWORK_CALLS[name], "RECOGNIZED_IO_PRIMITIVE"
    if name in LOCK_DURABILITY_CALLS:
        return LOCK_DURABILITY_CALLS[name], "RECOGNIZED_IO_PRIMITIVE"
    if name in PROCESS_EXECUTION_CALLS:
        return PROCESS_EXECUTION_CALLS[name], "RECOGNIZED_IO_PRIMITIVE"
    if name in FILE_CALLS:
        return FILE_CALLS[name], "RECOGNIZED_IO_PRIMITIVE"
    if name in {"open", "io.open"}:
        mode = "r"
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                mode = str(keyword.value.value)
        operation = "FILE_WRITE" if any(marker in mode for marker in "wax+") else "FILE_READ"
        return operation, "RECOGNIZED_IO_PRIMITIVE"
    if lowered.endswith("write_json_atomic"):
        return "FILE_ATOMIC_WRITE", "RECOGNIZED_IO_PRIMITIVE"
    if attribute in REDIS_KV_METHODS and receiver_matches(("redis", "cache", "kv")):
        return REDIS_KV_METHODS[attribute], "RECOGNIZED_IO_PRIMITIVE"
    if attribute and receiver_matches(("redis", "cache", "kv")):
        return "UNCLASSIFIED_IO_PRIMITIVE", "UNCLASSIFIED"
    if attribute in DB_METHODS and receiver_matches(
        ("session", "database", "db", "connection", "conn", "engine", "table", "op")
    ):
        return DB_METHODS[attribute], "RECOGNIZED_IO_PRIMITIVE"
    if attribute == "get" and receiver_matches(("session",)):
        return "DB_READ", "RECOGNIZED_IO_PRIMITIVE"
    if attribute in NETWORK_METHODS and receiver_matches(
        ("client", "http", "provider", "request", "transport", "url")
    ):
        return "NETWORK_TRANSPORT", "RECOGNIZED_IO_PRIMITIVE"
    if attribute in FILE_METHODS and (
        attribute in {"write_text", "write_bytes", "writelines"}
        or receiver_matches(
            ("file", "path", "stream", "buffer", "handle", "output", "temp", "tmp")
        )
    ):
        return FILE_METHODS[attribute], "RECOGNIZED_IO_PRIMITIVE"
    if attribute in EXTERNAL_WRITE_METHODS:
        return EXTERNAL_WRITE_METHODS[attribute], "RECOGNIZED_IO_PRIMITIVE"
    if attribute and receiver_matches(IO_RECEIVER_MARKERS):
        return "UNCLASSIFIED_IO_PRIMITIVE", "UNCLASSIFIED"
    if name.startswith(("fcntl.", "subprocess.")):
        return "UNCLASSIFIED_IO_PRIMITIVE", "UNCLASSIFIED"
    if any(
        marker in lowered
        for marker in (
            "http",
            "request",
            "urlopen",
            "socket",
            "execute",
            "commit",
            "flush",
            "persist",
            "save_",
            "write_",
            "upload",
            "publish",
            "send_message",
            "put_object",
        )
    ):
        return "UNCLASSIFIED_IO_PRIMITIVE", "UNCLASSIFIED"
    return None


def risk_candidates(
    files: dict[str, str], accounting: dict[str, Any] | None = None
) -> dict[str, list[dict[str, Any]]]:
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
                control_nodes = _control_nodes(node)
                direct_raise_count = sum(isinstance(child, ast.Raise) for child in control_nodes)
                nested_raise_count = (
                    sum(isinstance(child, ast.Raise) for child in ast.walk(node))
                    - direct_raise_count
                )
                all_paths_terminate = _block_terminates(node.body)
                handler_action, handler_calls = _handler_action(node)
                candidate = _candidate(
                    path,
                    node.lineno,
                    "R2",
                    (
                        "R2_HANDLER_ALL_PATHS_TERMINATE_CANDIDATE"
                        if all_paths_terminate
                        else "R2_HANDLER_MAY_CONTINUE_CANDIDATE"
                    ),
                    "ERROR_PROPAGATION_AND_ROLLBACK_CONTRACT",
                    status="PENDING_S07",
                    target_gate="PENDING_S07",
                )
                candidate.update(
                    {
                        "candidate_id": _candidate_id("R2", path, node.lineno),
                        "symbol": _scope_name(node, parents),
                        "operation": (
                            f"except {ast.unparse(node.type)}" if node.type else "bare except"
                        ),
                        "handler_action": handler_action,
                        "handler_calls": handler_calls,
                        "broad_handler": broad,
                        "direct_raise_count": direct_raise_count,
                        "nested_scope_raise_count": nested_raise_count,
                        "all_paths_terminate_handler_control_flow": all_paths_terminate,
                        "may_fallthrough": not all_paths_terminate,
                        "denominator_status": "ENUMERATED_HANDLER",
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
    accounting = accounting or all_call_accounting(files)
    for call in accounting["calls"]:
        disposition = call["disposition"]
        if disposition not in {
            "RECOGNIZED_SIDE_EFFECT_PRIMITIVE",
            "UNRESOLVED_EXTERNAL_CALL",
            "UNRESOLVED_DYNAMIC_CALL",
        }:
            continue
        unresolved = disposition.startswith("UNRESOLVED_")
        candidate = _candidate(
            call["path"],
            call["line"],
            "R3",
            disposition,
            "TRANSACTION_AND_EXTERNAL_IO_CONTRACT",
            status="UNCLASSIFIED" if unresolved else "PENDING_S07",
            target_gate="PENDING_S07",
        )
        candidate.update(
            {
                "candidate_id": call["call_site_id"],
                "call_site_id": call["call_site_id"],
                "caller_id": call["caller_id"],
                "symbol": call["caller_id"].rsplit(":", 1)[-1],
                "operation": call.get("operation", disposition),
                "call": call["call"],
                "callable_signature": call.get("callable_signature"),
                "call_disposition": disposition,
                "io_primitive_status": (
                    "UNCLASSIFIED" if unresolved else "RECOGNIZED_IO_PRIMITIVE"
                ),
                "denominator_status": "ENUMERATED_ALL_CALL_R3",
                "source_excerpt": call["source_excerpt"],
            }
        )
        rows["R3"].append(candidate)
    return {
        key: sorted(value, key=lambda row: (row["path"], row["line"]))
        for key, value in sorted(rows.items())
    }


def _module_path(module: str, files: dict[str, str]) -> str | None:
    if not module.startswith("w2"):
        return None
    stem = "src/" + module.replace(".", "/")
    for candidate in (f"{stem}.py", f"{stem}/__init__.py"):
        if candidate in files:
            return candidate
    return None


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _static_call_edges(files: dict[str, str], base_sha: str) -> list[dict[str, Any]]:
    function_names: dict[str, set[str]] = defaultdict(set)
    class_names: dict[str, set[str]] = defaultdict(set)
    definitions: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    trees: dict[str, ast.Module] = {}
    imports: dict[str, dict[str, tuple[str, str | None]]] = defaultdict(dict)
    external_imports: dict[str, dict[str, str]] = defaultdict(dict)
    for path, source in files.items():
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise AuditError(f"PRODUCTION_PYTHON_SYNTAX_ERROR: {path}:{exc.lineno}") from None
        trees[path] = tree
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_names[path].add(node.name)
                definitions[path][node.name].append(node.lineno)
            elif isinstance(node, ast.ClassDef):
                class_names[path].add(node.name)
                definitions[path][node.name].append(node.lineno)
            elif isinstance(node, ast.ImportFrom) and node.module:
                import_target_path = _module_path(node.module, files)
                if import_target_path:
                    for alias in node.names:
                        imports[path][alias.asname or alias.name] = (
                            import_target_path,
                            alias.name,
                        )
                else:
                    for alias in node.names:
                        external_imports[path][alias.asname or alias.name] = (
                            f"{node.module}.{alias.name}"
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    import_target_path = _module_path(alias.name, files)
                    if import_target_path:
                        imports[path][alias.asname or alias.name.rsplit(".", 1)[-1]] = (
                            import_target_path,
                            None,
                        )
                    else:
                        root_module = alias.name.split(".", 1)[0]
                        external_imports[path][alias.asname or root_module] = (
                            alias.name if alias.asname else root_module
                        )

    edges: list[dict[str, Any]] = []
    for path, tree in trees.items():
        source = files[path]
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            caller = _scope_name(node, parents)
            expression = ast.unparse(node.func)
            target_path: str | None = None
            target_symbol: str | None = None
            external_signature: str | None = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in function_names[path] or name in class_names[path]:
                    target_path, target_symbol = path, name
                elif name in imports[path]:
                    target_path, target_symbol = imports[path][name]
                elif name in external_imports[path]:
                    external_signature = external_imports[path][name]
                elif hasattr(builtins, name):
                    external_signature = f"builtins.{name}"
            elif isinstance(node.func, ast.Attribute):
                target_symbol = node.func.attr
                value = node.func.value
                if isinstance(value, ast.Name) and value.id == "self":
                    target_path = path if target_symbol in function_names[path] else None
                elif isinstance(value, ast.Name) and value.id in imports[path]:
                    imported_path, imported_symbol = imports[path][value.id]
                    if imported_symbol is None:
                        target_path = imported_path
                elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                    constructor = value.func.id
                    if constructor in class_names[path]:
                        target_path = path
                    elif constructor in imports[path]:
                        target_path = imports[path][constructor][0]
                root_name = _root_name(value)
                if root_name in external_imports[path]:
                    external_signature = (
                        external_imports[path][root_name]
                        + ast.unparse(node.func)[len(root_name) :]
                    )
                if target_path and target_symbol not in (
                    function_names[target_path] | class_names[target_path]
                ):
                    target_path = None
            caller_id = f"{path}:{caller}"
            definition_lines = (
                definitions[target_path].get(target_symbol, [])
                if target_path and target_symbol
                else []
            )
            callee_id = (
                f"{target_path}:{target_symbol}" if len(definition_lines) == 1 else None
            )
            callee_candidate_id = (
                hashlib.sha256(
                    f"PROJECT_CALLEE:{callee_id}:{definition_lines[0]}".encode()
                ).hexdigest()
                if callee_id
                else None
            )
            primitive = _io_call(node, external_signature or expression)
            call_site_id = hashlib.sha256(
                f"CALL:{path}:{node.lineno}:{node.col_offset}:{expression}".encode()
            ).hexdigest()
            edge_id = hashlib.sha256(
                f"{caller_id}:{node.lineno}:{node.col_offset}:{expression}:"
                f"{callee_id or 'UNRESOLVED'}".encode()
            ).hexdigest()
            edges.append(
                {
                    "edge_id": edge_id,
                    "call_site_id": call_site_id,
                    "caller_id": caller_id,
                    "path": path,
                    "line": node.lineno,
                    "column": node.col_offset,
                    "call": expression,
                    "callee_id": callee_id,
                    "callee_candidate_id": callee_candidate_id,
                    "callee_definition_line": definition_lines[0] if callee_id else None,
                    "external_signature": external_signature,
                    "primitive_operation": primitive[0] if primitive else None,
                    "primitive_status": primitive[1] if primitive else None,
                    "resolution": (
                        "RESOLVED_EXACT_PROJECT_CALLEE"
                        if callee_id
                        else (
                            "UNRESOLVED_AMBIGUOUS_PROJECT_CALLEE"
                            if target_path and target_symbol
                            else (
                                "RESOLVED_EXTERNAL_SIGNATURE"
                                if external_signature
                                else "UNRESOLVED_DYNAMIC_CALL"
                            )
                        )
                    ),
                    "evidence": f"{path}@{base_sha}:{node.lineno}:{expression}",
                    "source_excerpt": (
                        ast.get_source_segment(source, node) or ast.unparse(node)
                    )[:500],
                }
            )
    return edges


def validate_all_call_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(row.get("disposition") for row in rows)
    unaccounted = sum(row.get("disposition") not in CALL_DISPOSITIONS for row in rows)
    if unaccounted or len({row.get("call_site_id") for row in rows}) != len(rows):
        raise AuditError(
            "ALL_CALL_ACCOUNTING_FAILED: every production ast.Call must have one unique "
            "call-site ID and exactly one disposition"
        )
    return {
        "total_production_ast_calls": len(rows),
        **{category.lower(): counts[category] for category in CALL_DISPOSITIONS},
        "unaccounted_production_calls": unaccounted,
    }


def all_call_accounting(
    files: dict[str, str], base_sha: str = BASE_SHA
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for edge in _static_call_edges(files, base_sha):
        signature = edge["external_signature"]
        if edge["callee_id"] and edge["callee_candidate_id"]:
            disposition = "INTERNAL_PROJECT_CALL"
            reason = "exact project definition path/symbol/line resolved"
        elif edge["primitive_status"] == "RECOGNIZED_IO_PRIMITIVE":
            disposition = "RECOGNIZED_SIDE_EFFECT_PRIMITIVE"
            reason = f"explicit primitive registry: {edge['primitive_operation']}"
        elif signature in KNOWN_PURE_CALLS:
            disposition = "KNOWN_PURE_OR_LOCAL_TRANSFORM"
            reason = KNOWN_PURE_CALLS[signature]
        elif signature:
            disposition = "UNRESOLVED_EXTERNAL_CALL"
            reason = "static external callable signature is not independently disposed"
        else:
            disposition = "UNRESOLVED_DYNAMIC_CALL"
            reason = edge["resolution"]
        row = {
            "call_site_id": edge["call_site_id"],
            "path": edge["path"],
            "line": edge["line"],
            "column": edge["column"],
            "caller_id": edge["caller_id"],
            "call": edge["call"],
            "disposition": disposition,
            "reason": reason,
            "source_excerpt": edge["source_excerpt"],
        }
        if disposition == "INTERNAL_PROJECT_CALL":
            row.update(
                {
                    "callee_id": edge["callee_id"],
                    "callee_candidate_id": edge["callee_candidate_id"],
                    "callee_definition_line": edge["callee_definition_line"],
                    "call_edge_id": edge["edge_id"],
                }
            )
        elif disposition == "KNOWN_PURE_OR_LOCAL_TRANSFORM":
            row["callable_signature"] = signature
        elif disposition == "RECOGNIZED_SIDE_EFFECT_PRIMITIVE":
            row.update(
                {
                    "callable_signature": signature or edge["call"],
                    "operation": edge["primitive_operation"],
                }
            )
        elif disposition == "UNRESOLVED_EXTERNAL_CALL":
            row["callable_signature"] = signature
        rows.append(row)

    return {
        "calls": sorted(rows, key=lambda row: (row["path"], row["line"], row["column"])),
        "counts": validate_all_call_rows(rows),
    }


def call_edge_manifest(files: dict[str, str], base_sha: str = BASE_SHA) -> dict[str, Any]:
    """Build an auditable static call-edge proposal rooted at the one-shot CLI."""
    edges = _static_call_edges(files, base_sha)

    reviewed_dynamic = (
        (
            "src/w2/ingestion/future_refresh.py:_request",
            877,
            "self.client.request_live",
            "src/w2/providers/api_football.py:request_live",
            "default FutureFixtureRefreshService client binds ApiFootballClient at lines 671-675",
        ),
        (
            "src/w2/providers/api_football.py:record",
            120,
            "ledger.record_request",
            "src/w2/providers/ledger.py:record_request",
            "ProviderRequestLedger dynamic dispatch; concrete DB implementation remains "
            "reviewer-bound",
        ),
    )
    for caller_id, line, expression, callee_id, evidence in reviewed_dynamic:
        edge_id = hashlib.sha256(
            f"{caller_id}:{line}:{expression}:{callee_id}:PROPOSED".encode()
        ).hexdigest()
        edges.append(
            {
                "edge_id": edge_id,
                "caller_id": caller_id,
                "path": caller_id.rsplit(":", 1)[0],
                "line": line,
                "call": expression,
                "callee_id": callee_id,
                "resolution": "PROPOSED_REVIEWED_DYNAMIC_EDGE",
                "evidence": evidence,
            }
        )

    root = str(ONE_SHOT_CANARY_SCOPE["entrypoint"])
    reachable = {root}
    predecessor: dict[str, dict[str, Any]] = {}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            callee = edge["callee_id"]
            if edge["caller_id"] in reachable and callee and callee not in reachable:
                reachable.add(callee)
                predecessor[callee] = edge
                changed = True
    chains: dict[str, list[str]] = {root: []}
    for target in reachable - {root}:
        current = target
        chain: list[str] = []
        seen: set[str] = set()
        while current != root and current in predecessor and current not in seen:
            seen.add(current)
            edge = predecessor[current]
            chain.append(edge["edge_id"])
            current = edge["caller_id"]
        if current == root:
            chains[target] = list(reversed(chain))
    auditable_edges = [edge for edge in edges if edge["caller_id"] in reachable]
    return {
        "root": root,
        "edges": sorted(
            auditable_edges, key=lambda row: (row["path"], row["line"], row["call"])
        ),
        "all_discovered_edge_count": len(edges),
        "rooted_edge_count": len(auditable_edges),
        "proposed_reachable_functions": sorted(chains),
        "chains": chains,
        "accepted_by_independent_reviewer": False,
    }


def _existing_blocker(candidate: dict[str, Any]) -> str | None:
    if candidate["risk_family"] == "R3" and candidate["operation"] != "DB_COMMIT":
        return None
    exact = {
        (family, path, line): blocker
        for family, path, line, blocker in EXACT_BLOCKER_SPECS
    }
    return exact.get((candidate["risk_family"], candidate["path"], candidate["line"]))


def _deferred_gate(candidate: dict[str, Any]) -> str:
    lowered = " ".join(
        str(candidate.get(field, "")).lower()
        for field in ("path", "symbol", "operation")
    )
    if any(word in lowered for word in ("scheduler", "celery", "stage7i", "monitoring", "retry")):
        return "PROPOSED_GATE_B"
    if any(
        word in lowered
        for word in (
            "analysis",
            "backtest",
            "dashboard",
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
        return "PROPOSED_GATE_C"
    if any(word in lowered for word in ("infrastructure", "readiness", "deploy", "release")):
        return "PROPOSED_GATE_D"
    return "PROPOSED_ACCEPTED_WITH_REASON"


def _review_domain(path: str) -> str:
    parts = Path(path).parts
    if path.startswith("src/w2/") and len(parts) > 2:
        return f"W2_{parts[2].upper()}"
    if path.startswith("apps/") and len(parts) > 1:
        return f"APP_{parts[1].upper()}"
    if path.startswith("migrations/"):
        return "MIGRATIONS"
    if path.startswith("scripts/"):
        return "SCRIPTS"
    return "OTHER_PRODUCTION"


def _dynamic_receiver_shape(expression: str) -> tuple[str, str]:
    try:
        node = ast.parse(expression, mode="eval").body
    except SyntaxError:
        return "COMPLEX_DYNAMIC_RECEIVER", expression
    if isinstance(node, ast.Name):
        return "BARE_CALLABLE", node.id
    if not isinstance(node, ast.Attribute):
        return "COMPLEX_DYNAMIC_RECEIVER", expression
    method = node.attr
    receiver = node.value
    if isinstance(receiver, ast.Name):
        if receiver.id == "self":
            return "SELF", method
        if receiver.id == "cls":
            return "CLASS", method
        return "LOCAL_NAME", method
    if isinstance(receiver, ast.Attribute):
        root = _root_name(receiver)
        return ("SELF_ATTRIBUTE_CHAIN" if root == "self" else "ATTRIBUTE_CHAIN"), method
    if isinstance(receiver, ast.Call):
        return "CALL_RESULT", method
    if isinstance(receiver, ast.Subscript):
        return "SUBSCRIPT", method
    return "COMPLEX_DYNAMIC_RECEIVER", method


BUSINESS_WRITE_OPERATIONS = {
    "DB_COMMIT",
    "DB_EXECUTE",
    "DB_FLUSH",
    "DB_WRITE_STAGE",
    "FILE_ATOMIC_WRITE",
    "FILE_COPY",
    "FILE_DELETE",
    "FILE_RENAME",
    "FILE_REPLACE",
    "FILE_TREE_COPY",
    "FILE_TREE_DELETE",
    "FILE_WRITE",
    "MESSAGE_PUBLISH",
    "MESSAGE_SEND",
    "OBJECT_STORE_DELETE",
    "OBJECT_STORE_WRITE",
    "REDIS_KV_COUNTER_WRITE",
    "REDIS_KV_DELETE",
    "REDIS_KV_EXPIRY_WRITE",
    "REDIS_KV_SCRIPT_WRITE",
    "REDIS_KV_STREAM_WRITE",
    "REDIS_KV_WRITE",
}
EVIDENCE_PERSISTENCE_PATHS = {
    "src/w2/ingestion/future_refresh_repository.py",
    "src/w2/matchday/repository.py",
    "src/w2/operations/runtime_evidence.py",
    "src/w2/providers/ledger.py",
}
DEFERRED_DOMAIN_RULES = {
    "APP_SCHEDULER": ("QUEUE_DEFER_GATE_B_DOMAIN", "PROPOSED_DEFERRED_GATE_B"),
    "APP_WORKER": ("QUEUE_DEFER_GATE_B_DOMAIN", "PROPOSED_DEFERRED_GATE_B"),
    "W2_INGESTION": ("QUEUE_DEFER_GATE_B_DOMAIN", "PROPOSED_DEFERRED_GATE_B"),
    "W2_OPERATIONS": ("QUEUE_DEFER_GATE_B_DOMAIN", "PROPOSED_DEFERRED_GATE_B"),
    "W2_PROVIDERS": ("QUEUE_DEFER_GATE_B_DOMAIN", "PROPOSED_DEFERRED_GATE_B"),
    "W2_ANALYSIS": ("QUEUE_DEFER_GATE_C_DOMAIN", "PROPOSED_DEFERRED_GATE_C"),
    "W2_DASHBOARD": ("QUEUE_DEFER_GATE_C_DOMAIN", "PROPOSED_DEFERRED_GATE_C"),
    "W2_STRATEGY": ("QUEUE_DEFER_GATE_C_DOMAIN", "PROPOSED_DEFERRED_GATE_C"),
    "W2_TRACKING": ("QUEUE_DEFER_GATE_C_DOMAIN", "PROPOSED_DEFERRED_GATE_C"),
    "MIGRATIONS": ("QUEUE_DEFER_GATE_D_DOMAIN", "PROPOSED_DEFERRED_GATE_D"),
    "SCRIPTS": ("QUEUE_DEFER_GATE_D_DOMAIN", "PROPOSED_DEFERRED_GATE_D"),
}


def _review_member_metadata(
    member: dict[str, Any], call_manifest: dict[str, Any]
) -> dict[str, Any]:
    function_id = member.get("caller_id") or f"{member['path']}:{member['symbol']}"
    rooted = function_id in call_manifest["chains"]
    disposition = member.get("call_disposition", "R2_HANDLER")
    receiver_shape = "NOT_APPLICABLE"
    method_name = member.get("operation", member.get("handler_action", "R2_HANDLER"))
    if disposition == "UNRESOLVED_DYNAMIC_CALL":
        receiver_shape, method_name = _dynamic_receiver_shape(member["call"])
    signature = member.get("callable_signature") or member.get("call")
    domain = _review_domain(member["path"])
    grouping_key: tuple[Any, ...]
    if member["risk_family"] == "R2":
        grouping_key = (
            "R2_HANDLER",
            member.get("handler_action", "UNKNOWN_HANDLER"),
            domain,
            function_id,
            rooted,
        )
    elif disposition == "UNRESOLVED_EXTERNAL_CALL":
        grouping_key = ("UNRESOLVED_EXTERNAL", signature, domain, function_id)
    elif disposition == "UNRESOLVED_DYNAMIC_CALL":
        grouping_key = (
            "UNRESOLVED_DYNAMIC",
            receiver_shape,
            method_name,
            domain,
            rooted,
        )
    else:
        grouping_key = (
            "RECOGNIZED_SIDE_EFFECT",
            member["operation"],
            signature,
            domain,
            function_id,
            rooted,
        )
    blocker = _existing_blocker(member)
    indicators: set[str] = set()
    if disposition == "RECOGNIZED_SIDE_EFFECT_PRIMITIVE":
        indicators.add(f"EXPLICIT_PRIMITIVE_REGISTRY:{member['operation']}")
    if blocker:
        indicators.add(f"EXACT_C1_C11_MAPPING:{blocker}")
    if member.get("operation") in BUSINESS_WRITE_OPERATIONS:
        indicators.add("BUSINESS_WRITE_BOUNDARY")
    if member["path"].startswith("src/w2/providers/"):
        indicators.add("PROVIDER_BOUNDARY")
    if (
        member["path"] in EVIDENCE_PERSISTENCE_PATHS
        and member.get("operation") in BUSINESS_WRITE_OPERATIONS
    ):
        indicators.add("EVIDENCE_PERSISTENCE_BOUNDARY")
    reviewed_side_effect_methods = (
        set(NETWORK_METHODS)
        | set(REDIS_KV_METHODS)
        | set(DB_METHODS)
        | set(FILE_METHODS)
        | set(EXTERNAL_WRITE_METHODS)
    )
    if disposition.startswith("UNRESOLVED_") and method_name in reviewed_side_effect_methods:
        indicators.add(f"REVIEWED_SIDE_EFFECT_METHOD:{method_name}")
    if member["risk_family"] == "R2":
        for handler_call in member.get("handler_calls", []):
            method = handler_call.rsplit(".", 1)[-1]
            if method in reviewed_side_effect_methods:
                indicators.add(f"HANDLER_SIDE_EFFECT_METHOD:{method}")
    return {
        "member": member,
        "member_id": member["candidate_id"],
        "function_id": function_id,
        "rooted": rooted,
        "domain": domain,
        "disposition": disposition,
        "receiver_shape": receiver_shape,
        "method_name": method_name,
        "grouping_key": grouping_key,
        "blocker": blocker,
        "side_effect_indicators": sorted(indicators),
    }


def grouped_review_queue(
    candidates: list[dict[str, Any]], call_manifest: dict[str, Any]
) -> dict[str, Any]:
    metadata = [_review_member_metadata(member, call_manifest) for member in candidates]
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in metadata:
        grouped[row["grouping_key"]].append(row)
    review_groups: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    assigned: list[str] = []
    for grouping_key, members in sorted(grouped.items(), key=lambda item: repr(item[0])):
        group_id = hashlib.sha256(
            f"T00_REVIEW_GROUP:{json.dumps(grouping_key, sort_keys=True)}".encode()
        ).hexdigest()
        assigned.extend(member["member_id"] for member in members)
        blockers = sorted({member["blocker"] for member in members if member["blocker"]})
        has_gate_a_spec = any(
            (
                member["member"]["risk_family"],
                member["member"]["path"],
                member["member"]["line"],
            )
            in PROPOSED_TEST_CONTRACT_SPECS
            for member in members
        )
        rooted_count = sum(member["rooted"] for member in members)
        unresolved = any(member["disposition"].startswith("UNRESOLVED_") for member in members)
        recognized = any(
            member["disposition"] == "RECOGNIZED_SIDE_EFFECT_PRIMITIVE"
            for member in members
        )
        indicators = sorted(
            {
                indicator
                for member in members
                for indicator in member["side_effect_indicators"]
            }
        )
        domain = members[0]["domain"]
        if has_gate_a_spec:
            rule_id, proposed = "QUEUE_EXACT_GATE_A_CONTRACT", "PROPOSED_GATE_A_REVIEW"
        elif blockers:
            rule_id, proposed = "QUEUE_EXACT_C1_C11_MAPPING", "PROPOSED_CANARY_REVIEW"
        elif rooted_count and recognized:
            rule_id, proposed = (
                "QUEUE_ROOTED_RECOGNIZED_SIDE_EFFECT",
                "PROPOSED_CANARY_REVIEW",
            )
        elif rooted_count and unresolved:
            rule_id, proposed = (
                "QUEUE_ROOTED_UNRESOLVED_FRONTIER",
                "PROPOSED_CANARY_REVIEW",
            )
        elif indicators:
            rule_id, proposed = (
                "QUEUE_MACHINE_SIDE_EFFECT_INDICATOR",
                "PROPOSED_CANARY_REVIEW",
            )
        else:
            rule_id, proposed = DEFERRED_DOMAIN_RULES.get(
                domain,
                ("QUEUE_ACCEPT_NONROOTED_NO_INDICATOR", "PROPOSED_ACCEPTED_WITH_REASON"),
            )
        exception_ids: list[str] = []
        for member in members:
            reasons: list[str] = []
            if member["blocker"]:
                reasons.append("EXACT_C1_C11_MAPPING_REQUIRES_SITE_REVIEW")
            if member["receiver_shape"] in {
                "CALL_RESULT",
                "SUBSCRIPT",
                "COMPLEX_DYNAMIC_RECEIVER",
            }:
                reasons.append("COMPLEX_DYNAMIC_RECEIVER_REQUIRES_SITE_REVIEW")
            if not reasons:
                continue
            exception_id = hashlib.sha256(
                f"T00_REVIEW_EXCEPTION:{group_id}:{member['member_id']}:{','.join(reasons)}".encode()
            ).hexdigest()
            exception_ids.append(exception_id)
            exceptions.append(
                {
                    "exception_id": exception_id,
                    "review_group_id": group_id,
                    "member_call_site_id": member["member_id"],
                    "reasons": reasons,
                    "evidence": (
                        f"{member['member']['path']}:{member['member']['line']}:"
                        f"{member['member'].get('call', member['member'].get('operation'))}"
                    ),
                    "independent_review_status": "PENDING_INDEPENDENT_REVIEW",
                    "accepted_by_independent_reviewer": False,
                }
            )
        review_groups.append(
            {
                "review_group_id": group_id,
                "rule_id": rule_id,
                "grouping_key": list(grouping_key),
                "member_count": len(members),
                "member_call_site_ids": sorted(member["member_id"] for member in members),
                "representative_sites": [
                    {
                        "member_call_site_id": member["member_id"],
                        "path": member["member"]["path"],
                        "line": member["member"]["line"],
                        "call": member["member"].get(
                            "call", member["member"].get("operation")
                        ),
                        "caller_context": member["function_id"],
                    }
                    for member in members[:3]
                ],
                "rooted_reachability": {
                    "root": call_manifest["root"],
                    "rooted_member_count": rooted_count,
                    "status": (
                        "ROOTED"
                        if rooted_count == len(members)
                        else ("NOT_ROOTED" if rooted_count == 0 else "MIXED")
                    ),
                },
                "side_effect_indicators": indicators,
                "proposed_disposition": proposed,
                "exception_ids": sorted(exception_ids),
                "independent_review_status": "PENDING_INDEPENDENT_REVIEW",
                "accepted_by_independent_reviewer": False,
            }
        )
    expected = [member["candidate_id"] for member in candidates]
    assignment_counts = Counter(assigned)
    unassigned = sorted(set(expected) - set(assigned))
    duplicates = sorted(member_id for member_id, count in assignment_counts.items() if count != 1)
    unresolved_ids = {
        member["candidate_id"]
        for member in candidates
        if member.get("call_disposition", "").startswith("UNRESOLVED_")
    }
    ungrouped_unresolved = sorted(unresolved_ids - set(assigned))
    if unassigned or duplicates or ungrouped_unresolved:
        raise AuditError("GROUPED_REVIEW_QUEUE_ACCOUNTING_FAILED")
    return {
        "all_call_completeness_ledger": "FROZEN_SEPARATE_ARTIFACT",
        "grouped_review_queue": review_groups,
        "review_exceptions": sorted(exceptions, key=lambda row: row["exception_id"]),
        "member_assignments": {
            member_id: group["review_group_id"]
            for group in review_groups
            for member_id in group["member_call_site_ids"]
        },
        "counts": {
            "total_review_members": len(expected),
            "total_review_groups": len(review_groups),
            "canary_review_groups": sum(
                group["proposed_disposition"]
                in {"PROPOSED_GATE_A_REVIEW", "PROPOSED_CANARY_REVIEW"}
                for group in review_groups
            ),
            "deferred_review_groups": sum(
                group["proposed_disposition"]
                not in {"PROPOSED_GATE_A_REVIEW", "PROPOSED_CANARY_REVIEW"}
                for group in review_groups
            ),
            "review_exception_sites": len(exceptions),
            "unassigned_review_group_members": len(unassigned),
            "ungrouped_unresolved_calls": len(ungrouped_unresolved),
            "duplicate_review_group_members": len(duplicates),
            "proposed_gate_a_groups": sum(
                group["proposed_disposition"] == "PROPOSED_GATE_A_REVIEW"
                for group in review_groups
            ),
            "final_gate_a_groups": 0,
            "independently_accepted_groups": 0,
        },
    }


def _proposed_test_contract(
    candidate: dict[str, Any], blocker: str, base_sha: str
) -> dict[str, Any]:
    path = candidate["path"]
    if path == "src/w2/providers/ledger.py":
        target = "tests/unit/test_provider_ledger.py"
    elif path == "src/w2/matchday/repository.py":
        target = "tests/integration/test_matchday_intake_v2_persistence.py"
    elif path == "src/w2/prematch/read_model_projection.py":
        target = "tests/unit/test_frozen_analysis_materializer.py"
    elif path == "src/w2/prematch/analysis_calculator.py":
        target = "tests/unit/test_public_analysis_card_bounded.py"
    elif path == "src/w2/ingestion/future_refresh_repository.py":
        target = "tests/integration/test_future_refresh_db_persistence.py"
    elif candidate["operation"] == "DB_COMMIT":
        target = "tests/integration/test_future_refresh_db_persistence.py"
    else:
        target = "tests/unit/test_future_fixture_refresh.py"
    pre_provider = path == "src/w2/matchday/repository.py" and candidate["symbol"] == (
        "validate_checkpoint_claim"
    )
    if pre_provider:
        stage = "BEFORE_FIRST_PROVIDER_REQUEST"
    elif path == "src/w2/providers/ledger.py":
        stage = "AFTER_PROVIDER_RESPONSE_LEDGER_STAGE"
    elif path == "src/w2/ingestion/future_refresh.py" and candidate["symbol"] == "_request":
        stage = "PROVIDER_ATTEMPT_OR_POST_RESPONSE_STAGE"
    else:
        stage = "PERSISTENCE_OR_EVIDENCE_STAGE_AFTER_ENTRY"
    trigger = (
        f"{stage}:INJECT_{candidate['operation'].upper().replace(' ', '_')}_AT_"
        f"{path}@{base_sha}:{candidate['line']}"
    )

    def proposed_delta(value: int | str, evidence: str) -> dict[str, Any]:
        return {
            "value": value,
            "status": (
                "EVIDENCE_ATTACHED_PENDING_INDEPENDENT_REVIEW"
                if value != "PENDING_REVIEW"
                else "PENDING_REVIEW"
            ),
            "evidence": evidence,
        }

    provider_delta = proposed_delta(
        0 if pre_provider else "PENDING_REVIEW",
        (
            f"{path}@{base_sha}:{candidate['line']} occurs before provider dispatch"
            if pre_provider
            else (
                f"{path}@{base_sha}:{candidate['line']} stage={stage}; exact prior-attempt count "
                "depends on the independently reviewed candidate call sequence"
            )
        ),
    )
    business_delta = proposed_delta(
        0 if pre_provider else "PENDING_REVIEW",
        (
            "checkpoint claim validation precedes Provider and business persistence"
            if pre_provider
            else (
                f"{path}@{base_sha}:{candidate['line']} may follow earlier raw/ledger/business "
                "writes; failed-path net delta needs stage-specific fault injection"
            )
        ),
    )
    evidence_delta = proposed_delta(
        "PENDING_REVIEW",
        (
            f"{path}@{base_sha}:{candidate['line']} has no implemented Wave-1 fault injection; "
            "durable evidence type and delta remain reviewer-bound"
        ),
    )
    return {
        "test_id": f"T00_GATE_A_{candidate['candidate_id'][:16]}",
        "contract_status": "PROPOSED_TEST_CONTRACT",
        "accepted_by_independent_reviewer": False,
        "target_test_file": target,
        "trigger": trigger,
        "failure_stage": stage,
        "stage_evidence": (
            f"{path}@{base_sha}:{candidate['line']}:{candidate['source_excerpt'][:180]}"
        ),
        "expected_terminal_status": {
            "value": "BLOCKED",
            "status": "PROPOSED_PENDING_INDEPENDENT_REVIEW",
            "evidence": f"Issue #454 v5 blocker {blocker}",
        },
        "expected_provider_call_delta": provider_delta,
        "expected_business_write_delta": business_delta,
        "expected_evidence_delta": evidence_delta,
        "mapped_blocker": blocker,
    }


def adjudicate_s07(
    candidates: list[dict[str, Any]],
    call_manifest: dict[str, Any],
    base_sha: str = BASE_SHA,
) -> list[dict[str, Any]]:
    adjudicated: list[dict[str, Any]] = []
    edge_by_id = {row["edge_id"]: row for row in call_manifest["edges"]}
    for original in candidates:
        row = dict(original)
        path, symbol = row["path"], row["symbol"]
        function_id = f"{path}:{symbol}"
        chain_ids = call_manifest["chains"].get(function_id, [])
        reachable = function_id in call_manifest["chains"]
        operation = row["operation"]
        blocker = _existing_blocker(row)
        terminal_raise = row.get("handler_action") == "RAISE_TERMINAL"
        read_or_rollback = operation in {"DB_READ", "FILE_READ", "DB_ROLLBACK"}
        external_after_failure = (
            "PROPOSED_TRUE"
            if operation.startswith(
                (
                    "NETWORK_",
                    "DB_",
                    "FILE_",
                    "OBJECT_",
                    "MESSAGE_",
                    "PROCESS_",
                    "REDIS_KV_",
                )
            )
            else "PENDING_REVIEW"
        )
        business_write = (
            "PROPOSED_TRUE"
            if operation
            in {
                "DB_COMMIT",
                "DB_FLUSH",
                "DB_WRITE_STAGE",
                "DB_EXECUTE",
                "FILE_WRITE",
                "FILE_ATOMIC_WRITE",
                "REDIS_KV_WRITE",
                "REDIS_KV_COUNTER_WRITE",
                "REDIS_KV_DELETE",
                "REDIS_KV_EXPIRY_WRITE",
                "REDIS_KV_SCRIPT_WRITE",
                "REDIS_KV_STREAM_WRITE",
            }
            else "PENDING_REVIEW"
        )
        evidence_break = "PROPOSED_TRUE" if blocker else "PENDING_REVIEW"
        excluded = "PROPOSED_TRUE" if terminal_raise or read_or_rollback else "PENDING_REVIEW"
        admission = {
            "directly_affects_one_shot_foreground_canary": (
                "PROPOSED_TRUE" if reachable else "PENDING_REVIEW"
            ),
            "code_or_runtime_evidence": "EVIDENCE_ATTACHED",
            "not_excluded_by_preflight_or_isolation": (
                "PROPOSED_FALSE" if excluded == "PROPOSED_TRUE" else "PENDING_REVIEW"
            ),
            "explicit_trigger_and_acceptance_criteria": (
                "PROPOSED_TRUE" if blocker else "PENDING_REVIEW"
            ),
            "accepted_by_independent_reviewer": False,
        }
        if (row["risk_family"], path, row["line"]) in PROPOSED_TEST_CONTRACT_SPECS:
            proposed_gate = "PROPOSED_GATE_A"
        elif row["risk_family"] == "R2" and terminal_raise:
            proposed_gate = "PROPOSED_SAFE_DEGRADATION"
        elif reachable:
            proposed_gate = "PROPOSED_ACCEPTED_WITH_REASON"
        else:
            proposed_gate = _deferred_gate(row)
        chain = [edge_by_id[edge_id] for edge_id in chain_ids]
        row.update(
            {
                "entrypoint_reachable_from_one_shot_canary": (
                    "PROPOSED_REACHABLE" if reachable else "PENDING_CALL_EDGE_REVIEW"
                ),
                "candidate_call_edge_ids": chain_ids,
                "candidate_call_edges": chain,
                "external_side_effect_after_failure": external_after_failure,
                "business_write_reachable": business_write,
                "evidence_chain_break_possible": evidence_break,
                "preflight_or_isolation_excludes": excluded,
                "mapped_existing_blocker": blocker,
                "blocker_mapping_basis": (
                    f"EXACT_CANDIDATE_ID:{row['candidate_id']}" if blocker else "NO_EXACT_MAPPING"
                ),
                "review_evidence": [
                    f"{path}:{row['line']}:{row['source_excerpt'][:180]}",
                    f"call_edge_ids={','.join(chain_ids) if chain_ids else 'PENDING_REVIEW'}",
                    "#452 frozen one-shot scope; #454 v5 five-condition Gate-A rule",
                ],
                "gate_a_admission_conditions": admission,
                "proposed_target_gate": proposed_gate,
                "final_target_gate": "PENDING_INDEPENDENT_REVIEW",
                "target_gate": proposed_gate,
                "classification": (
                    row["call_disposition"]
                    if row.get("call_disposition", "").startswith("UNRESOLVED_")
                    else "PROPOSED_DISPOSITION_PENDING_INDEPENDENT_REVIEW"
                ),
                "status": (
                    "UNCLASSIFIED"
                    if row.get("call_disposition", "").startswith("UNRESOLVED_")
                    else "PROPOSED_PENDING_INDEPENDENT_REVIEW"
                ),
                "independent_review": "PENDING_S07_8",
                "accepted_by_independent_reviewer": False,
            }
        )
        if proposed_gate == "PROPOSED_GATE_A":
            row["proposed_test_contract"] = _proposed_test_contract(
                row, blocker or "", base_sha
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
    pr458_head = git("rev-parse", "HEAD")
    baseline = ast.parse(show(config.base_sha, DELIVERY_TEST))
    proposed = ast.parse(show(config.pr450_ref, DELIVERY_TEST))
    head_tree = ast.parse(show(pr458_head, DELIVERY_TEST))
    baseline_tests = _test_nodes(baseline)
    proposed_tests = _test_nodes(proposed)
    head_tests = _test_nodes(head_tree)
    proposed_assertions = _assertions_by_ast(proposed_tests)
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
                    "classification": "RETAINED_IN_PR450",
                    "trusted_main_classification": "RETAINED_ON_TRUSTED_MAIN",
                    "evidence": "exact test identity exists in PR #450",
                }
            )
        else:
            removed_rows.append(
                {
                    "guard_id": f"TEST:{test_name}",
                    "original_guard": test_name,
                    "current_equivalent": _guard_target(
                        config.base_sha, test_name, baseline_tests[test_name].lineno
                    ),
                    "classification": "LOST_IN_PR450",
                    "trusted_main_classification": "RETAINED_ON_TRUSTED_MAIN",
                    "repair_requirement": "REPAIR_REQUIRED_IN_PR450",
                    "pr458_head_contains_guard": test_name in head_tests,
                    "evidence": (
                        "absent from exact PR #450 head; retained at exact trusted main; "
                        "PR #458 does not claim restoration"
                    ),
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
                        "classification": "RETAINED_IN_PR450",
                        "trusted_main_classification": "RETAINED_ON_TRUSTED_MAIN",
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
                classification = "RETAINED_IN_PR450" if target else "LOST_IN_PR450"
                equivalent = (
                    _guard_target(config.pr450_head, target[0], target[1])
                    if target
                    else _guard_target(config.base_sha, test_name, assertion.lineno)
                )
                evidence = review["evidence"] if target else "reviewed semantic target missing"
            elif digest in RETIRED_GUARD_REVIEWS:
                classification = "INTENTIONALLY_RETIRED_WITH_EVIDENCE"
                equivalent = None
                evidence = RETIRED_GUARD_REVIEWS[digest]
            else:
                classification = "LOST_IN_PR450"
                equivalent = _guard_target(config.base_sha, test_name, assertion.lineno)
                evidence = (
                    "absent from exact PR #450 head; normalized assertion remains at exact "
                    "trusted main and requires repair in PR #450"
                )
            removed_rows.append(
                {
                    "guard_id": f"ASSERT:{test_name}:{assertion.lineno}",
                    "original_guard": label,
                    "current_equivalent": equivalent,
                    "classification": classification,
                    "trusted_main_classification": "RETAINED_ON_TRUSTED_MAIN",
                    "repair_requirement": (
                        "REPAIR_REQUIRED_IN_PR450"
                        if classification == "LOST_IN_PR450"
                        else "NOT_REQUIRED_WITH_REVIEWED_EVIDENCE"
                    ),
                    "evidence": evidence,
                }
            )
    return {
        "baseline": config.base_sha,
        "pr450_head": config.pr450_head,
        "source_mode": "EXACT_GIT_OBJECTS_ONLY",
        "pr458_changes_delivery_test": bool(
            git("diff", "--name-only", config.base_sha, pr458_head, "--", DELIVERY_TEST)
        ),
        "exact_equivalents": exact_rows,
        "removed_guards": removed_rows,
        "repair_required_guards": sum(
            row.get("repair_requirement") == "REPAIR_REQUIRED_IN_PR450"
            for row in removed_rows
        ),
        "unclassified_removed_guards": sum(
            row["classification"] == "UNCLASSIFIED" for row in removed_rows
        ),
    }


def safe_report(config: AuditConfig) -> dict[str, Any]:
    production_scope = production_python_scope(config.base_sha)
    files = python_files(config.base_sha)
    base_paths = set(tree_paths(config.base_sha))
    accounting = all_call_accounting(files, config.base_sha)
    risks = risk_candidates(files, accounting)
    call_manifest = call_edge_manifest(files, config.base_sha)
    review_members = risks.get("R2", []) + risks.get("R3", [])
    review_bundle = grouped_review_queue(review_members, call_manifest)
    review_groups_by_id = {
        row["review_group_id"]: row for row in review_bundle["grouped_review_queue"]
    }
    for row in review_members:
        group_id = review_bundle["member_assignments"][row["candidate_id"]]
        group = review_groups_by_id[group_id]
        row.update(
            {
                "review_group_id": group_id,
                "grouped_proposed_disposition": group["proposed_disposition"],
                "target_gate": group["proposed_disposition"],
                "status": "GROUPED_PENDING_INDEPENDENT_REVIEW",
                "accepted_by_independent_reviewer": False,
            }
        )
    proposed_candidates = adjudicate_s07(
        [
            row
            for row in review_members
            if (row["risk_family"], row["path"], row["line"])
            in PROPOSED_TEST_CONTRACT_SPECS
        ],
        call_manifest,
        config.base_sha,
    )
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
            **(
                {"scope": INDEPENDENT_BLOCKER_SCOPES[f"C{index}"]}
                if f"C{index}" in INDEPENDENT_BLOCKER_SCOPES
                else {}
            ),
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
    proposed_contract_fields = {
        "test_id",
        "contract_status",
        "accepted_by_independent_reviewer",
        "target_test_file",
        "trigger",
        "failure_stage",
        "stage_evidence",
        "expected_terminal_status",
        "expected_provider_call_delta",
        "expected_business_write_delta",
        "expected_evidence_delta",
        "mapped_blocker",
    }
    proposed_test_contracts = [
        row["proposed_test_contract"]
        for row in proposed_candidates
        if row["proposed_target_gate"] == "PROPOSED_GATE_A"
    ]
    incomplete_proposed_test_contracts = sum(
        not proposed_contract_fields.issubset(contract)
        or contract["target_test_file"] not in base_paths
        for contract in proposed_test_contracts
    )
    accounting_counts = accounting["counts"]
    derived_r3_denominator = sum(
        accounting_counts[category.lower()]
        for category in (
            "RECOGNIZED_SIDE_EFFECT_PRIMITIVE",
            "UNRESOLVED_EXTERNAL_CALL",
            "UNRESOLVED_DYNAMIC_CALL",
        )
    )
    if derived_r3_denominator != len(risks.get("R3", [])):
        raise AuditError("R3_DENOMINATOR_DOES_NOT_MATCH_ALL_CALL_ACCOUNTING")
    return {
        "schema_version": "w2.t00.safe.v1",
        "base_sha": config.base_sha,
        "remote": config.remote,
        "pr450_ref": config.pr450_ref,
        "scan_strategy": "AST_FIRST_WITH_TEXT_FALLBACK",
        "production_python_scope": production_scope,
        "all_call_accounting": accounting,
        "risk_candidates": risks,
        "storage_inventory": storage_inventory(files, config.base_sha),
        "computation_authorities": computations,
        "findings": findings,
        "validated_findings": validated_findings,
        "one_shot_canary_scope": ONE_SHOT_CANARY_SCOPE,
        "candidate_call_edge_manifest": call_manifest,
        "grouped_decision_review_bundle": review_bundle,
        "s07_gate_proposals": {
            "exact_gate_a_candidate_proposals": proposed_candidates,
            "proposed_test_contracts": proposed_test_contracts,
            "counts": {
                **accounting_counts,
                "r2_handler_denominator": len(risks.get("R2", [])),
                "r3_side_effect_denominator": len(risks.get("R3", [])),
                "total_candidates": len(review_members),
                **review_bundle["counts"],
                "final_gate_a": 0,
                "mapped_to_c1_c11": sum(
                    _existing_blocker(row) is not None for row in review_members
                ),
                "new_finding_ids": [],
                "independent_review_pending": review_bundle["counts"][
                    "total_review_groups"
                ],
                "unresolved_external_and_dynamic_calls": (
                    accounting_counts["unresolved_external_call"]
                    + accounting_counts["unresolved_dynamic_call"]
                ),
                "redis_kv_primitives": sum(
                    row["operation"].startswith("REDIS_KV_")
                    for row in risks.get("R3", [])
                ),
                "lock_durability_primitives": sum(
                    row["operation"] in LOCK_DURABILITY_CALLS.values()
                    for row in risks.get("R3", [])
                ),
                "process_execution_primitives": sum(
                    row["operation"] == "PROCESS_EXECUTION"
                    for row in risks.get("R3", [])
                ),
                "proposed_test_contracts": len(proposed_test_contracts),
                "independently_accepted_test_contracts": 0,
                "incomplete_proposed_test_contracts": incomplete_proposed_test_contracts,
            },
        },
        "pr450_guard_matrix": guards,
        "counts": {
            "unclassified_findings": sum(
                not required_fields.issubset(row)
                for row in findings
            )
            + sum(
                not {
                    "review_group_id",
                    "rule_id",
                    "member_count",
                    "member_call_site_ids",
                    "representative_sites",
                    "rooted_reachability",
                    "side_effect_indicators",
                    "proposed_disposition",
                    "exception_ids",
                    "independent_review_status",
                }.issubset(row)
                or row["accepted_by_independent_reviewer"] is not False
                for row in review_bundle["grouped_review_queue"]
            )
            + incomplete_proposed_test_contracts,
            "unclassified_io_primitives": 0,
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
