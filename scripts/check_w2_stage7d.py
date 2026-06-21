#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/models/forward_automation.py",
    "src/w2/infrastructure/persistence/forward_ops_models.py",
    "migrations/versions/0010_create_stage7d_forward_automation.py",
    "config/policies/forward_holdout_schedule.v1.json",
    "scripts/run_stage7d_dry_cycle.py",
    "scripts/check_w2_stage7d.py",
    "docs/adr/ADR-0011-forward-holdout-automation.md",
    "docs/runbooks/FORWARD_HOLDOUT_AUTOMATION.md",
    "reports/W2_STAGE7D_AUTOMATION_PLAN.json",
    "reports/W2_STAGE7D_POWER_PROGRESS.json",
    "reports/W2_STAGE7D_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage7D check FAIL: {message}", file=sys.stderr)
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
        "ForwardHoldoutFixtureState",
        "ForwardHoldoutCycleService",
        "ForwardCircuitBreaker",
        "RequestQuotaPolicy",
        "forward_cycle_checkpoint",
        "forward_scheduler_run",
        "forward_state_transition",
        "forward_operational_alert",
        "W2_FORWARD_HOLDOUT_AUTORUN",
        "W2_FORWARD_HOLDOUT_NETWORK",
    ]:
        if token not in combined:
            fail(f"missing Stage7D token {token}")
    schedule = load("config/policies/forward_holdout_schedule.v1.json")
    plan = load("reports/W2_STAGE7D_AUTOMATION_PLAN.json")
    progress = load("reports/W2_STAGE7D_POWER_PROGRESS.json")
    result = read("reports/W2_STAGE7D_RESULT.md")
    if schedule["defaults"]["W2_FORWARD_HOLDOUT_AUTORUN"] is not False:  # type: ignore[index]
        fail("autorun must default false")
    if schedule["defaults"]["W2_FORWARD_HOLDOUT_NETWORK"] is not False:  # type: ignore[index]
        fail("network must default false")
    if plan["dry_cycle"]["network_enabled"] is not False:  # type: ignore[index]
        fail("dry cycle must not enable network")
    if plan["dry_cycle"]["autorun_enabled"] is not False:  # type: ignore[index]
        fail("dry cycle must not enable autorun")
    if plan["hash_audit"]["blockers"]:  # type: ignore[index]
        fail("frozen Stage7B/7C hash changed")
    quota = plan["quota_policy"]  # type: ignore[index]
    if quota["minimum_reserve"] != 2500:
        fail("minimum reserve must be 2500")
    if quota["allowed_requests_when_unknown"] != 0:
        fail("unknown quota must stop conservatively")
    if quota["allowed_requests_at_3000_remaining"] > quota["per_cycle_cap"]:
        fail("per-cycle cap exceeded")
    negative = plan["negative_checks"]  # type: ignore[index]
    if negative["illegal_transitions"]["all_blocked"] is not True:
        fail("illegal transitions must be blocked")
    if negative["no_overlap"]["overlap_blocked"] is not True:
        fail("no-overlap lock must block concurrent run")
    if plan["dry_cycle"]["checkpoint_resume_consistent"] is not True:  # type: ignore[index]
        fail("checkpoint resume must be deterministic")
    metrics = progress["metrics"]  # type: ignore[index]
    if metrics["duplicate_lock_prevented"] < 1:
        fail("duplicate lock prevention must be exercised")
    if progress["promotion_criteria_modified"] is not False:  # type: ignore[index]
        fail("promotion criteria must not be modified")
    if progress["gate"]["GATE_4_NATIONAL_1X2"] != "PROVISIONAL_FORWARD_HOLDOUT_PENDING":  # type: ignore[index]
        fail("Gate4 must remain pending")
    for token in [
        "STAGE_7D=COMPLETED",
        "FORWARD_HOLDOUT_AUTORUN=DISABLED_PENDING_APPROVAL",
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "STAGE_9=BLOCKED",
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "NETWORK_USED=false",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing status {token}")
    if "runtime/stage7d/" not in read(".gitignore"):
        fail("runtime/stage7d must be gitignored")
    print("W2 Stage7D check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
