#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/models/forward_autorun.py",
    "archive/scripts/enable_stage7e_autorun.py",
    "archive/scripts/run_stage7e_live_cycle.py",
    "scripts/check_w2_stage7e.py",
    "docs/adr/ADR-0012-live-forward-autorun.md",
    "docs/runbooks/STAGE7E_AUTORUN_OPERATIONS.md",
    "reports/W2_STAGE7E_ENABLEMENT.json",
    "reports/W2_STAGE7E_FIRST_LIVE_CYCLE.json",
    "reports/W2_STAGE7E_SCHEDULER_AUDIT.json",
    "reports/W2_STAGE7E_API_USAGE.json",
    "reports/W2_STAGE7E_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage7E check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> object:
    return json.loads(read(path))


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    combined = "\n".join(read(path) for path in REQUIRED if path.endswith((".py", ".md")))
    for token in [
        "ForwardAutorunSettings",
        "ForwardQuotaLedger",
        "ForwardRuntimeGuard",
        "ForwardSchedulerAudit",
        "daily_hard_budget",
        "minimum_reserve",
        "DeepSeek must remain disabled",
        "recommendation output must remain disabled",
    ]:
        if token not in combined:
            fail(f"missing Stage7E token {token}")
    enablement = load("reports/W2_STAGE7E_ENABLEMENT.json")
    first = load("reports/W2_STAGE7E_FIRST_LIVE_CYCLE.json")
    scheduler = load("reports/W2_STAGE7E_SCHEDULER_AUDIT.json")
    usage = load("reports/W2_STAGE7E_API_USAGE.json")
    result = read("reports/W2_STAGE7E_RESULT.md")
    if enablement["environment"] not in {"local", "staging"}:  # type: ignore[index]
        fail("environment must be local or staging")
    if enablement["hash_audit"]["blockers"]:  # type: ignore[index]
        fail("frozen hash blocker present")
    if enablement["production_config_modified"] is not False:  # type: ignore[index]
        fail("production config must not be modified")
    if enablement["api_key_status"] not in {"PRESENT", "ABSENT"}:  # type: ignore[index]
        fail("api key status must be redacted")
    if usage["daily_hard_budget"] != 6000:  # type: ignore[index]
        fail("daily hard budget must be 6000")
    if usage["minimum_reserve"] != 1500:  # type: ignore[index]
        fail("minimum reserve must be 1500")
    if usage["per_cycle_cap"] != 1000:  # type: ignore[index]
        fail("per-cycle cap must be 1000")
    if usage["total_requests"] > 1000:  # type: ignore[index]
        fail("single validation request usage is too high")
    if usage["remaining_quota"] is None or usage["remaining_quota"] <= 1500:  # type: ignore[index]
        fail("remaining quota must stay above reserve")
    if first["checkpoint"]["new_lock_count"] < 1:  # type: ignore[index]
        fail("first live cycle must lock at least one eligible phase")
    if first["lock_append_only"] is not True:  # type: ignore[index]
        fail("locks must be append-only")
    if first["market_snapshot_semantics"] != "CAPTURED_AT":  # type: ignore[index]
        fail("market snapshots must be captured-at")
    for key in [
        "training_performed",
        "deepseek_called",
        "candidate_output",
        "recommendation_output",
    ]:
        if first[key] is not False:  # type: ignore[index]
            fail(f"{key} must be false")
    if scheduler["exit_status"] != "COMPLETED":  # type: ignore[index]
        fail("scheduler cycle must complete")
    if scheduler["request_count"] < 1:  # type: ignore[index]
        fail("scheduler cycle must perform a controlled status request")
    if scheduler["no_overlap"] is not True:  # type: ignore[index]
        fail("scheduler no-overlap must be true")
    if not scheduler["scheduler_run_id"]:  # type: ignore[index]
        fail("scheduler run id required")
    if scheduler["cycle_checkpoint"]["new_lock_count"] != 0:  # type: ignore[index]
        fail("scheduler cycle must not duplicate already locked phases")
    if "authorization" in json.dumps([usage, first, scheduler]).lower():
        fail("authorization header leaked")
    for token in [
        "STAGE_7E=COMPLETED",
        "FORWARD_HOLDOUT_AUTORUN=ENABLED_LOCAL_OR_STAGING",
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "STAGE_9=BLOCKED",
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "PRODUCTION_ENABLED=false",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing status {token}")
    if "runtime/stage7e/" not in read(".gitignore"):
        fail("runtime/stage7e must be gitignored")
    print("W2 Stage7E check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
