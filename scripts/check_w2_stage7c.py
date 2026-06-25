#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "src/w2/models/forward_ops.py",
    "src/w2/infrastructure/persistence/forward_ops_models.py",
    "migrations/versions/0009_create_stage7c_forward_ops.py",
    "archive/scripts/run_stage7c_forward_cycle.py",
    "scripts/check_w2_stage7c.py",
    "docs/adr/ADR-0010-forward-holdout-operations.md",
    "docs/runbooks/FORWARD_HOLDOUT_CYCLE.md",
    "reports/W2_STAGE7C_API_USAGE.json",
    "reports/W2_STAGE7C_LOCK_AUDIT.json",
    "reports/W2_STAGE7C_SETTLEMENT.json",
    "reports/W2_STAGE7C_FORWARD_METRICS.json",
    "reports/W2_STAGE7C_POWER_ANALYSIS.json",
    "archive/reports/W2_STAGE7C_GATE4_DECISION.json",
    "reports/W2_STAGE7C_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage7C check FAIL: {message}", file=sys.stderr)
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
        "ForwardResultEvent",
        "ForwardMarketSnapshot",
        "ForwardCycleLedger",
        "preregistered_evaluation_plan",
        "forward_result_event",
        "forward_market_snapshot",
        "forward_gate_audit",
        "forward_cycle_run",
    ]:
        if token not in combined:
            fail(f"missing Stage7C token {token}")
    usage = load("reports/W2_STAGE7C_API_USAGE.json")
    lock_audit = load("reports/W2_STAGE7C_LOCK_AUDIT.json")
    settlement = load("reports/W2_STAGE7C_SETTLEMENT.json")
    metrics = load("reports/W2_STAGE7C_FORWARD_METRICS.json")
    gate = load("archive/reports/W2_STAGE7C_GATE4_DECISION.json")
    result = read("reports/W2_STAGE7C_RESULT.md")
    if usage["requests_used"] > usage["request_budget"]:  # type: ignore[index]
        fail("request budget exceeded")
    if usage["requests_used"] > 500:  # type: ignore[index]
        fail("authorized 500 request cap exceeded")
    if lock_audit["frozen_manifest"]["blockers"]:  # type: ignore[index]
        fail("frozen manifest hash changed")
    if lock_audit["lock_count"] != 5:  # type: ignore[index]
        fail("existing five Stage7B locks must be audited")
    for finding in lock_audit["findings"]:  # type: ignore[index]
        if finding["status"] != "PASS":
            fail("existing lock audit failed")
    if settlement["append_only"] is not True or settlement["idempotent_replay"] is not True:  # type: ignore[index]
        fail("settlement must be append-only and idempotent")
    if settlement["model_feature_calibration_feedback"] is not False:  # type: ignore[index]
        fail("results must not feed back into model/features/calibration")
    if metrics["metrics"] not in {"INSUFFICIENT_SAMPLE", "READY"}:  # type: ignore[index]
        fail("forward metrics status invalid")
    if gate["GATE_4_NATIONAL_1X2"] not in {  # type: ignore[index]
        "CLOSED",
        "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "PROVISIONAL_FAILED_TO_OUTPERFORM",
    }:
        fail("Gate4 national status invalid")
    if gate["GATE_4_AH"] != "BLOCKED_FORWARD_ONLY":  # type: ignore[index]
        fail("AH must remain blocked")
    for token in [
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing status {token}")
    if "runtime/stage7c/" not in read(".gitignore"):
        fail("runtime/stage7c must be gitignored")
    print("W2 Stage7C check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
