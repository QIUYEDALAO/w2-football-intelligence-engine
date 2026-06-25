from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "archive/reports/W2_GATE3_MARKET_BASELINE_DECISION.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"
STATUS = ROOT / "reports/W2_ROADMAP_STATUS.json"


def load_decision() -> dict:
    return json.loads(DECISION.read_text(encoding="utf-8"))


def test_baselight_limited_walk_forward_reconciles_ah_blockers() -> None:
    payload = load_decision()
    baselight = payload["baselight"]
    ah = payload["asian_handicap"]

    assert ah["historical_ah_status"] == "BASELIGHT_LIMITED_WALK_FORWARD_PASS"
    assert ah["historical_build_status"] == "PASS_LIMITED_WALK_FORWARD"
    assert ah["closure_blocker"] is None
    assert baselight["ah_walk_forward_status"] == "PASS_LIMITED_WALK_FORWARD"
    assert baselight["limited_extract_fixture_count"] >= 500
    assert baselight["fold_count"] >= 5
    assert baselight["limited_extract_bookmaker_count"] >= 5
    assert baselight["limited_extract_line_bucket_count"] >= 8
    assert baselight["limited_extract_competition_count"] >= 5
    assert "HISTORICAL_AH_BASELINE_BACKTEST_MISSING" not in payload["blockers"]
    assert "AH_WALK_FORWARD_EVIDENCE_MISSING" not in payload["blockers"]
    assert "EXTERNAL_HISTORICAL_AH_SOURCE_DECISION_REQUIRED" not in payload["blockers"]


def test_retained_gate3_limitations_keep_gate3_partial() -> None:
    payload = load_decision()
    status = json.loads(STATUS.read_text(encoding="utf-8"))

    assert payload["status"] == "PARTIAL"
    assert status["gates"]["3"]["status"] == "PARTIAL"
    for blocker in {
        "CAPTURED_AT_PHASE_BACKTEST_RESULTS_MISSING",
        "CLOSING_ONLY_HISTORICAL_OU_BACKTEST_LIMITATION",
        "BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE",
        "PRECISE_PHASE_COVERAGE_UNAVAILABLE",
        "EXPORT_AND_RETENTION_POLICY_UNVERIFIED",
        "CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS",
        "UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS",
    }:
        assert blocker in payload["blockers"]


def test_gate3_checker_audit_passes_closure_fails() -> None:
    audit = subprocess.run(
        [sys.executable, "archive/scripts/check_w2_gate3_market_baseline.py", "--mode", "audit"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    closure = subprocess.run(
        [sys.executable, "archive/scripts/check_w2_gate3_market_baseline.py", "--mode", "closure"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert audit.returncode == 0, audit.stderr
    assert closure.returncode != 0
    assert "closure mode requires Gate3 status CLOSED" in closure.stderr


def test_handoff_v34_and_no_recommendation_flags() -> None:
    payload = load_decision()
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert "handoff_version: 41" in handoff
    assert "gate3_ah_historical_status: BASELIGHT_LIMITED_WALK_FORWARD_PASS" in handoff
    assert "gate3_closure_audit_checker: PASS" in handoff
    assert "gate3_closure_checker: EXPECTED_FAIL_REMAINING_LIMITATIONS" in handoff
    assert "stage7i_status: BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP" in handoff
    assert "gate5: OPEN" in handoff
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert "candidate: false" in handoff
    assert "formal_recommendation: false" in handoff
