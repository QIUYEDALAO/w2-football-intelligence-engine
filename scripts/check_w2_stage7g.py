#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "scripts/run_stage7g_continuity_audit.py",
    "scripts/check_w2_stage7g.py",
    "docs/runbooks/FORWARD_HOLDOUT_HOST_REQUIREMENTS.md",
    "reports/W2_STAGE7G_SCHEDULER_CONTINUITY.json",
    "reports/W2_STAGE7G_ZERO_SAMPLE_DIAGNOSIS.json",
    "reports/W2_STAGE7G_ELIGIBILITY_CALENDAR.json",
    "reports/W2_STAGE7G_API_USAGE.json",
    "reports/W2_STAGE7G_RESULT.md",
]
REASON_CODES = {
    "OUTSIDE_T24_WINDOW",
    "OUTSIDE_T1_WINDOW",
    "ALREADY_LOCKED",
    "KICKOFF_PASSED",
    "RESULT_NOT_FINAL",
    "COMPETITION_NOT_ELIGIBLE",
    "FIXTURE_MAPPING_MISSING",
    "MODEL_INPUT_MISSING",
    "MARKET_UNAVAILABLE",
    "DATA_BLOCKED",
    "DISCOVERY_MISSED",
}


def fail(message: str) -> None:
    print(f"W2 Stage7G check FAIL: {message}", file=sys.stderr)
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
    if "runtime/stage7g/" not in read(".gitignore"):
        fail("runtime/stage7g must be gitignored")
    scheduler = load("reports/W2_STAGE7G_SCHEDULER_CONTINUITY.json")
    diagnosis = load("reports/W2_STAGE7G_ZERO_SAMPLE_DIAGNOSIS.json")
    calendar = load("reports/W2_STAGE7G_ELIGIBILITY_CALENDAR.json")
    usage = load("reports/W2_STAGE7G_API_USAGE.json")
    result = read("reports/W2_STAGE7G_RESULT.md")
    assert_no_sensitive_text([scheduler, diagnosis, calendar, usage])
    if scheduler["status"] not in {"RUNNING", "PERSISTENT_SCHEDULER_HOST_REQUIRED"}:
        fail("scheduler continuity status invalid")
    if scheduler["system_daemon_started"] is not False:
        fail("Stage7G must not start system daemon")
    if scheduler["frozen_hashes"]["blockers"]:
        fail("frozen hash blocker present")
    if usage["api_key_status"] not in {"PRESENT", "ABSENT"}:
        fail("API key status must be redacted")
    if usage["minimum_reserve"] != 1500:
        fail("minimum reserve must be 1500")
    if usage["requests_used"] > 100:
        fail("Stage7G request cap exceeded")
    if usage["requests_used"] > usage["request_budget"]:
        fail("request budget exceeded")
    if calendar["window_days"] != 60:
        fail("eligibility calendar must cover 60 days")
    for row in calendar["fixtures"]:
        for key in [
            "fixture_id",
            "competition",
            "kickoff_utc",
            "t24_eligibility_time",
            "t1_eligibility_time",
            "settlement_check_time",
            "model_eligibility",
            "expected_market_availability",
            "current_state",
        ]:
            if key not in row:
                fail(f"calendar row missing {key}")
        unknown = set(row.get("zero_sample_reasons", [])) - REASON_CODES
        if unknown:
            fail(f"unknown zero-sample reason {sorted(unknown)}")
    if not diagnosis["reason_counts"]:
        fail("zero-sample diagnosis must include reason counts")
    if diagnosis["stage7f_settled_fixture_n"] != 0:
        fail("Stage7F zero-sample diagnosis drifted")
    for token in [
        "PERSISTENT_SCHEDULER_HOST_REQUIRED",
        "GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "CANDIDATE_OUTPUT=false",
        "RECOMMENDATION_OUTPUT=false",
        "TRAINING_PERFORMED=false",
        "PUSH_BLOCKED_NO_ORIGIN",
    ]:
        if token not in result:
            fail(f"missing result token {token}")
    print("W2 Stage7G check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
