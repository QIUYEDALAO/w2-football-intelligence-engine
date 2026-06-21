#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "scripts/run_stage7f_gate4_checkpoint.py",
    "scripts/check_w2_stage7f.py",
    "reports/W2_STAGE7F_API_USAGE.json",
    "reports/W2_STAGE7F_LOCK_AUDIT.json",
    "reports/W2_STAGE7F_SETTLEMENT.json",
    "reports/W2_STAGE7F_FORWARD_METRICS.json",
    "reports/W2_STAGE7F_GATE4_DECISION.json",
    "reports/W2_STAGE7F_RESULT.md",
]


def fail(message: str) -> None:
    print(f"W2 Stage7F check FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load(path: str) -> Any:
    return json.loads(read(path))


def assert_no_sensitive_text(payload: object) -> None:
    text = json.dumps(payload, sort_keys=True).lower()
    env_assignment = "w2_api" + "_football_api_key="
    for forbidden in ["authorization", "x-apisports-key", env_assignment]:
        if forbidden in text:
            fail(f"sensitive request material leaked: {forbidden}")


def main() -> int:
    for path in REQUIRED:
        if not (ROOT / path).is_file():
            fail(f"missing {path}")
    if "runtime/stage7f/" not in read(".gitignore"):
        fail("runtime/stage7f must be gitignored")
    usage = load("reports/W2_STAGE7F_API_USAGE.json")
    lock_audit = load("reports/W2_STAGE7F_LOCK_AUDIT.json")
    settlement = load("reports/W2_STAGE7F_SETTLEMENT.json")
    metrics = load("reports/W2_STAGE7F_FORWARD_METRICS.json")
    gate = load("reports/W2_STAGE7F_GATE4_DECISION.json")
    result = read("reports/W2_STAGE7F_RESULT.md")
    assert_no_sensitive_text([usage, lock_audit, settlement, metrics, gate])
    if usage["api_key_status"] not in {"PRESENT", "ABSENT"}:
        fail("API key status must be redacted")
    if usage["minimum_reserve"] != 1500:
        fail("minimum reserve must be 1500")
    if usage["requests_used"] > 500:
        fail("authorized request cap exceeded")
    if usage["requests_used"] > usage["request_budget"]:
        fail("request budget exceeded")
    if lock_audit["frozen_hashes"]["blockers"]:
        fail("frozen hash blocker present")
    if lock_audit["failed_count"]:
        fail("lock audit has failures")
    if lock_audit["watch_skip_only"] is not True:
        fail("locks must be WATCH/SKIP only")
    if lock_audit["duplicate_lock_prevented"] is not True:
        fail("duplicate fixture+phase lock detected")
    if settlement["append_only"] is not True or settlement["idempotent_replay"] is not True:
        fail("settlement must be append-only and idempotent")
    for key in ["model_feature_calibration_feedback", "training_performed", "calibration_updated"]:
        if settlement[key] is not False:
            fail(f"{key} must be false")
    if metrics["metrics_status"] not in {"INSUFFICIENT_SAMPLE", "READY"}:
        fail("metrics status invalid")
    if metrics["metrics_status"] == "INSUFFICIENT_SAMPLE":
        if metrics["ece"] is not None or metrics["bootstrap_ci"] is not None:
            fail("small sample must not force ECE or bootstrap conclusion")
    if gate["GATE_4_NATIONAL_1X2"] not in {
        "CLOSED",
        "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "PROVISIONAL_FAILED_TO_OUTPERFORM",
    }:
        fail("Gate 4 national status invalid")
    if gate["GATE_4_AH"] != "BLOCKED_FORWARD_ONLY":
        fail("AH Gate 4 must remain blocked")
    if gate["GATE_4_NATIONAL_1X2"] != "CLOSED" and gate["STAGE_9"] != "BLOCKED":
        fail("Stage 9 must remain blocked while Gate 4 is not closed")
    if gate["gate_rule_modified"] is not False:
        fail("promotion criteria must not be modified")
    for token in [
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "TRAINING_PERFORMED=false",
        "CALIBRATION_UPDATED=false",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing result token {token}")
    print("W2 Stage7F check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
