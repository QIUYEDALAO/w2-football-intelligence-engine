#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/operations/governance.py",
    "migrations/versions/0016_create_stage15a_operational_governance.py",
    "docs/adr/ADR-0018-operational-governance.md",
    "docs/operations/W2_DAILY_OPERATIONS_V1.md",
    "docs/operations/W2_WEEKLY_OPERATIONS_V1.md",
    "docs/operations/W2_RELEASE_AND_ROLLBACK_V1.md",
    "docs/operations/W2_DATA_RETENTION_V1.md",
    "docs/runbooks/LONG_TERM_OPERATIONS.md",
    "config/policies/operations.v1.json",
    "config/policies/retention.v1.json",
    "scripts/run_stage15a_operations_dry_run.py",
    "scripts/check_w2_stage15a.py",
]
REPORT_ARTIFACTS = [
    "reports/W2_STAGE15A_OPERATIONS.json",
    "reports/W2_STAGE15A_DEPENDENCY_AUDIT.json",
    "reports/W2_STAGE15A_RELEASE_READINESS.json",
    "reports/W2_STAGE15A_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage15A check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md", ".json")))
    for token in [
        "OperationsCycle",
        "DAILY",
        "WEEKLY",
        "MATCHDAY",
        "ROUND_END",
        "SEASON_END",
        "MODEL_RELEASE",
        "ModelCard",
        "ReleaseCandidate",
        "ReleaseApproval",
        "RollbackManifest",
        "ChangeFreeze",
        "ReleaseAudit",
        "DISABLED_GATE4",
    ]:
        if token not in combined:
            fail(f"missing token {token}")
    if all((ROOT / path).is_file() for path in REPORT_ARTIFACTS):
        operations = load("reports/W2_STAGE15A_OPERATIONS.json")
        dependency = load("reports/W2_STAGE15A_DEPENDENCY_AUDIT.json")
        release = load("reports/W2_STAGE15A_RELEASE_READINESS.json")
        result = read("reports/W2_STAGE15A_RESULT.md")
        if operations["operational_autorun"] or operations["external_alerting"]:  # type: ignore[index]
            fail("autorun and external alerting must stay disabled")
        if operations["production_release"]:  # type: ignore[index]
            fail("production release must stay disabled")
        if len(operations["cycles"]) != 6:  # type: ignore[index]
            fail("all six operations cycles must be present")
        if operations["retention"]["files_deleted"]:  # type: ignore[index]
            fail("retention must be dry-run only")
        if release["approval_status"] == "READY":  # type: ignore[index]
            fail("release must not be ready in Stage15A")
        if dependency["npm"]["force_fix_used"]:  # type: ignore[index]
            fail("npm audit force fix must not be used")
        for token in [
            "STAGE_15A=COMPLETED",
            "LONG_TERM_OPERATIONS=READY_LOCAL_STAGING",
            "OPERATIONAL_AUTORUN=DISABLED_PENDING_APPROVAL",
            "PRODUCTION_RELEASE=DISABLED",
            "EXTERNAL_ALERTING=DISABLED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "STAGE_9=BLOCKED",
            "PUSH_BLOCKED_NO_ORIGIN",
        ]:
            if token not in result:
                fail(f"missing status {token}")
    print("W2 Stage15A check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
